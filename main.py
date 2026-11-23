"""Duplicate Image Finder - entry point.

Kept minimal on purpose: worker processes (spawned on Windows) re-import this
module, so heavy imports (Qt) happen only inside main().

    main.py                 -> GUI
    main.py --cli <args>    -> headless scan (see dif/cli.py), used for testing
"""

import multiprocessing as mp
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        import os
        from dif import APP_DIR
        if sys.stdout is None:  # windowed .exe has no console: write to a file
            os.makedirs(APP_DIR, exist_ok=True)
            sys.stdout = sys.stderr = open(os.path.join(APP_DIR, "cli_output.txt"), "w", encoding="utf-8")
        from dif.cli import main as cli_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return cli_main()

    import os
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QStyleFactory
    from dif import RES_DIR
    from dif.gui.main_window import MainWindow

    if os.name == "nt":   # own taskbar icon instead of the Python one
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DuplicateImageFinder")
    app = QApplication(sys.argv)
    app.setDesktopFileName("duplicate-image-finder")    # Linux: matches the .desktop file (taskbar icon)
    icon = os.path.join(RES_DIR, "assets", "icon.ico" if os.name == "nt" else "icon_512.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    # Native style where it follows light/dark mode well (Windows 11, macOS); Fusion elsewhere.
    styles = [s.lower() for s in QStyleFactory.keys()]
    app.setStyle(next((s for s in ("windows11", "macos") if s in styles), "Fusion"))
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
