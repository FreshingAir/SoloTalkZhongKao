# -*- coding: utf-8 -*-
"""练习 / 模考页面主体。

本类只负责：页面骨架、状态与定时器、试音阶段、全屏与按键屏蔽、跳过/上一步；
具体考试流程与音频/录音/进度/批改分别由各 Mixin 提供。
"""

import sys
import os
import time

import pygame

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from ...config import DEFAULT_SCHEME, get_scheme
from ...models import PracticeSession
from ...win_key_blocker import WindowsKeyBlocker
from ..theme import (ACCENT, ACCENT_DEEP, ACCENT_SOFT, BG_BOT, BG_TOP, BD, CARD,
                     ICON_MIC, MUTED, SUB, TEXT, ask, bind_font,
                     secondary_button, svg_pixmap)
from .audio import AudioMixin
from .evaluation_flow import EvaluationMixin
from .part_a import PartAMixin
from .part_b import PartBMixin
from .part_c import PartCMixin
from .progress import ProgressMixin
from .recording import RecordingMixin


class PracticePage(PartAMixin, PartBMixin, PartCMixin,
                   AudioMixin, RecordingMixin, ProgressMixin, EvaluationMixin,
                   QWidget):
    """练习/模考页。mode 为 "practice"（可跳过、可上一步）或 "exam"（全屏、不可跳过）。"""

    signal_update_display = pyqtSignal(str, str)
    signal_tts_ready = pyqtSignal()
    signal_tts_next = pyqtSignal()
    # 生成完成的朗读文件；(路径, 任务代次) —— 代次用于丢弃被“跳过/上一步”取消的旧任务
    signal_tts_file_ready = pyqtSignal(str, int)
    signal_finished = pyqtSignal()

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.pkg = None
        self.session = None
        self.scheme_key = DEFAULT_SCHEME
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        except Exception as e:
            raise RuntimeError(f"pygame.mixer 初始化失败：{e}")
        self._audio_end_timer = QTimer()
        self._audio_end_timer.setInterval(100)
        self._audio_end_timer.timeout.connect(self._poll_audio_end)
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_tick)
        self._current_phase = None
        self._phase_end_time = 0
        self._timer_callback = None
        self._teardown_done = False
        self._audio_frames = []
        self._stream = None
        self._is_recording = False
        self._tts_stop_event = None
        self._tts_thread = None
        self._tts_token = 0
        self._tts_done_token = None
        self._tts_next_callback = None
        self._audio_callback = None
        self._navigating = False
        self._exam_active = False
        self.mode = "practice"
        self._win_key_blocker = None
        self._fullscreen = False
        self._vlc_parent_hwnd = None

        self._mindmap_pixmap = None

        self._step_index = 0
        self._b_moments = []
        self._b_step = 0
        self._c_step = 0

        self.setup_ui()
        self.signal_update_display.connect(self._update_display)
        self.signal_tts_ready.connect(self._prepare_tts_done)
        self.signal_tts_next.connect(self._on_tts_next)
        self.signal_tts_file_ready.connect(self._on_tts_file_ready)
        self.signal_finished.connect(self._on_exam_finished)

    def setup_ui(self):
        self.setObjectName("practiceRoot")
        self.setStyleSheet(
            f"#practiceRoot {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 {BG_TOP}, stop:1 {BG_BOT}); }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 20, 26, 18)
        layout.setSpacing(12)

        # ---------- 顶部：模式徽标 + 分制 + 返回 ----------
        top = QHBoxLayout()
        top.setSpacing(8)

        ic = QLabel()
        ic.setFixedSize(34, 34)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(svg_pixmap(ICON_MIC, ACCENT_DEEP, 22))
        ic.setStyleSheet(f"background:{ACCENT_SOFT}; border-radius:17px;")
        top.addWidget(ic)

        self.mode_label = QLabel("练习模式")
        bind_font(self.mode_label, 16, medium=True)
        self.mode_label.setStyleSheet(f"color:{TEXT};")
        top.addWidget(self.mode_label)

        self.scheme_label = QLabel("30分制")
        bind_font(self.scheme_label, 12)
        self.scheme_label.setStyleSheet(
            "#schemeChip{background:#F2F8FD;border:1px solid #DCE9F3;border-radius:9px;"
            "color:#283593;padding:4px 10px;}")
        self.scheme_label.setObjectName("schemeChip")
        top.addWidget(self.scheme_label)
        top.addStretch(1)
        btn_back = secondary_button("返回主页", self._request_back, height=34)
        top.addWidget(btn_back)
        layout.addLayout(top)

        # ---------- 主展示卡 ----------
        card = QFrame()
        card.setObjectName("practiceCard")
        card.setStyleSheet(
            f"#practiceCard {{ background:{CARD}; border:1px solid {BD};"
            f" border-radius:16px; }}")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(24, 18, 24, 20)
        cv.setSpacing(10)

        self.main_label = QLabel("准备开始练习")
        self.main_label.setAlignment(Qt.AlignCenter)
        self.main_label.setWordWrap(True)
        bind_font(self.main_label, 24, medium=True)
        self.main_label.setStyleSheet(f"color:{TEXT}; background:transparent;")

        self.sub_label = QLabel("")
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setWordWrap(True)
        bind_font(self.sub_label, 14)
        self.sub_label.setStyleSheet(f"color:{SUB}; background:transparent;")

        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        bind_font(self.countdown_label, 30, bold=True)
        self.countdown_label.setStyleSheet(
            "color:#C0392B; background:transparent;")
        self.countdown_label.hide()

        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setMinimumHeight(180)
        self.text_display.setPlaceholderText("选择题目包后，点击下方「开始练习」进入试音与正式流程。")
        bind_font(self.text_display, 16)
        self.text_display.setStyleSheet(
            "QTextEdit { background:#FBFDFF; border:1px solid #E8F1F8;"
            " border-radius:12px; padding:12px 14px; color:#22313F; }")

        self.mindmap_label = QLabel()
        self.mindmap_label.setAlignment(Qt.AlignCenter)
        self.mindmap_label.setMinimumHeight(220)
        self.mindmap_label.setStyleSheet(
            "background:#FBFDFF; border:1px solid #E8F1F8; border-radius:12px;")
        self.mindmap_label.hide()

        cv.addWidget(self.main_label)
        cv.addWidget(self.sub_label)
        cv.addWidget(self.countdown_label)
        cv.addWidget(self.text_display, 1)
        cv.addWidget(self.mindmap_label, 1)
        layout.addWidget(card, 1)

        # ---------- 底部按钮 ----------
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.start_btn = QPushButton("开始练习")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setFixedHeight(42)
        self.start_btn.setMinimumWidth(150)
        bind_font(self.start_btn, 14, medium=True)
        self.start_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT_DEEP}; border:none; border-radius:10px;"
            f" padding:0 26px; color:#FFFFFF; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{ACCENT}; }}"
            f"QPushButton:disabled {{ background:{MUTED}; }}")
        self.start_btn.clicked.connect(self.start_exam)

        self.skip_btn = QPushButton("跳过")
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.setFixedHeight(42)
        bind_font(self.skip_btn, 13, medium=True)
        self.skip_btn.setEnabled(False)
        self.skip_btn.clicked.connect(self._skip_current)

        self.prev_btn = QPushButton("上一步")
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setFixedHeight(42)
        bind_font(self.prev_btn, 13)
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._prev_current)
        self.prev_btn.setStyleSheet(
            f"QPushButton {{ background:#FFFFFF; border:1px solid {BD};"
            f" border-radius:10px; padding:0 20px; color:{SUB}; }}"
            f"QPushButton:hover {{ background:#F4F9FD; color:{TEXT}; }}"
            f"QPushButton:disabled {{ color:{MUTED}; background:#F5F8FA; }}")

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.prev_btn)
        btn_layout.addWidget(self.skip_btn)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self._update_skip_label()

    # ---------- 思维导图 ----------
    def _show_mindmap(self):
        mm = (self.pkg.partC_secA.get("mindmap_image")
              if self.pkg and self.pkg.partC_secA else None)
        if not mm or not os.path.isfile(mm):
            self.mindmap_label.hide()
            self.text_display.show()
            self._mindmap_pixmap = None
            return
        pix = QPixmap(mm)
        if pix.isNull():
            self.mindmap_label.hide()
            self.text_display.show()
            self._mindmap_pixmap = None
            return
        self._mindmap_pixmap = pix
        self._rescale_mindmap()
        self.mindmap_label.show()
        self.text_display.show()

    def _hide_mindmap(self):
        self.mindmap_label.hide()

    def _rescale_mindmap(self):
        if not self._mindmap_pixmap:
            return
        w = max(self.mindmap_label.width(), 600)
        h = max(self.mindmap_label.height(), 220)
        self.mindmap_label.setPixmap(
            self._mindmap_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_mindmap()

    # ---------- 退出 / 收尾 ----------
    def _request_back(self):
        if self.request_exit():
            self.main.go_to(self.main.home_page)

    def _confirm_abort(self):
        return ask(
            self, "确认退出",
            "中途退出将保存当前进度与已录制音频，下次可从本次位置继续。",
            informative="确定要退出吗？", ok_text="退出", cancel_text="继续练习")

    def request_exit(self):
        if self._exam_active:
            if not self._confirm_abort():
                return False
        self._teardown_exam()
        return True

    def _teardown_exam(self):
        self._teardown_done = True
        self.timer.stop()
        self._cancel_tts()
        self._stop_video()
        try:
            pygame.mixer.music.set_volume(1.0)
        except Exception:
            pass
        self._finalize_current_recording()
        if self._exam_active and self._current_phase:
            self._save_progress()
        self.stop_recording()
        self._reset_page_state()

    def _reset_page_state(self):
        self._exam_active = False
        self._teardown_done = False
        self._navigating = False
        self._current_phase = None
        self._step_index = 0
        self._b_step = 0
        self._c_step = 0
        self._b_moments = []
        self._timer_callback = None
        self._tts_token += 1          # 让在途的朗读任务作废
        self._tts_done_token = None
        self._tts_next_callback = None
        self._audio_callback = None
        self._is_recording = False
        self._audio_frames = []
        self.countdown_label.hide()
        self._stop_video()
        self._hide_mindmap()
        self.text_display.show()
        self.main_label.setText("准备开始" + ("模考" if self.mode == "exam" else "练习"))
        self.sub_label.setText("")
        self.text_display.clear()
        self.start_btn.setEnabled(True)
        self._update_nav_buttons()
        self._restore_window()
        self._unblock_windows_key()

    def abort_exam(self):
        self._teardown_exam()

    # ---------- Windows 键 ----------
    def _block_windows_key(self):
        if sys.platform != "win32":
            return
        try:
            if self._win_key_blocker is None:
                self._win_key_blocker = WindowsKeyBlocker()
            self._win_key_blocker.install()
        except Exception as e:
            print("Windows 键屏蔽安装失败：", e)
            self._win_key_blocker = None

    def _unblock_windows_key(self):
        if self._win_key_blocker is not None:
            try:
                self._win_key_blocker.uninstall()
            except Exception:
                pass
            self._win_key_blocker = None

    # ---------- 全屏 ----------
    def _enter_fullscreen(self):
        if sys.platform == "win32":
            self.main.showFullScreen()
        else:
            self.main.showMaximized()
        self._fullscreen = True

    def _restore_window(self):
        if self._fullscreen:
            self.main.showNormal()
            self._fullscreen = False

    # ---------- 按钮状态 ----------
    def _update_skip_label(self):
        if self.mode == "exam":
            return
        if self._is_recording:
            self.skip_btn.setText("结束录音")
            self.skip_btn.setStyleSheet(
                "QPushButton { background:#C0392B; color:white; border:none;"
                " border-radius:10px; padding:0 20px; font-weight:bold; }"
                f"QPushButton:disabled {{ background:#DDE6EE; color:{MUTED}; }}")
        else:
            self.skip_btn.setText("跳过")
            self.skip_btn.setStyleSheet(
                "QPushButton { background:#F39C12; color:white; border:none;"
                " border-radius:10px; padding:0 20px; font-weight:bold; }"
                f"QPushButton:disabled {{ background:#DDE6EE; color:{MUTED}; }}")

    def _update_nav_buttons(self):
        if self.mode == "exam":
            self.skip_btn.setVisible(False)
            self.prev_btn.setVisible(False)
            return
        self.skip_btn.setVisible(True)
        self.prev_btn.setVisible(True)
        active = getattr(self, "_exam_active", False)
        rec = getattr(self, "_is_recording", False)
        self.skip_btn.setEnabled(active)
        can_prev = active and not rec and self._current_phase in ("partA", "partB", "partC")
        self.prev_btn.setEnabled(can_prev)
        self._update_skip_label()

    # ---------- 开始考试 ----------
    def set_mode(self, mode):
        self.mode = mode
        self.start_btn.setText("开始练习" if mode == "practice" else "开始模考")
        self.mode_label.setText("练习模式" if mode == "practice" else "模考模式")
        self.mode_label.setStyleSheet(
            f"color:{TEXT if mode == 'practice' else '#8a6d1f'};")
        try:
            pkg = self.main.current_package
            self.scheme_label.setText(
                get_scheme(str(pkg.meta.get("scheme", DEFAULT_SCHEME)))["name"])
        except Exception:
            pass
        self._reset_page_state()

    def start_exam(self):
        self.pkg = self.main.current_package
        self.scheme_key = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
        self.scheme_label.setText(get_scheme(self.scheme_key)["name"])
        self.session = PracticeSession(self.pkg.meta.get("name", "练习"))
        self.start_btn.setEnabled(False)
        self._exam_active = True
        self._update_nav_buttons()
        if self.mode == "exam":
            self._enter_fullscreen()
            self._block_windows_key()
        self._prepare_phase()

    # ---------- 试音阶段 ----------
    def _prepare_phase(self):
        self._current_phase = "mic"
        author = self.pkg.meta.get("author", "")
        author_text = f"题目作者：{author}" if author else "题目作者：未知"
        scheme_name = get_scheme(self.scheme_key)["name"]
        self._prepare_text = (f"{author_text}\n评分分制：{scheme_name}\n\n"
                              f"生活就像海洋，只有意志坚强的人才能到达彼岸。\n"
                              f"This is an apple, I like apples, apples are good for our health.")
        self.signal_update_display.emit("准备阶段", self._prepare_text)
        self._start_tts(
            "生活就像海洋，只有意志坚强的人才能到达彼岸。 This is an apple, I like apples, apples are good for our health.",
            self.signal_tts_ready,
            force_fallback=True,
        )

    def _prepare_tts_done(self):
        self._mic_test()

    def _mic_test(self):
        test_text = self._prepare_text + "\n\n请说话，录音10秒..."
        self.signal_update_display.emit("麦克风测试", test_text)
        self._start_recording()
        self._set_timer(10, self._mic_test_playback)

    def _mic_test_playback(self):
        if self._current_phase != "mic":
            return
        self._stop_recording()
        test_path = self._save_recording("mic_test")
        if test_path and os.path.exists(test_path):
            self._play_file(test_path)
            reply = ask(
                self, "麦克风测试", "录音回放中，麦克风是否正常？",
                informative="选择「正常」将开始正式考试；「不正常」会重新试音。",
                ok_text="正常", cancel_text="不正常")
            self._stop_video()
            try:
                os.remove(test_path)
            except Exception:
                pass
            if reply:
                self.signal_update_display.emit("准备开始", "即将开始" + ("模考" if self.mode == "exam" else "练习"))
                self._set_timer(3, self._run_part_a)
            else:
                self._mic_test()
        else:
            ask(self, "录音失败", "没有录到声音，请检查麦克风设备。",
                ok_text="重新试音", cancel_text="关闭")
            self._mic_test()

    # ---------- 计时器 ----------
    def _set_timer(self, seconds, callback=None):
        self._phase_end_time = time.time() + seconds
        self._timer_callback = callback
        self.countdown_label.show()
        self.timer.start(100)

    def _on_tick(self):
        if self._teardown_done:
            return
        remaining = max(0, int(self._phase_end_time - time.time()))
        self.countdown_label.setText(f"剩余 {remaining} 秒")
        if time.time() >= self._phase_end_time:
            self.timer.stop()
            self.countdown_label.hide()
            if self._timer_callback:
                cb = self._timer_callback
                self._timer_callback = None
                cb()
            else:
                self._next_step_default()

    def _next_step_default(self):
        """计时结束且未指定回调时，按当前 Part 自动进入下一步。"""
        if self._current_phase == "partA":
            self._next_partA_step()
        elif self._current_phase == "partB":
            self._next_partB_step()
        elif self._current_phase == "partC":
            self._next_partC_step()

    @pyqtSlot(str, str)
    def _update_display(self, main, sub):
        self.main_label.setText(main)
        # 题目内容只在下方的文本框中展示，避免与上方重复；sub_label 仅用于录音提示
        self.sub_label.setText("")
        self.text_display.setPlainText(sub)

    # ---------- 跳过 / 上一步（仅练习模式） ----------
    def _skip_current(self):
        if self.mode != "practice":
            return
        if self._current_phase not in ("mic", "partA", "partB", "partC"):
            return
        if self._navigating:
            return
        self._navigating = True
        try:
            self.timer.stop()
            self.countdown_label.hide()
            self._timer_callback = None
            self._cancel_tts()
            self._tts_next_callback = None
            try:
                self.signal_tts_next.disconnect()
            except Exception:
                pass
            self._finalize_current_recording()
            self._stop_video()
            self._audio_callback = None

            if self._current_phase == "mic":
                self._stop_recording()
                self._stop_video()
                self._run_part_a()
                return
            if self._current_phase == "partA":
                self._next_partA_step()
            elif self._current_phase == "partB":
                self._next_partB_step()
            elif self._current_phase == "partC":
                self._next_partC_step()
        finally:
            self._navigating = False

    def _prev_current(self):
        if self.mode != "practice":
            return
        if self._current_phase not in ("partA", "partB", "partC"):
            return
        if self._is_recording or self._navigating:
            return
        self._navigating = True
        try:
            self.timer.stop()
            self.countdown_label.hide()
            self._timer_callback = None
            self._cancel_tts()
            self._stop_video()
            self._audio_callback = None

            if self._current_phase == "partA":
                if self._step_index > 0:
                    self._step_index -= 1
                    self._exec_partA_step()
            elif self._current_phase == "partB":
                if self._b_step > 0:
                    self._b_step -= 1
                    self._exec_partB_step()
            elif self._current_phase == "partC":
                if self._c_step > 0:
                    self._c_step -= 1
                    self._exec_partC_step()
        finally:
            self._navigating = False
