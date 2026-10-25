# -*- coding: utf-8 -*-
"""编辑模式主页面：顶部信息卡（名称/作者/分制/操作）+ 三个 Part 页签。"""

import os
import json
import zipfile
import tempfile

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ...config import DEFAULT_SCHEME, SCORE_SCHEMES
from ...models import SoloPackage
from ..theme import (ACCENT_DEEP, BG_BOT, BG_TOP, BD, FluentSelect, ICON_EDITOR,
                     ICON_OK, ICON_WARN, SUB, TEXT, bind_font, notify, svg_pixmap)
from .part_a import PartAEditor
from .part_b import PartBEditor
from .part_c import PartCEditor


class EditorPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.pkg = self.main.current_package
        self.setup_ui()

    def setup_ui(self):
        self.setObjectName("editorRoot")
        self.setStyleSheet(
            f"#editorRoot {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 {BG_TOP}, stop:1 {BG_BOT}); }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        # ---------- 顶部信息卡 ----------
        bar = QFrame()
        bar.setObjectName("editorBar")
        bar.setStyleSheet(
            f"#editorBar {{ background:#FFFFFF; border:1px solid {BD}; border-radius:14px; }}")
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        ic = QLabel()
        ic.setFixedSize(34, 34)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(svg_pixmap(ICON_EDITOR, ACCENT_DEEP, 24))
        ic.setStyleSheet("background:#E8F6FF; border-radius:17px;")
        title_row.addWidget(ic)
        t = QLabel("编辑模式")
        bind_font(t, 16, medium=True)
        t.setStyleSheet(f"color:{TEXT};")
        title_row.addWidget(t)
        title_row.addStretch(1)
        btn_new = self._btn("新建", self.new_package)
        btn_open = self._btn("打开 .solo", self.open_package)
        btn_save = self._primary("保存", self.save_package)
        btn_back = self._btn("返回主页", lambda: self.main.go_to(self.main.home_page))
        title_row.addWidget(btn_new)
        title_row.addWidget(btn_open)
        title_row.addWidget(btn_save)
        title_row.addWidget(btn_back)
        outer.addLayout(title_row)

        fields = QHBoxLayout()
        fields.setSpacing(10)
        self.name_edit = QLineEdit(self.pkg.meta.get("name", ""))
        self.name_edit.setPlaceholderText("题目包名称")
        self.name_edit.setMinimumWidth(180)
        self.author_edit = QLineEdit(self.pkg.meta.get("author", ""))
        self.author_edit.setPlaceholderText("题目作者（可选）")
        self.author_edit.setMinimumWidth(150)
        self.anonymous_check = QCheckBox("匿名")
        self.anonymous_check.setChecked(self.pkg.meta.get("anonymous", False))

        self.scheme_combo = FluentSelect(min_width=150)
        for key, sc in SCORE_SCHEMES.items():
            self.scheme_combo.addItem(sc["name"], key)
        _cur = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
        for i, (key, _sc) in enumerate(SCORE_SCHEMES.items()):
            if key == _cur:
                self.scheme_combo.setCurrentIndex(i)
                break

        for text, widget in (("名称", self.name_edit), ("作者", self.author_edit),
                             ("评分分制", self.scheme_combo)):
            lb = QLabel(text)
            bind_font(lb, 13)
            lb.setStyleSheet(f"color:{SUB};")
            fields.addWidget(lb)
            fields.addWidget(widget, 1 if widget is not self.scheme_combo else 0)
            if widget is self.author_edit:
                fields.addWidget(self.anonymous_check)
        fields.addStretch(1)
        outer.addLayout(fields)
        layout.addWidget(bar)

        # ---------- 页签 ----------
        self.tabs = QTabWidget()
        self.partA_widget = PartAEditor(self.pkg)
        self.partB_widget = PartBEditor(self.pkg)
        self.partC_widget = PartCEditor(self.pkg)
        self.tabs.addTab(self.partA_widget, "Part A 模仿朗读")
        self.tabs.addTab(self.partB_widget, "Part B 信息获取")
        self.tabs.addTab(self.partC_widget, "Part C 信息转述及询问")
        layout.addWidget(self.tabs, 1)

    def _btn(self, text, slot):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(34)
        bind_font(b, 13)
        b.setStyleSheet(
            f"QPushButton {{ background:#FFFFFF; border:1px solid {BD};"
            f" border-radius:8px; padding:0 16px; color:{SUB}; }}"
            f"QPushButton:hover {{ background:#F4F9FD; color:{TEXT}; }}")
        b.clicked.connect(slot)
        return b

    def _primary(self, text, slot):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(34)
        bind_font(b, 13, medium=True)
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT_DEEP}; border:none; border-radius:8px;"
            f" padding:0 18px; color:#FFFFFF; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#66CCFF; }}")
        b.clicked.connect(slot)
        return b

    def new_package(self):
        self.main.current_package = SoloPackage()
        self.pkg = self.main.current_package
        self.name_edit.setText("")
        self.author_edit.setText("")
        self.anonymous_check.setChecked(False)
        self.scheme_combo.setCurrentIndex(
            max(0, self.scheme_combo.findData(DEFAULT_SCHEME)))
        self.partA_widget.pkg = self.pkg
        self.partB_widget.set_package(self.pkg)
        self.partC_widget.set_package(self.pkg)
        self.partA_widget.refresh()
        self.partB_widget.refresh()
        self.partC_widget.refresh()

    def open_package(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if path:
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    with zf.open('data.json') as f:
                        data = json.load(f)
                    temp_dir = tempfile.mkdtemp(prefix="solotalk_")
                    zf.extractall(temp_dir)
                    self.pkg.from_dict(data, base_dir=temp_dir)
                    self.pkg.meta['temp_dir'] = temp_dir
                self.name_edit.setText(self.pkg.meta.get("name", ""))
                self.author_edit.setText(self.pkg.meta.get("author", ""))
                self.anonymous_check.setChecked(self.pkg.meta.get("anonymous", False))
                _s = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
                for i, key in enumerate(SCORE_SCHEMES.keys()):
                    if key == _s:
                        self.scheme_combo.setCurrentIndex(i)
                        break
                # 保证所有子编辑器都指向同一个（已载入数据的）题目包对象
                self.partA_widget.pkg = self.pkg
                self.partB_widget.set_package(self.pkg)
                self.partC_widget.set_package(self.pkg)
                self.partA_widget.refresh()
                self.partB_widget.refresh()
                self.partC_widget.refresh()
            except Exception as e:
                notify(self, "打开失败", f"无法打开题目包：{e}", icon=ICON_WARN)

    def save_package(self):
        """把界面内容写回 pkg 并打包成 .solo（zip：data.json + 音频 + 思维导图）。"""
        path, _ = QFileDialog.getSaveFileName(self, "保存 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if not path:
            return
        self.pkg.meta["name"] = self.name_edit.text() or "Untitled"
        self.pkg.meta["author"] = ("匿名" if self.anonymous_check.isChecked()
                                   else self.author_edit.text())
        self.pkg.meta["anonymous"] = self.anonymous_check.isChecked()
        self.pkg.meta["scheme"] = self.scheme_combo.currentData() or DEFAULT_SCHEME
        self.partA_widget.save_to_pkg()
        self.partB_widget.save_to_pkg()
        self.partC_widget.save_to_pkg()
        try:
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('data.json', json.dumps(self.pkg.to_dict(), indent=2, ensure_ascii=False))

                def _add(p, bucket, seen):
                    if p and os.path.exists(p) and p not in seen:
                        seen.add(p)
                        bucket.append(p)

                audio_files, seen = [], set()
                _add(self.pkg.partA_audio_path, audio_files, seen)
                for seg in self.pkg.partB_secA:
                    _add(seg.get("audio_path"), audio_files, seen)
                _add(self.pkg.partB_secB.get("audio_path"), audio_files, seen)
                _add(self.pkg.partC_secA.get("audio_path"), audio_files, seen)
                for ap in audio_files:
                    zf.write(ap, os.path.basename(ap))
                mm = self.pkg.partC_secA.get("mindmap_image")
                if mm and os.path.exists(mm):
                    zf.write(mm, os.path.basename(mm))
            notify(self, "保存成功", f"题目包已保存至：{path}", icon=ICON_OK)
        except Exception as e:
            notify(self, "保存失败", str(e), icon=ICON_WARN)
