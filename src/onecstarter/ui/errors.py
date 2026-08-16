"""Показ ошибок слоя services: сообщение вместо трассировки (спека 4a, §3).

Текст любого ServicesError безопасен для показа и для буфера обмена:
слой services гарантирует отсутствие секретов в сообщениях (инвариант 5).
"""

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from onecstarter.services.errors import ServicesError


def build_error_box(parent: QWidget | None, error: ServicesError) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("OneCStarter")
    box.setText(str(error))
    box.addButton(QMessageBox.StandardButton.Ok)
    copy_button = box.addButton("Скопировать", QMessageBox.ButtonRole.ActionRole)
    copy_button.clicked.connect(lambda: QApplication.clipboard().setText(str(error)))
    return box


def show_service_error(parent: QWidget | None, error: ServicesError) -> None:
    build_error_box(parent, error).exec()
