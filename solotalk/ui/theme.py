# -*- coding: utf-8 -*-
"""界面主题：设计 token、字体、单色线性图标、Fluent 控件与全局样式表。

所有页面共用这里的一套视觉语言（天蓝主色 + 白色大圆角卡片 + 细描边）：
    BG_TOP/BG_BOT   页面渐变底色
    CARD/BD/LINE    卡片、描边、浅分割线
    TEXT/SUB/MUTED  主文字 / 次要文字 / 弱化文字
    ACCENT*         强调色（天蓝）
"""

import html
import weakref

from PyQt5.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
                             QMenu, QPushButton, QScrollArea, QSizePolicy,
                             QVBoxLayout, QWidget, QAction)
from PyQt5.QtCore import (QByteArray, QEasingCurve, QObject, QPoint, QPropertyAnimation,
                          Qt, pyqtSignal)
from PyQt5.QtGui import QFont, QFontDatabase, QPainter, QPixmap

from ..paths import resolve_resource_file

try:
    from PyQt5.QtSvg import QSvgRenderer as _QSvgRenderer
except Exception:  # QtSvg 缺失时图标静默降级为空图
    _QSvgRenderer = None


# ========== 设计 token ==========
BG_TOP = "#F7FBFF"
BG_BOT = "#EDF6FC"
CARD = "#FFFFFF"
BD = "#E3ECF3"
LINE = "#EEF3F7"
DIV = "#BCCFE0"
TEXT = "#1A2B3C"
SUB = "#5A6B7B"
MUTED = "#9AA7B4"
ACCENT = "#66CCFF"
ACCENT_DEEP = "#0A9BE0"
ACCENT_SOFT = "#E8F6FF"

# 兼容短名（详情卡片等处的旧写法）
D_BG_TOP, D_BG_BOT = BG_TOP, BG_BOT
D_CARD, D_BD, D_LINE = CARD, BD, LINE
D_TEXT, D_SUB, D_MUTED = TEXT, SUB, MUTED
D_DIV = DIV
D_ACCENT, D_ACCENT_DEEP, D_ACCENT_SOFT = ACCENT, ACCENT_DEEP, ACCENT_SOFT


# ========== 单色线性图标（24 viewBox，描边无填充） ==========
ICON_PRACTICE = ["M4 15v-3a8 8 0 0 1 16 0v3",
                 "M3.5 14.5h4v6h-4z",
                 "M16.5 14.5h4v6h-4z"]
ICON_EXAM = ["M6 3h9l4 4v14H6z", "M15 3v4h4", "M9 12h6", "M9 16h4"]
ICON_EDITOR = ["M4 20l4-1 11-11a2.3 2.3 0 0 0-3.3-3.3L4.7 15.7z",
               "M14.5 6.6l3.3 3.3"]
ICON_HISTORY = ["M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z",
                "M12 7.5V12l3.2 2"]
ICON_CHART = ["M18 20V10", "M12 20V4", "M6 20v-6"]
ICON_MIC = ["M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z",
            "M19 10v2a7 7 0 0 1-14 0v-2", "M12 19v4", "M8 23h8"]
ICON_WARN = ["M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3"
             "L13.71 3.86a2 2 0 0 0-3.42 0z", "M12 9v4", "M12 17h.01"]
ICON_OK = ["M22 11.08V12a10 10 0 1 1-5.93-9.14", "M22 4L12 14.01l-3-3"]
ICON_DOC = ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z",
            "M14 2v6h6", "M16 13H8", "M16 17H8", "M10 9H8"]
ICON_INFO = ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 10.5V16", "M12 7.5h.01"]
ICON_DOWNLOAD = ["M12 3v12", "M7 10l5 5 5-5", "M4 20h16"]
ICON_CHAT = ["M21 11.5a8.5 8.5 0 0 1-12.4 7.5L3 21l2-5.6A8.5 8.5 0 1 1 21 11.5z"]
ICON_GEAR = ["M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z",
             "M12 2.5v2.2", "M12 19.3v2.2", "M4.4 4.4l1.6 1.6",
             "M18 18l1.6 1.6", "M2.5 12h2.2", "M19.3 12h2.2",
             "M4.4 19.6L6 18", "M18 6l1.6-1.6"]
