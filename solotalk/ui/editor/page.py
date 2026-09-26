# -*- coding: utf-8 -*-
"""编辑模式主页面：工具栏（名称/作者/分制/新建/打开/保存）+ 三个 Part 页签。"""

import os
import json
import zipfile
import tempfile

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ...config import DEFAULT_SCHEME, SCORE_SCHEMES
from ...models import SoloPackage
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
        layout = QVBoxLayout()
        top_bar = QHBoxLayout()
        self.name_edit = QLineEdit(self.pkg.meta.get("name", ""))
        self.name_edit.setPlaceholderText("题目包名称")
        self.author_edit = QLineEdit(self.pkg.meta.get("author", ""))
        self.author_edit.setPlaceholderText("题目作者（可选）")
        self.anonymous_check = QCheckBox("匿名")
        self.anonymous_check.setChecked(self.pkg.meta.get("anonymous", False))

        # 分制选择（随包保存）
        self.scheme_combo = QComboBox()
        for key, sc in SCORE_SCHEMES.items():
            self.scheme_combo.addItem(sc["name"], key)
        _cur = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
        _idx = self.scheme_combo.findData(_cur)
        if _idx >= 0:
            self.scheme_combo.setCurrentIndex(_idx)
        self.scheme_combo.setMinimumWidth(180)

        btn_new = QPushButton("新建")
        btn_open = QPushButton("打开 .solo")
        btn_save = QPushButton("保存")
        btn_back = QPushButton("返回主页")
        top_bar.addWidget(QLabel("名称："))
        top_bar.addWidget(self.name_edit)
        top_bar.addWidget(QLabel("作者："))
        top_bar.addWidget(self.author_edit)
        top_bar.addWidget(self.anonymous_check)
        top_bar.addWidget(QLabel("评分分制："))
        top_bar.addWidget(self.scheme_combo)
        top_bar.addWidget(btn_new)
        top_bar.addWidget(btn_open)
        top_bar.addWidget(btn_save)
        top_bar.addStretch()
        top_bar.addWidget(btn_back)
        btn_new.clicked.connect(self.new_package)
        btn_open.clicked.connect(self.open_package)
        btn_save.clicked.connect(self.save_package)
        btn_back.clicked.connect(lambda: self.main.go_to(self.main.home_page))
        layout.addLayout(top_bar)

        self.tabs = QTabWidget()
        self.partA_widget = PartAEditor(self.pkg)
        self.partB_widget = PartBEditor(self.pkg)
        self.partC_widget = PartCEditor(self.pkg)
        self.tabs.addTab(self.partA_widget, "Part A 模仿朗读")
        self.tabs.addTab(self.partB_widget, "Part B 信息获取")
        self.tabs.addTab(self.partC_widget, "Part C 信息转述及询问")
        layout.addWidget(self.tabs)
        self.setLayout(layout)

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
                _i = self.scheme_combo.findData(_s)
                if _i >= 0:
                    self.scheme_combo.setCurrentIndex(_i)
                # 保证所有子编辑器都指向同一个（已载入数据的）题目包对象
                self.partA_widget.pkg = self.pkg
                self.partB_widget.set_package(self.pkg)
                self.partC_widget.set_package(self.pkg)
                self.partA_widget.refresh()
                self.partB_widget.refresh()
                self.partC_widget.refresh()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"打开失败：{str(e)}")

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
            QMessageBox.information(self, "成功", f"题目包已保存至 {path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
