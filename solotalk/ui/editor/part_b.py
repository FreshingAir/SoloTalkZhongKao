# -*- coding: utf-8 -*-
"""Part B 信息获取编辑器：Section A 听选信息 / Section B 回答问题。"""

import os

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *


class PartBEditor(QWidget):
    """Part B 容器，仅组合两个 Section 编辑器。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout()
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

    def _make_audio_row(self):
        label = QLabel("未选择音频")
        label.setStyleSheet("color:#666;")
        btn_choose = QPushButton("选择音频")
        btn_clear = QPushButton("清除")
        row = QHBoxLayout()
        row.addWidget(label)
        row.addWidget(btn_choose)
        row.addWidget(btn_clear)
        return row, label, btn_choose, btn_clear

    def setup_ui(self):
        scroll = QScrollArea()
        widget = QWidget()
        layout = QVBoxLayout()
        self.segment_widgets = []
        for seg_idx in range(3):
            grp = QGroupBox(f"对话/独白 {seg_idx + 1}")
            seg_layout = QVBoxLayout()
            src_combo = QComboBox()
            src_combo.addItems(["💻电脑 TTS", "上传音频"])
            tts_edit = QTextEdit()
            tts_edit.setPlaceholderText("听力原文（TTS朗读）")
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel("音频来源："))
            hbox.addWidget(src_combo)
            seg_layout.addLayout(hbox)
            seg_layout.addWidget(tts_edit)

            a_row, a_label, a_btn, a_clear = self._make_audio_row()
            a_btn.clicked.connect(lambda _, i=seg_idx, lb=a_label: self._choose_audio(i, lb))
            a_clear.clicked.connect(lambda _, i=seg_idx, lb=a_label: self._clear_audio(i, lb))
            seg_layout.addLayout(a_row)

            q_widgets = []
            for q_idx in range(2):
                q_grp = QGroupBox(f"问题{q_idx + 1}")
                q_layout = QFormLayout()
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
                q_grp.setLayout(q_layout)
                seg_layout.addWidget(q_grp)
                q_widgets.append({"q_edit": q_edit, "optA": optA, "optB": optB,
                                  "optC": optC, "correct_edit": correct_edit})
            grp.setLayout(seg_layout)
            layout.addWidget(grp)
            self.segment_widgets.append({
                "src_combo": src_combo, "tts_edit": tts_edit,
                "audio_lbl": a_label, "q_widgets": q_widgets,
            })
        widget.setLayout(layout)
        scroll.setWidget(widget)
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def _choose_audio(self, seg_idx, label):
        path, _ = QFileDialog.getOpenFileName(self, f"选择对话{seg_idx + 1}音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self.segment_audio_paths[seg_idx] = path
            label.setText(os.path.basename(path))

    def _clear_audio(self, seg_idx, label):
        self.segment_audio_paths[seg_idx] = None
        label.setText("未选择音频")

    def save_to_pkg(self):
        self.pkg.partB_secA = []
        for seg_idx, w in enumerate(self.segment_widgets):
            seg = {
                "audio_source_type": "tts" if w["src_combo"].currentIndex() == 0 else "audio",
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
            w["audio_lbl"].setText(os.path.basename(seg["audio_path"])
                                   if seg.get("audio_path") else "未选择音频")
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
        layout = QFormLayout()
        self.src_combo = QComboBox()
        self.src_combo.addItems(["💻电脑 TTS", "上传音频"])
        layout.addRow("独白音频来源：", self.src_combo)
        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("独白文本（TTS朗读）")
        layout.addRow("独白文本：", self.tts_edit)
        self.audio_lbl = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        hbox = QHBoxLayout()
        hbox.addWidget(self.audio_lbl)
        hbox.addWidget(self.audio_btn)
        layout.addRow("音频文件：", hbox)

        self.q_widgets = []
        for i in range(4):
            grp = QGroupBox(f"问题{i + 1}")
            inner = QFormLayout()
            q_edit = QLineEdit(); q_edit.setPlaceholderText("英文问题")
            hid_edit = QLineEdit(); hid_edit.setPlaceholderText("标准答案（隐藏）")
            inner.addRow("问题：", q_edit)
            inner.addRow("答案：", hid_edit)
            grp.setLayout(inner)
            layout.addRow(grp)
            self.q_widgets.append((q_edit, hid_edit))
        self.setLayout(layout)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择独白音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self._audio_path = path
            self.audio_lbl.setText(os.path.basename(path))

    def save_to_pkg(self):
        self.pkg.partB_secB["audio_source_type"] = "tts" if self.src_combo.currentIndex() == 0 else "audio"
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
        self.audio_lbl.setText(os.path.basename(secB["audio_path"]) if secB.get("audio_path") else "未选择音频")
        self.tts_edit.setPlainText(secB.get("tts_text", ""))
        questions = secB.get("questions", [])
        for i, (q_edit, hid_edit) in enumerate(self.q_widgets):
            if i < len(questions):
                q_edit.setText(questions[i].get("question_text", ""))
                hid_edit.setText(questions[i].get("hidden_answer", ""))
            else:
                q_edit.clear(); hid_edit.clear()
