# -*- coding: utf-8 -*-
"""Part B 信息获取编辑器：Section A 听选信息 / Section B 回答问题。"""

import os

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..theme import SUB, bind_font
from .widgets import audio_picker, file_name, source_select


class PartBEditor(QWidget):
    """Part B 容器，仅组合两个 Section 编辑器。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 10, 4, 4)
        tabs = QTabWidget()
        self.secA_widget = PartBSecAEditor(self.pkg)
        self.secB_widget = PartBSecBEditor(self.pkg)
        tabs.addTab(self.secA_widget, "Section A 听选信息")
        tabs.addTab(self.secB_widget, "Section B 回答问题")
        main_layout.addWidget(tabs)
        self.setLayout(main_layout)

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


class PartBSecAEditor(QWidget):
    """听选信息：3 段对话，每段 2 题（含三选一提示与隐藏正确答案）。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.segment_widgets = []
        self.segment_audio_paths = [None, None, None]
        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        widget = QWidget()
        widget.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 10)
        layout.setSpacing(12)

        for seg_idx in range(3):
            grp = QGroupBox(f"对话 / 独白 {seg_idx + 1}")
            seg_layout = QVBoxLayout(grp)
            seg_layout.setContentsMargins(14, 18, 14, 12)
            seg_layout.setSpacing(9)

            src_row = QHBoxLayout()
            src_row.setSpacing(10)
            src_lb = QLabel("音频来源")
            bind_font(src_lb, 13)
            src_lb.setStyleSheet(f"color:{SUB};")
            src_row.addWidget(src_lb)
            src_combo = source_select()
            src_row.addWidget(src_combo)
            src_row.addStretch(1)
            seg_layout.addLayout(src_row)

            tts_edit = QTextEdit()
            tts_edit.setMinimumHeight(96)
            tts_edit.setPlaceholderText(
                "听力原文（TTS朗读）。双角色对话请每行一个角色：\n"
                "W: 女声台词\n"
                "M: 男声台词\n"
                "标记只用于区分音色，不会被朗读。")
            seg_layout.addWidget(tts_edit)

            a_row, a_label, a_choose, a_clear = audio_picker()
            a_choose.clicked.connect(
                lambda _=False, i=seg_idx: self._choose_audio(i))
            a_clear.clicked.connect(
                lambda _=False, i=seg_idx: self._clear_audio(i))
            seg_layout.addWidget(a_row)

            q_widgets = []
            for q_idx in range(2):
                q_grp = QGroupBox(f"问题 {q_idx + 1}")
                q_layout = QFormLayout(q_grp)
                q_layout.setContentsMargins(14, 16, 14, 10)
                q_layout.setSpacing(8)
                q_edit = QLineEdit(); q_edit.setPlaceholderText("英文问题")
                optA = QLineEdit(); optA.setPlaceholderText("A. ...")
                optB = QLineEdit(); optB.setPlaceholderText("B. ...")
                optC = QLineEdit(); optC.setPlaceholderText("C. ...")
                correct_edit = QLineEdit(); correct_edit.setPlaceholderText("正确答案文本（隐藏）")
                q_layout.addRow("问题：", q_edit)
                q_layout.addRow("选项A：", optA)
                q_layout.addRow("选项B：", optB)
                q_layout.addRow("选项C：", optC)
                q_layout.addRow("正确答案：", correct_edit)
                seg_layout.addWidget(q_grp)
                q_widgets.append({"q_edit": q_edit, "optA": optA, "optB": optB,
                                  "optC": optC, "correct_edit": correct_edit})
            layout.addWidget(grp)
            self.segment_widgets.append({
                "src_combo": src_combo, "tts_edit": tts_edit,
                "audio_row": a_row, "audio_lbl": a_label, "q_widgets": q_widgets,
            })

        layout.addStretch(1)
        scroll.setWidget(widget)
        outer.addWidget(scroll)
        self.setLayout(outer)

    def _choose_audio(self, seg_idx):
        path, _ = QFileDialog.getOpenFileName(self, f"选择对话{seg_idx + 1}音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self.segment_audio_paths[seg_idx] = path
            self.segment_widgets[seg_idx]["audio_lbl"].setText(os.path.basename(path))

    def _clear_audio(self, seg_idx):
        self.segment_audio_paths[seg_idx] = None
        self.segment_widgets[seg_idx]["audio_lbl"].setText("未选择音频")

    def save_to_pkg(self):
        self.pkg.partB_secA = []
        for seg_idx, w in enumerate(self.segment_widgets):
            seg = {
                "audio_source_type": w["src_combo"].currentData() or "tts",
                "tts_text": w["tts_edit"].toPlainText(),
                "audio_path": self.segment_audio_paths[seg_idx],
                "questions": [],
            }
            for qw in w["q_widgets"]:
                seg["questions"].append({
                    "question_text": qw["q_edit"].text(),
                    "options": [qw["optA"].text(), qw["optB"].text(), qw["optC"].text()],
                    "correct_option_text": qw["correct_edit"].text(),
                })
            self.pkg.partB_secA.append(seg)

    def refresh(self):
        while len(self.pkg.partB_secA) < 3:
            self.pkg.partB_secA.append({
                "audio_source_type": "tts", "tts_text": "", "audio_path": None,
                "questions": [{"question_text": "", "options": ["", "", ""],
                               "correct_option_text": ""} for _ in range(2)]
            })
        for seg_idx, w in enumerate(self.segment_widgets):
            seg = self.pkg.partB_secA[seg_idx]
            self.segment_audio_paths[seg_idx] = seg.get("audio_path")
            w["src_combo"].setCurrentIndex(1 if seg.get("audio_source_type") == "audio" else 0)
            w["audio_lbl"].setText(file_name(seg.get("audio_path")))
            w["tts_edit"].setPlainText(seg.get("tts_text", ""))
            for q_idx, qw in enumerate(w["q_widgets"]):
                if q_idx < len(seg.get("questions", [])):
                    q = seg["questions"][q_idx]
                    qw["q_edit"].setText(q.get("question_text", ""))
                    opts = q.get("options", ["", "", ""])
                    qw["optA"].setText(opts[0] if len(opts) > 0 else "")
                    qw["optB"].setText(opts[1] if len(opts) > 1 else "")
                    qw["optC"].setText(opts[2] if len(opts) > 2 else "")
                    qw["correct_edit"].setText(q.get("correct_option_text", ""))
                else:
                    qw["q_edit"].clear()
                    qw["optA"].clear(); qw["optB"].clear(); qw["optC"].clear()
                    qw["correct_edit"].clear()


class PartBSecBEditor(QWidget):
    """回答问题：1 段独白 + 4 个问题（隐藏标准答案）。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self._audio_path = None
        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        widget = QWidget()
        widget.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 10)
        layout.setSpacing(12)

        audio_group = QGroupBox("独白音频")
        av = QVBoxLayout(audio_group)
        av.setContentsMargins(14, 18, 14, 12)
        av.setSpacing(9)

        src_row = QHBoxLayout()
        src_row.setSpacing(10)
        src_lb = QLabel("音频来源")
        bind_font(src_lb, 13)
        src_lb.setStyleSheet(f"color:{SUB};")
        src_row.addWidget(src_lb)
        self.src_combo = source_select()
        src_row.addWidget(self.src_combo)
        src_row.addStretch(1)
        av.addLayout(src_row)

        self.tts_edit = QTextEdit()
        self.tts_edit.setMinimumHeight(110)
        self.tts_edit.setPlaceholderText("独白文本（TTS朗读）")
        av.addWidget(self.tts_edit)

        self.audio_row, self.audio_lbl, btn_choose, btn_clear = audio_picker()
        btn_choose.clicked.connect(self.upload_audio)
        btn_clear.clicked.connect(self.clear_audio)
        av.addWidget(self.audio_row)
        layout.addWidget(audio_group)

        self.q_widgets = []
        for i in range(4):
            grp = QGroupBox(f"问题 {i + 1}")
            inner = QFormLayout(grp)
            inner.setContentsMargins(14, 16, 14, 10)
            inner.setSpacing(8)
            q_edit = QLineEdit(); q_edit.setPlaceholderText("英文问题")
            hid_edit = QLineEdit(); hid_edit.setPlaceholderText("标准答案（隐藏）")
            inner.addRow("问题：", q_edit)
            inner.addRow("答案：", hid_edit)
            layout.addWidget(grp)
            self.q_widgets.append((q_edit, hid_edit))

        layout.addStretch(1)
        scroll.setWidget(widget)
        outer.addWidget(scroll)
        self.setLayout(outer)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择独白音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self._audio_path = path
            self.audio_lbl.setText(os.path.basename(path))

    def clear_audio(self):
        self._audio_path = None
        self.audio_lbl.setText("未选择音频")

    def save_to_pkg(self):
        self.pkg.partB_secB["audio_source_type"] = self.src_combo.currentData() or "tts"
        self.pkg.partB_secB["tts_text"] = self.tts_edit.toPlainText()
        self.pkg.partB_secB["audio_path"] = self._audio_path
        self.pkg.partB_secB["questions"] = []
        for q_edit, hid_edit in self.q_widgets:
            self.pkg.partB_secB["questions"].append({
                "question_text": q_edit.text(),
                "hidden_answer": hid_edit.text(),
            })

    def refresh(self):
        secB = self.pkg.partB_secB
        self._audio_path = secB.get("audio_path")
        self.src_combo.setCurrentIndex(1 if secB.get("audio_source_type") == "audio" else 0)
        self.audio_lbl.setText(file_name(secB.get("audio_path")))
        self.tts_edit.setPlainText(secB.get("tts_text", ""))
        questions = secB.get("questions", [])
        for i, (q_edit, hid_edit) in enumerate(self.q_widgets):
            if i < len(questions):
                q_edit.setText(questions[i].get("question_text", ""))
                hid_edit.setText(questions[i].get("hidden_answer", ""))
            else:
                q_edit.clear(); hid_edit.clear()
