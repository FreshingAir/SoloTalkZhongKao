# -*- coding: utf-8 -*-
"""Part A 模仿朗读编辑器。"""

import os

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..theme import SUB, bind_font
from .widgets import audio_picker, file_name, source_select


class PartAEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 10, 4, 4)
        outer.setSpacing(12)

        # ---- 短文音频 ----
        audio_group = QGroupBox("短文音频")
        av = QVBoxLayout(audio_group)
        av.setContentsMargins(14, 18, 14, 12)
        av.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        lb = QLabel("音频来源")
        bind_font(lb, 13)
        lb.setStyleSheet(f"color:{SUB};")
        row.addWidget(lb)
        self.source_combo = source_select()
        self.source_combo.changed.connect(self.toggle_source)
        row.addWidget(self.source_combo)
        row.addStretch(1)
        av.addLayout(row)

        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("短文文本（电脑朗读）")
        self.tts_edit.setMinimumHeight(120)
        av.addWidget(self.tts_edit)

        self.audio_row, self.audio_label, btn_choose, btn_clear = audio_picker()
        btn_choose.clicked.connect(self.upload_audio)
        btn_clear.clicked.connect(self.clear_audio)
        av.addWidget(self.audio_row)
        outer.addWidget(audio_group)

        # ---- 隐藏原文 ----
        hidden_group = QGroupBox("原文（隐藏，仅用于批改）")
        hv = QVBoxLayout(hidden_group)
        hv.setContentsMargins(14, 18, 14, 12)
        self.hidden_edit = QTextEdit()
        self.hidden_edit.setPlaceholderText("输入原文，练习/模考时用于对照朗读与批改")
        self.hidden_edit.setMinimumHeight(140)
        hv.addWidget(self.hidden_edit)
        outer.addWidget(hidden_group, 1)

        self.setLayout(outer)
        self.toggle_source()

    def toggle_source(self, *_):
        is_tts = self.source_combo.currentData() != "audio"
        self.tts_edit.setVisible(is_tts)
        self.audio_row.setVisible(not is_tts)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self.pkg.partA_audio_path = path
            self.audio_label.setText(os.path.basename(path))

    def clear_audio(self):
        self.pkg.partA_audio_path = None
        self.audio_label.setText("未选择音频")

    def save_to_pkg(self):
        self.pkg.partA_audio_source_type = self.source_combo.currentData() or "tts"
        self.pkg.partA_tts_text = self.tts_edit.toPlainText()
        self.pkg.partA_hidden_text = self.hidden_edit.toPlainText()

    def refresh(self):
        is_audio = self.pkg.partA_audio_source_type == "audio"
        self.source_combo.setCurrentIndex(1 if is_audio else 0)
        self.audio_label.setText(file_name(self.pkg.partA_audio_path))
        self.tts_edit.setPlainText(self.pkg.partA_tts_text)
        self.hidden_edit.setPlainText(self.pkg.partA_hidden_text)
        self.toggle_source()
