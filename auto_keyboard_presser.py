"""
Auto Presser — híbrido teclado + mouse.
Gravação/reprodução de teclas, auto-click e ambos juntos.
Threaded, delays precisos, panic stop e UX moderna.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk
from pynput import keyboard, mouse

# ── theme ───────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C = {
    "bg": "#0c0e14",
    "panel": "#141820",
    "card": "#1a2030",
    "card2": "#222a3a",
    "border": "#2c3548",
    "text": "#eef2fa",
    "muted": "#8b95a8",
    "accent": "#4c8dff",
    "accent_h": "#6ba1ff",
    "ok": "#3dd68c",
    "danger": "#f07178",
    "warn": "#e6b450",
    "idle": "#8b95a8",
    "rec": "#f07178",
    "play": "#3dd68c",
}

APP_DIR = Path(__file__).resolve().parent
PROFILES_DIR = APP_DIR / "profiles"
SETTINGS_FILE = APP_DIR / "settings.json"

MODIFIERS = {
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "shift", "shift_l", "shift_r",
    "cmd", "cmd_l", "cmd_r",
}

MIN_INTERVAL_MS = 10
MAX_INTERVAL_MS = 3_600_000
DEFAULT_PANIC = "f8"


# ── helpers ─────────────────────────────────────────────────────────────────

@dataclass
class KeyAction:
    key: str
    delay_ms: int = 0


def key_to_str(key: keyboard.Key | keyboard.KeyCode) -> str:
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return key.char.lower() if key.char.isalpha() else key.char
        if key.vk is not None:
            return f"vk_{key.vk}"
        return "unknown"
    return str(key).replace("Key.", "")


def str_to_key(name: str):
    name = name.strip()
    if name.startswith("vk_"):
        try:
            return keyboard.KeyCode.from_vk(int(name[3:]))
        except ValueError:
            return None
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    try:
        return getattr(keyboard.Key, name)
    except AttributeError:
        return None


def clamp_int(raw: str, lo: int, hi: int, fallback: int) -> int:
    try:
        return max(lo, min(hi, int(float(raw))))
    except (TypeError, ValueError):
        return fallback


def hotkey_spec(name: str) -> str:
    name = name.strip().lower()
    return name if len(name) == 1 else f"<{name}>"


class PreciseSleeper:
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event

    def sleep(self, ms: float) -> bool:
        if ms <= 0:
            return not self.stop_event.is_set()
        end = time.perf_counter() + ms / 1000.0
        while True:
            if self.stop_event.is_set():
                return False
            rem = end - time.perf_counter()
            if rem <= 0:
                return True
            if rem > 0.002:
                if self.stop_event.wait(rem - 0.001):
                    return False
            else:
                while time.perf_counter() < end:
                    if self.stop_event.is_set():
                        return False
                return True


# ── engine ──────────────────────────────────────────────────────────────────

class Engine:
    """Keyboard sequence + mouse auto-click, independently or together."""

    def __init__(self, on_ui: Callable[[Callable[[], None]], None]):
        self.on_ui = on_ui
        self.lock = threading.RLock()

        self.state = "idle"  # idle | recording | running
        self.stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        # modules
        self.kb_enabled = True
        self.mouse_enabled = False

        # keyboard
        self.actions: list[KeyAction] = []
        self.kb_delay_ms = 300
        self.kb_hold_ms = 30
        self.record_hotkey = "f6"

        # mouse
        self.click_button = "left"  # left | right | middle
        self.click_interval_ms = 100
        self.click_count_per_tick = 1
        self.click_pos_mode = "current"  # current | fixed
        self.click_x = 0
        self.click_y = 0

        # shared repeat
        self.repeat_mode = "continuous"  # times | continuous
        self.repeat_count = 1

        # hotkeys
        self.run_hotkey = "f7"
        self.panic_hotkey = DEFAULT_PANIC

        self._kb = keyboard.Controller()
        self._ms = mouse.Controller()
        self._listener: Optional[keyboard.Listener] = None
        self._hotkeys: Optional[keyboard.GlobalHotKeys] = None
        self._ignore_until = 0.0
        self._pressed: set[str] = set()

        self.on_state: Optional[Callable[[str], None]] = None
        self.on_actions: Optional[Callable[[], None]] = None
        self.on_before_run: Optional[Callable[[], None]] = None

        # Debounce UI refresh durante gravação rápida
        self._actions_dirty = False
        self._last_emit = 0.0

    # ── settings I/O ────────────────────────────────────────────────────────
    def load_settings(self) -> None:
        if not SETTINGS_FILE.exists():
            return
        try:
            d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        try:
            self.record_hotkey = str(d.get("record_hotkey", self.record_hotkey)).lower()
            self.run_hotkey = str(d.get("run_hotkey", self.run_hotkey)).lower()
            self.panic_hotkey = str(d.get("panic_hotkey", self.panic_hotkey)).lower()
            self.kb_enabled = bool(d.get("kb_enabled", self.kb_enabled))
            self.mouse_enabled = bool(d.get("mouse_enabled", self.mouse_enabled))
            self.kb_delay_ms = clamp_int(str(d.get("kb_delay_ms", self.kb_delay_ms)), MIN_INTERVAL_MS, MAX_INTERVAL_MS, self.kb_delay_ms)
            self.kb_hold_ms = clamp_int(str(d.get("kb_hold_ms", self.kb_hold_ms)), 1, 500, self.kb_hold_ms)
            btn = str(d.get("click_button", self.click_button)).lower()
            self.click_button = btn if btn in ("left", "right", "middle") else "left"
            self.click_interval_ms = clamp_int(str(d.get("click_interval_ms", self.click_interval_ms)), MIN_INTERVAL_MS, MAX_INTERVAL_MS, self.click_interval_ms)
            self.click_count_per_tick = clamp_int(str(d.get("click_count_per_tick", self.click_count_per_tick)), 1, 100, self.click_count_per_tick)
            pos = str(d.get("click_pos_mode", self.click_pos_mode)).lower()
            self.click_pos_mode = pos if pos in ("current", "fixed") else "current"
            self.click_x = clamp_int(str(d.get("click_x", self.click_x)), 0, 100_000, self.click_x)
            self.click_y = clamp_int(str(d.get("click_y", self.click_y)), 0, 100_000, self.click_y)
            mode = str(d.get("repeat_mode", self.repeat_mode)).lower()
            self.repeat_mode = mode if mode in ("times", "continuous") else "continuous"
            self.repeat_count = clamp_int(str(d.get("repeat_count", self.repeat_count)), 1, 1_000_000, self.repeat_count)
            # Evita atalhos duplicados após settings corrompidos
            used = {self.record_hotkey, self.run_hotkey}
            if self.panic_hotkey in used:
                self.panic_hotkey = DEFAULT_PANIC
                if self.panic_hotkey in used:
                    self.panic_hotkey = "f9"
        except (TypeError, ValueError, AttributeError):
            pass

    def save_settings(self) -> None:
        data = {
            "record_hotkey": self.record_hotkey,
            "run_hotkey": self.run_hotkey,
            "panic_hotkey": self.panic_hotkey,
            "kb_enabled": self.kb_enabled,
            "mouse_enabled": self.mouse_enabled,
            "kb_delay_ms": self.kb_delay_ms,
            "kb_hold_ms": self.kb_hold_ms,
            "click_button": self.click_button,
            "click_interval_ms": self.click_interval_ms,
            "click_count_per_tick": self.click_count_per_tick,
            "click_pos_mode": self.click_pos_mode,
            "click_x": self.click_x,
            "click_y": self.click_y,
            "repeat_mode": self.repeat_mode,
            "repeat_count": self.repeat_count,
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def save_profile(self, path: Path) -> None:
        data = {
            "actions": [asdict(a) for a in self.actions],
            **{
                k: getattr(self, k)
                for k in (
                    "kb_enabled", "mouse_enabled",
                    "kb_delay_ms", "kb_hold_ms",
                    "click_button", "click_interval_ms", "click_count_per_tick",
                    "click_pos_mode", "click_x", "click_y",
                    "repeat_mode", "repeat_count",
                )
            },
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_profile(self, path: Path) -> None:
        d = json.loads(path.read_text(encoding="utf-8"))
        with self.lock:
            self.actions = [KeyAction(**a) for a in d.get("actions", [])]
            for k in (
                "kb_enabled", "mouse_enabled",
                "kb_delay_ms", "kb_hold_ms",
                "click_button", "click_interval_ms", "click_count_per_tick",
                "click_pos_mode", "click_x", "click_y",
                "repeat_mode", "repeat_count",
            ):
                if k in d:
                    setattr(self, k, d[k])
        self._emit_actions()

    # ── state ───────────────────────────────────────────────────────────────
    def _set_state(self, state: str) -> None:
        self.state = state
        if self.on_state:
            self.on_ui(lambda s=state: self.on_state(s))

    def _emit_actions(self, force: bool = False) -> None:
        """Atualiza a lista na UI. Em gravação, faz throttle (~15 fps)."""
        if not self.on_actions:
            return
        now = time.perf_counter()
        if not force and self.state == "recording" and (now - self._last_emit) < 0.066:
            self._actions_dirty = True
            return
        self._actions_dirty = False
        self._last_emit = now
        self.on_ui(self.on_actions)

    def flush_actions_ui(self) -> None:
        if self._actions_dirty:
            self._emit_actions(force=True)

    def can_run(self) -> tuple[bool, str]:
        if not self.kb_enabled and not self.mouse_enabled:
            return False, "Ative Teclado e/ou Mouse."
        if self.kb_enabled and not self.actions:
            return False, "Grave ao menos uma tecla, ou desative Teclado."
        if self.kb_enabled and self.kb_delay_ms < MIN_INTERVAL_MS:
            return False, f"Delay do teclado mínimo: {MIN_INTERVAL_MS} ms."
        if self.mouse_enabled and self.click_interval_ms < MIN_INTERVAL_MS:
            return False, f"Intervalo do mouse mínimo: {MIN_INTERVAL_MS} ms."
        return True, ""

    # ── recording ───────────────────────────────────────────────────────────
    def toggle_record(self) -> None:
        if self.state == "running":
            return
        if self.state == "recording":
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        with self.lock:
            if self.state != "idle":
                return
            self.state = "recording"
            self._pressed.clear()
            self._ignore_until = time.perf_counter() + 0.25
        self._set_state("recording")

    def stop_recording(self) -> None:
        with self.lock:
            if self.state != "recording":
                return
            self.state = "idle"
            self._pressed.clear()
        self._emit_actions(force=True)
        self._set_state("idle")

    def _on_press(self, key) -> None:
        name = key_to_str(key)
        if name in MODIFIERS:
            return

        # Fallback hotkeys if GlobalHotKeys failed
        if self._hotkeys is None and name not in self._pressed:
            if name == self.record_hotkey:
                self._pressed.add(name)
                self._ignore_until = time.perf_counter() + 0.3
                self.on_ui(self.toggle_record)
                return
            if name == self.run_hotkey:
                self._pressed.add(name)
                self._ignore_until = time.perf_counter() + 0.3
                self.on_ui(self.toggle_run)
                return
            if name == self.panic_hotkey:
                self._pressed.add(name)
                self.on_ui(self.panic)
                return

        if time.perf_counter() < self._ignore_until:
            return
        if name in (self.record_hotkey, self.run_hotkey, self.panic_hotkey):
            return

        with self.lock:
            if self.state != "recording":
                return
            if name in self._pressed:
                return
            self._pressed.add(name)
            self.actions.append(KeyAction(key=name))
        self._emit_actions()

    def _on_release(self, key) -> None:
        self._pressed.discard(key_to_str(key))

    # ── run / stop ──────────────────────────────────────────────────────────
    def toggle_run(self) -> None:
        if self.state == "recording":
            return
        if self.state == "running":
            self.stop_run()
        else:
            if self.on_before_run:
                try:
                    self.on_before_run()
                except Exception:
                    pass
            self.start_run()

    def start_run(self) -> None:
        ok, reason = self.can_run()
        if not ok:
            self.on_ui(lambda: messagebox.showinfo("Não é possível iniciar", reason))
            return
        with self.lock:
            if self.state != "idle":
                return
            self.stop_event.clear()
            self.state = "running"
            snapshot = self._snapshot()
        self._set_state("running")
        self._worker = threading.Thread(
            target=self._run_loop, args=(snapshot,), daemon=True, name="autopresser"
        )
        self._worker.start()

    def stop_run(self) -> None:
        self.stop_event.set()

    def panic(self) -> None:
        """Emergency stop — always safe to call."""
        self.stop_event.set()
        with self.lock:
            if self.state == "recording":
                self.state = "idle"
                self._pressed.clear()
                self._emit_actions(force=True)
                self._set_state("idle")
            elif self.state == "running":
                # Estado idle confirmado no finally do worker; feedback imediato
                pass

    def shutdown(self) -> None:
        self.stop_event.set()
        worker = self._worker
        with self.lock:
            self.state = "idle"
        self.save_settings()
        for lst in (self._hotkeys, self._listener):
            if lst is not None:
                try:
                    lst.stop()
                except Exception:
                    pass
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.5)

    def _snapshot(self) -> dict:
        return {
            "kb": self.kb_enabled,
            "mouse": self.mouse_enabled,
            "actions": list(self.actions),
            "kb_delay": self.kb_delay_ms,
            "kb_hold": self.kb_hold_ms,
            "btn": self.click_button,
            "click_iv": self.click_interval_ms,
            "click_n": max(1, self.click_count_per_tick),
            "pos_mode": self.click_pos_mode,
            "x": self.click_x,
            "y": self.click_y,
            "mode": self.repeat_mode,
            "count": max(1, self.repeat_count),
        }

    def _run_loop(self, cfg: dict) -> None:
        sleeper = PreciseSleeper(self.stop_event)
        loops = 10**9 if cfg["mode"] == "continuous" else cfg["count"]
        btn_map = {
            "left": mouse.Button.left,
            "right": mouse.Button.right,
            "middle": mouse.Button.middle,
        }
        button = btn_map.get(cfg["btn"], mouse.Button.left)

        try:
            for _ in range(loops):
                if self.stop_event.is_set():
                    break

                # 1) Sequência de teclado
                if cfg["kb"] and cfg["actions"]:
                    for action in cfg["actions"]:
                        if self.stop_event.is_set():
                            break
                        wait = cfg["kb_delay"] + max(0, action.delay_ms)
                        if not sleeper.sleep(wait):
                            break
                        self._tap_key(action.key, cfg["kb_hold"], sleeper)

                # 2) Auto-click (N cliques por ciclo)
                if cfg["mouse"] and not self.stop_event.is_set():
                    for _ in range(cfg["click_n"]):
                        if self.stop_event.is_set():
                            break
                        if not sleeper.sleep(cfg["click_iv"]):
                            break
                        self._do_click(button, cfg)

        finally:
            with self.lock:
                self.state = "idle"
            self._set_state("idle")

    def _tap_key(self, name: str, hold_ms: int, sleeper: PreciseSleeper) -> None:
        key = str_to_key(name)
        if key is None:
            return
        try:
            self._kb.press(key)
            sleeper.sleep(hold_ms)
            self._kb.release(key)
        except Exception:
            try:
                self._kb.release(key)
            except Exception:
                pass

    def _do_click(self, button, cfg: dict) -> None:
        try:
            if cfg["pos_mode"] == "fixed":
                self._ms.position = (cfg["x"], cfg["y"])
            self._ms.click(button, 1)
        except Exception:
            pass

    # ── list edits ──────────────────────────────────────────────────────────
    def clear_actions(self) -> None:
        with self.lock:
            if self.state != "idle":
                return
            self.actions.clear()
        self._emit_actions()

    def remove_indices(self, indices: list[int]) -> None:
        with self.lock:
            if self.state != "idle":
                return
            for i in sorted(indices, reverse=True):
                if 0 <= i < len(self.actions):
                    self.actions.pop(i)
        self._emit_actions()

    def move_action(self, index: int, direction: int) -> None:
        with self.lock:
            if self.state != "idle":
                return
            j = index + direction
            if 0 <= index < len(self.actions) and 0 <= j < len(self.actions):
                self.actions[index], self.actions[j] = self.actions[j], self.actions[index]
        self._emit_actions()

    # ── listeners ───────────────────────────────────────────────────────────
    def start_listeners(self) -> None:
        self._restart_hotkeys()
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def _restart_hotkeys(self) -> None:
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
            self._hotkeys = None

        keys = {
            self.record_hotkey: self._hk_record,
            self.run_hotkey: self._hk_run,
            self.panic_hotkey: self._hk_panic,
        }
        # Deduplicate if user set same key twice
        mapping = {}
        for name, cb in keys.items():
            mapping[hotkey_spec(name)] = cb

        try:
            self._hotkeys = keyboard.GlobalHotKeys(mapping)
            self._hotkeys.daemon = True
            self._hotkeys.start()
        except Exception:
            self._hotkeys = None

    def _hk_record(self) -> None:
        self._ignore_until = time.perf_counter() + 0.3
        self.on_ui(self.toggle_record)

    def _hk_run(self) -> None:
        self._ignore_until = time.perf_counter() + 0.3
        self.on_ui(self.toggle_run)

    def _hk_panic(self) -> None:
        self.on_ui(self.panic)

    def set_hotkey(self, which: str, name: str) -> bool:
        name = name.strip().lower()
        if not name:
            return False
        others = {
            "record": self.record_hotkey,
            "run": self.run_hotkey,
            "panic": self.panic_hotkey,
        }
        others.pop(which, None)
        if name in others.values():
            return False
        if which == "record":
            self.record_hotkey = name
        elif which == "run":
            self.run_hotkey = name
        elif which == "panic":
            self.panic_hotkey = name
        else:
            return False
        self.save_settings()
        self._restart_hotkeys()
        return True


# ── UI helpers ──────────────────────────────────────────────────────────────

def card(parent, title: str | None = None) -> ctk.CTkFrame:
    box = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
    if title:
        ctk.CTkLabel(
            box, text=title,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=11),
            text_color=C["muted"],
        ).pack(anchor="w", padx=14, pady=(12, 2))
    return box


def soft_btn(parent, text, command, **kw):
    defaults = dict(
        height=32, corner_radius=8,
        fg_color=C["card2"], hover_color=C["border"],
        text_color=C["text"],
        font=ctk.CTkFont(family="Segoe UI", size=12),
    )
    defaults.update(kw)
    return ctk.CTkButton(parent, text=text, command=command, **defaults)


# ── App ─────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Auto Presser")
        self.geometry("920x640")
        self.minsize(860, 580)
        self.configure(fg_color=C["bg"])

        self._q: queue.Queue = queue.Queue()
        self.engine = Engine(on_ui=self._marshal)
        self.engine.on_state = self._on_state
        self.engine.on_actions = self._refresh_list
        self.engine.on_before_run = self._flush_settings
        self.engine.load_settings()

        self._capturing: Optional[str] = None
        PROFILES_DIR.mkdir(exist_ok=True)

        self._build()
        self._sync_from_engine()
        self.engine.start_listeners()
        self.after(40, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _marshal(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    def _drain(self) -> None:
        try:
            while True:
                fn = self._q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.after(40, self._drain)

    # ── build ───────────────────────────────────────────────────────────────
    def _build(self) -> None:
        # Header
        hdr = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=0, height=68)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        left_h = ctk.CTkFrame(hdr, fg_color="transparent")
        left_h.pack(side="left", padx=20, pady=14)
        ctk.CTkLabel(
            left_h, text="Auto Presser",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            left_h, text="Teclado · Mouse · Híbrido",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=C["muted"],
        ).pack(anchor="w")

        right_h = ctk.CTkFrame(hdr, fg_color="transparent")
        right_h.pack(side="right", padx=20)
        self.status = ctk.CTkLabel(
            right_h, text="●  IDLE",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=C["idle"],
        )
        self.status.pack(side="left", padx=(0, 12))
        self.panic_btn = soft_btn(
            right_h, f"Panic  {self.engine.panic_hotkey.upper()}",
            self.engine.panic,
            width=110, height=34,
            fg_color="#3a1f24", hover_color="#5a2a32",
            text_color=C["danger"],
        )
        self.panic_btn.pack(side="left")

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=16)

        # Mode switches row
        modes = ctk.CTkFrame(body, fg_color=C["panel"], corner_radius=12)
        modes.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            modes, text="Módulos ativos",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=C["text"],
        ).pack(side="left", padx=16, pady=14)

        self.kb_sw = ctk.CTkSwitch(
            modes, text="Teclado",
            command=self._on_modules,
            font=ctk.CTkFont(size=13),
            text_color=C["text"],
            progress_color=C["accent"],
        )
        self.kb_sw.pack(side="left", padx=12)

        self.ms_sw = ctk.CTkSwitch(
            modes, text="Mouse (auto-click)",
            command=self._on_modules,
            font=ctk.CTkFont(size=13),
            text_color=C["text"],
            progress_color=C["accent"],
        )
        self.ms_sw.pack(side="left", padx=12)

        self.mode_hint = ctk.CTkLabel(
            modes, text="",
            font=ctk.CTkFont(size=12), text_color=C["muted"],
        )
        self.mode_hint.pack(side="right", padx=16)

        # Columns
        cols = ctk.CTkFrame(body, fg_color="transparent")
        cols.pack(fill="both", expand=True)

        self.left = ctk.CTkFrame(cols, fg_color=C["panel"], corner_radius=12)
        self.left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.right = ctk.CTkFrame(cols, fg_color=C["panel"], corner_radius=12, width=320)
        self.right.pack(side="right", fill="y")
        self.right.pack_propagate(False)

        self._build_keyboard_panel(self.left)
        self._build_side_panel(self.right)

        # Footer
        self.tip = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=C["muted"],
        )
        self.tip.pack(fill="x", padx=20, pady=(0, 12))
        self._update_tip()

    def _build_keyboard_panel(self, parent) -> None:
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(14, 6))
        ctk.CTkLabel(
            head, text="Sequência de teclado",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=15),
            text_color=C["text"],
        ).pack(side="left")
        self.count_lbl = ctk.CTkLabel(
            head, text="0 teclas",
            font=ctk.CTkFont(size=12), text_color=C["muted"],
        )
        self.count_lbl.pack(side="right")

        wrap = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=10)
        wrap.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        cols = ctk.CTkFrame(wrap, fg_color="transparent")
        cols.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(cols, text="#", width=36, anchor="w",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left")
        ctk.CTkLabel(cols, text="TECLA", anchor="w",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left", padx=8)

        self.listbox = tk.Listbox(
            wrap,
            bg=C["card"], fg=C["text"],
            selectbackground=C["accent"], selectforeground="#fff",
            activestyle="none", highlightthickness=0, borderwidth=0,
            font=("Consolas", 12), exportselection=False,
        )
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=(0, 8))
        soft_btn(btns, "▲", lambda: self._move(-1), width=44).pack(side="left", padx=(0, 4))
        soft_btn(btns, "▼", lambda: self._move(1), width=44).pack(side="left", padx=(0, 4))
        soft_btn(btns, "Remover", self._remove, width=90).pack(side="left", padx=(0, 4))
        soft_btn(
            btns, "Limpar", self._clear, width=80,
            fg_color="#3a1f24", hover_color="#5a2a32", text_color=C["danger"],
        ).pack(side="left")
        soft_btn(btns, "Salvar", self._save_profile, width=80).pack(side="right", padx=(4, 0))
        soft_btn(btns, "Abrir", self._load_profile, width=80).pack(side="right")

        # Keyboard timing
        self.kb_card = card(parent, "TEMPO ENTRE TECLAS")
        self.kb_card.pack(fill="x", padx=14, pady=(0, 14))
        row = ctk.CTkFrame(self.kb_card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(4, 12))

        self.kb_delay = ctk.StringVar()
        e = ctk.CTkEntry(row, textvariable=self.kb_delay, width=90, height=34,
                         font=ctk.CTkFont(family="Consolas", size=14), justify="center")
        e.pack(side="left")
        e.bind("<FocusOut>", lambda _e: self._apply_kb_timing())
        e.bind("<Return>", lambda _e: self._apply_kb_timing())
        ctk.CTkLabel(row, text="ms", text_color=C["muted"]).pack(side="left", padx=8)

        ctk.CTkLabel(row, text="Hold", text_color=C["muted"]).pack(side="left", padx=(16, 4))
        self.kb_hold = ctk.StringVar()
        he = ctk.CTkEntry(row, textvariable=self.kb_hold, width=60, height=30,
                          font=ctk.CTkFont(family="Consolas", size=12), justify="center")
        he.pack(side="left")
        he.bind("<FocusOut>", lambda _e: self._apply_kb_timing())
        he.bind("<Return>", lambda _e: self._apply_kb_timing())
        ctk.CTkLabel(row, text="ms", text_color=C["muted"]).pack(side="left", padx=4)

    def _build_side_panel(self, parent) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        ctk.CTkLabel(
            scroll, text="Controles",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=15),
            text_color=C["text"],
        ).pack(anchor="w", padx=10, pady=(10, 8))

        # Mouse card
        self.ms_card = card(scroll, "AUTO-CLICK (MOUSE)")
        self.ms_card.pack(fill="x", padx=10, pady=(0, 10))

        # Button select — segmented (reliable, not radio)
        ctk.CTkLabel(
            self.ms_card, text="Botão",
            font=ctk.CTkFont(size=12), text_color=C["text"],
        ).pack(anchor="w", padx=14, pady=(4, 2))
        self.click_btn_seg = ctk.CTkSegmentedButton(
            self.ms_card,
            values=["Esquerdo", "Direito", "Meio"],
            command=self._on_click_btn,
            font=ctk.CTkFont(size=12),
            height=32,
            selected_color=C["accent"],
            selected_hover_color=C["accent_h"],
            unselected_color=C["card2"],
            unselected_hover_color=C["border"],
        )
        self.click_btn_seg.pack(fill="x", padx=14, pady=(0, 8))
        self.click_btn_seg.set("Esquerdo")

        # Interval
        ir = ctk.CTkFrame(self.ms_card, fg_color="transparent")
        ir.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(ir, text="Intervalo", text_color=C["muted"],
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self.click_iv = ctk.StringVar()
        ie = ctk.CTkEntry(ir, textvariable=self.click_iv, width=80, height=30,
                          font=ctk.CTkFont(family="Consolas", size=13), justify="center")
        ie.pack(side="right")
        ie.bind("<FocusOut>", lambda _e: self._apply_mouse())
        ie.bind("<Return>", lambda _e: self._apply_mouse())
        ctk.CTkLabel(ir, text="ms", text_color=C["muted"]).pack(side="right", padx=6)

        # Clicks per tick
        nr = ctk.CTkFrame(self.ms_card, fg_color="transparent")
        nr.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(nr, text="Cliques por ciclo", text_color=C["muted"],
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self.click_n = ctk.StringVar()
        ne = ctk.CTkEntry(nr, textvariable=self.click_n, width=60, height=30,
                          font=ctk.CTkFont(family="Consolas", size=13), justify="center")
        ne.pack(side="right")
        ne.bind("<FocusOut>", lambda _e: self._apply_mouse())
        ne.bind("<Return>", lambda _e: self._apply_mouse())

        # Position
        ctk.CTkLabel(
            self.ms_card, text="Posição",
            font=ctk.CTkFont(size=12), text_color=C["text"],
        ).pack(anchor="w", padx=14, pady=(4, 2))
        self.pos_seg = ctk.CTkSegmentedButton(
            self.ms_card,
            values=["Cursor atual", "Fixo (X,Y)"],
            command=self._on_pos_mode,
            font=ctk.CTkFont(size=12),
            height=32,
            selected_color=C["accent"],
            selected_hover_color=C["accent_h"],
            unselected_color=C["card2"],
            unselected_hover_color=C["border"],
        )
        self.pos_seg.pack(fill="x", padx=14, pady=(0, 8))
        self.pos_seg.set("Cursor atual")

        self.pos_row = ctk.CTkFrame(self.ms_card, fg_color="transparent")
        self.pos_row.pack(fill="x", padx=14, pady=(0, 8))
        self.click_x = ctk.StringVar(value="0")
        self.click_y = ctk.StringVar(value="0")
        ctk.CTkLabel(self.pos_row, text="X", text_color=C["muted"]).pack(side="left")
        xe = ctk.CTkEntry(self.pos_row, textvariable=self.click_x, width=70, height=28,
                          font=ctk.CTkFont(family="Consolas", size=12), justify="center")
        xe.pack(side="left", padx=4)
        ctk.CTkLabel(self.pos_row, text="Y", text_color=C["muted"]).pack(side="left", padx=(8, 0))
        ye = ctk.CTkEntry(self.pos_row, textvariable=self.click_y, width=70, height=28,
                          font=ctk.CTkFont(family="Consolas", size=12), justify="center")
        ye.pack(side="left", padx=4)
        soft_btn(self.pos_row, "Pegar", self._grab_pos, width=64, height=28).pack(side="left", padx=6)
        for w in (xe, ye):
            w.bind("<FocusOut>", lambda _e: self._apply_mouse())
            w.bind("<Return>", lambda _e: self._apply_mouse())

        soft_btn(
            self.ms_card, "Testar 1 clique", self._test_click,
            height=30, fg_color=C["card2"],
        ).pack(fill="x", padx=14, pady=(0, 12))

        # Repetition — segmented, NOT radio (fixes "travado")
        rep = card(scroll, "REPETIÇÃO")
        rep.pack(fill="x", padx=10, pady=(0, 10))

        self.rep_seg = ctk.CTkSegmentedButton(
            rep,
            values=["N vezes", "Contínuo"],
            command=self._on_rep_mode,
            font=ctk.CTkFont(size=13),
            height=34,
            selected_color=C["accent"],
            selected_hover_color=C["accent_h"],
            unselected_color=C["card2"],
            unselected_hover_color=C["border"],
        )
        self.rep_seg.pack(fill="x", padx=14, pady=(6, 8))

        self.times_row = ctk.CTkFrame(rep, fg_color="transparent")
        self.times_row.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(
            self.times_row, text="Quantidade",
            font=ctk.CTkFont(size=12), text_color=C["muted"],
        ).pack(side="left")
        self.rep_times = ctk.StringVar()
        te = ctk.CTkEntry(
            self.times_row, textvariable=self.rep_times, width=70, height=30,
            font=ctk.CTkFont(family="Consolas", size=13), justify="center",
        )
        te.pack(side="right")
        te.bind("<FocusOut>", lambda _e: self._apply_repeat())
        te.bind("<Return>", lambda _e: self._apply_repeat())

        # Hotkeys
        hk = card(scroll, "ATALHOS GLOBAIS")
        hk.pack(fill="x", padx=10, pady=(0, 10))
        self.hk_record = ctk.StringVar()
        self.hk_run = ctk.StringVar()
        self.hk_panic = ctk.StringVar()
        self._hk_row(hk, "Gravar teclado", self.hk_record, "record")
        self._hk_row(hk, "Iniciar / Parar", self.hk_run, "run")
        self._hk_row(hk, "Panic (para tudo)", self.hk_panic, "panic")

        # Safety note
        safe = card(scroll, "SEGURANÇA")
        safe.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(
            safe,
            text=f"• Intervalo mínimo {MIN_INTERVAL_MS} ms\n"
                 f"• Panic sempre disponível\n"
                 f"• Atalhos não entram na gravação\n"
                 f"• Pare antes de editar a lista",
            justify="left", anchor="w",
            font=ctk.CTkFont(size=12), text_color=C["muted"],
        ).pack(anchor="w", padx=14, pady=(4, 12))

        # Main actions
        actions = ctk.CTkFrame(scroll, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=6)

        self.btn_rec = ctk.CTkButton(
            actions, text="●  Gravar teclado",
            command=self.engine.toggle_record,
            height=42, corner_radius=10,
            fg_color="#3a1f24", hover_color="#5a2a32",
            text_color=C["danger"],
            font=ctk.CTkFont(family="Segoe UI Semibold", size=14),
        )
        self.btn_rec.pack(fill="x", pady=(0, 8))

        self.btn_run = ctk.CTkButton(
            actions, text="▶  Iniciar",
            command=self._start_or_stop,
            height=44, corner_radius=10,
            fg_color=C["accent"], hover_color=C["accent_h"],
            font=ctk.CTkFont(family="Segoe UI Semibold", size=15),
        )
        self.btn_run.pack(fill="x", pady=(0, 8))

        soft_btn(
            actions, "■  Parar", self.engine.panic,
            height=36, fg_color=C["card2"],
        ).pack(fill="x")

        soft_btn(
            scroll, "Sair", self._close,
            height=30, width=80,
            fg_color="transparent", border_width=1, border_color=C["border"],
            text_color=C["muted"],
        ).pack(anchor="e", padx=10, pady=14)

    def _hk_row(self, parent, label, var, kind) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(row, text=label, anchor="w",
                     font=ctk.CTkFont(size=12), text_color=C["text"]).pack(anchor="w")
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", pady=(4, 0))
        ctk.CTkEntry(
            inner, textvariable=var, width=90, height=30, state="readonly",
            font=ctk.CTkFont(family="Consolas", size=12), justify="center",
        ).pack(side="left")
        soft_btn(
            inner, "Definir", lambda: self._capture(kind),
            width=70, height=30, fg_color=C["accent"], hover_color=C["accent_h"],
        ).pack(side="left", padx=8)

    # ── sync ────────────────────────────────────────────────────────────────
    def _sync_from_engine(self) -> None:
        e = self.engine
        if e.kb_enabled:
            self.kb_sw.select()
        else:
            self.kb_sw.deselect()
        if e.mouse_enabled:
            self.ms_sw.select()
        else:
            self.ms_sw.deselect()

        self.kb_delay.set(str(e.kb_delay_ms))
        self.kb_hold.set(str(e.kb_hold_ms))
        self.click_iv.set(str(e.click_interval_ms))
        self.click_n.set(str(e.click_count_per_tick))
        self.click_x.set(str(e.click_x))
        self.click_y.set(str(e.click_y))
        self.rep_times.set(str(e.repeat_count))

        btn_map = {"left": "Esquerdo", "right": "Direito", "middle": "Meio"}
        self.click_btn_seg.set(btn_map.get(e.click_button, "Esquerdo"))
        self.pos_seg.set("Fixo (X,Y)" if e.click_pos_mode == "fixed" else "Cursor atual")
        self.rep_seg.set("Contínuo" if e.repeat_mode == "continuous" else "N vezes")

        self.hk_record.set(e.record_hotkey.upper())
        self.hk_run.set(e.run_hotkey.upper())
        self.hk_panic.set(e.panic_hotkey.upper())

        self._refresh_list()
        self._on_modules()
        self._on_rep_mode(self.rep_seg.get())
        self._on_pos_mode(self.pos_seg.get())

    def _on_modules(self) -> None:
        self.engine.kb_enabled = bool(self.kb_sw.get())
        self.engine.mouse_enabled = bool(self.ms_sw.get())
        self.engine.save_settings()

        kb_on = self.engine.kb_enabled
        ms_on = self.engine.mouse_enabled

        if kb_on and ms_on:
            self.mode_hint.configure(text="Híbrido: teclado + mouse no mesmo ciclo")
        elif kb_on:
            self.mode_hint.configure(text="Só teclado")
        elif ms_on:
            self.mode_hint.configure(text="Só auto-click")
        else:
            self.mode_hint.configure(text="Ative ao menos um módulo")

        # Feedback visual nos painéis
        kb_color = C["text"] if kb_on else C["muted"]
        self.count_lbl.configure(text_color=kb_color if kb_on else C["muted"])

    def _on_click_btn(self, value: str) -> None:
        self.engine.click_button = {
            "Esquerdo": "left", "Direito": "right", "Meio": "middle",
        }.get(value, "left")
        self.engine.save_settings()

    def _on_pos_mode(self, value: str) -> None:
        fixed = value.startswith("Fixo")
        self.engine.click_pos_mode = "fixed" if fixed else "current"
        # Show/hide XY row
        if fixed:
            self.pos_row.pack(fill="x", padx=14, pady=(0, 8))
        else:
            self.pos_row.pack_forget()
        self.engine.save_settings()

    def _on_rep_mode(self, value: str) -> None:
        continuous = value.startswith("Contínuo")
        self.engine.repeat_mode = "continuous" if continuous else "times"
        if continuous:
            self.times_row.pack_forget()
        else:
            self.times_row.pack(fill="x", padx=14, pady=(0, 12))
        self.engine.save_settings()

    def _apply_kb_timing(self) -> None:
        self.engine.kb_delay_ms = clamp_int(
            self.kb_delay.get(), MIN_INTERVAL_MS, MAX_INTERVAL_MS, self.engine.kb_delay_ms
        )
        self.engine.kb_hold_ms = clamp_int(self.kb_hold.get(), 1, 500, self.engine.kb_hold_ms)
        self.kb_delay.set(str(self.engine.kb_delay_ms))
        self.kb_hold.set(str(self.engine.kb_hold_ms))
        self.engine.save_settings()

    def _apply_mouse(self) -> None:
        self.engine.click_interval_ms = clamp_int(
            self.click_iv.get(), MIN_INTERVAL_MS, MAX_INTERVAL_MS, self.engine.click_interval_ms
        )
        self.engine.click_count_per_tick = clamp_int(
            self.click_n.get(), 1, 100, self.engine.click_count_per_tick
        )
        self.engine.click_x = clamp_int(self.click_x.get(), 0, 100_000, self.engine.click_x)
        self.engine.click_y = clamp_int(self.click_y.get(), 0, 100_000, self.engine.click_y)
        self.click_iv.set(str(self.engine.click_interval_ms))
        self.click_n.set(str(self.engine.click_count_per_tick))
        self.click_x.set(str(self.engine.click_x))
        self.click_y.set(str(self.engine.click_y))
        self.engine.save_settings()

    def _apply_repeat(self) -> None:
        self.engine.repeat_count = clamp_int(self.rep_times.get(), 1, 1_000_000, self.engine.repeat_count)
        self.rep_times.set(str(self.engine.repeat_count))
        self.engine.save_settings()

    def _grab_pos(self) -> None:
        # Grab after short delay so user can move mouse
        self.mode_hint.configure(text="Posicione o cursor… 1s")
        self.after(1000, self._grab_pos_now)

    def _grab_pos_now(self) -> None:
        pos = self.engine._ms.position
        self.click_x.set(str(int(pos[0])))
        self.click_y.set(str(int(pos[1])))
        self._apply_mouse()
        self._on_modules()

    def _test_click(self) -> None:
        if self.engine.state != "idle":
            return
        self._apply_mouse()
        btn = {
            "left": mouse.Button.left,
            "right": mouse.Button.right,
            "middle": mouse.Button.middle,
        }[self.engine.click_button]
        self.engine._do_click(btn, {
            "pos_mode": self.engine.click_pos_mode,
            "x": self.engine.click_x,
            "y": self.engine.click_y,
        })

    # ── hotkey capture ──────────────────────────────────────────────────────
    def _capture(self, kind: str) -> None:
        if self.engine.state != "idle":
            messagebox.showinfo("Aguarde", "Pare tudo antes de mudar o atalho.")
            return
        self._capturing = kind
        var = {"record": self.hk_record, "run": self.hk_run, "panic": self.hk_panic}[kind]
        var.set("...")
        self.bind("<KeyPress>", self._on_capture)
        self.focus_force()

    def _on_capture(self, event) -> str:
        if not self._capturing:
            return "break"
        keysym = event.keysym.lower()
        aliases = {"escape": "esc", "return": "enter", "prior": "page_up", "next": "page_down"}
        name = aliases.get(keysym, keysym)
        if name.startswith(("shift", "control", "alt", "meta")):
            return "break"

        kind = self._capturing
        self._capturing = None
        self.unbind("<KeyPress>")

        ok = self.engine.set_hotkey(kind, name)
        var = {"record": self.hk_record, "run": self.hk_run, "panic": self.hk_panic}[kind]
        cur = {
            "record": self.engine.record_hotkey,
            "run": self.engine.run_hotkey,
            "panic": self.engine.panic_hotkey,
        }[kind]
        var.set(cur.upper())
        if not ok:
            messagebox.showwarning("Atalho inválido", "Escolha uma tecla diferente dos outros atalhos.")
        else:
            self._update_tip()
            if kind == "panic":
                self.panic_btn.configure(text=f"Panic  {cur.upper()}")
        return "break"

    def _update_tip(self) -> None:
        e = self.engine
        self.tip.configure(
            text=f"[{e.record_hotkey.upper()}] gravar   ·   "
                 f"[{e.run_hotkey.upper()}] iniciar/parar   ·   "
                 f"[{e.panic_hotkey.upper()}] panic   ·   "
                 f"funcionam com o app em segundo plano"
        )

    # ── list ────────────────────────────────────────────────────────────────
    def _refresh_list(self) -> None:
        sel = list(self.listbox.curselection())
        self.listbox.delete(0, tk.END)
        for i, a in enumerate(self.engine.actions, 1):
            self.listbox.insert(tk.END, f"  {i:<4}  {a.key}")
        for i in sel:
            if i < self.listbox.size():
                self.listbox.selection_set(i)
        n = len(self.engine.actions)
        self.count_lbl.configure(text=f"{n} tecla{'s' if n != 1 else ''}")

    def _remove(self) -> None:
        idxs = list(self.listbox.curselection())
        if idxs:
            self.engine.remove_indices(idxs)

    def _clear(self) -> None:
        if self.engine.state != "idle":
            return
        if self.engine.actions and messagebox.askyesno("Limpar", "Apagar toda a sequência?"):
            self.engine.clear_actions()

    def _move(self, d: int) -> None:
        idxs = list(self.listbox.curselection())
        if len(idxs) != 1:
            return
        i = idxs[0]
        self.engine.move_action(i, d)
        j = i + d
        if 0 <= j < self.listbox.size():
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(j)
            self.listbox.see(j)

    def _flush_settings(self) -> None:
        self._apply_kb_timing()
        self._apply_mouse()
        self._apply_repeat()

    def _start_or_stop(self) -> None:
        self.engine.toggle_run()

    def _save_profile(self) -> None:
        self._apply_kb_timing()
        self._apply_mouse()
        self._apply_repeat()
        path = filedialog.asksaveasfilename(
            initialdir=str(PROFILES_DIR), defaultextension=".json",
            filetypes=[("JSON", "*.json")], title="Salvar perfil",
        )
        if path:
            try:
                self.engine.save_profile(Path(path))
            except OSError as err:
                messagebox.showerror("Erro", str(err))

    def _load_profile(self) -> None:
        if self.engine.state != "idle":
            messagebox.showinfo("Aguarde", "Pare antes de carregar.")
            return
        path = filedialog.askopenfilename(
            initialdir=str(PROFILES_DIR), filetypes=[("JSON", "*.json")], title="Abrir perfil",
        )
        if path:
            try:
                self.engine.load_profile(Path(path))
                self._sync_from_engine()
            except (OSError, json.JSONDecodeError, TypeError, KeyError) as err:
                messagebox.showerror("Erro", f"Não foi possível abrir:\n{err}")

    # ── state UI ────────────────────────────────────────────────────────────
    def _on_state(self, state: str) -> None:
        styles = {
            "idle": ("●  IDLE", C["idle"], "●  Gravar teclado", "▶  Iniciar"),
            "recording": ("●  GRAVANDO", C["rec"], "■  Parar gravação", "▶  Iniciar"),
            "running": ("●  RODANDO", C["play"], "●  Gravar teclado", "■  Parar"),
        }
        label, color, rec, run = styles[state]
        self.status.configure(text=label, text_color=color)
        self.btn_rec.configure(text=rec)
        self.btn_run.configure(text=run)

    def _close(self) -> None:
        self.engine.shutdown()
        self.destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
