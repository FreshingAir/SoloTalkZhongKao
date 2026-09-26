# -*- coding: utf-8 -*-
"""首页：四个功能入口 + 更多页入口，并负责加载 .solo 文件后进入练习/模考。"""

import json
import zipfile
import tempfile

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *


class HomePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 18)
        layout.addStretch(1)
        title = QLabel("SoloTalk 中考版")
        title.setStyleSheet("font-size:42px; font-weight:bold; color:#2c3e50;")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("单机版听说模考编辑器 · 完全免费")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:16px; color:#7f8c8d; margin-bottom:30px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        btn_style = """
            QPushButton { font-size:20px; padding:18px 50px; border:2px solid #3498db;
                          border-radius:10px; background:white; color:#2c3e50; }
            QPushButton:hover { background:#ecf0f1; }
        """
        btn_editor = QPushButton("✏️  编辑模式")
        btn_editor.setStyleSheet(btn_style)
        btn_editor.clicked.connect(lambda: self.main.go_to(self.main.editor_page))
        btn_practice = QPushButton("🎧  练习模式")
        btn_practice.setStyleSheet(btn_style)
        btn_practice.setToolTip("可跳过 / 上一步，开头试音也能跳过")
        btn_practice.clicked.connect(lambda: self.load_and_start("practice"))
        btn_exam = QPushButton("📝  模考模式")
        btn_exam.setStyleSheet(btn_style)
        btn_exam.setToolTip("不可跳过 / 上一步，试音也不能跳过")
        btn_exam.clicked.connect(lambda: self.load_and_start("exam"))
        btn_history = QPushButton("📋  历史记录")
        btn_history.setStyleSheet(btn_style)
        btn_history.clicked.connect(lambda: self.main.go_to(self.main.history_page))
        layout.addWidget(btn_editor, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_practice, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_exam, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_history, alignment=Qt.AlignCenter)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        btn_more = QPushButton("⋯  更多")
        btn_more.setCursor(Qt.PointingHandCursor)
        btn_more.setStyleSheet(
            "QPushButton { font-size:14px; padding:8px 18px; border:1px solid #cfd8dc;"
            " border-radius:8px; background:white; color:#607d8b; }"
            "QPushButton:hover { background:#ecf0f1; color:#2c3e50; }"
        )
        btn_more.clicked.connect(lambda: self.main.go_to(self.main.more_page))
        bottom.addWidget(btn_more)
        bottom.addStretch(1)
        layout.addLayout(bottom)
        self.setLayout(layout)

    def load_and_start(self, mode):
        """选择 .solo 文件 → 解包到临时目录 → 进入练习/模考页。"""
        path, _ = QFileDialog.getOpenFileName(self, "选择 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if not path:
            return
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                with zf.open('data.json') as f:
                    data = json.load(f)
                temp_dir = tempfile.mkdtemp(prefix="solotalk_")
                zf.extractall(temp_dir)
                self.main.current_package.from_dict(data, base_dir=temp_dir)
                self.main.current_package.meta['temp_dir'] = temp_dir
            self.main.practice_page.pkg = self.main.current_package
            self.main.practice_page.set_mode(mode)
            self.main.go_to(self.main.practice_page)
            self.main.practice_page._check_and_prompt_progress()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败：{str(e)}")
