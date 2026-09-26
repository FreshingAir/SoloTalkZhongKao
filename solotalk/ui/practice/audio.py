# -*- coding: utf-8 -*-
"""音频播放与 TTS：负责“放音”这一件事，不含考试流程。"""

import os
import time
import threading

import pygame

from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer

from ...paths import resolve_resource_file
from ...tts import (EDGE_TTS_AVAILABLE, TTS_EDGE_DIR,
                    speak_blocking, tts_generate_audio)


class AudioMixin:
    """TTS 异步生成 + pygame.mixer 播放 + 播放结束回调。"""

    # ---------- TTS 管理 ----------
    def _start_tts(self, text, signal=None, force_fallback=False):
        self._cancel_tts()
        self._tts_stop_event = threading.Event()
        self._tts_thread = threading.Thread(
            target=self._tts_runner, args=(text, signal, force_fallback))
        self._tts_thread.daemon = True
        self._tts_thread.start()

    def _tts_runner(self, text, signal, force_fallback=False):
        """优先用 edge-tts 生成 mp3 再播放，失败则回退系统语音（阻塞朗读）。"""
        if not force_fallback and EDGE_TTS_AVAILABLE and text and text.strip():
            try:
                os.makedirs(TTS_EDGE_DIR, exist_ok=True)
            except Exception:
                pass
            out = os.path.join(TTS_EDGE_DIR,
                               f"tts_{int(time.time() * 1000)}_{threading.get_ident()}.mp3")
            if tts_generate_audio(text, out):
                self._tts_done_signal = signal
                self._tts_tmp_file = out
                self.signal_tts_file_ready.emit(out)
                return
        speak_blocking(text, self._tts_stop_event)
        if signal:
            signal.emit()

    def _on_tts_file_ready(self, path):
        if self._teardown_done:
            return
        if not path or not os.path.exists(path):
            sig = getattr(self, "_tts_done_signal", None)
            self._tts_done_signal = None
            if sig:
                sig.emit()
            return
        self._audio_callback = self._tts_file_done
        self._play_file(path)

    def _tts_file_done(self):
        sig = getattr(self, "_tts_done_signal", None)
        self._tts_done_signal = None
        tmp = getattr(self, "_tts_tmp_file", None)
        self._tts_tmp_file = None
        if tmp:
            try:
                os.remove(tmp)
            except Exception:
                pass
        if sig:
            sig.emit()

    def _cancel_tts(self):
        if self._tts_stop_event:
            self._tts_stop_event.set()
            self._tts_stop_event = None

    def _set_tts_callback(self, callback):
        self._tts_next_callback = callback
        try:
            self.signal_tts_next.disconnect()
        except Exception:
            pass
        self.signal_tts_next.connect(self._on_tts_next)

    def _on_tts_next(self):
        if self._teardown_done:
            return
        if self._tts_next_callback:
            cb = self._tts_next_callback
            self._tts_next_callback = None
            cb()

    # ---------- 通用音频 ----------
    def _speak_instruction(self, text, on_done):
        """播放一句口头指令，播完后执行 on_done。

        注意：这里必须把 signal_tts_next 作为“播放完成信号”传给 _start_tts。
        真实实现中 `_start_tts(text, None)` 播放结束后不会发出任何信号，
        会导致考试流程永久停在该步骤，所以引导语一律走本方法。
        """
        self._set_tts_callback(on_done)
        self._start_tts(text, self.signal_tts_next)

    def _play_audio_by_source(self, source_type, tts_text, audio_path, callback):
        """按题目包的音频来源（tts / audio）播放，结束后调用 callback。"""
        if source_type == "tts":
            self._set_tts_callback(callback)
            self._start_tts(tts_text, self.signal_tts_next)
        else:
            if audio_path and os.path.exists(audio_path):
                self._audio_callback = callback
                self._play_file(audio_path)
            else:
                QMessageBox.warning(self, "警告", "音频文件不存在，跳过")
                callback()

    def _play_beep(self, callback, **kwargs):
        """播放答题提示音后触发 callback（提示音缺失时立即触发）。"""
        path = os.path.join("material", "di.mp3")
        resolved = resolve_resource_file(path)
        fired = [False]

        def fire_once():
            if not fired[0]:
                fired[0] = True
                callback(**kwargs)

        if resolved and os.path.isfile(resolved):
            self._play_file(resolved, on_end=None)
            QTimer.singleShot(1000, fire_once)
        else:
            callback(**kwargs)

    def _stop_video(self):
        try:
            self._audio_end_timer.stop()
        except Exception:
            pass
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

    def _play_file(self, path, on_end=None):
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play()
            self._audio_callback = on_end if on_end is not None else self._audio_callback
            self._audio_end_timer.start()
        except Exception as e:
            print("播放失败：", e)
            cb = self._audio_callback
            self._audio_callback = None
            if cb:
                QTimer.singleShot(0, cb)

    def _poll_audio_end(self):
        """定时检查 pygame 是否播完，播完则触发回调。"""
        if self._teardown_done:
            self._audio_end_timer.stop()
            return
        try:
            busy = pygame.mixer.music.get_busy()
        except Exception:
            busy = False
        if not busy:
            self._audio_end_timer.stop()
            if self._audio_callback:
                cb = self._audio_callback
                self._audio_callback = None
                QTimer.singleShot(0, cb)
