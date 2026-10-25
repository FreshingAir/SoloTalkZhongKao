# -*- coding: utf-8 -*-
"""Part C 信息转述及询问编辑器：Section A 信息转述 / Section B 询问信息。"""

import os

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..theme import MUTED, SUB, bind_font
from .widgets import audio_picker, file_name, mini_button, source_select


class PartCEditor(QWidget):
    """Part C 容器，仅组合两个 Section 编辑器。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 10, 4, 4)
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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        widget = QWidget()
        widget.setStyleSheet("background:transparent;")
        body = QVBoxLayout(widget)
        body.setContentsMargins(4, 4, 4, 10)
        body.setSpacing(12)

        # ---- 听力材料 ----
        audio_group = QGroupBox("听力材料")
        av = QVBoxLayout(audio_group)
        av.setContentsMargins(14, 18, 14, 12)
        av.setSpacing(9)

        src_row = QHBoxLayout()
        src_row.setSpacing(10)
        src_lb = QLabel("听力内容来源")
        bind_font(src_lb, 13)
        src_lb.setStyleSheet(f"color:{SUB};")
        src_row.addWidget(src_lb)
        self.src_combo = source_select()
        src_row.addWidget(self.src_combo)
        src_row.addStretch(1)
        av.addLayout(src_row)

        self.tts_edit = QTextEdit()
        self.tts_edit.setMinimumHeight(110)
        self.tts_edit.setPlaceholderText("听力材料全文（TTS朗读）")
        av.addWidget(self.tts_edit)

        self.audio_row, self.audio_lbl, btn_choose, btn_clear = audio_picker()
        btn_choose.clicked.connect(self.upload_audio)
        btn_clear.clicked.connect(self.clear_audio)
        av.addWidget(self.audio_row)
        body.addWidget(audio_group)

        # ---- 要点 ----
        points_group = QGroupBox("要点")
        pv = QVBoxLayout(points_group)
        pv.setContentsMargins(14, 18, 14, 12)
        pv.setSpacing(8)
        self.key_points_edit = QTextEdit()
        self.key_points_edit.setPlaceholderText("要点提示（显示在屏幕上，如中文关键词）")
        self.key_points_edit.setMaximumHeight(80)
        pv.addWidget(self.key_points_edit)
        self.hidden_points_edit = QTextEdit()
        self.hidden_points_edit.setPlaceholderText("答案要点（隐藏，英文逗号分隔，用于批改）")
        self.hidden_points_edit.setMaximumHeight(80)
        pv.addWidget(self.hidden_points_edit)
        body.addWidget(points_group)

        # ---- 思维导图 ----
        mm_group = QGroupBox("思维导图（图片，Part C 转述阶段显示）")
        mm_layout = QVBoxLayout(mm_group)
        mm_layout.setContentsMargins(14, 18, 14, 12)
        mm_layout.setSpacing(9)

        mm_top = QHBoxLayout()
        mm_top.setSpacing(8)
        self.mindmap_lbl = QLabel("未选择思维导图")
        bind_font(self.mindmap_lbl, 12)
        self.mindmap_lbl.setStyleSheet(f"color:{SUB};")
        mm_top.addWidget(self.mindmap_lbl, 1)
        self.mindmap_btn = mini_button("选择图片", self.upload_mindmap)
        self.mindmap_clear_btn = mini_button("清除", self.clear_mindmap)
        mm_top.addWidget(self.mindmap_btn)
        mm_top.addWidget(self.mindmap_clear_btn)
        mm_layout.addLayout(mm_top)

        self.mindmap_preview = QLabel()
        self.mindmap_preview.setMinimumHeight(220)
        self.mindmap_preview.setAlignment(Qt.AlignCenter)
        self.mindmap_preview.setStyleSheet(
            "border:1px dashed #c9d8e4; border-radius:10px; background:#fbfdff;"
            f" color:{MUTED};")
        self.mindmap_preview.setText("（思维导图预览，建议使用 PNG/JPG 格式）")
        mm_layout.addWidget(self.mindmap_preview, 1)
        body.addWidget(mm_group, 1)

        scroll.setWidget(widget)
        outer.addWidget(scroll)
        self.setLayout(outer)
        self._refresh_mindmap_ui()

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self._audio_path = path
            self.audio_lbl.setText(os.path.basename(path))

    def clear_audio(self):
        self._audio_path = None
        self.audio_lbl.setText("未选择音频")

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
        self.pkg.partC_secA["audio_source_type"] = self.src_combo.currentData() or "tts"
        self.pkg.partC_secA["tts_text"] = self.tts_edit.toPlainText()
        self.pkg.partC_secA["audio_path"] = self._audio_path
        self.pkg.partC_secA["key_points"] = self.key_points_edit.toPlainText()
        self.pkg.partC_secA["hidden_answer_points"] = self.hidden_points_edit.toPlainText()
        self.pkg.partC_secA["mindmap_image"] = self._mindmap_path

    def refresh(self):
        secA = self.pkg.partC_secA
        self._audio_path = secA.get("audio_path")
        self.src_combo.setCurrentIndex(1 if secA.get("audio_source_type") == "audio" else 0)
        self.audio_lbl.setText(file_name(secA.get("audio_path")))
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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 10, 4, 4)
        outer.setSpacing(12)

        situ_group = QGroupBox("情境描述")
        sv = QVBoxLayout(situ_group)
        sv.setContentsMargins(14, 18, 14, 12)
        self.situation_edit = QTextEdit()
        self.situation_edit.setPlaceholderText("情境描述（如：你希望了解更多关于活动的情况）")
        self.situation_edit.setMinimumHeight(90)
        sv.addWidget(self.situation_edit)
        outer.addWidget(situ_group)

        self.q_widgets = []
        for i in range(2):
            grp = QGroupBox(f"询问 {i + 1}")
            inner = QFormLayout(grp)
            inner.setContentsMargins(14, 16, 14, 10)
            inner.setSpacing(8)
            cn_edit = QLineEdit(); cn_edit.setPlaceholderText("中文提示（如：询问活动开始时间）")
            hid_edit = QLineEdit(); hid_edit.setPlaceholderText("标准提问（英文，隐藏）")
            inner.addRow("中文提示：", cn_edit)
            inner.addRow("标准提问：", hid_edit)
            outer.addWidget(grp)
            self.q_widgets.append((cn_edit, hid_edit))

        outer.addStretch(1)
        self.setLayout(outer)

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
