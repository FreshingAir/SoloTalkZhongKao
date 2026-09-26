# -*- coding: utf-8 -*-
"""录音：麦克风采集与 wav 落盘。"""

import os
import wave
import datetime

import numpy as np
import sounddevice as sd

from ...config import RECORDINGS_DIR, SAMPLE_RATE


class RecordingMixin:
    """把麦克风输入累积成帧，结束时写成 16bit/16kHz 单声道 wav。"""

    def _start_recording(self):
        self._audio_frames = []
        self._is_recording = True
        self._update_skip_label()
        self._update_nav_buttons()

        def callback(indata, frames, time_info, status):
            if self._is_recording:
                self._audio_frames.append(indata.copy())

        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                      dtype='int16', callback=callback)
        self._stream.start()
        self.sub_label.setText(self.sub_label.text() + "\n🔴 录音中...")

    def _stop_recording(self):
        self._is_recording = False
        self._update_skip_label()
        self._update_nav_buttons()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def stop_recording(self):
        self._stop_recording()

    def _save_recording(self, label):
        """把当前缓冲写盘，返回文件路径；无音频数据时返回 None。"""
        package_name = self.pkg.meta.get('name', 'unknown') if self.pkg else 'unknown'
        safe_name = "".join(c for c in package_name
                            if c.isalnum() or c in (' ', '-', '_')).rstrip() or "untitled"
        base_dir = os.path.join(RECORDINGS_DIR, safe_name)
        os.makedirs(base_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{safe_name}_{label}_{ts}.wav"
        path = os.path.join(base_dir, fname)
        if self._audio_frames:
            data = np.concatenate(self._audio_frames)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(data.astype(np.int16).tobytes())
            return path
        return None

    def _finalize_current_recording(self):
        """中途退出时，保住 Part A 已录到一半的内容。"""
        if not self._is_recording:
            return
        self._stop_recording()
        phase = self._current_phase
        if phase == "partA":
            self.session.partA_recording = self._save_recording("PartA")
