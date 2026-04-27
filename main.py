import sys

from app import create_app
from ui.main_window import MainWindow


def main():
    app = create_app()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
