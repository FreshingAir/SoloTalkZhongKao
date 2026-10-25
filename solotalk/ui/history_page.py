# -*- coding: utf-8 -*-
"""历史记录页：列表（标题 / 总分 / 分制 / 时间）、详情弹窗、重新批改、删除。"""

import os
import json
from pathlib import Path

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..asr import load_vosk_model
from ..config import DEFAULT_SCHEME, HISTORY_DIR, get_scheme
from ..evaluation import evaluate_recordings
from ..models import PracticeSession, SoloPackage
from ..scoring import compute_scores
from .theme import (ACCENT, ACCENT_DEEP, ACCENT_SOFT, BG_BOT, BG_TOP, BD, CARD,
                    DIV, ICON_CHART, ICON_WARN, LINE, MUTED, SUB, TEXT, ask, bind_font,
                    card, hline, label, notify, panel, score_color, score_row,
                    secondary_button, svg_pixmap)


class _HistRow(QTreeWidgetItem):
    """历史列表行：让「总分」列按数值排序。"""

    SCORE_ROLE = Qt.UserRole + 1

    def __lt__(self, other):
        tw = self.treeWidget()
        if tw is not None and tw.sortColumn() == 1:
            a = self.data(1, self.SCORE_ROLE)
            b = other.data(1, self.SCORE_ROLE)
            try:
                return float(a) < float(b)
            except (TypeError, ValueError):
                return str(a) < str(b)
        return QTreeWidgetItem.__lt__(self, other)


class HistoryPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.setObjectName("hsRoot")
        self.setStyleSheet(
            f"#hsRoot {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 {BG_TOP}, stop:1 {BG_BOT}); }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(12)

        title = QLabel("练习历史记录")
        bind_font(title, 20, medium=True)
        title.setStyleSheet(f"color:{TEXT}; background:transparent;")
        sub = QLabel("双击查看详情 · 选中后可重新批改或删除")
        bind_font(sub, 12)
        sub.setStyleSheet(f"color:{SUB}; background:transparent;")
        root.addWidget(title)
        root.addWidget(sub)

        card_frame = QFrame()
        card_frame.setObjectName("hsCard")
        card_frame.setStyleSheet(
            f"#hsCard {{ background:{CARD}; border:1px solid {BD}; border-radius:14px; }}")
        cv = QVBoxLayout(card_frame)
        cv.setContentsMargins(4, 2, 4, 4)
        cv.setSpacing(0)

        self.list_widget = QTreeWidget()
        self.list_widget.setObjectName("hsTree")
        self.list_widget.setColumnCount(4)
        self.list_widget.setHeaderLabels(["标题", "总分", "分制", "时间"])
        self.list_widget.setRootIsDecorated(False)
        self.list_widget.setUniformRowHeights(True)
        self.list_widget.setAllColumnsShowFocus(True)
        self.list_widget.setIndentation(0)
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.itemDoubleClicked.connect(lambda it, _c: self.view_detail(it))
        bind_font(self.list_widget, 14)

        hh = self.list_widget.header()
        hh.setSectionsMovable(False)
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        hh.resizeSection(1, 96)
        hh.resizeSection(2, 120)
        hh.resizeSection(3, 178)
        hh.setMinimumSectionSize(56)
        self.list_widget.headerItem().setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        self.list_widget.headerItem().setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)

        self.list_widget.setStyleSheet(f"""
            #hsTree {{ background:transparent; border:none; outline:none; }}
            #hsTree::item {{ height:44px; padding-left:8px; border:none; }}
            #hsTree::item:hover {{ background:#F2F8FD; }}
            #hsTree::item:selected {{ background:{ACCENT_SOFT}; color:{TEXT}; }}
            #hsTree QHeaderView {{ background:transparent; }}
            QHeaderView::section {{
                background:{CARD}; border:none;
                border-bottom:1px solid {LINE};
                border-right:1px solid {DIV};
                padding:6px 20px 6px 8px; font-size:12px; color:{SUB};
            }}
            QHeaderView::section:last {{ border-right:none; }}
        """)
        cv.addWidget(self.list_widget)
        root.addWidget(card_frame, 1)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addWidget(secondary_button("重新批改选中记录", self.reevaluate_selected))
        btns.addWidget(secondary_button("删除选中记录", self.delete_selected, danger=True))
        btns.addStretch(1)
        btns.addWidget(secondary_button(
            "返回主页", lambda: self.main.go_to(self.main.home_page)))
        root.addLayout(btns)

    def showEvent(self, event):
        self.load_history()
        super().showEvent(event)

    # ---------- 列表 ----------
    def load_history(self):
        self.list_widget.clear()
        if not os.path.exists(HISTORY_DIR):
            self.list_widget.addTopLevelItem(self._empty_row())
            return
        files = sorted(Path(HISTORY_DIR).glob("history_*.json"), reverse=True)
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                sc = (data.get('evaluation') or {}).get('scores') or {}
                scheme_name = sc.get('scheme_name') or get_scheme(
                    data.get('scheme_key') or DEFAULT_SCHEME)['name']

                total = sc.get('total')
                total_max = sc.get('total_max')
                if total is None:
                    score_txt, score_fg, score_key = "—", MUTED, -1.0
                else:
                    score_fg = score_color(total, total_max or 0)
                    score_txt = f"{total:.1f}/{total_max}"
                    score_key = total

                ts = str(data.get('timestamp', ''))
                ts_clean = ts.split('.')[0].replace('T', ' ') if ts else ''

                it = _HistRow([str(data.get('package', '?')), score_txt, scheme_name, ts_clean])
                it.setData(0, Qt.UserRole, str(f))
                it.setData(1, _HistRow.SCORE_ROLE, score_key)
                it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                it.setForeground(1, QBrush(QColor(score_fg)))
                it.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
                it.setForeground(3, QBrush(QColor(SUB)))
                it.setForeground(2, QBrush(Qt.transparent))
                self.list_widget.addTopLevelItem(it)

                wrap = QWidget()
                wrap.setStyleSheet("background:transparent;")
                wl = QHBoxLayout(wrap)
                wl.setContentsMargins(4, 5, 4, 5)
                tag = QLabel(scheme_name)
                tag.setObjectName("hsChip")
                tag.setAlignment(Qt.AlignCenter)
                tag.setFixedHeight(26)
                tag.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                bind_font(tag, 12)
                tag.setStyleSheet(
                    "#hsChip{background:#F2F8FD;border:1px solid #DCE9F3;"
                    "border-radius:9px;color:#283593;}")
                wl.addWidget(tag)
                self.list_widget.setItemWidget(it, 2, wrap)
            except Exception:
                pass

        if self.list_widget.topLevelItemCount() == 0:
            self.list_widget.addTopLevelItem(self._empty_row())
            return
        self.list_widget.setSortingEnabled(True)
        self.list_widget.sortByColumn(3, Qt.DescendingOrder)

    def _empty_row(self):
        empty = QTreeWidgetItem(["（暂无练习记录）", "", "", ""])
        empty.setDisabled(True)
        empty.setForeground(0, QBrush(QColor(MUTED)))
        return empty

    def _current_path(self):
        item = self.list_widget.currentItem()
        if not item:
            notify(self, "提示", "请先选择一条记录", icon=ICON_WARN)
            return None
        path = item.data(0, Qt.UserRole)
        if not path or not os.path.exists(path):
            return None
        return path

    # ---------- 删除 ----------
    def delete_selected(self):
        path = self._current_path()
        if not path:
            return
        if ask(self, "确认删除", "确定要删除该历史记录吗？",
               informative="删除后不可恢复。", danger=True, ok_text="删除"):
            try:
                os.remove(path)
                self.load_history()
            except Exception as e:
                notify(self, "删除失败", f"无法删除记录：{e}", icon=ICON_WARN)

    # ---------- 重新批改 ----------
    def reevaluate_selected(self):
        path = self._current_path()
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            notify(self, "文件损坏", "历史记录文件损坏，无法打开。", icon=ICON_WARN)
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
            notify(self, "无法重新批改", "Vosk 模型不可用，无法重新批改。", icon=ICON_WARN)
            return
        scheme_key = data.get('scheme_key') or temp_pkg.meta.get('scheme', DEFAULT_SCHEME)
        try:
            data['evaluation'] = evaluate_recordings(sess, temp_pkg, vosk_model)
            data['evaluation']['scores'] = compute_scores(data['evaluation'], scheme_key)
            data['scheme_key'] = str(scheme_key)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            notify(self, "重新批改失败", str(e), icon=ICON_WARN)
            return
        notify(self, "完成", "重新批改已完成。")
        self.load_history()

    # ---------- 详情 ----------
    def view_detail(self, item):
        path = item.data(0, Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        ev = data.get('evaluation') or {}
        sc = ev.get('scores') or {}
        pkg_name = str(data.get('package', '')) or "未命名题目包"
        ts = str(data.get('timestamp', '')).split('.')[0].replace('T', ' ')
        scheme_name = sc.get('scheme_name') or get_scheme(
            data.get('scheme_key') or DEFAULT_SCHEME)['name']

        dlg = QDialog(self)
        dlg.setWindowTitle("练习详情")
        dlg.setMinimumSize(760, 640)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setObjectName("detailRoot")
        dlg.setStyleSheet(
            f"#detailRoot {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 {BG_TOP}, stop:1 {BG_BOT}); }}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        # ---- 头部：题目名 + 徽标 + 总分 ----
        head, hv = card()
        hv.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        top.setSpacing(14)
        ic = QLabel()
        ic.setFixedSize(38, 38)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(svg_pixmap(ICON_CHART, ACCENT_DEEP, 26))
        ic.setStyleSheet(f"background:{ACCENT_SOFT}; border-radius:19px;")
        top.addWidget(ic, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(label(pkg_name, 18, TEXT, medium=True, wrap=True))
        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addWidget(self._tag(scheme_name), 0, Qt.AlignLeft)
        if ts:
            chips.addWidget(self._tag(ts), 0, Qt.AlignLeft)
        chips.addStretch(1)
        col.addLayout(chips)
        top.addLayout(col, 1)

        if sc:
            total = sc.get('total', 0)
            total_max = sc.get('total_max', 0)
            tcol = QVBoxLayout()
            tcol.setSpacing(0)
            tr = QHBoxLayout()
            tr.setSpacing(2)
            tr.addStretch(1)
            tr.addWidget(label(f"{total:.1f}", 30, score_color(total, total_max),
                               bold=True, wrap=False))
            tr.addWidget(label(f"/{total_max}", 13, MUTED, wrap=False))
            tcol.addLayout(tr)
            tl = label("总分", 12, SUB, wrap=False)
            tl.setAlignment(Qt.AlignRight)
            tcol.addWidget(tl)
            top.addLayout(tcol)
        hv.addLayout(top)
        root.addWidget(head)

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(12)

        detail = sc.get('detail', {}) if sc else {}
        part_rows = [
            ("partA", "Part A 模仿朗读", "#E3F2FD", "#D6E9FA", "#1565C0"),
            ("partB_secA", "Part B SecA 听选信息", "#F7DCDC", "#F0D2D2", "#a04a4a"),
            ("partB_secB", "Part B SecB 回答问题", "#F7DCDC", "#F0D2D2", "#a04a4a"),
            ("partC_secA", "Part C SecA 信息转述", "#FFFDE7", "#F5EFC8", "#8a6d1f"),
            ("partC_secB", "Part C SecB 询问信息", "#FFFDE7", "#F5EFC8", "#8a6d1f"),
        ]
        if detail:
            grid_card, gv = card("分项得分", ICON_CHART)
            grid = QGridLayout()
            grid.setSpacing(10)
            for i, (key, name, bg, bd, fg) in enumerate(part_rows):
                if key not in detail:
                    continue
                d = detail[key]
                score = float(d.get('score', 0) or 0)
                max_score = float(d.get('max', 0) or 0)
                f, pv = panel(bg, bd, margins=(14, 10, 14, 10), spacing=2)
                h = QHBoxLayout()
                h.setSpacing(6)
                h.addWidget(label(name, 13, fg, medium=True, wrap=False))
                h.addStretch(1)
                h.addWidget(label(f"{score:.1f}", 17, score_color(score, max_score),
                                  bold=True, wrap=False))
                h.addWidget(label(f"/{max_score:g}", 12, SUB, wrap=False))
                pv.addLayout(h)
                extra = []
                if d.get('coverage'):
                    extra.append(f"要点覆盖 {d['coverage']}")
                if d.get('items'):
                    extra.append(f"共 {d['items']} 题")
                if extra:
                    pv.addWidget(label(" · ".join(extra), 11, SUB, wrap=False))
                grid.addWidget(f, i // 2, i % 2)
            gv.addLayout(grid)
            bv.addWidget(grid_card)

        # ---- Part A ----
        pa = ev.get('partA')
        if pa:
            content = QWidget()
            content.setStyleSheet("background:transparent;")
            cv = QVBoxLayout(content)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(8)
            acc = float(pa.get('accuracy', 0) or 0) * 100
            wer = float(pa.get('wer', 0) or 0)
            cv.addWidget(self._metric_row("识别准确率", f"{acc:.1f}%",
                                          f"WER {wer:.2f}"))
            rec = (pa.get('recognized') or '').strip()
            cv.addWidget(self._quote(rec or "（未识别到朗读内容）"))
            bv.addWidget(self._section_card("Part A 模仿朗读", "#1565C0", content))

        # ---- Part B SecA / SecB ----
        secA = ev.get('partB_secA') or []
        if secA:
            content = QWidget()
            content.setStyleSheet("background:transparent;")
            cv = QVBoxLayout(content)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(7)
            for it in secA:
                per = 1.0
                sim = float(it.get('similarity', 0) or 0)
                pts = 0.0
                if detail.get('partB_secA', {}).get('max'):
                    d = detail['partB_secA']
                    per = d['max'] / max(1, d.get('items', 1))
                    pts = per if sim >= 0.5 else 0.0
                cv.addWidget(score_row(
                    f"对话 {it.get('seg', '?')} · 问题 {it.get('q', '?')}",
                    pts, per, score_color(pts, per), ACCENT,
                    extra=f"匹配度 {sim * 100:.0f}%"))
                cv.addWidget(self._answer_block(it.get('recognized'),
                                                it.get('correct')))
            bv.addWidget(self._section_card("Part B SecA 听选信息", "#a04a4a", content))

        secB = ev.get('partB_secB') or []
        if secB:
            content = QWidget()
            content.setStyleSheet("background:transparent;")
            cv = QVBoxLayout(content)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(7)
            for it in secB:
                per = 1.0
                sim = float(it.get('similarity', 0) or 0)
                pts = sim
                if detail.get('partB_secB', {}).get('max'):
                    d = detail['partB_secB']
                    per = d['max'] / max(1, d.get('items', 1))
                    pts = sim * per
                cv.addWidget(score_row(
                    f"问题 {it.get('q', '?')}", pts, per,
                    score_color(pts, per), ACCENT, extra=f"匹配度 {sim * 100:.0f}%"))
                cv.addWidget(self._answer_block(it.get('recognized'),
                                                it.get('correct')))
            bv.addWidget(self._section_card("Part B SecB 回答问题", "#a04a4a", content))

        # ---- Part C ----
        pcA = ev.get('partC_secA')
        if pcA:
            content = QWidget()
            content.setStyleSheet("background:transparent;")
            cv = QVBoxLayout(content)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(8)
            cv.addWidget(self._metric_row("要点覆盖", str(pcA.get('coverage', '0/0')), ""))
            rec = (pcA.get('recognized') or '').strip()
            cv.addWidget(self._quote(rec or "（未识别到转述内容）"))
            bv.addWidget(self._section_card("Part C SecA 信息转述", "#8a6d1f", content))

        pcB = ev.get('partC_secB') or []
        if pcB:
            content = QWidget()
            content.setStyleSheet("background:transparent;")
            cv = QVBoxLayout(content)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(7)
            for it in pcB:
                per = 1.0
                sim = float(it.get('similarity', 0) or 0)
                pts = sim
                if detail.get('partC_secB', {}).get('max'):
                    d = detail['partC_secB']
                    per = d['max'] / max(1, d.get('items', 1))
                    pts = sim * per
                cv.addWidget(score_row(
                    f"提问 {it.get('q', '?')}", pts, per,
                    score_color(pts, per), ACCENT, extra=f"匹配度 {sim * 100:.0f}%"))
                cv.addWidget(self._answer_block(it.get('recognized'),
                                                it.get('correct')))
            bv.addWidget(self._section_card("Part C SecB 询问信息", "#8a6d1f", content))

        # ---- 思维导图 ----
        mm_copy = data.get("mindmap_copy")
        if mm_copy and os.path.exists(mm_copy):
            mm_card, mv = card("思维导图")
            pic = QLabel()
            pic.setAlignment(Qt.AlignCenter)
            pix = QPixmap(mm_copy)
            if not pix.isNull():
                pic.setPixmap(pix.scaled(640, 280, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))
            mv.addWidget(pic)
            bv.addWidget(mm_card)

        bv.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.viewport().setStyleSheet("background:transparent;")
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(secondary_button("关闭", dlg.accept))
        root.addLayout(foot)

        dlg.exec_()

    # ---------- 详情小组件 ----------
    @staticmethod
    def _tag(text):
        lb = label(text, 12, "#283593", wrap=False)
        lb.setStyleSheet(
            "#detailTag{background:#F2F8FD;border:1px solid #DCE9F3;border-radius:9px;"
            "color:#283593;padding:3px 10px;}")
        lb.setObjectName("detailTag")
        return lb

    def _section_card(self, title, color, body):
        f, v = card()
        head = QHBoxLayout()
        head.setSpacing(8)
        bar = QFrame()
        bar.setFixedSize(4, 16)
        bar.setStyleSheet(f"background:{color}; border-radius:2px;")
        head.addWidget(bar)
        head.addWidget(label(title, 15, TEXT, medium=True, wrap=False))
        head.addStretch(1)
        v.addLayout(head)
        v.addWidget(hline())
        v.addWidget(body)
        return f

    def _metric_row(self, name, value, extra=""):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        h.addWidget(label(name, 13, SUB, wrap=False))
        h.addWidget(label(value, 14, TEXT, medium=True, wrap=False))
        if extra:
            h.addWidget(label(extra, 12, MUTED, wrap=False))
        h.addStretch(1)
        return w

    def _quote(self, text):
        f, v = panel("#F8FBFD", "#E6EEF5", margins=(12, 9, 12, 9))
        v.addWidget(label(text, 13, "#2C3E50", selectable=True))
        return f

    def _answer_block(self, recognized, correct):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 0, 12, 0)
        v.setSpacing(4)
        v.addWidget(label(f"你的回答：{recognized or '（未识别到内容）'}", 12, SUB,
                          selectable=True))
        if correct:
            v.addWidget(label(f"参考答案：{correct}", 12, ACCENT_DEEP, selectable=True))
        return w
