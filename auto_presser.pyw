"""Duplo clique para abrir sem janela de CMD (pythonw)."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _show_error(exc: BaseException) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Auto Presser",
            f"Falha ao iniciar:\n\n{exc}\n\n{traceback.format_exc()}",
        )
        root.destroy()
    except Exception:
        Path(__file__).with_name("auto_presser_error.log").write_text(
            traceback.format_exc(), encoding="utf-8"
        )


if __name__ == "__main__":
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from auto_presser import main

        main()
    except Exception as e:
        _show_error(e)
        sys.exit(1)
