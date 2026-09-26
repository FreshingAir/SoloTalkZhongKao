# -*- coding: utf-8 -*-
"""未完成考试的进度保存与恢复。

进度文件放在 history/progress_<mode>_<题目名>.json，退出时可选择续考。
"""

import os
import json
import datetime

from PyQt5.QtWidgets import QMessageBox

from ...config import DEFAULT_SCHEME, HISTORY_DIR
from ...models import PracticeSession


class ProgressMixin:
    """进度文件的读写 / 清理 / 询问与恢复。"""

    # ---------- 进度文件 ----------
    def _progress_file_path(self):
        pkg = self.pkg or getattr(self.main, "current_package", None)
        pkg_name = pkg.meta.get("name", "untitled") if pkg else "untitled"
        safe = "".join(c for c in pkg_name if c.isalnum() or c in (" ", "-", "_")).rstrip().replace(" ", "_")
        if not safe:
            safe = "untitled"
        return os.path.join(HISTORY_DIR, f"progress_{self.mode}_{safe}.json")

    def _save_progress(self):
        if not self.pkg or not self.session:
            return
        try:
            data = {
                "mode": self.mode,
                "package": self.pkg.meta.get("name", ""),
                "scheme_key": self.scheme_key,
                "phase": self._current_phase,
                "step_index": self._step_index,
                "b_step": self._b_step,
                "c_step": self._c_step,
                "mic_test_active": self._current_phase == "mic" and self._is_recording,
                "prepare_text": getattr(self, "_prepare_text", ""),
                "recordings": {
                    "partA": self.session.partA_recording,
                    "partB_secA": self.session.partB_secA_recordings,
                    "partB_secB": self.session.partB_secB_recordings,
                    "partC_secA": self.session.partC_secA_recording,
                    "partC_secB": self.session.partC_secB_recordings,
                },
                "timestamp": datetime.datetime.now().isoformat(),
            }
            os.makedirs(HISTORY_DIR, exist_ok=True)
            with open(self._progress_file_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print("保存进度失败：", e)

    def _load_progress(self):
        path = self._progress_file_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("读取进度失败：", e)
            return None

    def _clear_progress(self, delete_recordings=False):
        if delete_recordings:
            data = self._load_progress()
            if data:
                recs = data.get("recordings", {}) or {}
                paths = []
                for k in ("partA", "partC_secA"):
                    if recs.get(k):
                        paths.append(recs[k])
                for k in ("partB_secA", "partB_secB", "partC_secB"):
                    for p in (recs.get(k) or []):
                        if p:
                            paths.append(p)
                for p in paths:
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
        path = self._progress_file_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    def _describe_progress(self, data):
        mode_text = "模考" if data.get("mode") == "exam" else "练习"
        phase_map = {"mic": "试音阶段", "partA": "Part A", "partB": "Part B", "partC": "Part C"}
        phase = phase_map.get(data.get("phase", ""), data.get("phase", "未知"))
        ts = data.get("timestamp", "")
        ts_show = ts[:19].replace("T", " ") if ts else "未知"
        return f"模式：{mode_text}\n当前位置：{phase}\n保存时间：{ts_show}"

    def _check_and_prompt_progress(self):
        """进入练习前调用：有未完成进度则询问继续还是重来。"""
        saved = self._load_progress()
        if not saved:
            return
        mode_text = "模考" if self.mode == "exam" else "练习"
        desc = self._describe_progress(saved)
        msg = QMessageBox(self)
        msg.setWindowTitle("恢复进度")
        msg.setText(f"检测到未完成的{mode_text}进度：\n\n{desc}\n\n是否继续？")
        btn_continue = msg.addButton(f"继续{mode_text}", QMessageBox.AcceptRole)
        btn_restart = msg.addButton("重新开始", QMessageBox.RejectRole)
        msg.setDefaultButton(btn_continue)
        msg.exec_()
        clicked = msg.clickedButton()
        if clicked == btn_continue:
            self._restore_progress(saved)
        elif clicked == btn_restart:
            self._clear_progress(delete_recordings=True)
            self.start_btn.setText(f"开始{mode_text}")

    def _restore_progress(self, data):
        """按进度文件把考试状态机恢复到中断处。"""
        self.pkg = self.main.current_package
        self.scheme_key = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
        self.session = PracticeSession(self.pkg.meta.get("name", "练习"))
        recs = data.get("recordings", {})
        self.session.partA_recording = recs.get("partA")
        self.session.partB_secA_recordings = recs.get("partB_secA", [])
        self.session.partB_secB_recordings = recs.get("partB_secB", [])
        self.session.partC_secA_recording = recs.get("partC_secA")
        self.session.partC_secB_recordings = recs.get("partC_secB", [])

        self._exam_active = True
        self.start_btn.setEnabled(False)
        self._update_nav_buttons()
        if self.mode == "exam":
            self._enter_fullscreen()
            self._block_windows_key()

        phase = data.get("phase")
        self._step_index = data.get("step_index", 0)
        self._b_step = data.get("b_step", 0)
        self._c_step = data.get("c_step", 0)

        if phase == "mic":
            self._prepare_text = data.get("prepare_text", "")
            self._prepare_phase()
            return
        if phase == "partA":
            self._current_phase = "partA"
            self._step_index = 0
            self._exec_partA_step()
        elif phase == "partB":
            self._current_phase = "partB"
            self._run_part_b()
            self._b_step = max(0, min(self._b_step, len(self._b_moments)))
            self._exec_partB_step()
        elif phase == "partC":
            self._current_phase = "partC"
            self._c_step = 0
            self._exec_partC_step()
        else:
            self._prepare_phase()
