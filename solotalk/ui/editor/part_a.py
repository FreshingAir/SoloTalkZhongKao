# -*- coding: utf-8 -*-
"""Part A 模仿朗读编辑器。"""

import os

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *


class PartAEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItems(["💻电脑 TTS 朗读", "上传本地音频"])
        self.source_combo.currentIndexChanged.connect(self.toggle_source)
        layout.addRow("短文音频来源：", self.source_combo)

        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("短文文本（电脑朗读）")
        layout.addRow("短文文本：", self.tts_edit)

        self.audio_label = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        audio_box = QHBoxLayout()
        audio_box.addWidget(self.audio_label)
        audio_box.addWidget(self.audio_btn)
        layout.addRow("音频文件：", audio_box)

        self.hidden_edit = QTextEdit()
        self.hidden_edit.setPlaceholderText("原文（隐藏，仅用于批改）")
        layout.addRow("原文(隐藏)：", self.hidden_edit)

        self.setLayout(layout)
        self.toggle_source()

    def toggle_source(self):
        is_tts = self.source_combo.currentIndex() == 0
        self.tts_edit.setVisible(is_tts)
        self.audio_label.setVisible(not is_tts)
        self.audio_btn.setVisible(not is_tts)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self.pkg.partA_audio_path = path
            self.audio_label.setText(os.path.basename(path))

    def save_to_pkg(self):
        self.pkg.partA_audio_source_type = "tts" if self.source_combo.currentIndex() == 0 else "audio"
        self.pkg.partA_tts_text = self.tts_edit.toPlainText()
        self.pkg.partA_hidden_text = self.hidden_edit.toPlainText()

    def refresh(self):
        if self.pkg.partA_audio_source_type == "audio":
            self.source_combo.setCurrentIndex(1)
            self.audio_label.setText(os.path.basename(self.pkg.partA_audio_path)
                                     if self.pkg.partA_audio_path else "未选择音频")
        else:
            self.source_combo.setCurrentIndex(0)
        self.tts_edit.setPlainText(self.pkg.partA_tts_text)
        self.hidden_edit.setPlainText(self.pkg.partA_hidden_text)
        self.toggle_source()
