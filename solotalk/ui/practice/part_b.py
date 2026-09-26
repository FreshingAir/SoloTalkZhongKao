# -*- coding: utf-8 -*-
"""Part B 信息获取流程。

先把整段考试拆成一串「时刻」（_b_moments），再按时序遍历：
指令 → SecA 阅题/两遍听力/逐题作答 → SecB 指令/阅题/两遍听力/逐题作答。
"""


class PartBMixin:
    def _run_part_b(self):
        self._current_phase = "partB"
        self._b_step = 0
        self._b_moments = []
        self._b_moments.append({"t": "intro",
                                "main": "Part B 信息获取",
                                "sub": "听三段对话，每段播放两遍。各段播放前你有10秒钟的阅题时间。"})
        for seg_idx, seg in enumerate(self.pkg.partB_secA):
            self._b_moments.append({
                "t": "secA_prep", "seg": seg_idx,
                "main": f"对话 {seg_idx + 1} 阅题 (10秒)",
                "sub": self._format_secA_questions(seg),
            })
            self._b_moments.append({
                "t": "secA_play1", "seg": seg_idx,
                "main": f"对话 {seg_idx + 1} 第一遍", "sub": "",
            })
            self._b_moments.append({
                "t": "secA_gap", "seg": seg_idx,
                "main": f"对话 {seg_idx + 1} 第二遍", "sub": "",
            })
            self._b_moments.append({
                "t": "secA_play2", "seg": seg_idx,
                "main": f"对话 {seg_idx + 1} 第二遍", "sub": "",
            })
            for q_idx, q in enumerate(seg.get("questions", [])[:2]):
                self._b_moments.append({
                    "t": "secA_q", "seg": seg_idx, "q": q_idx,
                    "main": f"回答问题 {q_idx + 1}",
                    "sub": self._format_secA_q(q),
                })
        secB = self.pkg.partB_secB
        self._b_moments.append({
            "t": "secB_intro",
            "main": "Section B 回答问题",
            "sub": "听下面一段录音，录音播放两遍。现在你有15秒钟的时间阅读这四个问题。",
        })
        self._b_moments.append({
            "t": "secB_prep",
            "main": "阅读问题 (15秒)",
            "sub": self._format_secB_questions(secB),
        })
        self._b_moments.append({"t": "secB_play1", "main": "听独白第一遍", "sub": ""})
        self._b_moments.append({"t": "secB_play2", "main": "听独白第二遍", "sub": ""})
        for q_idx in range(len(secB.get("questions", []))):
            self._b_moments.append({
                "t": "secB_q", "q": q_idx,
                "main": f"回答问题 {q_idx + 1}",
                "sub": secB["questions"][q_idx].get("question_text", ""),
            })
        self._exec_partB_step()

    # ---------- 题目文本排版 ----------
    def _format_secA_questions(self, seg):
        lines = []
        for i, q in enumerate(seg.get("questions", [])[:2]):
            lines.append(f"问题{i + 1}: {q.get('question_text', '')}")
            opts = q.get("options", ["", "", ""])
            if len(opts) >= 3:
                lines.append(f"A. {opts[0]}\nB. {opts[1]}\nC. {opts[2]}")
        return "\n".join(lines)

    def _format_secA_q(self, q):
        opts = q.get("options", ["", "", ""])
        return (f"问题: {q.get('question_text', '')}\n"
                f"A. {opts[0] if len(opts) > 0 else ''}\n"
                f"B. {opts[1] if len(opts) > 1 else ''}\n"
                f"C. {opts[2] if len(opts) > 2 else ''}")

    def _format_secB_questions(self, secB):
        return "\n".join(f"{i + 1}. {q.get('question_text', '')}"
                         for i, q in enumerate(secB.get("questions", [])))

    # ---------- 时刻分发 ----------
    def _exec_partB_step(self):
        self._update_nav_buttons()
        if self._b_step >= len(self._b_moments):
            self._run_part_c()
            return
        m = self._b_moments[self._b_step]
        t = m["t"]

        if t == "intro":
            self.signal_update_display.emit(m["main"], m["sub"])
            self._speak_instruction(m["sub"], self._next_partB_step)

        elif t == "secA_prep":
            self.signal_update_display.emit(m["main"], m["sub"])
            self._set_timer(10)

        elif t == "secA_play1":
            seg = self.pkg.partB_secA[m["seg"]]
            self.signal_update_display.emit(m["main"], "")
            self._play_audio_by_source(
                seg.get("audio_source_type"), seg.get("tts_text"),
                seg.get("audio_path"), self._next_partB_step)

        elif t == "secA_gap":
            self._set_timer(1)

        elif t == "secA_play2":
            seg = self.pkg.partB_secA[m["seg"]]
            self.signal_update_display.emit(m["main"], "")
            self._play_audio_by_source(
                seg.get("audio_source_type"), seg.get("tts_text"),
                seg.get("audio_path"), self._next_partB_step)

        elif t == "secA_q":
            self.signal_update_display.emit(m["main"], m["sub"])
            self._play_beep(self._record_secA_answer, seg=m["seg"], q=m["q"])

        elif t == "secB_intro":
            self.signal_update_display.emit(m["main"], m["sub"])
            self._set_timer(2)

        elif t == "secB_prep":
            self.signal_update_display.emit(m["main"], m["sub"])
            self._set_timer(15)

        elif t == "secB_play1":
            self.signal_update_display.emit(m["main"], "")
            secB = self.pkg.partB_secB
            self._play_audio_by_source(
                secB.get("audio_source_type"), secB.get("tts_text"),
                secB.get("audio_path"), self._next_partB_step)

        elif t == "secB_play2":
            self.signal_update_display.emit(m["main"], "")
            secB = self.pkg.partB_secB
            self._play_audio_by_source(
                secB.get("audio_source_type"), secB.get("tts_text"),
                secB.get("audio_path"), self._next_partB_step)

        elif t == "secB_q":
            q = self.pkg.partB_secB["questions"][m["q"]]
            self.signal_update_display.emit(m["main"], q.get("question_text", ""))
            self._play_beep(self._record_secB_answer, q=m["q"])

    # ---------- 逐题作答（8 秒） ----------
    def _record_secA_answer(self, seg, q):
        self.signal_update_display.emit(f"请回答 (8秒)", "")
        self._start_recording()
        self._set_timer(8, lambda: self._finish_secA_answer(seg, q))

    def _finish_secA_answer(self, seg, q):
        self._stop_recording()
        path = self._save_recording(f"PartB_SecA{seg + 1}_Q{q + 1}")
        if path:
            while len(self.session.partB_secA_recordings) <= seg * 2 + q:
                self.session.partB_secA_recordings.append(None)
            self.session.partB_secA_recordings[seg * 2 + q] = path
        self._next_partB_step()

    def _record_secB_answer(self, q):
        self.signal_update_display.emit(f"请回答 (8秒)", "")
        self._start_recording()
        self._set_timer(8, lambda: self._finish_secB_answer(q))

    def _finish_secB_answer(self, q):
        self._stop_recording()
        path = self._save_recording(f"PartB_SecB_Q{q + 1}")
        if path:
            while len(self.session.partB_secB_recordings) <= q:
                self.session.partB_secB_recordings.append(None)
            self.session.partB_secB_recordings[q] = path
        self._next_partB_step()

    def _next_partB_step(self):
        self._b_step += 1
        self._exec_partB_step()
