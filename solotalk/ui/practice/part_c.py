# -*- coding: utf-8 -*-
"""Part C 信息转述及询问流程。

SecA 转述：指令 → 读要点(15s) → 两遍听力 → 准备(50s) → 转述录音(60s)
SecB 询问：指令 → 每题 准备(15s) + 提问录音(8s)
"""


class PartCMixin:
    def _run_part_c(self):
        self._current_phase = "partC"
        self._c_step = 0
        self._exec_partC_step()

    def _exec_partC_step(self):
        self._update_nav_buttons()
        s = self._c_step

        if s not in (1, 2, 3, 4, 5, 6):
            self._hide_mindmap()

        if s == 0:
            self.signal_update_display.emit(
                "Part C 信息转述及询问",
                "你将听到一段介绍。请根据所听到的内容和提示，在60秒钟内转述内容，包含全部要点。")
            self._speak_instruction(
                "你将听到一段介绍。请根据所听到的内容和提示，在60秒钟内转述内容，包含全部要点。",
                self._next_partC_step)
        elif s == 1:
            self.signal_update_display.emit("阅读要点提示 (15秒)",
                                            self.pkg.partC_secA["key_points"])
            self._show_mindmap()
            self._set_timer(15)
        elif s == 2:
            secA = self.pkg.partC_secA
            self.signal_update_display.emit("听材料第一遍", secA["key_points"])
            self._show_mindmap()
            self._play_audio_by_source(
                secA.get("audio_source_type"), secA.get("tts_text"),
                secA.get("audio_path"), self._next_partC_step)
        elif s == 3:
            self._show_mindmap()
            self._set_timer(1)
        elif s == 4:
            secA = self.pkg.partC_secA
            self.signal_update_display.emit("听材料第二遍", secA["key_points"])
            self._show_mindmap()
            self._play_audio_by_source(
                secA.get("audio_source_type"), secA.get("tts_text"),
                secA.get("audio_path"), self._next_partC_step)
        elif s == 5:
            self.signal_update_display.emit("准备转述 (50秒)", self.pkg.partC_secA["key_points"])
            self._show_mindmap()
            self._set_timer(50)
        elif s == 6:
            self.signal_update_display.emit("请开始转述 (60秒)", self.pkg.partC_secA["key_points"])
            self._show_mindmap()
            self._start_recording()
            self._set_timer(60, self._finish_retelling)
        elif s == 7:
            self._hide_mindmap()
            secB = self.pkg.partC_secB
            self.signal_update_display.emit(
                "询问信息",
                f"{secB.get('situation', '')}\n你希望了解更多信息，请根据以下提示提两个问题。")
            self._speak_instruction(
                "你希望了解更多信息，请根据以下提示提两个问题。每个问题有15秒钟的准备时间和8秒钟的提问时间。",
                lambda: self._show_secB_prepare(0))
        else:
            self._hide_mindmap()
            self._stop_recording()
            self.session.partC_secA_recording = self._save_recording("PartC_Retelling")
            self.signal_finished.emit()

    def _finish_retelling(self):
        self._stop_recording()
        self.session.partC_secA_recording = self._save_recording("PartC_Retelling")
        self._c_step = 7
        self._exec_partC_step()

    # ---------- SecB 逐题提问 ----------
    def _show_secB_prepare(self, idx):
        questions = self.pkg.partC_secB.get("questions", [])
        if idx >= len(questions):
            self.signal_finished.emit()
            return
        q = questions[idx]
        self.signal_update_display.emit(f"准备提问 {idx + 1} (15秒)", q.get("cn_prompt", ""))
        self._set_timer(15, lambda: self._record_secB_q(idx))

    def _record_secB_q(self, idx):
        self.signal_update_display.emit(
            f"请提问 {idx + 1} (8秒)",
            self.pkg.partC_secB["questions"][idx].get("cn_prompt", ""))
        self._start_recording()
        self._set_timer(8, lambda: self._finish_secB_q(idx))

    def _finish_secB_q(self, idx):
        self._stop_recording()
        path = self._save_recording(f"PartC_SecB_Q{idx + 1}")
        if path:
            while len(self.session.partC_secB_recordings) <= idx:
                self.session.partC_secB_recordings.append(None)
            self.session.partC_secB_recordings[idx] = path
        nxt = idx + 1
        if nxt < len(self.pkg.partC_secB.get("questions", [])):
            self._show_secB_prepare(nxt)
        else:
            self.signal_finished.emit()

    def _next_partC_step(self):
        self._c_step += 1
        self._exec_partC_step()
