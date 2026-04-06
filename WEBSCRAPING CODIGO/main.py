#!/usr/bin/env python3
"""
main.py — Punto de entrada de la aplicación SENAMHI.

Uso:
    python main.py

Dependencias:
    pip install PySide6 requests beautifulsoup4 selenium webdriver-manager
"""
import sys
from PySide6.QtWidgets import QApplication
from senamhi.app import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
