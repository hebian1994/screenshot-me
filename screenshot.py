import sys
import pyautogui
from PySide6 import QtWidgets, QtGui, QtCore


class ScreenshotTool(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("截图工具")
        self.setGeometry(300, 300, 200, 100)

        self.btn = QtWidgets.QPushButton("截图", self)
        self.btn.clicked.connect(self.start_snipping)
        self.setCentralWidget(self.btn)

    def start_snipping(self):
        self.hide()
        screenshot = pyautogui.screenshot()
        qimage = QtGui.QImage(
            screenshot.tobytes(), screenshot.width, screenshot.height, QtGui.QImage.Format_RGB888
        )
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self.snip = SnipOverlay(pixmap)
        self.snip.snip_done.connect(self.show_floating_image)
        self.snip.showFullScreen()

    def show_floating_image(self, pixmap):
        self.show()
        self.overlay = FloatingImage(pixmap)


class SnipOverlay(QtWidgets.QWidget):
    snip_done = QtCore.Signal(QtGui.QPixmap)

    def __init__(self, background_pixmap):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()
        self.background_pixmap = background_pixmap

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, self.background_pixmap)
        if not self.begin.isNull() and not self.end.isNull():
            painter.setPen(QtGui.QPen(QtCore.Qt.red, 2))
            painter.setBrush(QtCore.Qt.transparent)
            painter.drawRect(QtCore.QRect(self.begin, self.end))

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        rect = QtCore.QRect(self.begin, self.end).normalized()
        cropped = self.background_pixmap.copy(rect)
        self.snip_done.emit(cropped)
        self.close()


class FloatingImage(QtWidgets.QLabel):
    def __init__(self, pixmap):
        super().__init__()
        self.setPixmap(pixmap)
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        self.setStyleSheet("border: 2px solid red;")
        self.setScaledContents(True)
        self.resize(pixmap.size())
        self.show()
        self.old_pos = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def show_menu(self, pos):
        menu = QtWidgets.QMenu()
        close_action = menu.addAction("销毁图片")
        action = menu.exec(self.mapToGlobal(pos))
        if action == close_action:
            self.close()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ScreenshotTool()
    window.show()
    sys.exit(app.exec())

