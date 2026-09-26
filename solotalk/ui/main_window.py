# -*- coding: utf-8 -*-
"""主窗口：堆叠各页面，处理页面切换、关闭确认与更新提示。"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..config import APP_VERSION
from ..models import SoloPackage
from ..paths import resolve_resource_file
from ..settings import load_settings
from ..updater import UpdateChecker
from .editor import EditorPage
from .history_page import HistoryPage
from .home_page import HomePage
from .more_page import MorePage
from .practice import PracticePage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SoloTalk 中考版 {APP_VERSION} — 单机版听说模考编辑器")
        self.setMinimumSize(1024, 700)

        _icon_path = resolve_resource_file("xixi.ico")
        if _icon_path:
            self.setWindowIcon(QIcon(_icon_path))

        self.current_package = SoloPackage()
        self.current_session = None
        self.settings = load_settings()

        self.central = QStackedWidget()
        self.setCentralWidget(self.central)

        self.home_page = HomePage(self)
        self.editor_page = EditorPage(self)
        self.practice_page = PracticePage(self)
        self.history_page = HistoryPage(self)
        self.more_page = MorePage(self)

        self.central.addWidget(self.home_page)
        self.central.addWidget(self.editor_page)
        self.central.addWidget(self.practice_page)
        self.central.addWidget(self.history_page)
        self.central.addWidget(self.more_page)
        self.central.setCurrentWidget(self.home_page)

        if self.settings.get("auto_check_update", True):
            QTimer.singleShot(1500, self._check_update)

        self.show()

    def go_to(self, page):
        """切换页面；离开练习页时确保停止播放中的音频。"""
        try:
            if page is not self.practice_page and self.central.currentWidget() is self.practice_page:
                self.practice_page._stop_video()
        except Exception:
            pass
        self.central.setCurrentWidget(page)

    def closeEvent(self, event):
        if self.central.currentWidget() == self.practice_page:
            if not self.practice_page.request_exit():
                event.ignore()
                return
        event.accept()

    def _check_update(self):
        if getattr(self, "_updater", None) and self._updater.isRunning():
            return
        self._updater = UpdateChecker()
        self._updater.update_available.connect(self.show_update_dialog)
        self._updater.start()

    def show_update_dialog(self, info):
        dlg = QDialog(self)
        dlg.setWindowTitle("发现新版本")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setMinimumWidth(440)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"<b>发现新版本 SoloTalk 中考版 {info.get('version', '')}</b>"))
        notes = info.get("notes", "")
        if notes:
            tb = QTextEdit(notes)
            tb.setReadOnly(True)
            tb.setMaximumHeight(180)
            layout.addWidget(tb)

        def _go():
            url = info.get("url", "")
            if url:
                QDesktopServices.openUrl(QUrl(url))
            dlg.accept()

        btn_later = QPushButton("稍后提醒")
        btn_open = QPushButton("前往下载")
        btn_open.setStyleSheet("background:#3498db;color:white;font-weight:bold;")
        btn_later.clicked.connect(dlg.reject)
        btn_open.clicked.connect(_go)
        box = QHBoxLayout()
        box.addStretch(1)
        box.addWidget(btn_later)
        box.addWidget(btn_open)
        layout.addLayout(box)
        dlg.exec_()
