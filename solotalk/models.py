# -*- coding: utf-8 -*-
"""数据模型：.solo 题目包与一次练习会话。"""

import os
import datetime

from .config import DEFAULT_SCHEME, SCORE_SCHEMES


class SoloPackage:
    """一个 .solo 题目包的内存表示（编辑 / 练习 / 批改共用）。"""

    def __init__(self):
        self.meta = {
            "name": "Untitled",
            "version": "2.1",
            "created": datetime.datetime.now().isoformat(),
            "author": "",
            "anonymous": False,
            "scheme": DEFAULT_SCHEME,   # "30" / "25"
        }
        # Part A 模仿朗读
        self.partA_audio_source_type = "tts"
        self.partA_tts_text = ""
        self.partA_audio_path = None
        self.partA_hidden_text = ""

        # Part B Section A 听选信息（3 段，每段 2 题）
        self.partB_secA = []

        # Part B Section B 回答问题（1 段独白，4 题）
        self.partB_secB = {
            "audio_source_type": "tts",
            "tts_text": "",
            "audio_path": None,
            "questions": [],
        }

        # Part C Section A 信息转述
        self.partC_secA = {
            "audio_source_type": "tts",
            "tts_text": "",
            "audio_path": None,
            "key_points": "",
            "hidden_answer_points": "",
            "mindmap_image": None,
        }

        # Part C Section B 询问信息（2 问）
        self.partC_secB = {"situation": "", "questions": []}

    def to_dict(self):
        """序列化为可写入 data.json 的字典（音频字段只保留文件名）。"""
        return {
            "meta": self.meta,
            "partA": {
                "audio_source_type": self.partA_audio_source_type,
                "tts_text": self.partA_tts_text,
                "audio": os.path.basename(self.partA_audio_path) if self.partA_audio_path else None,
                "hidden_text": self.partA_hidden_text,
            },
            "partB_secA": [
                {
                    "audio_source_type": seg.get("audio_source_type"),
                    "tts_text": seg.get("tts_text"),
                    "audio": os.path.basename(seg.get("audio_path")) if seg.get("audio_path") else None,
                    "questions": seg.get("questions", []),
                } for seg in self.partB_secA
            ],
            "partB_secB": {
                "audio_source_type": self.partB_secB.get("audio_source_type"),
                "tts_text": self.partB_secB.get("tts_text"),
                "audio": os.path.basename(self.partB_secB.get("audio_path")) if self.partB_secB.get("audio_path") else None,
                "questions": self.partB_secB.get("questions", []),
            },
            "partC_secA": {
                "audio_source_type": self.partC_secA.get("audio_source_type"),
                "tts_text": self.partC_secA.get("tts_text"),
                "audio": os.path.basename(self.partC_secA.get("audio_path")) if self.partC_secA.get("audio_path") else None,
                "key_points": self.partC_secA.get("key_points"),
                "hidden_answer_points": self.partC_secA.get("hidden_answer_points"),
                "mindmap_image": os.path.basename(self.partC_secA.get("mindmap_image"))
                                  if self.partC_secA.get("mindmap_image") else None,
            },
            "partC_secB": self.partC_secB,
        }

    def from_dict(self, data, base_dir=None):
        """从 data.json 还原；base_dir 用于把音频文件名拼成绝对路径。"""
        self.meta = data.get("meta", self.meta)
        # 兼容旧包：无 scheme 时回退默认
        if "scheme" not in self.meta or str(self.meta.get("scheme")) not in SCORE_SCHEMES:
            self.meta["scheme"] = DEFAULT_SCHEME

        pa = data.get("partA", {})
        self.partA_audio_source_type = pa.get("audio_source_type", "tts")
        self.partA_tts_text = pa.get("tts_text", "")
        self.partA_hidden_text = pa.get("hidden_text", "")
        if pa.get("audio") and base_dir:
            self.partA_audio_path = os.path.join(base_dir, pa["audio"])
        else:
            self.partA_audio_path = None

        self.partB_secA = []
        for seg in data.get("partB_secA", []):
            self.partB_secA.append({
                "audio_source_type": seg.get("audio_source_type", "tts"),
                "tts_text": seg.get("tts_text", ""),
                "audio_path": os.path.join(base_dir, seg["audio"]) if seg.get("audio") and base_dir else None,
                "questions": seg.get("questions", []),
            })

        sb = data.get("partB_secB", {})
        self.partB_secB = {
            "audio_source_type": sb.get("audio_source_type", "tts"),
            "tts_text": sb.get("tts_text", ""),
            "audio_path": os.path.join(base_dir, sb["audio"]) if sb.get("audio") and base_dir else None,
            "questions": sb.get("questions", []),
        }

        pcA = data.get("partC_secA", {})
        self.partC_secA = {
            "audio_source_type": pcA.get("audio_source_type", "tts"),
            "tts_text": pcA.get("tts_text", ""),
            "audio_path": os.path.join(base_dir, pcA["audio"]) if pcA.get("audio") and base_dir else None,
            "key_points": pcA.get("key_points", ""),
            "hidden_answer_points": pcA.get("hidden_answer_points", ""),
            "mindmap_image": os.path.join(base_dir, pcA["mindmap_image"])
                               if pcA.get("mindmap_image") and base_dir else None,
        }
        self.partC_secB = data.get("partC_secB", {"situation": "", "questions": []})


class PracticeSession:
    """一次练习/模考的录音与批改结果。"""

    def __init__(self, package_name):
        self.package_name = package_name
        self.timestamp = datetime.datetime.now()
        self.partA_recording = None
        self.partB_secA_recordings = []
        self.partB_secB_recordings = []
        self.partC_secA_recording = None
        self.partC_secB_recordings = []
        self.evaluation = {}