ICON_PKG = ["M16.5 9.4l-9-5.19",
            "M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8"
            "a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z",
            "M3.27 6.96L12 12.01l8.73-5.05", "M12 22.08V12"]
ICON_BACK = ["M19 12H5", "M12 19l-7-7 7-7"]
ICON_PLAY = ["M8 5v14l11-7z"]
ICON_CHEVRON = ["M6.5 9.75L12 15.25l5.5-5.5"]
ICON_CHECK = ["M5 12l4 4 10-10"]


def escape(text):
    """富文本标签转义（QLabel.setTextFormat(RichText) 时必须）。"""
    return html.escape(str(text))


# ========== 字体 ==========
_FONT_FILES = {
    "regular": "fonts/HarmonyOS_Sans_SC_Regular.ttf",
    "medium": "fonts/HarmonyOS_Sans_SC_Medium.ttf",
}
_FONT_FALLBACK = ["Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC"]

EMBEDDED_FONT_KEY = "__embedded_harmonyos__"
DEFAULT_FONT_CHOICE = "Microsoft YaHei UI"
SETTINGS_FONT_KEY = "ui_font"

FONT_CHOICES = [
    ("微软雅黑 UI", "Microsoft YaHei UI"),
    ("鸿蒙 HarmonyOS Sans SC", EMBEDDED_FONT_KEY),
    ("思源黑体 Noto Sans SC", "Noto Sans SC"),
    ("系统默认 Segoe UI", "Segoe UI"),
]

_UI_FONT = {"regular": None, "medium": None, "choice": None}
_FONT_BOUND = []


def load_app_fonts():
    """把随包字体注册进 QFontDatabase（必须在 QApplication 之后调用）。"""
    for key, rel in _FONT_FILES.items():
        try:
            p = resolve_resource_file(rel)
            if not p:
                continue
            fid = QFontDatabase.addApplicationFont(p)
            if fid < 0:
                continue
            names = QFontDatabase.applicationFontFamilies(fid)
            if names:
                _UI_FONT[key] = names[0]
                print(f"[FONT] 已加载 {rel} -> {names[0]}")
        except Exception as e:
            print(f"[FONT] 加载异常 {rel}: {e}")
    return _UI_FONT


def available_font_choices():
    """本机可用的界面字体选项 [(显示名, 族名或哨兵)]。"""
    try:
        installed = set(QFontDatabase().families())
    except Exception:
        installed = set()
    out = []
    for label, key in FONT_CHOICES:
        if key == EMBEDDED_FONT_KEY:
            if _UI_FONT.get("regular"):
                out.append((label, key))
        elif key in installed:
            out.append((label, key))
    return out or [(label, key) for label, key in FONT_CHOICES[:1]]


def ui_font(size_px, medium=False, bold=False):
    """生成界面字体：用户选择 > 内嵌鸿蒙 > 系统回退。size 单位为像素。"""
    f = QFont()
    chosen = _UI_FONT.get("choice")
    fam_medium = _UI_FONT.get("medium")
    fam_regular = _UI_FONT.get("regular")
    if chosen == EMBEDDED_FONT_KEY:
        chosen = None

    if chosen:
        f.setFamilies([chosen] + [x for x in _FONT_FALLBACK if x != chosen])
        f.setWeight(QFont.Bold if (medium or bold) else QFont.Normal)
    elif medium and fam_medium:
        f.setFamily(fam_medium)
        f.setWeight(QFont.Normal)
    elif fam_regular:
        f.setFamily(fam_regular)
        f.setWeight(QFont.Bold if bold else QFont.Normal)
    else:
        f.setFamilies(_FONT_FALLBACK)
        f.setWeight(QFont.Bold if (bold or medium) else QFont.Normal)
    f.setPixelSize(size_px)
    return f


def bind_font(widget, size_px, medium=False, bold=False):
    """设置界面字体并登记，切换字体时统一直刷。返回控件本身，便于链式调用。"""
    try:
        widget.setFont(ui_font(size_px, medium=medium, bold=bold))
        _FONT_BOUND.append((weakref.ref(widget), size_px, medium, bold))
    except Exception:
        pass
    return widget


