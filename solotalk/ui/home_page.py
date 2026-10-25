# -*- coding: utf-8 -*-
"""首页：2×2 磁贴卡入口（练习 / 模考 / 编辑 / 历史）+ 更多入口，并负责加载 .solo 后进入练习/模考。"""

import json
import zipfile
import tempfile

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..config import APP_VERSION
from .theme import (ACCENT, ACCENT_DEEP, ACCENT_SOFT, BD, BG_BOT, BG_TOP, CARD,
                    TEXT, FluentMessageDialog, ICON_EDITOR, ICON_EXAM, ICON_HISTORY,
                    ICON_PRACTICE, ICON_WARN, bind_font, svg_pixmap)

TEXT_SUB = "#7A8A9A"


class HomePage(QWidget):
    """SecRandom 风格首页：天蓝渐变底 + 2×2 宽磁贴卡 + 单色线性图标。"""

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.setObjectName("homeRoot")
        self.setStyleSheet(
            f"#homeRoot {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 {BG_TOP}, stop:1 {BG_BOT}); }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 24)
        root.setSpacing(0)
        root.addStretch(1)

        center = QVBoxLayout()
        center.setSpacing(0)

        title = QLabel("SoloTalk")
        title.setAlignment(Qt.AlignCenter)
        bind_font(title, 40, medium=True)
        title.setStyleSheet(f"color:{TEXT}; background:transparent;")
        subtitle = QLabel("单机版英语听说模考编辑器 · 完全免费")
        subtitle.setAlignment(Qt.AlignCenter)
        bind_font(subtitle, 14)
        subtitle.setStyleSheet(f"color:{TEXT_SUB}; background:transparent;")
        center.addWidget(title)
        center.addWidget(subtitle)
        center.addSpacing(28)

        grid = QGridLayout()
        grid.setSpacing(16)
        tile_practice = self._tile(ICON_PRACTICE, "练习模式", "可跳过 / 上一步，试音也能跳过")
        tile_practice.clicked.connect(lambda: self.load_and_start("practice"))
        tile_exam = self._tile(ICON_EXAM, "模考模式", "不可跳过 / 上一步，试音不能跳过")
        tile_exam.clicked.connect(lambda: self.load_and_start("exam"))
        tile_editor = self._tile(ICON_EDITOR, "编辑模式", "制作与导入题目包（.solo）")
        tile_editor.clicked.connect(lambda: self.main.go_to(self.main.editor_page))
        tile_history = self._tile(ICON_HISTORY, "历史记录", "查看往次成绩与录音回放")
        tile_history.clicked.connect(lambda: self.main.go_to(self.main.history_page))
        grid.addWidget(tile_practice, 0, 0)
        grid.addWidget(tile_exam, 0, 1)
        grid.addWidget(tile_editor, 1, 0)
        grid.addWidget(tile_history, 1, 1)

        grid_row = QHBoxLayout()
        grid_row.addStretch(1)
        grid_row.addLayout(grid)
        grid_row.addStretch(1)
        center.addLayout(grid_row)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addLayout(center)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)

        bottom = QHBoxLayout()
        btn_more = QPushButton("更多")
        btn_more.setCursor(Qt.PointingHandCursor)
        btn_more.setToolTip("关于 / 更新 / 意见反馈 / 使用须知")
        bind_font(btn_more, 13)
        btn_more.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; border-radius:6px;"
            f" padding:8px 12px; color:{ACCENT_DEEP}; }}"
            f"QPushButton:hover {{ background:{ACCENT_SOFT}; }}"
        )
        btn_more.clicked.connect(lambda: self.main.go_to(self.main.more_page))
        bottom.addWidget(btn_more)
        bottom.addStretch(1)
        ver = QLabel(f"v{APP_VERSION}")
        bind_font(ver, 12)
        ver.setStyleSheet(f"color:{TEXT_SUB};")
        bottom.addWidget(ver)
        root.addLayout(bottom)

    @classmethod
    def _tile(cls, paths, name, desc):
        """一张磁贴按钮（圆形图标 + 标题 + 说明）。"""
        b = QPushButton()
        b.setObjectName("homeTile")
        b.setFixedSize(330, 104)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(
            f"#homeTile {{ background:{CARD}; border:1px solid {BD};"
            f" border-radius:14px; padding:0px; text-align:left; }}"
            f"#homeTile:hover {{ background:#FAFEFF; border:1px solid {ACCENT}; }}"
            f"#homeTile:pressed {{ background:{ACCENT_SOFT}; }}"
        )
        lay = QHBoxLayout(b)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(14)

        ic = QLabel()
        ic.setObjectName("homeIconBox")
        ic.setFixedSize(40, 40)
        ic.setAlignment(Qt.AlignCenter)
        ic.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        ic.setStyleSheet(
            f"#homeIconBox {{ background:{ACCENT_SOFT}; border-radius:20px; border:none; }}"
        )
        ic.setPixmap(svg_pixmap(paths, ACCENT_DEEP, 22))
        lay.addWidget(ic)

        txt = QVBoxLayout()
        txt.setSpacing(3)
        txt.addStretch(1)
        t = QLabel(name)
        bind_font(t, 16, medium=True)
        t.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        t.setStyleSheet(f"color:{TEXT}; background:transparent;")
        d = QLabel(desc)
        bind_font(d, 12)
        d.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        d.setStyleSheet(f"color:{TEXT_SUB}; background:transparent;")
        txt.addWidget(t)
        txt.addWidget(d)
        txt.addStretch(1)
        tw = QWidget()
        tw.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        tw.setLayout(txt)
        lay.addWidget(tw, 1)
        return b

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
            FluentMessageDialog(
                self, "加载失败", f"无法打开这个题目包：{str(e)}",
                icon=ICON_WARN, buttons=(("知道了", "primary", "ok"),)).exec_()
