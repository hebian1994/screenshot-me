import sys
import mss
import numpy as np
from PySide6 import QtWidgets, QtGui, QtCore
import ctypes
from ctypes import wintypes
import win32con
import win32gui
import pywintypes


# ----------------- 热键监听类 -----------------
class HotkeyListener(QtCore.QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == win32con.WM_HOTKEY:
                self.callback()
        return False, 0


def register_global_hotkey(modifiers, key_id, vk_code):
    try:
        win32gui.RegisterHotKey(None, key_id, modifiers, vk_code)
    except pywintypes.error as e:
        raise RuntimeError(f"快捷键注册失败！{e}")


def unregister_global_hotkey(key_id):
    win32gui.UnregisterHotKey(None, key_id)


# ----------------- 截图辅助函数 -----------------
def get_screen_index_from_cursor(pos: QtCore.QPoint):
    for i, screen in enumerate(QtWidgets.QApplication.screens()):
        if screen.geometry().contains(pos):
            return i
    return 0


def get_screen_pixmap(screen_index=0):
    with mss.mss() as sct:
        monitor = sct.monitors[screen_index + 1]
        sct_img = sct.grab(monitor)
        img = np.array(sct_img)
        h, w, _ = img.shape
        bytes_per_line = 4 * w
        image = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_ARGB32)
        return QtGui.QPixmap.fromImage(image), QtCore.QRect(monitor["left"], monitor["top"], monitor["width"],
                                                            monitor["height"])


# ----------------- 主窗口 -----------------
class ScreenshotTool(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("截图工具")
        self.setGeometry(300, 300, 200, 100)

        self.btn = QtWidgets.QPushButton("截图", self)
        self.btn.clicked.connect(self.start_snipping)
        self.setCentralWidget(self.btn)

        self.floating_images = []

        # 注册快捷键 Ctrl+Shift+F1
        self.hotkey_id = 1001
        # register_global_hotkey(win32con.MOD_CONTROL | win32con.MOD_SHIFT, self.hotkey_id, win32con.VK_F1)
        # 替换为 Ctrl + Alt + X（很少冲突）
        register_global_hotkey(win32con.MOD_CONTROL | win32con.MOD_ALT, 1001, ord('X'))

        self.hotkey_filter = HotkeyListener(self.on_hotkey_triggered)
        QtCore.QCoreApplication.instance().installNativeEventFilter(self.hotkey_filter)

    def on_hotkey_triggered(self):
        self.start_snipping()

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

    def closeEvent(self, event):
        unregister_global_hotkey(self.hotkey_id)
        event.accept()


# ----------------- 截图区域选择 -----------------
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


# ----------------- 图像展示及绘图 -----------------
class CanvasLabel(QtWidgets.QLabel):
    def __init__(self, pixmap, canvas):
        super().__init__()
        self._pixmap = pixmap
        self._canvas = canvas
        self.setFixedSize(pixmap.size())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.drawPixmap(0, 0, self._canvas)


class FloatingImage(QtWidgets.QWidget):
    def __init__(self, pixmap, parent_tool):
        super().__init__()
        self.parent_tool = parent_tool
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

        self.canvas = QtGui.QPixmap(pixmap.size())
        self.canvas.fill(QtCore.Qt.transparent)
        self.image_label = CanvasLabel(pixmap, self.canvas)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image_label)

        self.resize(pixmap.size())
        self.old_pos = None
        self.drawing = False
        self.draw_mode = None
        self.last_point = None
        self.start_point = None
        self.end_point = None

        self.toolbar = QtWidgets.QWidget(None, QtCore.Qt.Tool)
        self.toolbar.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.toolbar.setStyleSheet("background-color: #ddd; border: 1px solid #aaa;")
        layout_tb = QtWidgets.QHBoxLayout(self.toolbar)
        layout_tb.setContentsMargins(5, 5, 5, 5)

        self.btn_pencil = QtWidgets.QPushButton("铅笔")
        self.btn_rect = QtWidgets.QPushButton("矩形")
        self.btn_cancel = QtWidgets.QPushButton("取消绘制")
        layout_tb.addWidget(self.btn_pencil)
        layout_tb.addWidget(self.btn_rect)
        layout_tb.addWidget(self.btn_cancel)

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
            self.image_label.update()
        elif self.drawing and self.draw_mode == 'rect':
            self.end_point = event.pos()
            self.image_label.update()
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
            self.image_label.update()

        self.drawing = False
        self.start_point = None
        self.end_point = None

    def show_menu(self, pos):
        menu = QtWidgets.QMenu()
        close_action = menu.addAction("销毁图片")
        if self.draw_mode is None:
            draw_action = menu.addAction("绘制")
        else:
            draw_action = menu.addAction("取消绘制")
        copy_action = menu.addAction("复制图片")

        action = menu.exec(self.mapToGlobal(pos))
        if action == close_action:
            self.close()
        elif action == draw_action:
            if self.draw_mode is None:
                self.start_draw_mode()
            else:
                self.cancel_draw_mode()
        elif action == copy_action:
            self.copy_to_clipboard()

    def start_draw_mode(self):
        self.draw_mode = 'pencil'
        self.toolbar.show()
        self.toolbar.raise_()
        QtCore.QTimer.singleShot(0, self.adjust_toolbar_position)

    def cancel_draw_mode(self):
        self.draw_mode = None
        self.toolbar.hide()
        self.image_label.update()

    def adjust_toolbar_position(self):
        self.toolbar.move(self.geometry().topLeft() + QtCore.QPoint(10, 10))

    def set_pencil_mode(self):
        self.draw_mode = 'pencil'

    def set_rect_mode(self):
        self.draw_mode = 'rect'

    def copy_to_clipboard(self):
        combined = QtGui.QPixmap(self.image_label.size())
        combined.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(combined)
        painter.drawPixmap(0, 0, self.image_label._pixmap)
        painter.drawPixmap(0, 0, self.canvas)
        painter.end()
        QtWidgets.QApplication.clipboard().setPixmap(combined)

    def closeEvent(self, event):
        self.toolbar.close()
        if self in self.parent_tool.floating_images:
            self.parent_tool.floating_images.remove(self)
        event.accept()


# ----------------- 主程序入口 -----------------
if __name__ == "__main__":
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    app = QtWidgets.QApplication(sys.argv)
    window = ScreenshotTool()
    window.show()
    sys.exit(app.exec())
