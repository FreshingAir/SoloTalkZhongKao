# -*- coding: utf-8 -*-
"""Part C 信息转述及询问编辑器：Section A 信息转述 / Section B 询问信息。"""

import os

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *


class PartCEditor(QWidget):
    """Part C 容器，仅组合两个 Section 编辑器。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        tabs = QTabWidget()
        self.secA_widget = PartCSecAEditor(self.pkg)
        self.secB_widget = PartCSecBEditor(self.pkg)
        tabs.addTab(self.secA_widget, "Section A 信息转述")
        tabs.addTab(self.secB_widget, "Section B 询问信息")
        layout.addWidget(tabs)
        self.setLayout(layout)

    def set_package(self, pkg):
        """切换题目包：自身与两个 Section 编辑器必须指向同一个对象。"""
        self.pkg = pkg
        self.secA_widget.pkg = pkg
        self.secB_widget.pkg = pkg

    def save_to_pkg(self):
        self.secA_widget.save_to_pkg()
        self.secB_widget.save_to_pkg()

    def refresh(self):
        self.secA_widget.refresh()
        self.secB_widget.refresh()


class PartCSecAEditor(QWidget):
    """Part C Section A 编辑：含思维导图图片上传。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self._audio_path = None
        self._mindmap_path = None

        outer = QVBoxLayout()

        form = QFormLayout()
        self.src_combo = QComboBox()
        self.src_combo.addItems(["💻电脑 TTS", "上传音频"])
        form.addRow("听力内容来源：", self.src_combo)
        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("听力材料全文（TTS朗读）")
        form.addRow("全文：", self.tts_edit)

        self.audio_lbl = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        hbox = QHBoxLayout()
        hbox.addWidget(self.audio_lbl)
        hbox.addWidget(self.audio_btn)
        form.addRow("音频文件：", hbox)

        self.key_points_edit = QTextEdit()
        self.key_points_edit.setPlaceholderText("要点提示（显示在屏幕上，如中文关键词）")
        self.key_points_edit.setMaximumHeight(80)
        form.addRow("要点提示：", self.key_points_edit)

        self.hidden_points_edit = QTextEdit()
        self.hidden_points_edit.setPlaceholderText("答案要点（隐藏，英文逗号分隔，用于批改）")
        self.hidden_points_edit.setMaximumHeight(80)
        form.addRow("答案要点：", self.hidden_points_edit)
        outer.addLayout(form)

        mm_group = QGroupBox("思维导图（图片，Part C 转述阶段显示）")
        mm_layout = QVBoxLayout()

        mm_top = QHBoxLayout()
        self.mindmap_lbl = QLabel("未选择思维导图")
        self.mindmap_lbl.setStyleSheet("color:#666;")
        self.mindmap_btn = QPushButton("选择图片")
        self.mindmap_btn.clicked.connect(self.upload_mindmap)
        self.mindmap_clear_btn = QPushButton("清除")
        self.mindmap_clear_btn.clicked.connect(self.clear_mindmap)
        mm_top.addWidget(QLabel("图片文件："))
        mm_top.addWidget(self.mindmap_lbl, 1)
        mm_top.addWidget(self.mindmap_btn)
        mm_top.addWidget(self.mindmap_clear_btn)
        mm_layout.addLayout(mm_top)

        self.mindmap_preview = QLabel()
        self.mindmap_preview.setMinimumHeight(220)
        self.mindmap_preview.setAlignment(Qt.AlignCenter)
        self.mindmap_preview.setStyleSheet(
            "border:1px dashed #bdc3c7; background:#fafafa; color:#95a5a6;")
        self.mindmap_preview.setText("（思维导图预览，建议使用 PNG/JPG 格式）")
        mm_layout.addWidget(self.mindmap_preview, 1)

        mm_group.setLayout(mm_layout)
        outer.addWidget(mm_group, 1)

        self.setLayout(outer)
        self._refresh_mindmap_ui()

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self._audio_path = path
            self.audio_lbl.setText(os.path.basename(path))

    def upload_mindmap(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择思维导图图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self._mindmap_path = path
            self._refresh_mindmap_ui()

    def clear_mindmap(self):
        self._mindmap_path = None
        self._refresh_mindmap_ui()

    def _refresh_mindmap_ui(self):
        if self._mindmap_path and os.path.isfile(self._mindmap_path):
            self.mindmap_lbl.setText(os.path.basename(self._mindmap_path))
            pix = QPixmap(self._mindmap_path)
            if not pix.isNull():
                w = max(self.mindmap_preview.width(), 600)
                h = max(self.mindmap_preview.height(), 220)
                self.mindmap_preview.setPixmap(
                    pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.mindmap_preview.setText("")
            else:
                self.mindmap_preview.setPixmap(QPixmap())
                self.mindmap_preview.setText("（图片无法解析，请换 PNG/JPG 再试）")
        else:
            self.mindmap_lbl.setText("未选择思维导图")
            self.mindmap_preview.setPixmap(QPixmap())
            self.mindmap_preview.setText("（思维导图预览，建议使用 PNG/JPG 格式）")

    def save_to_pkg(self):
        self.pkg.partC_secA["audio_source_type"] = "tts" if self.src_combo.currentIndex() == 0 else "audio"
        self.pkg.partC_secA["tts_text"] = self.tts_edit.toPlainText()
        self.pkg.partC_secA["audio_path"] = self._audio_path
        self.pkg.partC_secA["key_points"] = self.key_points_edit.toPlainText()
        self.pkg.partC_secA["hidden_answer_points"] = self.hidden_points_edit.toPlainText()
        self.pkg.partC_secA["mindmap_image"] = self._mindmap_path

    def refresh(self):
        secA = self.pkg.partC_secA
        self._audio_path = secA.get("audio_path")
        self.src_combo.setCurrentIndex(1 if secA.get("audio_source_type") == "audio" else 0)
        self.audio_lbl.setText(os.path.basename(secA["audio_path"]) if secA.get("audio_path") else "未选择音频")
        self.tts_edit.setPlainText(secA.get("tts_text", ""))
        self.key_points_edit.setPlainText(secA.get("key_points", ""))
        self.hidden_points_edit.setPlainText(secA.get("hidden_answer_points", ""))
        self._mindmap_path = secA.get("mindmap_image")
        self._refresh_mindmap_ui()


class PartCSecBEditor(QWidget):
    """询问信息：情境描述 + 2 个中文提示与隐藏标准提问。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        layout = QFormLayout()
        self.situation_edit = QTextEdit()
        self.situation_edit.setPlaceholderText("情境描述（如：你希望了解更多关于活动的情况）")
        layout.addRow("情境描述：", self.situation_edit)
        self.q_widgets = []
        for i in range(2):
            grp = QGroupBox(f"询问{i + 1}")
            inner = QFormLayout()
            cn_edit = QLineEdit(); cn_edit.setPlaceholderText("中文提示（如：询问活动开始时间）")
            hid_edit = QLineEdit(); hid_edit.setPlaceholderText("标准提问（英文，隐藏）")
            inner.addRow("中文提示：", cn_edit)
            inner.addRow("标准提问：", hid_edit)
            grp.setLayout(inner)
            layout.addRow(grp)
            self.q_widgets.append((cn_edit, hid_edit))
        self.setLayout(layout)

    def save_to_pkg(self):
        self.pkg.partC_secB["situation"] = self.situation_edit.toPlainText()
        self.pkg.partC_secB["questions"] = []
        for cn_edit, hid_edit in self.q_widgets:
            self.pkg.partC_secB["questions"].append({
                "cn_prompt": cn_edit.text(),
                "hidden_question": hid_edit.text(),
            })

    def refresh(self):
        secB = self.pkg.partC_secB
        self.situation_edit.setPlainText(secB.get("situation", ""))
        questions = secB.get("questions", [])
        for i, (cn_edit, hid_edit) in enumerate(self.q_widgets):
            if i < len(questions):
                cn_edit.setText(questions[i].get("cn_prompt", ""))
                hid_edit.setText(questions[i].get("hidden_question", ""))
            else:
                cn_edit.clear(); hid_edit.clear()
