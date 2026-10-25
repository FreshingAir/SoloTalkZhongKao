# -*- coding: utf-8 -*-
"""考试结束后的批改与历史记录落盘。"""

import os
import json
import shutil
import datetime

from ...asr import load_vosk_model
from ...config import HISTORY_DIR
from ...evaluation import evaluate_recordings
from ...scoring import compute_scores
from ..theme import ICON_OK, ICON_WARN, notify


class EvaluationMixin:
    def _on_exam_finished(self):
        self._exam_active = False
        self.start_btn.setEnabled(True)
        self._stop_video()
        self._update_nav_buttons()
        self._restore_window()
        self._unblock_windows_key()
        self._clear_progress()
        self.run_evaluation()

    def run_evaluation(self):
        """加载 Vosk 模型并批改；模型不可用时只保存录音。"""
        vosk_model = load_vosk_model()
        if not vosk_model:
            self._save_history()
            notify(self, "无法自动批改",
                   "Vosk 离线识别模型不可用，录音已保存，稍后可在历史记录里重新批改。",
                   icon=ICON_WARN)
            return
        self._perform_evaluation(vosk_model)
        self._save_history()
        sc = self.session.evaluation.get("scores", {})
        notify(
            self, "批改完成",
            f"本次得分：{sc.get('total', 0)} / {sc.get('total_max', 0)}"
            f"（{sc.get('scheme_name', '')}）",
            informative="练习记录与参考批改已保存至历史记录。",
            icon=ICON_OK)

    def _perform_evaluation(self, vosk_model):
        self.session.evaluation = evaluate_recordings(self.session, self.pkg, vosk_model)
        self.session.evaluation["scores"] = compute_scores(
            self.session.evaluation, self.scheme_key)

    def _save_history(self):
        """把本次结果写入 history/history_*.json，并复制思维导图副本。"""
        os.makedirs(HISTORY_DIR, exist_ok=True)
        history = {
            "package": self.pkg.meta.get("name", ""),
            "timestamp": self.session.timestamp.isoformat(),
            "scheme_key": self.scheme_key,
            "recordings": {
                "partA": self.session.partA_recording,
                "partB_secA": self.session.partB_secA_recordings,
                "partB_secB": self.session.partB_secB_recordings,
                "partC_secA": self.session.partC_secA_recording,
                "partC_secB": self.session.partC_secB_recordings,
            },
            "evaluation": self.session.evaluation,
            "package_data": self.pkg.to_dict(),
        }
        mm_src = self.pkg.partC_secA.get("mindmap_image")
        if mm_src and os.path.exists(mm_src):
            try:
                mm_dst = os.path.join(
                    HISTORY_DIR,
                    f"mindmap_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    f"{os.path.splitext(mm_src)[1]}")
                shutil.copy2(mm_src, mm_dst)
                history["mindmap_copy"] = mm_dst
            except Exception as e:
                print("复制思维导图失败：", e)

        fname = f"history_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(os.path.join(HISTORY_DIR, fname), 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False, default=str)
