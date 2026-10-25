# -*- coding: utf-8 -*-
"""主窗口：堆叠各页面，处理页面切换、关闭确认与更新提示。"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..config import APP_VERSION
from ..models import SoloPackage
from ..paths import resolve_resource_file
from ..settings import load_settings, save_settings
from ..updater import UpdateChecker
from .editor import EditorPage
from .history_page import HistoryPage
from .home_page import HomePage
from .more_page import MorePage
from .practice import PracticePage
from .theme import (ACCENT_DEEP, BG_BOT, BG_TOP, BD, ICON_INFO, SETTINGS_FONT_KEY,
                    SUB, TEXT, bind_font, secondary_button, set_ui_font_choice,
                    svg_pixmap)


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

        # 用户上次选的界面字体（缺失时保持默认回退字体）
        _font_choice = self.settings.get(SETTINGS_FONT_KEY)
        if _font_choice:
            set_ui_font_choice(_font_choice)

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

    def set_ui_font(self, family):
        """切换界面字体（更多 → 个性化调用）：立即生效并记住选择。"""
        try:
            set_ui_font_choice(family)
        except Exception as e:
            print(f"[FONT] 切换失败: {e}")
            return False
        self.settings[SETTINGS_FONT_KEY] = family
        save_settings(self.settings)
        return True

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

    def _check_update(self, manual=False):
        if getattr(self, "_updater", None) and self._updater.isRunning():
            return
        self._updater = UpdateChecker()
        self._updater.update_available.connect(self.show_update_dialog)
        self._updater.start()

    def show_update_dialog(self, info):
        dlg = QDialog(self)
        dlg.setWindowTitle("发现新版本")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setMinimumWidth(460)
        dlg.setObjectName("updateRoot")
        dlg.setStyleSheet(
            f"#updateRoot {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 {BG_TOP}, stop:1 {BG_BOT}); }}")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        ic = QLabel()
        ic.setFixedSize(36, 36)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(svg_pixmap(ICON_INFO, ACCENT_DEEP, 28))
        ic.setStyleSheet("background:#E8F6FF; border-radius:18px;")
        head.addWidget(ic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        t = QLabel(f"发现新版本 SoloTalk 中考版 {info.get('version', '')}")
        bind_font(t, 16, medium=True)
        t.setStyleSheet(f"color:{TEXT};")
        s = QLabel("新版本已发布，可前往发布页手动下载。")
        bind_font(s, 12)
        s.setStyleSheet(f"color:{SUB};")
        col.addWidget(t)
        col.addWidget(s)
        head.addLayout(col, 1)
        layout.addLayout(head)

        notes = info.get("notes", "")
        if notes:
            tb = QTextEdit(notes)
            tb.setReadOnly(True)
            tb.setMaximumHeight(190)
            bind_font(tb, 13)
            layout.addWidget(tb)

        def _go():
            url = info.get("url", "")
            if url:
                QDesktopServices.openUrl(QUrl(url))
            dlg.accept()

        box = QHBoxLayout()
        box.setSpacing(10)
        box.addStretch(1)
        box.addWidget(secondary_button("稍后提醒", dlg.reject, height=36))
        btn_open = QPushButton("前往下载")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setFixedHeight(36)
        bind_font(btn_open, 13, medium=True)
        btn_open.setStyleSheet(
            f"QPushButton {{ background:{ACCENT_DEEP}; border:none; border-radius:9px;"
            f" padding:0 20px; color:#FFFFFF; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#66CCFF; }}")
        btn_open.clicked.connect(_go)
        box.addWidget(btn_open)
        layout.addLayout(box)
        dlg.exec_()
