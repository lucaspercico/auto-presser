"""
Abra este arquivo (duplo clique) para iniciar sem janela de CMD.
No Windows, .pyw roda com pythonw.exe (sem console).
"""

from __future__ import annotations

import sys
import traceback


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
        # Último recurso: grava log ao lado do script
        from pathlib import Path

        log = Path(__file__).with_name("auto_presser_error.log")
        log.write_text(traceback.format_exc(), encoding="utf-8")


if __name__ == "__main__":
    try:
        # Garante que o .py ao lado seja encontrado
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from auto_keyboard_presser import main

        main()
    except Exception as e:
        _show_error(e)
        sys.exit(1)
