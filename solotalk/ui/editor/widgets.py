# -*- coding: utf-8 -*-
"""编辑模式通用小组件：音频来源下拉、音频文件行、小按钮。"""

import os

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget
from PyQt5.QtCore import Qt

from ..theme import BD, FluentSelect, SUB, bind_font


def mini_button(text, slot=None):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(30)
    bind_font(b, 12)
    b.setStyleSheet(
        f"QPushButton {{ background:#FFFFFF; border:1px solid {BD}; border-radius:7px;"
        f" padding:0 14px; color:{SUB}; }}"
        f"QPushButton:hover {{ background:#F4F9FD; }}")
    if slot is not None:
        b.clicked.connect(slot)
    return b


def source_select(min_width=170):
    """音频来源下拉：data 为 "tts" / "audio"。"""
    sel = FluentSelect(min_width=min_width, height=34)
    sel.addItem("电脑 TTS", "tts")
    sel.addItem("上传音频", "audio")
    sel.setCurrentIndex(0)
    return sel


def audio_picker(initial="未选择音频"):
    """一行「文件名 + 选择音频 + 清除」，返回 (行控件, 文件名标签, 选择按钮, 清除按钮)。"""
    row = QWidget()
    row.setStyleSheet("background:transparent;")
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lbl = QLabel(initial)
    lbl.setStyleSheet(f"color:{SUB}; background:transparent;")
    lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    bind_font(lbl, 12)
    h.addWidget(lbl, 1)
    btn_choose = mini_button("选择音频")
    btn_clear = mini_button("清除")
    h.addWidget(btn_choose)
    h.addWidget(btn_clear)
    return row, lbl, btn_choose, btn_clear


def file_name(path, empty="未选择音频"):
    return os.path.basename(path) if path else empty
