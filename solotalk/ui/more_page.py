# -*- coding: utf-8 -*-
"""更多页：关于 / 更新&下载 / 使用须知。"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..config import APP_VERSION
from ..settings import save_settings


class MorePage(QWidget):
    REPO_URL = "https://github.com/FallingLighty/SoloTalk"
    RELEASES_URL = "https://github.com/FallingLighty/SoloTalk/releases"

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        left = QFrame()
        left.setFixedWidth(188)
        left.setStyleSheet("QFrame { background:#f7f9fb; border-right:1px solid #e6ebef; }")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        self.nav = QListWidget()
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setStyleSheet(
            "QListWidget { background:transparent; border:none; outline:none; padding:10px 0; }"
            "QListWidget::item { height:44px; margin:2px 10px; border-radius:8px; color:#55606b; font-size:14px; }"
            "QListWidget::item:selected { background:#e4eff9; color:#1f6fb2; }"
        )
        for txt in ["  ℹ️    关于", "  ⬆️    更新&下载", "  📌    使用须知"]:
            item = QListWidgetItem(txt)
            item.setSizeHint(QSize(0, 44))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav)
        lv.addWidget(self.nav, 1)

        foot = QWidget()
        fv = QVBoxLayout(foot)
        fv.setContentsMargins(18, 12, 18, 16)
        btn_back = QPushButton("返回主页")
        btn_back.setStyleSheet(
            "QPushButton { font-size:13px; padding:7px 0; border:1px solid #cfd8dc;"
            " border-radius:8px; background:white; color:#55606b; }"
            "QPushButton:hover { background:#f4f7f9; }"
        )
        btn_back.clicked.connect(lambda: self.main.go_to(self.main.home_page))
        fv.addWidget(btn_back)
        lv.addWidget(foot)

        root.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(26, 22, 26, 20)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_about())
        self.stack.addWidget(self._page_update())
        self.stack.addWidget(self._page_terms())
        rv.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self.nav.setCurrentRow(0)
        self.setLayout(root)

    def _on_nav(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _page_about(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignTop)
        t = QLabel("SoloTalk 中考版")
        t.setStyleSheet("font-size:26px; font-weight:bold; color:#2c3e50;")
        v.addWidget(t)
        v.addWidget(QLabel(f"版本 v{APP_VERSION}"))
        v.addWidget(QLabel("单机版英语听说模考编辑器 · 完全免费"))
        v.addWidget(QLabel(" "))
        v.addWidget(QLabel("作者：晖落然（FallingLighty）、cheng、咸鱼"))
        v.addWidget(QLabel("适用地区：佛山、中山、珠海、广州、湛江、茂名、阳江、清远、韶关、潮州、揭阳、云浮、梅州、江门（改革后）、惠州（改革后）、深圳（25分）、东莞（25分）"))
        v.addStretch(1)
        return w

    def _page_update(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignTop)
        t = QLabel("版本更新")
        t.setStyleSheet("font-size:20px; font-weight:bold;")
        v.addWidget(t)
        v.addWidget(QLabel(f"当前版本：SoloTalk 中考版 {APP_VERSION}"))
        row = QHBoxLayout()
        btn = QPushButton("检查更新")
        btn.setStyleSheet("background:#3498db; color:white; border:none; border-radius:6px; padding:8px 22px; font-weight:bold;")
        btn.clicked.connect(self.main._check_update)
        row.addWidget(btn)
        self.chk = QCheckBox("启动时自动检查更新")
        self.chk.setChecked(bool(self.main.settings.get("auto_check_update", True)))
        self.chk.toggled.connect(self._on_toggle)
        row.addWidget(self.chk)
        row.addStretch(1)
        v.addLayout(row)

        v.addWidget(QLabel("下载地址："))
        btn2 = QPushButton("前往 GitHub 发布页")
        btn2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.RELEASES_URL)))
        v.addWidget(btn2)
        v.addStretch(1)
        return w

    def _on_toggle(self, checked):
        self.main.settings["auto_check_update"] = bool(checked)
        save_settings(self.main.settings)

    def _page_terms(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignTop)
        t = QLabel("使用须知 & 声明")
        t.setStyleSheet("font-size:20px; font-weight:bold;")
        v.addWidget(t)
        for line in [
            "1、录音识别与批改全部在本地完成，断网也能完整考完；",
            "2、联网时会自动启用更自然的在线朗读语音，并在启动时检查一次新版本；",
            "3、适用人群：想提前体验听说考试流程的学生；",
            "4、Part C 要点请用英文逗号隔开，否则无法识别；",
            "5、批改结果基于离线语音识别，仅供参考；",
            "6、评分分制（30/25）由题目作者在编辑模式中指定，随 .solo 包分发。",
        ]:
            lb = QLabel(line)
            lb.setWordWrap(True)
            v.addWidget(lb)
        v.addStretch(1)
        return w
