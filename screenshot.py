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
        overlay = FloatingImage(pixmap, self)
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


class FloatingImage(QtWidgets.QWidget):
    def __init__(self, pixmap, parent_tool):
        super().__init__()
        self.parent_tool = parent_tool

        self.original_pixmap = pixmap.copy()
        self.canvas = QtGui.QPixmap(pixmap.size())
        self.canvas.fill(QtCore.Qt.transparent)

        self.image_label = QtWidgets.QLabel(self)
        self.image_label.setPixmap(self.original_pixmap)
        self.image_label.setScaledContents(False)
        self.image_label.resize(pixmap.size())

        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        self.resize(pixmap.size())
        self.old_pos = None

        self.drawing = False
        self.draw_mode = None
        self.last_point = None
        self.start_point = None
        self.end_point = None

        self.toolbar = QtWidgets.QWidget(self)
        self.toolbar.setFixedWidth(80)
        self.toolbar.setStyleSheet("background-color: #ddd; border-left: 1px solid #aaa;")
        self.toolbar.move(0, 0)
        self.toolbar.hide()

        layout = QtWidgets.QVBoxLayout(self.toolbar)
        layout.setContentsMargins(5, 5, 5, 5)

        self.btn_pencil = QtWidgets.QPushButton("铅笔")
        self.btn_rect = QtWidgets.QPushButton("矩形")
        self.btn_cancel = QtWidgets.QPushButton("取消")

        layout.addWidget(self.btn_pencil)
        layout.addWidget(self.btn_rect)
        layout.addWidget(self.btn_cancel)

        self.btn_pencil.clicked.connect(self.set_pencil_mode)
        self.btn_rect.clicked.connect(self.set_rect_mode)
        self.btn_cancel.clicked.connect(self.cancel_draw_mode)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self.draw_mode in ('pencil', 'rect'):
                self.drawing = True
                self.start_point = event.pos()
                self.last_point = event.pos()
            else:
                self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.drawing and self.draw_mode == 'pencil':
            painter = QtGui.QPainter(self.canvas)
            pen = QtGui.QPen(QtCore.Qt.red, 2)
            painter.setPen(pen)
            painter.drawLine(self.last_point, event.pos())
            self.last_point = event.pos()
            self.update_image()
        elif self.drawing and self.draw_mode == 'rect':
            self.end_point = event.pos()
            self.update_image()
        elif event.buttons() & QtCore.Qt.LeftButton and self.draw_mode is None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if self.drawing and self.draw_mode == 'rect':
            painter = QtGui.QPainter(self.canvas)
            pen = QtGui.QPen(QtCore.Qt.red, 2)
            painter.setPen(pen)
            rect = QtCore.QRect(self.start_point, event.pos()).normalized()
            painter.drawRect(rect)
        self.drawing = False
        self.start_point = None
        self.end_point = None
        self.update_image()

    def update_image(self):
        result = self.original_pixmap.copy()
        painter = QtGui.QPainter(result)
        painter.drawPixmap(0, 0, self.canvas)
        if self.drawing and self.draw_mode == 'rect' and self.start_point and self.end_point:
            painter.setPen(QtGui.QPen(QtCore.Qt.red, 2))
            painter.setBrush(QtCore.Qt.transparent)
            rect = QtCore.QRect(self.start_point, self.end_point).normalized()
            painter.drawRect(rect)
        painter.end()
        self.image_label.setPixmap(result)

    def show_menu(self, pos):
        menu = QtWidgets.QMenu()
        close_action = menu.addAction("销毁图片")
        draw_action = menu.addAction("取消绘制" if self.draw_mode else "绘制")
        copy_action = menu.addAction("复制图片")

        action = menu.exec(self.mapToGlobal(pos))

        if action == close_action:
            self.close()
        elif action == draw_action:
            if self.draw_mode:
                self.cancel_draw_mode()
            else:
                self.start_draw_mode()
        elif action == copy_action:
            self.copy_to_clipboard()

    def start_draw_mode(self):
        self.draw_mode = 'pencil'
        self.toolbar.show()
        self.toolbar.raise_()

    def cancel_draw_mode(self):
        self.draw_mode = None
        self.toolbar.hide()

    def set_pencil_mode(self):
        self.draw_mode = 'pencil'

    def set_rect_mode(self):
        self.draw_mode = 'rect'

    def copy_to_clipboard(self):
        result = self.original_pixmap.copy()
        painter = QtGui.QPainter(result)
        painter.drawPixmap(0, 0, self.canvas)
        painter.end()
        QtWidgets.QApplication.clipboard().setPixmap(result)

    def closeEvent(self, event):
        if self in self.parent_tool.floating_images:
            self.parent_tool.floating_images.remove(self)
        event.accept()


if __name__ == "__main__":
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    app = QtWidgets.QApplication(sys.argv)
    window = ScreenshotTool()
    window.show()
    sys.exit(app.exec())