def refresh_bound_fonts():
    global _FONT_BOUND
    alive = []
    for ref, size_px, medium, bold in _FONT_BOUND:
        w = ref()
        if w is None:
            continue
        try:
            w.setFont(ui_font(size_px, medium=medium, bold=bold))
            alive.append((ref, size_px, medium, bold))
        except RuntimeError:
            pass
    _FONT_BOUND = alive


def repolish_all(app=None):
    """强制所有控件重新套用样式表（QSS 里写死的字号需要它才会跟着换字体）。"""
    app = app or QApplication.instance()
    if app is None:
        return 0
    n = 0
    for w in app.allWidgets():
        try:
            st = w.style()
            st.unpolish(w)
            st.polish(w)
            w.update()
            n += 1
        except RuntimeError:
            pass
    return n


def set_ui_font_choice(family):
    """应用界面字体（立即生效）。返回是否成功。"""
    _UI_FONT["choice"] = family
    app = QApplication.instance()
    if app is None:
        return False
    app.setFont(ui_font(12))
    refresh_bound_fonts()
    repolish_all(app)
    return True


# ========== 图标 ==========
def svg_pixmap(paths, color, size):
    """把一组 SVG path 渲成单色线性图标；QtSvg 缺失时返回空图（静默降级）。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    if _QSvgRenderer is None:
        return pix
    body = "".join(f'<path d="{d}"/>' for d in paths)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"'
           f' viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8"'
           f' stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    r = _QSvgRenderer(QByteArray(svg.encode("utf-8")))
    p = QPainter(pix)
    r.render(p)
    p.end()
    return pix


def icon_label(paths, color=ACCENT_DEEP, size=22, box=36):
    """圆形浅色底 + 线性图标，返回 QLabel。"""
    lb = QLabel()
    lb.setFixedSize(box, box)
    lb.setAlignment(Qt.AlignCenter)
    lb.setStyleSheet(f"background:{ACCENT_SOFT}; border-radius:{box // 2}px;")
    lb.setPixmap(svg_pixmap(paths, color, size))
    return lb


# ========== 富文本小组件 ==========
def label(text, size_px=13, color=TEXT, medium=False, bold=False,
          wrap=True, selectable=False, parent=None):
    lb = QLabel(parent)
    lb.setTextFormat(Qt.RichText)
    lb.setText(f"<span style='color:{color}'>{escape(str(text).strip())}</span>")
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    bind_font(lb, size_px, medium=medium, bold=bold)
    lb.setStyleSheet("background:transparent;")
    return lb


def hline():
    ln = QFrame()
    ln.setObjectName("themeLine")
    ln.setFixedHeight(1)
    ln.setStyleSheet(f"#themeLine{{background:{LINE};border:none;}}")
    return ln


def card(title=None, icon_paths=None, margins=(18, 15, 18, 17), spacing=11):
    """白色大圆角卡片：标题行 + 细分割线。返回 (卡片, 内容布局)。"""
    f = QFrame()
    f.setObjectName("themeCard")
    f.setStyleSheet(
        f"#themeCard{{background:{CARD};border:1px solid {BD};border-radius:14px;}}")
    v = QVBoxLayout(f)
    v.setContentsMargins(*margins)
    v.setSpacing(spacing)
    if title:
        hd = QHBoxLayout()
        hd.setSpacing(8)
        if icon_paths:
            ic = QLabel()
            ic.setFixedSize(18, 18)
            ic.setStyleSheet("background:transparent;")
            ic.setPixmap(svg_pixmap(icon_paths, ACCENT_DEEP, 18))
            hd.addWidget(ic)
        hd.addWidget(label(title, 15, TEXT, medium=True, wrap=False))
        hd.addStretch(1)
        v.addLayout(hd)
        v.addWidget(hline())
    return f, v


def panel(bg, border, radius=10, margins=(14, 11, 14, 12), spacing=6):
    """带底色的圆角面板（QSS 的 border-radius 在 QFrame 上真实生效）。"""
    f = QFrame()
    f.setObjectName("themePanel")
    f.setStyleSheet(
        f"#themePanel{{background:{bg};border:1px solid {border};"
        f"border-radius:{radius}px;}}")
    v = QVBoxLayout(f)
    v.setContentsMargins(*margins)
    v.setSpacing(spacing)
    return f, v


def chip(text, fit=False):
    """小标签：浅蓝底、圆角、可选中复制。"""
    lb = label(text, 12, "#283593", wrap=not fit, selectable=True)
    lb.setObjectName("themeChip")
    if fit:
        lb.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    else:
        lb.setMinimumWidth(60)
        lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    lb.setStyleSheet(
        "#themeChip{background:#F2F8FD;border:1px solid #DCE9F3;border-radius:8px;"
        "color:#283593;padding:6px 10px;}")
    return lb


def score_row(text, score, per, color, bar_color=ACCENT, extra=""):
    """一行得分：白底 + 左侧彩色竖条，左侧说明、右侧分数。"""
    f = QFrame()
    f.setObjectName("themeScoreRow")
    f.setStyleSheet(
        f"#themeScoreRow{{background:#FFFFFF;border:none;"
        f"border-left:4px solid {bar_color};border-radius:6px;}}")
    h = QHBoxLayout(f)
    h.setContentsMargins(12, 7, 12, 7)
    h.setSpacing(0)
    h.addWidget(label(text, 13, "#2C3E50", wrap=True), 1)
    if extra:
        h.addWidget(label(extra, 12, MUTED, wrap=False))
        h.addSpacing(10)
    h.addWidget(label("得分：", 12, SUB, wrap=False))
    h.addWidget(label(f"{score:.1f}", 15, color, bold=True, wrap=False))
    h.addWidget(label(f"/{per}", 12, MUTED, wrap=False))
    return f


def section(title, color, body_widget):
    """「▍标题 + 内容块」小节。"""
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(7)
    head = QLabel(f"<span style='color:{color};'>▍</span>{escape(title)}")
    head.setTextFormat(Qt.RichText)
    bind_font(head, 13, medium=True)
    head.setStyleSheet("background:transparent;")
    v.addWidget(head)
    v.addWidget(body_widget)
    return w


def score_color(score, full):
    """按得分率给出颜色（红 / 橙 / 绿）。"""
    ratio = (score / full) if full else 0
    if ratio < 0.6:
        return "#c0392b"
    if ratio < 0.8:
        return "#e67e22"
    return "#27ae60"


# ========== 按钮 ==========
def primary_button(text, slot=None, height=40, min_width=0):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(height)
    if min_width:
        b.setMinimumWidth(min_width)
    bind_font(b, 13, medium=True)
    b.setStyleSheet(
        f"QPushButton {{ background:{ACCENT_DEEP}; border:none; border-radius:10px;"
        f" padding:0 22px; color:#FFFFFF; font-weight:bold; }}"
        f"QPushButton:hover {{ background:{ACCENT}; }}"
        f"QPushButton:disabled {{ background:{MUTED}; }}")
    if slot is not None:
        b.clicked.connect(slot)
    return b


def secondary_button(text, slot=None, height=40, danger=False):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(height)
    bind_font(b, 13)
    if danger:
        fg, bd, hv = "#C0392B", "#F0D5D5", "#FDECEC"
    else:
        fg, bd, hv = SUB, BD, LINE
    b.setStyleSheet(
        f"QPushButton {{ background:{CARD}; border:1px solid {bd};"
        f" border-radius:10px; padding:0 22px; color:{fg}; }}"
        f"QPushButton:hover {{ background:{hv}; }}"
        f"QPushButton:disabled {{ color:{MUTED}; }}")
    if slot is not None:
        b.clicked.connect(slot)
    return b


def flat_link_button(text, slot=None, size_px=13, color=ACCENT_DEEP):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    bind_font(b, size_px)
    b.setStyleSheet(
        f"QPushButton {{ background:transparent; border:none; padding:6px 10px;"
        f" border-radius:6px; color:{color}; }}"
        f"QPushButton:hover {{ background:{ACCENT_SOFT}; }}")
    if slot is not None:
        b.clicked.connect(slot)
    return b


# ========== 缓动滚动 ==========
class SmoothScroll(QObject):
    """接管鼠标滚轮，用 QPropertyAnimation 缓动滚动条（微信那种跟手手感）。"""

    DURATION_MS = 190
    PX_PER_NOTCH = 100

    def __init__(self, area):
        super().__init__(area)
        self._v = area.verticalScrollBar()
        self._h = area.horizontalScrollBar()
        self._av = self._make_anim(self._v)
        self._ah = self._make_anim(self._h)
        area.viewport().installEventFilter(self)

    def _make_anim(self, bar):
        a = QPropertyAnimation(bar, b"value", self)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.setDuration(self.DURATION_MS)
        return a

    def _glide(self, anim, bar, delta_px):
        if bar.maximum() <= bar.minimum():
            return False
        anim.stop()
        anim.setStartValue(bar.value())
        anim.setEndValue(max(bar.minimum(),
                             min(bar.maximum(), bar.value() + delta_px)))
        anim.start()
        return True

    def eventFilter(self, obj, ev):
        if obj is self.parent().viewport():
            if ev.type() == ev.Wheel:
                dy = ev.angleDelta().y()
                dx = ev.angleDelta().x()
                step = self.PX_PER_NOTCH * (dy / 120.0) if dy else 0
                hstep = self.PX_PER_NOTCH * (dx / 120.0) if dx else 0
                if step and self._glide(self._av, self._v, -step):
                    return True
                if hstep and self._glide(self._ah, self._h, -hstep):
                    return True
        return QObject.eventFilter(self, obj, ev)


def install_smooth_scroll():
    """给当前已存在的 QScrollArea 装上缓动滚动（主窗口构造完之后调用）。"""
    n = 0
    for w in QApplication.allWidgets():
        if isinstance(w, QScrollArea):
            SmoothScroll(w)
            n += 1
    return n


# ========== Fluent 下拉选择 ==========
class FluentSelect(QPushButton):
    """白底圆角按钮 + 干净菜单的下拉选择（避免 QComboBox 的原生观感）。"""

    changed = pyqtSignal(object)

    def __init__(self, parent=None, min_width=180, height=36, font_px=13):
        super().__init__(parent)
        self._items = []
        self._index = 0
        self.setObjectName("fluentSelect")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(min_width)
        self.setFixedHeight(height)
        self.setStyleSheet(
            f"QPushButton#fluentSelect {{ background:#ffffff; border:1px solid #d7e0e8;"
            f" border-radius:8px; padding:0px; text-align:left; }}"
            f"QPushButton#fluentSelect:hover {{ border:1px solid {ACCENT}; }}"
            f"QPushButton#fluentSelect:pressed {{ background:#F4FAFF; }}")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(8)
        self._label = QLabel("")
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._label.setStyleSheet(f"color:{TEXT}; background:transparent;")
        bind_font(self._label, font_px)
        row.addWidget(self._label, 1)
        self._chev = QLabel()
        self._chev.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._chev.setFixedSize(16, 16)
        self._chev.setPixmap(svg_pixmap(ICON_CHEVRON, "#8fa3b5", 16))
        row.addWidget(self._chev, 0, Qt.AlignVCenter)

        self._menu = QMenu(self)
        self._menu.setWindowFlags(
            self._menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._menu.setAttribute(Qt.WA_TranslucentBackground, True)
        self._menu.setStyleSheet(
            f"QMenu {{ background:#ffffff; border:1px solid {BD}; border-radius:10px;"
            f" padding:6px; }}"
            f"QMenu::item {{ padding:8px 26px 8px 12px; border-radius:6px;"
            f" color:{TEXT}; font-size:13px; }}"
            f"QMenu::item:selected {{ background:{ACCENT_SOFT}; color:{ACCENT_DEEP}; }}"
            f"QMenu::item:checked {{ color:{ACCENT_DEEP}; font-weight:bold; }}"
            f"QMenu::indicator {{ width:0px; height:0px; }}")
        self.clicked.connect(self._open_menu)

    def addItem(self, text, data=None):
        act = QAction(text, self._menu)
        act.setCheckable(True)
        act.setData(data)
        act.triggered.connect(lambda _=False, a=act: self._on_pick(a))
        self._menu.addAction(act)
        self._items.append(act)
        if len(self._items) == 1:
            self.setCurrentIndex(0)
        return act

    def addItems(self, texts):
        for t in texts:
            self.addItem(t, None)

    def currentData(self):
        if 0 <= self._index < len(self._items):
            return self._items[self._index].data()
        return None

    def currentText(self):
        if 0 <= self._index < len(self._items):
            return self._items[self._index].text()
        return ""

    def findData(self, data):
        for i, act in enumerate(self._items):
            if act.data() == data:
                return i
        return -1

    def setCurrentData(self, data):
        idx = self.findData(data)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def setCurrentIndex(self, idx, emit=False):
        if not (0 <= idx < len(self._items)):
            return
        self._index = idx
        for i, act in enumerate(self._items):
            act.setChecked(i == idx)
        self._label.setText(self._items[idx].text())
        if emit:
            self.changed.emit(self._items[idx].data())

    def _on_pick(self, act):
        self.setCurrentIndex(self._items.index(act), emit=True)

    def _open_menu(self):
        self._menu.setMinimumWidth(self.width())
        self._menu.exec_(self.mapToGlobal(QPoint(0, self.height() + 4)))


# ========== Fluent 提示 / 确认框 ==========
class FluentMessageDialog(QDialog):
    """渐变底 + 线条图标 + 圆角按钮的提示/确认框。

    buttons 每项 = (文字, kind, 回传 key)，kind ∈ primary / secondary / danger。
    用户直接关窗时 clicked_key 为 None。
    """

    def __init__(self, parent, title, message, informative="", icon=None,
                 buttons=(("确定", "primary", "ok"),), default_key="ok",
                 min_width=440, icon_color="#E6A23C"):
        super().__init__(parent)
        self.clicked_key = None
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(min_width)
        self.setObjectName("fmRoot")
        self.setStyleSheet(
            f"#fmRoot {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 {BG_TOP}, stop:1 {BG_BOT}); }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(14)
        if icon:
            ic = QLabel()
            ic.setFixedSize(36, 36)
            ic.setAlignment(Qt.AlignCenter)
            ic.setPixmap(svg_pixmap(icon, icon_color, 30))
            ic.setStyleSheet("background:transparent;")
            top.addWidget(ic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(7)
        col.addWidget(label(title, 16, TEXT, medium=True, wrap=True))
        col.addWidget(label(message, 13, SUB, wrap=True))
        if informative:
            col.addWidget(label(informative, 12, MUTED, wrap=True))
        top.addLayout(col, 1)
        root.addLayout(top)
        root.addSpacing(20)

        foot = QHBoxLayout()
        foot.setSpacing(10)
        foot.addStretch(1)
        self._btns = {}
        for text, kind, key in buttons:
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(38)
            b.setMinimumWidth(104)
            bind_font(b, 13, medium=(kind == "primary"))
            b.setStyleSheet(self._btn_qss(kind))
            b.clicked.connect(lambda _=False, k=key: self._choose(k))
            foot.addWidget(b)
            self._btns[key] = b
        root.addLayout(foot)
        b0 = self._btns.get(default_key)
        if b0 is not None:
            b0.setDefault(True)
            b0.setFocus()

    @staticmethod
    def _btn_qss(kind):
        if kind == "primary":
            return (f"QPushButton {{ background:{ACCENT_DEEP}; border:none;"
                    f" border-radius:10px; padding:0 22px; color:#FFFFFF;"
                    f" font-weight:bold; }}"
                    f"QPushButton:hover {{ background:{ACCENT}; }}")
        if kind == "danger":
            return ("QPushButton { background:#FFFFFF; border:1px solid #F0D5D5;"
                    " border-radius:10px; padding:0 22px; color:#C0392B; }"
                    "QPushButton:hover { background:#FDECEC; }")
        return (f"QPushButton {{ background:#FFFFFF; border:1px solid {BD};"
                f" border-radius:10px; padding:0 22px; color:{SUB}; }}"
                f"QPushButton:hover {{ background:{LINE}; }}")

    def _choose(self, key):
        self.clicked_key = key
        self.accept()


def ask(parent, title, message, informative="", icon=ICON_WARN,
        ok_text="确定", cancel_text="取消", danger=False):
    """是 / 否 确认框，返回 True 表示点了确认。"""
    dlg = FluentMessageDialog(
        parent, title, message, informative=informative, icon=icon,
        buttons=((cancel_text, "secondary", "no"),
                 (ok_text, "danger" if danger else "primary", "yes")))
    dlg.exec_()
    return dlg.clicked_key == "yes"


def notify(parent, title, message, informative="", icon=ICON_OK, icon_color="#4CAF50"):
    """只有一个「知道了」按钮的提示框。"""
    FluentMessageDialog(parent, title, message, informative=informative,
                        icon=icon, icon_color=icon_color,
                        buttons=(("知道了", "primary", "ok"),)).exec_()


# ========== 全局样式表 ==========
APP_STYLE_SHEET = f"""
QMainWindow {{ background:{BG_TOP}; }}
QWidget {{ color:{TEXT}; }}
QLabel {{ background:transparent; }}
QToolTip {{ background:#FFFFFF; color:{TEXT}; border:1px solid {BD}; padding:6px 8px; }}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {{
    background:#FFFFFF; border:1px solid #D8E4ED; border-radius:8px;
    padding:6px 9px; selection-background-color:#CFEBFF; selection-color:{TEXT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border:1px solid {ACCENT}; }}
QLineEdit:read-only {{ background:#F7FAFC; color:{SUB}; }}
QComboBox {{
    background:#FFFFFF; border:1px solid #D8E4ED; border-radius:8px;
    padding:5px 9px; selection-background-color:#CFEBFF;
}}
QComboBox:focus {{ border:1px solid {ACCENT}; }}
QComboBox::drop-down {{ border:none; width:22px; }}
QComboBox QAbstractItemView {{
    background:#FFFFFF; border:1px solid {BD}; border-radius:8px;
    selection-background-color:{ACCENT_SOFT}; selection-color:{ACCENT_DEEP};
    outline:none;
}}
QPushButton {{
    background:#FFFFFF; border:1px solid {BD}; border-radius:8px;
    padding:7px 16px; color:{SUB};
}}
QPushButton:hover {{ background:{LINE}; }}
QPushButton:disabled {{ color:{MUTED}; background:#F5F8FA; border-color:{LINE}; }}
QCheckBox {{ color:{SUB}; spacing:7px; }}
QCheckBox::indicator {{
    width:16px; height:16px; border:1px solid #C9D6E0; border-radius:4px;
    background:#FFFFFF;
}}
QCheckBox::indicator:checked {{ background:{ACCENT_DEEP}; border:1px solid {ACCENT_DEEP}; }}
QTabWidget::pane {{
    border:1px solid {BD}; border-radius:12px; background:{CARD}; top:-1px;
}}
QTabBar::tab {{
    background:transparent; color:{SUB}; padding:9px 18px; margin-right:4px;
    border-radius:8px;
}}
QTabBar::tab:hover {{ background:{ACCENT_SOFT}; color:{ACCENT_DEEP}; }}
QTabBar::tab:selected {{ background:{ACCENT_SOFT}; color:{ACCENT_DEEP}; font-weight:bold; }}
QGroupBox {{
    background:#FFFFFF; border:1px solid {BD}; border-radius:12px;
    margin-top:16px; padding:16px 12px 10px 12px; font-weight:bold;
}}
QGroupBox::title {{
    subcontrol-origin:margin; subcontrol-position: top left;
    left:14px; padding:0 6px; color:{ACCENT_DEEP}; background:#FFFFFF;
}}
QScrollArea {{ background:transparent; border:none; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:#CBD9E4; border-radius:5px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:#AFC3D4; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:#CBD9E4; border-radius:5px; min-width:30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background:transparent; }}
"""
