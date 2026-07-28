#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal Tkinter entry point for IR Learning Studio R5.

This file only:
1. Validates ProjectRoot
2. Calls composition_root.create_runtime()
3. Creates DesktopApp
4. Enters Tk event loop
5. Calls runtime.close() in finally

No SQLite SQL, no serial IO, no capture save, no canonical approval here.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import composition_root
import desktop_app


def main() -> int:
    project_root = HERE.parents[3]  # Navigate up from tools/ir_learning_studio to Firmware/Remote_AC_Controller

    # Create runtime
    runtime = composition_root.create_runtime(project_root, mode="production")
    if runtime.mutex is None and runtime.mode != "demo":
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "IR Learning Studio R5",
            "Another instance is already running, or project root is invalid.",
        )
        root.destroy()
        return 2

    root = tk.Tk()
    try:
        app = desktop_app.DesktopApp(root, runtime)
        root.mainloop()
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
