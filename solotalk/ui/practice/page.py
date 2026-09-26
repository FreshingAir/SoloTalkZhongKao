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
    signal_tts_file_ready = pyqtSignal(str)
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
        layout = QVBoxLayout()
        self.main_label = QLabel("准备开始练习")
        self.main_label.setAlignment(Qt.AlignCenter)
        self.main_label.setStyleSheet("font-size:28px; font-weight:bold;")
        self.sub_label = QLabel("")
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setStyleSheet("font-size:18px; color:gray;")
        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("font-size:20px; color:#e74c3c; font-weight:bold;")
        self.countdown_label.hide()
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setStyleSheet("font-size:18px;")
        self.text_display.setMaximumHeight(180)

        self.mindmap_label = QLabel()
        self.mindmap_label.setAlignment(Qt.AlignCenter)
        self.mindmap_label.setMinimumHeight(220)
        self.mindmap_label.setStyleSheet("background:#fdfdfd; border:1px solid #e0e0e0;")
        self.mindmap_label.hide()

        layout.addWidget(self.main_label)
        layout.addWidget(self.sub_label)
        layout.addWidget(self.countdown_label)
        layout.addWidget(self.text_display)
        layout.addWidget(self.mindmap_label, 1)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始练习")
        self.start_btn.clicked.connect(self.start_exam)
        self.skip_btn = QPushButton("⏭  跳过")
        self.skip_btn.setStyleSheet(
            "QPushButton { background:#f39c12; color:white; border:1px solid #e67e22; font-weight:bold; }"
            "QPushButton:disabled { background:#bdc3c7; color:#ecf0f1; }"
        )
        self.skip_btn.setEnabled(False)
        self.skip_btn.clicked.connect(self._skip_current)
        self.prev_btn = QPushButton("⏮  上一步")
        self.prev_btn.setStyleSheet(
            "QPushButton { background:#3498db; color:white; border:1px solid #2980b9; font-weight:bold; }"
            "QPushButton:disabled { background:#bdc3c7; color:#ecf0f1; }"
        )
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._prev_current)
        btn_back = QPushButton("返回主页")
        btn_back.clicked.connect(self._request_back)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.prev_btn)
        btn_layout.addWidget(self.skip_btn)
        btn_layout.addWidget(btn_back)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    # ---------- 思维导图 ----------
    def _show_mindmap(self):
        mm = (self.pkg.partC_secA.get("mindmap_image")
              if self.pkg and self.pkg.partC_secA else None)
        if not mm or not os.path.isfile(mm):
            self.mindmap_label.hide()
            self._mindmap_pixmap = None
            return
        pix = QPixmap(mm)
        if pix.isNull():
            self.mindmap_label.hide()
            self._mindmap_pixmap = None
            return
        self._mindmap_pixmap = pix
        self._rescale_mindmap()
        self.mindmap_label.show()

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
        reply = QMessageBox.warning(
            self, "确认退出",
            "中途退出将保存当前进度与已录制音频，下次可从本次位置继续。\n确定要退出吗？",
            QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes

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
        self._tts_next_callback = None
        self._audio_callback = None
        self._is_recording = False
        self._audio_frames = []
        self.countdown_label.hide()
        self._stop_video()
        self._hide_mindmap()
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
            self.skip_btn.setText("⏹  结束录音")
            self.skip_btn.setStyleSheet(
                "QPushButton { background:#e74c3c; color:white; border:1px solid #c0392b; font-weight:bold; }"
                "QPushButton:disabled { background:#bdc3c7; color:#ecf0f1; }"
            )
        else:
            self.skip_btn.setText("⏭  跳过")
            self.skip_btn.setStyleSheet(
                "QPushButton { background:#f39c12; color:white; border:1px solid #e67e22; font-weight:bold; }"
                "QPushButton:disabled { background:#bdc3c7; color:#ecf0f1; }"
            )

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
        self._reset_page_state()

    def start_exam(self):
        self.pkg = self.main.current_package
        self.scheme_key = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
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
            reply = QMessageBox.question(self, "麦克风测试", "录音回放中，麦克风是否正常？",
                                         QMessageBox.Yes | QMessageBox.No)
            self._stop_video()
            try:
                os.remove(test_path)
            except Exception:
                pass
            if reply == QMessageBox.Yes:
                self.signal_update_display.emit("准备开始", "即将开始" + ("模考" if self.mode == "exam" else "练习"))
                self._set_timer(3, self._run_part_a)
            else:
                self._mic_test()
        else:
            QMessageBox.warning(self, "错误", "录音失败，请检查设备")
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
        self.countdown_label.setText(f"剩余时间：{remaining} 秒")
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
        self.sub_label.setText(sub)
        self.text_display.setPlainText(sub if sub else main)

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
