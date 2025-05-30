import sys
import mss
import numpy as np
from PySide6 import QtWidgets, QtGui, QtCore


def get_screen_index_from_cursor(pos: QtCore.QPoint):
    """返回鼠标所在屏幕的索引"""
    for i, screen in enumerate(QtWidgets.QApplication.screens()):
        if screen.geometry().contains(pos):
            return i
    return 0


def get_screen_pixmap(screen_index=0):
    """使用 mss 截图指定屏幕，返回 QPixmap 和该屏幕的 QRect"""
    with mss.mss() as sct:
        monitor = sct.monitors[screen_index + 1]  # mss 的屏幕从 1 开始
        sct_img = sct.grab(monitor)
        img = np.array(sct_img)  # BGRA

        h, w, _ = img.shape
        bytes_per_line = 4 * w
        image = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format_RGBA8888)
        return QtGui.QPixmap.fromImage(image), QtCore.QRect(monitor["left"], monitor["top"], monitor["width"], monitor["height"])


class ScreenshotTool(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("截图工具")
        self.setGeometry(300, 300, 200, 100)

        self.btn = QtWidgets.QPushButton("截图", self)
        self.btn.clicked.connect(self.start_snipping)
        self.setCentralWidget(self.btn)

        self.floating_images = []  # ✅ 保存贴图，避免被销毁

    def start_snipping(self):
        self.hide()

        cursor_pos = QtGui.QCursor.pos()
        screen_index = get_screen_index_from_cursor(cursor_pos)
        self.pixmap, self.screen_geometry = get_screen_pixmap(screen_index)

        self.snip = SnipOverlay(self.pixmap, self.screen_geometry)
        self.snip.snip_done.connect(self.show_floating_image)
        self.snip.showFullScreen()

    def show_floating_image(self, global_pos, pixmap):
        self.show()
        overlay = FloatingImage(pixmap)
        overlay.move(global_pos)
        overlay.show()
        self.floating_images.append(overlay)  # ✅ 防止被垃圾回收


class SnipOverlay(QtWidgets.QWidget):
    snip_done = QtCore.Signal(QtCore.QPoint, QtGui.QPixmap)

    def __init__(self, background_pixmap, screen_geometry):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setCursor(QtCore.Qt.CrossCursor)

        self.background_pixmap = background_pixmap
        self.screen_geometry = screen_geometry

        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawPixmap(self.screen_geometry.topLeft(), self.background_pixmap)
        if not self.begin.isNull() and not self.end.isNull():
            rect = QtCore.QRect(self.begin, self.end)
            painter.setPen(QtGui.QPen(QtCore.Qt.red, 2))
            painter.setBrush(QtCore.Qt.transparent)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        self.begin = event.globalPosition().toPoint()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.globalPosition().toPoint()
        self.update()

    def mouseReleaseEvent(self, event):
        self.end = event.globalPosition().toPoint()
        rect = QtCore.QRect(self.begin, self.end).normalized()

        relative_rect = QtCore.QRect(
            rect.topLeft() - self.screen_geometry.topLeft(),
            rect.size()
        )
        cropped = self.background_pixmap.copy(relative_rect)
        self.snip_done.emit(rect.topLeft(), cropped)
        self.close()


class FloatingImage(QtWidgets.QLabel):
    def __init__(self, pixmap):
        super().__init__()
        self.setPixmap(pixmap)
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Tool
        )
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        self.setStyleSheet("border: 2px solid red;")
        self.setScaledContents(False)
        self.resize(pixmap.size())
        self.old_pos = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def show_menu(self, pos):
        menu = QtWidgets.QMenu()
        close_action = menu.addAction("销毁图片")
        action = menu.exec(self.mapToGlobal(pos))
        if action == close_action:
            self.close()


if __name__ == "__main__":
    # ✅ 必须启用高 DPI 支持
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    app = QtWidgets.QApplication(sys.argv)
    window = ScreenshotTool()
    window.show()
    sys.exit(app.exec())
