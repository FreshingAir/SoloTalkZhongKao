# -*- coding: utf-8 -*-
"""更多页：左侧导航 + 右侧单栏内容（个性化 / 关于 / 更新&下载 / 意见反馈 / 使用须知）。"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ..config import APP_VERSION
from ..paths import resolve_resource_file
from ..settings import save_settings
from .theme import (ACCENT, ACCENT_DEEP, ACCENT_SOFT, CARD, FluentSelect, ICON_CHAT,
                    ICON_DOC, ICON_DOWNLOAD, ICON_GEAR, ICON_INFO, ICON_PKG, SUB, TEXT,
                    _UI_FONT, available_font_choices, bind_font, svg_pixmap)

# 外链集中在此，日后改地址只改这一处
REPO_URL = "https://github.com/FreshingAir/SoloTalkZhongKao"
RELEASES_URL = "https://github.com/FreshingAir/SoloTalkZhongKao/releases"
BILIBILI_URL = "https://space.bilibili.com/1667914290"
QQ_JOIN_URL = "https://qm.qq.com/q/o4Yfw2jsDm"
QQ_GROUP_NO = "1091799764"
QR_FILENAME = "qq_group_qr.jpg"
ICON_FILENAME = "xixi.ico"
LABEL_W = 96


class MorePage(QWidget):
    NAV_ITEMS = [
        (ICON_GEAR, "个性化"),
        (ICON_INFO, "关于"),
        (ICON_DOWNLOAD, "更新&下载地址"),
        (ICON_CHAT, "意见反馈"),
        (ICON_DOC, "使用须知&声明"),
    ]

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 左侧导航 ----------
        left = QFrame()
        left.setObjectName("moreSide")
        left.setFixedWidth(188)
        left.setStyleSheet(
            "QFrame#moreSide { background:#f7f9fb; border:none;"
            " border-right:1px solid #e6ebef; }")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setStyleSheet(
            "QListWidget { background:transparent; border:none; outline:none; padding:10px 0; }"
            "QListWidget::item { height:44px; margin:2px 10px; border-radius:8px;"
            " color:#55606b; font-size:14px; }"
            "QListWidget::item:hover { background:#edf1f4; }"
            f"QListWidget::item:selected {{ background:{ACCENT_SOFT}; color:{ACCENT_DEEP}; }}")
        for icon_paths, name in self.NAV_ITEMS:
            item = QListWidgetItem(f"    {name}")
            item.setIcon(QIcon(svg_pixmap(icon_paths, "#5C6B7A", 18)))
            item.setSizeHint(QSize(0, 44))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav)
        lv.addWidget(self.nav, 1)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#e6ebef;")
        sep_row = QHBoxLayout()
        sep_row.setContentsMargins(18, 0, 18, 0)
        sep_row.addWidget(sep)
        lv.addLayout(sep_row)

        foot = QWidget()
        fv = QVBoxLayout(foot)
        fv.setContentsMargins(18, 12, 18, 16)
        btn_back = QPushButton("返回主页")
        btn_back.setCursor(Qt.PointingHandCursor)
        bind_font(btn_back, 13)
        btn_back.setStyleSheet(
            "QPushButton { padding:7px 0; border:1px solid #cfd8dc;"
            " border-radius:8px; background:white; color:#55606b; }"
            "QPushButton:hover { background:#f4f7f9; color:#2c3e50; }")
        btn_back.clicked.connect(lambda: self.main.go_to(self.main.home_page))
        fv.addWidget(btn_back)
        lv.addWidget(foot)
        root.addWidget(left)

        # ---------- 右侧内容 ----------
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(26, 22, 26, 20)
        rv.setSpacing(10)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._scroll(self._page_personalize()))
        self.stack.addWidget(self._scroll(self._page_about()))
        self.stack.addWidget(self._scroll(self._page_update()))
        self.stack.addWidget(self._scroll(self._page_feedback()))
        self.stack.addWidget(self._scroll(self._page_terms()))
        rv.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        self.nav.setCurrentRow(1)
        self.setLayout(root)

    def _on_nav(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    # ---------- 通用小组件 ----------
    def _page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 2, 2)
        v.setSpacing(12)
        v.setAlignment(Qt.AlignTop)
        return w, v

    def _scroll(self, inner):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        sc.viewport().setAutoFillBackground(False)
        sc.viewport().setStyleSheet("background: transparent;")
        sc.setWidget(inner)
        return sc

    def _heading(self, text, size=20):
        lb = QLabel(text)
        bind_font(lb, size, medium=True)
        lb.setStyleSheet(f"color:{TEXT};")
        return lb

    def _sub(self, text, size=18):
        lb = QLabel(f"<span style='color:{ACCENT_DEEP};'>▍</span>{text}")
        lb.setWordWrap(True)
        lb.setTextFormat(Qt.RichText)
        bind_font(lb, size, medium=True)
        lb.setStyleSheet(f"color:{TEXT};")
        return lb

    def _para(self, text, size=14, color=SUB):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bind_font(lb, size)
        lb.setStyleSheet(f"color:{color};")
        return lb

    def _primary_btn(self, label, slot):
        btn = QPushButton(label)
        btn.setCursor(Qt.PointingHandCursor)
        bind_font(btn, 14, medium=True)
        btn.setStyleSheet(
            f"QPushButton {{ padding:8px 22px; border:none; border-radius:8px;"
            f" background:{ACCENT_DEEP}; color:white; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{ACCENT}; }}")
        btn.clicked.connect(slot)
        return btn

    def _secondary_btn(self, label, slot=None):
        btn = QPushButton(label)
        btn.setCursor(Qt.PointingHandCursor)
        bind_font(btn, 13)
        btn.setStyleSheet(
            f"QPushButton {{ padding:5px 16px; border:1px solid #cfd8dc;"
            f" border-radius:6px; background:white; color:#55606b; }}"
            f"QPushButton:hover {{ background:#f4f7f9; color:#2c3e50; }}")
        if slot is not None:
            btn.clicked.connect(slot)
        return btn

    def _link_row(self, links, center=False):
        row = QHBoxLayout()
        row.setSpacing(4)
        if center:
            row.addStretch(1)
        for i, (label, url) in enumerate(links):
            if i:
                sep = QLabel("·")
                sep.setStyleSheet("color:#b8c2cc; font-size:14px;")
                row.addWidget(sep)
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            bind_font(btn, 14)
            btn.setStyleSheet(
                f"QPushButton {{ border:none; background:transparent; color:{ACCENT_DEEP};"
                f" padding:2px 6px; }}"
                f"QPushButton:hover {{ color:{ACCENT}; }}")
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(btn)
        if center:
            row.addStretch(1)
        return row

    def _info_value(self, value):
        ed = QLineEdit(value)
        ed.setReadOnly(True)
        ed.setCursorPosition(0)
        bind_font(ed, 13)
        return ed

    def _info_row(self, label, value=None, btn_label=None, slot=None,
                  primary_btn=False):
        row = QHBoxLayout()
        row.setSpacing(10)
        lb = QLabel(label)
        lb.setFixedWidth(LABEL_W)
        lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bind_font(lb, 14)
        lb.setStyleSheet("color:#55606b;")
        row.addWidget(lb)
        if value is not None:
            row.addWidget(self._info_value(value), 1)
        if btn_label is not None:
            row.addWidget(self._primary_btn(btn_label, slot) if primary_btn
                          else self._secondary_btn(btn_label, slot))
        row.addStretch(1)
        return row

    # ---------- 个性化 ----------
    def _page_personalize(self):
        w, v = self._page()
        v.addWidget(self._sub("界面字体"))
        v.addWidget(self._para("换一个你看着舒服的字体，改动立即生效，并会记到下次启动。",
                               13, "#6b7785"))

        card = QFrame()
        card.setObjectName("pfCard")
        card.setStyleSheet(
            f"#pfCard {{ background:{CARD}; border:1px solid #e6ebef; border-radius:10px; }}")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(20, 18, 20, 18)
        cv.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)
        lb = QLabel("字体")
        lb.setFixedWidth(LABEL_W)
        bind_font(lb, 14)
        lb.setStyleSheet(f"color:{TEXT};")
        row.addWidget(lb)

        self.cmb_font = FluentSelect(min_width=300)
        cur = _UI_FONT.get("choice")
        sel = 0
        for i, (name, fam) in enumerate(available_font_choices()):
            self.cmb_font.addItem(name, fam)
            if fam == cur:
                sel = i
        self.cmb_font.setCurrentIndex(sel)
        self.cmb_font.changed.connect(self._on_font_changed)
        row.addWidget(self.cmb_font)
        row.addStretch(1)
        cv.addLayout(row)

        pv = QLabel("预览")
        bind_font(pv, 13)
        pv.setStyleSheet("color:#6b7785;")
        cv.addWidget(pv)

        prev = QFrame()
        prev.setObjectName("pfPrev")
        prev.setStyleSheet(
            "#pfPrev { background:#f7f9fb; border:1px solid #eaf0f4; border-radius:8px; }")
        pvv = QVBoxLayout(prev)
        pvv.setContentsMargins(16, 14, 16, 14)
        pvv.setSpacing(6)
        for text, size_px, medium, color in (
            ("SoloTalk 英语听说模考", 20, True, TEXT),
            ("Part A Reading Aloud　模仿朗读", 14, False, "#2c3e50"),
            ("单机版英语听说模考编辑器 · 断网可用", 12, False, "#7a8a9a"),
        ):
            lb2 = QLabel(text)
            bind_font(lb2, size_px, medium=medium)
            lb2.setStyleSheet(f"color:{color}; background:transparent;")
            pvv.addWidget(lb2)
        cv.addWidget(prev)

        v.addWidget(card)
        return w

    def _on_font_changed(self, fam):
        if not self.main.set_ui_font(fam):
            print("[FONT] 切换失败，字体保持原样")

    # ---------- 关于 ----------
    def _page_about(self):
        w, v = self._page()

        icon_lb = QLabel()
        icon_lb.setAlignment(Qt.AlignCenter)
        _icon_path = resolve_resource_file(ICON_FILENAME)
        _pix = QIcon(_icon_path).pixmap(96, 96) if _icon_path else QPixmap()
        if not _pix.isNull():
            icon_lb.setPixmap(_pix)
        else:
            # 没有随包图标时用同色系线性图标占位，保持版面完整
            icon_lb.setFixedSize(96, 96)
            icon_lb.setStyleSheet(
                f"background:{ACCENT_SOFT}; border-radius:24px;")
            icon_lb.setPixmap(svg_pixmap(ICON_PKG, ACCENT_DEEP, 48))
        v.addWidget(icon_lb, 0, Qt.AlignHCenter)

        name = QLabel("SoloTalk")
        name.setAlignment(Qt.AlignCenter)
        bind_font(name, 26, medium=True)
        name.setStyleSheet(f"color:{TEXT};")
        v.addWidget(name)

        ver = QLabel(f"v{APP_VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setFixedWidth(66)
        bind_font(ver, 13)
        ver.setStyleSheet(
            "color:#55606b; background:#eef2f5; border-radius:11px; padding:4px 0;")
        ver_row = QHBoxLayout()
        ver_row.addStretch(1)
        ver_row.addWidget(ver)
        ver_row.addStretch(1)
        v.addLayout(ver_row)

        desc = QLabel("单机版英语听说模考编辑器 · 完全免费 · 开源")
        desc.setAlignment(Qt.AlignCenter)
        bind_font(desc, 14)
        desc.setStyleSheet("color:#7f8c8d;")
        v.addWidget(desc)

        v.addLayout(self._link_row([
            ("源码仓库", REPO_URL),
            ("哔哩哔哩主页", BILIBILI_URL),
            ("Github 发布页", RELEASES_URL),
        ], center=True))

        v.addSpacing(4)
        v.addWidget(self._para("作者：晖落然（FallingLighty）、cheng、咸鱼、FreshingAir", size=14))
        v.addWidget(self._para(
            "适用地区：佛山、中山、珠海、广州、湛江、茂名、阳江、清远、韶关、潮州、"
            "揭阳、云浮、梅州、江门（改革后）、惠州（改革后）、深圳（25分）、东莞（25分）。",
            size=13, color="#7f8c8d"))
        v.addStretch(1)
        return w

    # ---------- 更新&下载 ----------
    def _page_update(self):
        w, v = self._page()
        v.addWidget(self._heading("版本更新"))
        v.addWidget(self._para("仅提示新版本，不自动下载或替换；需要时前往发布页手动下载。",
                               13, "#7f8c8d"))

        v.addWidget(self._para(f"当前版本：SoloTalk 中考版 {APP_VERSION}", size=15))
        v.addWidget(self._para("运行平台：电脑（Windows）", size=15))
        v.addWidget(self._para("运行模式：模考（不可跳过 / 不可返回） / 练习（可跳过、可返回）",
                               size=15))

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self._primary_btn("检查更新", self.main._check_update))
        self.chk_auto_update = QCheckBox("启动时自动检查更新")
        self.chk_auto_update.setCursor(Qt.PointingHandCursor)
        self.chk_auto_update.setChecked(bool(self.main.settings.get("auto_check_update", True)))
        bind_font(self.chk_auto_update, 13)
        self.chk_auto_update.setStyleSheet("QCheckBox { color:#55606b; }")
        self.chk_auto_update.toggled.connect(self._on_auto_update_toggled)
        row.addWidget(self.chk_auto_update)
        row.addStretch(1)
        v.addLayout(row)

        v.addSpacing(10)
        v.addWidget(self._heading("下载地址"))
        v.addLayout(self._info_row(
            "QQ群：", btn_label=f"点击加入群聊(QQ：{QQ_GROUP_NO})",
            slot=lambda: QDesktopServices.openUrl(QUrl(QQ_JOIN_URL)), primary_btn=True))
        v.addLayout(self._info_row(
            "发布页：", btn_label="前往发布页",
            slot=lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)), primary_btn=True))

        v.addStretch(1)
        return w

    def _on_auto_update_toggled(self, checked):
        self.main.settings["auto_check_update"] = bool(checked)
        save_settings(self.main.settings)

    # ---------- 意见反馈 ----------
    def _page_feedback(self):
        w, v = self._page()
        v.addWidget(self._heading("意见反馈"))
        v.addWidget(self._para("使用中遇到问题、或想提功能建议，欢迎进 QQ 群反馈。",
                               13, "#7f8c8d"))
        v.addWidget(self._para("QQ 群：SoloTalkの创意工坊", size=15))
        v.addWidget(self._para(f"群号：{QQ_GROUP_NO}", size=15, color="#7f8c8d"))

        join_row = QHBoxLayout()
        join_row.addWidget(self._primary_btn(
            "点击加入群聊", lambda: QDesktopServices.openUrl(QUrl(QQ_JOIN_URL))))
        join_row.addStretch(1)
        v.addLayout(join_row)

        qr_row = QHBoxLayout()
        qr_row.addStretch(1)
        _qr = resolve_resource_file(QR_FILENAME)
        if _qr:
            _qrpix = QPixmap(_qr)
            if not _qrpix.isNull():
                pic = QLabel()
                pic.setPixmap(_qrpix.scaledToWidth(210, Qt.SmoothTransformation))
                qr_row.addWidget(pic)
        qr_row.addStretch(1)
        v.addLayout(qr_row)

        cap = QLabel(f"扫一扫，加入 QQ 交流群（群号 {QQ_GROUP_NO}）")
        cap.setAlignment(Qt.AlignCenter)
        bind_font(cap, 13)
        cap.setStyleSheet("color:#95a5a6;")
        v.addWidget(cap)
        v.addStretch(1)
        return w

    # ---------- 使用须知 ----------
    def _page_terms(self):
        w, v = self._page()

        v.addWidget(self._sub("联网说明"))
        v.addWidget(self._para(
            "录音识别与批改全部在本地完成，断网也能完整考完；联网时会自动启用更自然的"
            "在线朗读语音，并在启动时检查一次新版本（可在「更新&下载地址」里关闭）。",
            size=14))

        v.addWidget(self._sub("适用人群"))
        for line in [
            "1、想提前体验听说考试流程，但学校还未购买 E 听说 E 卡的学生",
            "2、学校未强制，且用不上 E 听说复杂功能的学生",
            "3、真的买不起 E 听说 E 卡的学生",
        ]:
            v.addWidget(self._para(line, size=14))

        v.addSpacing(10)
        v.addWidget(self._sub("使用须知"))
        for line in [
            "1、为保障题目原创权，题目署名一经保存不可更改，请慎重",
            "2、Part C 要点请用英文逗号隔开，否则无法识别",
            "3、批改结果基于离线语音识别，仅供参考",
            "4、评分分制（30 / 25）由题目作者在编辑模式中指定，随 .solo 包分发",
            "5、朗读音频会缓存在本机，同一题目再次练习可直接复用（跳过朗读也保留）",
            "6、中途返回主页相当于暂停，再次打开同一题目会从当前位置继续",
            "7、电脑版请使用全英文路径",
        ]:
            v.addWidget(self._para(line, size=14))

        v.addSpacing(10)
        v.addWidget(self._sub("免责声明"))
        v.addWidget(self._para(
            "本软件为自制、免费、非商用、开源的英语听说练习工具，用于提前体验考试流程；"
            "批改可能存在不够准确的情况，请不要把它当作备考的唯一依据。", size=14))
        v.addWidget(self._para(
            "题库需要大家共同创作，欢迎在 QQ 群分享与反馈题目。", size=14))

        v.addStretch(1)
        return w
