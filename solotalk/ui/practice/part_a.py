# -*- coding: utf-8 -*-
"""Part A 模仿朗读流程（听指令 → 听短文 → 准备 → 朗读 → 录音结束）。"""


class PartAMixin:
    def _run_part_a(self):
        self._current_phase = "partA"
        self._step_index = 0
        self._exec_partA_step()

    def _exec_partA_step(self):
        """Part A 的 5 个步骤，按 _step_index 顺序推进。"""
        self._update_nav_buttons()
        idx = self._step_index
        if idx == 0:
            self.signal_update_display.emit(
                "Part A 模仿朗读",
                "听以下短文一遍，你有50秒钟的时间准备，然后模仿朗读。")
            self._start_tts("听以下短文一遍，你有50秒钟的时间准备，然后模仿朗读。",
                            self.signal_tts_next)
            self._set_tts_callback(self._next_partA_step)
        elif idx == 1:
            self.signal_update_display.emit("请认真听短文，注意语音语调。", "")
            self._play_audio_by_source(
                self.pkg.partA_audio_source_type,
                self.pkg.partA_tts_text,
                self.pkg.partA_audio_path,
                self._next_partA_step)
        elif idx == 2:
            self.signal_update_display.emit("请准备朗读。", "")
            self._set_timer(50)
        elif idx == 3:
            self.signal_update_display.emit("请开始模仿朗读 (60秒)。", "")
            self._start_recording()
            self._set_timer(60)
        else:
            self._stop_recording()
            self.session.partA_recording = self._save_recording("PartA")
            self._run_part_b()

    def _next_partA_step(self):
        self._step_index += 1
        self._exec_partA_step()
