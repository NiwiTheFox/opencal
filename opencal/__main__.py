"""Start OpenCal: ``python -m opencal [file.bin]``."""
import os
import sys


def main() -> int:
    from PySide6 import QtWidgets

    from . import APP_NAME
    from .gui import theme
    from .gui.mainwindow import MainWindow

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("OpenCal")
    theme.apply(app)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        w._guard(lambda: w.load(sys.argv[1]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
