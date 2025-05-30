import sys
import mss
import numpy as np
from PySide6 import QtWidgets, QtGui, QtCore


def get_screen_index_from_cursor(pos: QtCore.QPoint):
    for i, screen in enumerate(QtWidgets.QApplication.screens()):
        if screen.geometry().contains(pos):
            return i
    return 0


def get_screen_pixmap(screen_index=0):
    with mss.mss() as sct:
        monitor = sct.monitors[screen_index + 1]
        sct_img = sct.grab(monitor)
        img = np.array(sct_img)  # BGRA

        h, w, _ = img.shape
        bytes_per_line = 4 * w
        image = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_ARGB32)
        return QtGui.QPixmap.fromImage(image), QtCore.QRect(monitor["left"], monitor["top"], monitor["width"], monitor["height"])



class ScreenshotTool(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("截图工具")
        self.setGeometry(300, 300, 200, 100)

        self.btn = QtWidgets.QPushButton("截图", self)
        self.btn.clicked.connect(self.start_snipping)
        self.setCentralWidget(self.btn)

        self.floating_images = []

    def start_snipping(self):
        self.hide()

        cursor_pos = QtGui.QCursor.pos()
        screen_index = get_screen_index_from_cursor(cursor_pos)
        self.pixmap, self.screen_geometry = get_screen_pixmap(screen_index)

        self.snip = SnipOverlay(self.screen_geometry)
        self.snip.snip_done.connect(self.show_floating_image)
        self.snip.showFullScreen()

    def show_floating_image(self, global_pos, pixmap):
        self.show()
        overlay = FloatingImage(pixmap)
        overlay.move(global_pos)
        overlay.show()
        self.floating_images.append(overlay)


class SnipOverlay(QtWidgets.QWidget):
    snip_done = QtCore.Signal(QtCore.QPoint, QtGui.QPixmap)

    def __init__(self, screen_geometry):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setCursor(QtCore.Qt.CrossCursor)

        self.screen_geometry = screen_geometry
        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        # 绘制灰色半透明遮罩
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 80))

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

        # 因为没背景图，所以用 mss 重新截一次屏幕对应区域
        with mss.mss() as sct:
            monitor = {
                "left": rect.left(),
                "top": rect.top(),
                "width": rect.width(),
                "height": rect.height()
            }
            sct_img = sct.grab(monitor)
            img = np.array(sct_img)

        h, w, _ = img.shape
        bytes_per_line = 4 * w
        image = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format_ARGB32)
        cropped_pixmap = QtGui.QPixmap.fromImage(image)

        self.snip_done.emit(rect.topLeft(), cropped_pixmap)
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
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    app = QtWidgets.QApplication(sys.argv)
    window = ScreenshotTool()
    window.show()
    sys.exit(app.exec())
