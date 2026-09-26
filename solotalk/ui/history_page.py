# -*- coding: utf-8 -*-
"""历史记录页：列出 history/history_*.json，支持查看详情、重新批改、删除。"""

import os
import json
from pathlib import Path

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..asr import load_vosk_model
from ..config import DEFAULT_SCHEME, HISTORY_DIR
from ..evaluation import evaluate_recordings
from ..models import PracticeSession, SoloPackage
from ..scoring import compute_scores


class HistoryPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.view_detail)
        self.btn_reeval = QPushButton("重新批改选中记录")
        self.btn_reeval.clicked.connect(self.reevaluate_selected)
        self.btn_delete = QPushButton("删除选中记录")
        self.btn_delete.clicked.connect(self.delete_selected)
        btn_back = QPushButton("返回主页")
        btn_back.clicked.connect(lambda: self.main.go_to(self.main.home_page))
        layout.addWidget(QLabel("练习历史记录（双击查看详情）"))
        layout.addWidget(self.list_widget)
        layout.addWidget(self.btn_reeval)
        layout.addWidget(self.btn_delete)
        layout.addWidget(btn_back)
        self.setLayout(layout)

    def showEvent(self, event):
        self.load_history()
        super().showEvent(event)

    def load_history(self):
        self.list_widget.clear()
        if not os.path.exists(HISTORY_DIR):
            return
        files = sorted(Path(HISTORY_DIR).glob("history_*.json"), reverse=True)
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                sc = (data.get('evaluation') or {}).get('scores') or {}
                score_txt = (f"  [{sc.get('total', 0)}/{sc.get('total_max', 0)}]"
                             if sc else "")
                item_text = f"{data.get('package', '?')}  {data.get('timestamp', '')}{score_txt}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, str(f))
                self.list_widget.addItem(item)
            except Exception:
                pass

    def delete_selected(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        path = current_item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        reply = QMessageBox.question(self, "确认删除", "确定要删除该历史记录吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                os.remove(path)
                self.load_history()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败：{str(e)}")

    def reevaluate_selected(self):
        """用记录内保存的题目数据与录音重新跑一遍批改。"""
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        path = current_item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            QMessageBox.critical(self, "错误", "历史记录文件损坏")
            return
        recs = data.get('recordings', {})
        pkg_dict = data.get('package_data', {})
        temp_pkg = SoloPackage()
        temp_pkg.from_dict(pkg_dict)

        sess = PracticeSession(data.get('package', ''))
        sess.partA_recording = recs.get('partA')
        sess.partB_secA_recordings = recs.get('partB_secA', [])
        sess.partB_secB_recordings = recs.get('partB_secB', [])
        sess.partC_secA_recording = recs.get('partC_secA')
        sess.partC_secB_recordings = recs.get('partC_secB', [])

        vosk_model = load_vosk_model()
        if not vosk_model:
            QMessageBox.warning(self, "错误", "Vosk 模型不可用，无法重新批改")
            return
        scheme_key = data.get('scheme_key') or temp_pkg.meta.get('scheme', DEFAULT_SCHEME)
        data['evaluation'] = evaluate_recordings(sess, temp_pkg, vosk_model)
        data['evaluation']['scores'] = compute_scores(data['evaluation'], scheme_key)
        data['scheme_key'] = str(scheme_key)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        QMessageBox.information(self, "完成", "重新批改已完成")
        self.load_history()

    def view_detail(self, item):
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        detail = f"题目包：{data.get('package', '')}\n时间：{data.get('timestamp', '')}\n\n录音文件：\n"
        rec = data.get('recordings', {})
        detail += f"Part A: {rec.get('partA', '')}\n"
        for i, r in enumerate(rec.get('partB_secA', []) or []):
            detail += f"Part B SecA #{i + 1}: {r}\n"
        for i, r in enumerate(rec.get('partB_secB', []) or []):
            detail += f"Part B SecB #{i + 1}: {r}\n"
        detail += f"Part C SecA: {rec.get('partC_secA', '')}\n"
        for i, r in enumerate(rec.get('partC_secB', []) or []):
            detail += f"Part C SecB #{i + 1}: {r}\n\n批改结果：\n"

        ev = data.get('evaluation', {})
        sc = ev.get('scores')
        if sc:
            detail += (f"\n【总分】{sc.get('total', 0)} / "
                       f"{sc.get('total_max', 0)}"
                       f"  （{sc.get('scheme_name', '')}）\n")
            d = sc.get('detail', {})
            for k, label in [("partA", "Part A 模仿朗读"),
                             ("partB_secA", "Part B SecA 听选信息"),
                             ("partB_secB", "Part B SecB 回答问题"),
                             ("partC_secA", "Part C SecA 短文复述"),
                             ("partC_secB", "Part C SecB 提问")]:
                if k in d:
                    detail += (f"  {label}: {d[k].get('score', 0)} / "
                               f"{d[k].get('max', 0)}\n")
            detail += "\n"

        if 'partA' in ev:
            detail += (f"Part A 准确率: {ev['partA'].get('accuracy', 0) * 100:.1f}%  "
                       f"WER: {ev['partA'].get('wer', 0):.2f}\n")
        if 'partC_secA' in ev:
            detail += f"Part C 转述要点覆盖: {ev['partC_secA'].get('coverage', '')}\n"
        detail += "\n批改结果基于离线语音识别，仅供参考。"

        dlg = QDialog(self)
        dlg.setWindowTitle("练习详情")
        dlg.resize(720, 640)
        layout = QVBoxLayout(dlg)
        tb = QTextEdit()
        tb.setReadOnly(True)
        tb.setPlainText(detail)
        layout.addWidget(tb)

        mm_copy = data.get("mindmap_copy")
        if mm_copy and os.path.exists(mm_copy):
            mm_lbl = QLabel()
            mm_lbl.setAlignment(Qt.AlignCenter)
            pix = QPixmap(mm_copy)
            if not pix.isNull():
                mm_lbl.setPixmap(pix.scaled(640, 260, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))
                layout.addWidget(QLabel("思维导图："))
                layout.addWidget(mm_lbl)

        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()
