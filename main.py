#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SoloTalk 中考版 2.1 — 单机版听说模考编辑器（广州中考题型）
依赖安装：pip install PyQt5 pyttsx3 sounddevice vosk pygame numpy edge-tts
（edge-tts 为高质量神经语音，需联网；未安装或断网时自动回退系统 SAPI5 语音）

Vosk 英语模型请下载并解压到本脚本同级目录，或修改 MODEL_PATH 变量。

题型：Part A 模仿朗读 / Part B 听选+回答 / Part C 信息转述+询问
评分：Levenshtein WER / Jaccard / keyword_coverage
分制：30分制 / 25分制，由编辑模式指定并随 .solo 包保存

本版本新增：
- Part C 信息转述思维导图（图片）支持
- 编辑模式分制选择（30/25），随包分发，练习/模考自动读取
- 批改按分制计算各分项得分与总分
"""

import sys
import os
import json
import zipfile
import tempfile
import wave
import datetime
import time
import threading
import ctypes
import shutil
from pathlib import Path
import urllib.request

# ========== 路径 & DLL 注册 ==========
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
    if hasattr(sys, "_MEIPASS"):
        _BASE_DIR = sys._MEIPASS
    if os.path.basename(_BASE_DIR) == "_internal":
        _BASE_DIR = os.path.dirname(_BASE_DIR)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPT_DIR = _BASE_DIR
_INTERNAL_DIR = os.path.join(_BASE_DIR, "_internal")

_dll_dir_cookies = []
if sys.platform == "win32":
    try:
        ctypes.windll.kernel32.AddDllDirectory(_SCRIPT_DIR)
    except Exception:
        pass
    if getattr(sys, "frozen", False) and os.path.isdir(_INTERNAL_DIR):
        try:
            ctypes.windll.kernel32.AddDllDirectory(_INTERNAL_DIR)
        except Exception:
            pass
        _ort_dll_dir = os.path.join(_INTERNAL_DIR, "onnxruntime", "capi")
        if os.path.isdir(_ort_dll_dir):
            try:
                ctypes.windll.kernel32.AddDllDirectory(_ort_dll_dir)
            except Exception:
                pass


def _pick_log_path():
    if not getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "_solo_diag.log")
    exe_log = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "_solo_diag.log")
    try:
        with open(exe_log, "a", encoding="utf-8"):
            pass
        return exe_log
    except Exception:
        return os.path.join(os.path.expanduser("~"), "_solo_diag.log")


_diag_project_log = _pick_log_path()


class _ConsoleTee:
    def __init__(self, stream, log_path, is_error=False):
        self._stream = stream
        self._log_path = log_path
        self._is_error = is_error
        self._buf = []
        self._lock = threading.Lock()

    def write(self, data):
        if not data:
            return
        try:
            if self._stream is not None:
                self._stream.write(data)
                self._stream.flush()
        except Exception:
            pass
        with self._lock:
            self._buf.append(data)
            joined = "".join(self._buf)
            parts = joined.split("\n")
            self._buf = [parts[-1]] if parts[-1] else []
            for line in parts[:-1]:
                self._flush_line(line)

    def flush(self):
        try:
            if self._stream is not None:
                self._stream.flush()
        except Exception:
            pass

    def _flush_line(self, line):
        if not line:
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag = "STDERR" if self._is_error else "OUT"
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}][{tag}] {line}\n")
        except Exception:
            pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")

    def fileno(self):
        return -1

    def writable(self):
        return True


def _install_console_tee():
    sys.stdout = _ConsoleTee(sys.stdout, _diag_project_log)
    sys.stderr = _ConsoleTee(sys.stderr, _diag_project_log, is_error=True)


_install_console_tee()


def _log_exception(exc_type, exc_value, exc_tb):
    try:
        import traceback
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        tb_text = f"{exc_type}: {exc_value}"
    msg = f"\n[EXCEPTION] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{tb_text}"
    try:
        with open(_diag_project_log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    if exc_type is not SystemExit:
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass


sys.excepthook = _log_exception

try:
    import faulthandler
    _fh_path = (os.path.join(os.path.expanduser("~"), "_solo_diag.log")
                if getattr(sys, "frozen", False)
                else os.path.join(_SCRIPT_DIR, "_solo_diag.log"))
    _fh_file = open(_fh_path, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_fh_file, all_threads=True)
except Exception:
    pass

print("=== SoloTalk 中考版 startup ===")
print(f"log_path={_diag_project_log}")
print(f"frozen={getattr(sys, 'frozen', False)}")
print(f"_BASE_DIR={_BASE_DIR}")


def _resolve_model_dir(name):
    for base in (_BASE_DIR, _INTERNAL_DIR, os.getcwd()):
        p = os.path.join(base, name)
        if os.path.isdir(p):
            return p
    return os.path.join(_BASE_DIR, name)


def _resolve_resource_file(name):
    for base in (_BASE_DIR, _INTERNAL_DIR, os.getcwd()):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return p
    return None


if os.getcwd() != _SCRIPT_DIR:
    try:
        os.chdir(_SCRIPT_DIR)
    except Exception:
        pass

# ========== 第三方导入 ==========
import pyttsx3
import sounddevice as sd
import numpy as np
import pygame

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# ========== Windows 键屏蔽 ==========
def _wintype(name, fallback):
    return getattr(ctypes.wintypes, name, fallback)

_LRESULT = _wintype("LRESULT", ctypes.c_ssize_t)
_WPARAM = _wintype("WPARAM", ctypes.c_size_t)
_LPARAM = _wintype("LPARAM", ctypes.c_ssize_t)
_HHOOK = _wintype("HHOOK", ctypes.c_void_p)
_DWORD = _wintype("DWORD", ctypes.c_uint32)
_BOOL = _wintype("BOOL", ctypes.c_int)
_ULONG_PTR = ctypes.c_size_t


class WindowsKeyBlocker:
    _VK_LWIN = 0x5B
    _VK_RWIN = 0x5C
    _VK_MENU = 0x12
    _VK_TAB = 0x09
    _WH_KEYBOARD_LL = 13
    _BLOCK_KEYS = (_VK_LWIN, _VK_RWIN, _VK_MENU, _VK_TAB)

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", _DWORD), ("scanCode", _DWORD), ("flags", _DWORD),
            ("time", _DWORD), ("dwExtraInfo", ctypes.POINTER(_ULONG_PTR)),
        ]

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._user32.SetWindowsHookExW.restype = _HHOOK
        self._user32.UnhookWindowsHookEx.restype = _BOOL
        self._user32.UnhookWindowsHookEx.argtypes = [_HHOOK]
        self._user32.CallNextHookEx.restype = _LRESULT
        self._user32.CallNextHookEx.argtypes = [_HHOOK, ctypes.c_int, _WPARAM, _LPARAM]
        self._hook = None
        self._proc = None

    def _callback(self, nCode, wParam, lParam):
        try:
            if nCode == 0:
                kbd = ctypes.cast(lParam, ctypes.POINTER(self.KBDLLHOOKSTRUCT)).contents
                if kbd.vkCode in self._BLOCK_KEYS:
                    return 1
        except Exception:
            pass
        return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

    def install(self):
        if self._hook:
            return
        self._proc = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, _WPARAM, _LPARAM)(self._callback)
        self._hook = self._user32.SetWindowsHookExW(self._WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            raise ctypes.WinError()

    def uninstall(self):
        if self._hook:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._proc = None

# ========== 全局配置 ==========
APP_VERSION = "2.1"
MODEL_PATH = _resolve_model_dir("vosk-model-small-en-us-0.15")
RECORDINGS_DIR = "recordings"
HISTORY_DIR = "history"
SAMPLE_RATE = 16000
TTS_TIMEOUT = 30
SETTINGS_FILE = "solotalk_settings.json"

# ========== 分制配置 ==========
SCORE_SCHEMES = {
    "30": {
        "name": "30分制",
        "total": 30,
        "partA": {"count": 1, "per": 6.0},
        "partB_secA": {"count": 6, "per": 1.0},
        "partB_secB": {"count": 4, "per": 1.5},
        "partC_secA": {"count": 1, "per": 8.0},
        "partC_secB": {"count": 2, "per": 2.0},
    },
    "25": {
        "name": "25分制",
        "total": 25,
        "partA": {"count": 1, "per": 4.0},
        "partB_secA": {"count": 6, "per": 1.0},
        "partB_secB": {"count": 4, "per": 1.0},
        "partC_secA": {"count": 1, "per": 8.0},
        "partC_secB": {"count": 2, "per": 1.5},
    },
}
DEFAULT_SCHEME = "30"


def _get_scheme(key):
    return SCORE_SCHEMES.get(str(key), SCORE_SCHEMES[DEFAULT_SCHEME])


def compute_scores(eval_result, scheme_key):
    """根据批改结果和分制计算各项得分。"""
    scheme = _get_scheme(scheme_key)
    scores = {
        "scheme": str(scheme_key),
        "scheme_name": scheme["name"],
        "total_max": scheme["total"],
        "detail": {},
    }
    total = 0.0

    # Part A：accuracy × 满分
    pa = eval_result.get("partA", {})
    pa_max = scheme["partA"]["per"] * scheme["partA"]["count"]
    pa_score = round(max(0.0, min(1.0, pa.get("accuracy", 0.0))) * pa_max, 2)
    scores["detail"]["partA"] = {"score": pa_score, "max": pa_max}
    total += pa_score

    # Part B SecA：选择题，相似度 ≥ 0.5 得满分
    secA_list = eval_result.get("partB_secA", [])
    secA_per = scheme["partB_secA"]["per"]
    secA_max = secA_per * scheme["partB_secA"]["count"]
    secA_score = 0.0
    for item in secA_list:
        if item.get("similarity", 0.0) >= 0.5:
            secA_score += secA_per
    secA_score = round(min(secA_score, secA_max), 2)
    scores["detail"]["partB_secA"] = {"score": secA_score, "max": secA_max,
                                      "items": len(secA_list)}
    total += secA_score

    # Part B SecB：similarity 折算
    secB_list = eval_result.get("partB_secB", [])
    secB_per = scheme["partB_secB"]["per"]
    secB_max = secB_per * scheme["partB_secB"]["count"]
    secB_score = 0.0
    for item in secB_list:
        sim = max(0.0, min(1.0, item.get("similarity", 0.0)))
        secB_score += sim * secB_per
    secB_score = round(min(secB_score, secB_max), 2)
    scores["detail"]["partB_secB"] = {"score": secB_score, "max": secB_max,
                                      "items": len(secB_list)}
    total += secB_score

    # Part C SecA：要点覆盖率 × 满分
    pcA = eval_result.get("partC_secA", {})
    pcA_max = scheme["partC_secA"]["per"] * scheme["partC_secA"]["count"]
    cov_total = pcA.get("total", 0)
    cov_found = pcA.get("found", 0)
    cov_ratio = (cov_found / cov_total) if cov_total > 0 else 0.0
    pcA_score = round(cov_ratio * pcA_max, 2)
    scores["detail"]["partC_secA"] = {"score": pcA_score, "max": pcA_max,
                                      "coverage": f"{cov_found}/{cov_total}"}
    total += pcA_score

    # Part C SecB：similarity 折算
    pcB_list = eval_result.get("partC_secB", [])
    pcB_per = scheme["partC_secB"]["per"]
    pcB_max = pcB_per * scheme["partC_secB"]["count"]
    pcB_score = 0.0
    for item in pcB_list:
        sim = max(0.0, min(1.0, item.get("similarity", 0.0)))
        pcB_score += sim * pcB_per
    pcB_score = round(min(pcB_score, pcB_max), 2)
    scores["detail"]["partC_secB"] = {"score": pcB_score, "max": pcB_max,
                                      "items": len(pcB_list)}
    total += pcB_score

    scores["total"] = round(total, 2)
    return scores


def _load_settings():
    try:
        path = _resolve_resource_file(SETTINGS_FILE) or SETTINGS_FILE
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"[SETTINGS] 读取失败: {e}")
    return {}


def _save_settings(data):
    try:
        if getattr(sys, "frozen", False):
            path = os.path.join(_BASE_DIR, SETTINGS_FILE)
        else:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[SETTINGS] 保存失败: {e}")
        return False

# ========== TTS ==========
try:
    import edge_tts as _edge_tts
    EDGE_TTS_AVAILABLE = True
except Exception:
    EDGE_TTS_AVAILABLE = False

TTS_EDGE_VOICE = "en-US-JennyNeural"
TTS_EDGE_DIR = os.path.join(tempfile.gettempdir(), "solotalk_tts")


def tts_generate_audio(text, out_path):
    if not EDGE_TTS_AVAILABLE or not (text and text.strip()):
        return False
    try:
        import asyncio
        async def _gen():
            com = _edge_tts.Communicate(text.strip(), voice=TTS_EDGE_VOICE)
            await asyncio.wait_for(com.save(out_path), timeout=TTS_TIMEOUT)
        asyncio.run(_gen())
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception as e:
        print(f"edge-tts 失败，回退系统语音: {e}")
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        return False


def _tts_split_sentences(text):
    import re
    parts = re.split(r'(?<=[.!?;:])\s+', text.strip())
    return [p for p in parts if p.strip()]


def tts_speak_blocking(text, stop_event=None):
    engine = None
    try:
        engine = pyttsx3.init()
        try:
            voices = engine.getProperty('voices')
            for v in voices:
                vid = str(getattr(v, 'id', '') or '')
                if 'en' in vid.lower():
                    engine.setProperty('voice', v.id)
                    break
        except Exception:
            pass
        engine.setProperty('rate', 140)
        engine.setProperty('volume', 1.0)
        if stop_event:
            def timeout_monitor():
                if stop_event.wait(TTS_TIMEOUT):
                    try:
                        engine.stop()
                    except Exception:
                        pass
            threading.Thread(target=timeout_monitor, daemon=True).start()
        for sent in (_tts_split_sentences(text) or [text]):
            if stop_event and stop_event.is_set():
                break
            engine.say(sent)
            engine.runAndWait()
            if stop_event and stop_event.is_set():
                break
            time.sleep(0.18)
    except Exception as e:
        print(f"TTS error: {e}")
    finally:
        if engine:
            try:
                engine.stop()
                del engine
            except Exception:
                pass

# ========== 评分工具 ==========
def levenshtein_wer(ref, hyp):
    ref_words = ref.lower().split()
    hyp_words = hyp.lower().split()
    n = len(ref_words)
    if n == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0, 1.0 if len(hyp_words) == 0 else 0.0
    dp = [[0] * (len(hyp_words) + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, len(hyp_words) + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    wer = dp[n][len(hyp_words)] / n
    return wer, 1.0 - wer


def jaccard_similarity(text1, text2):
    set1 = set(text1.lower().split())
    set2 = set(text2.lower().split())
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


def keyword_coverage(text, keywords_str):
    keywords = [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]
    if not keywords:
        return 0, 0, []
    text_lower = text.lower()
    found = [kw for kw in keywords if kw in text_lower]
    return len(found), len(keywords), found


def recognize_audio_file(filepath, model):
    if not model or not filepath or not isinstance(filepath, str) or not os.path.exists(filepath):
        return ""
    try:
        wf = wave.open(filepath, 'rb')
    except Exception:
        return ""
    try:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != SAMPLE_RATE:
            return "[格式不符]"
        rec = KaldiRecognizer(model, SAMPLE_RATE)
        result_text = ""
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                result_text += res.get("text", "") + " "
        res = json.loads(rec.FinalResult())
        result_text += res.get("text", "")
        return result_text.strip()
    except Exception:
        return "[识别失败]"
    finally:
        try:
            wf.close()
        except Exception:
            pass


# ========== 数据模型 ==========
class SoloPackage:
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
    def __init__(self, package_name):
        self.package_name = package_name
        self.timestamp = datetime.datetime.now()
        self.partA_recording = None
        self.partB_secA_recordings = []
        self.partB_secB_recordings = []
        self.partC_secA_recording = None
        self.partC_secB_recordings = []
        self.evaluation = {}


# ========== 主窗口 ==========
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SoloTalk 中考版 {APP_VERSION} — 单机版听说模考编辑器")
        self.setMinimumSize(1024, 700)

        _icon_path = _resolve_resource_file("xixi.ico")
        if _icon_path:
            self.setWindowIcon(QIcon(_icon_path))

        self.current_package = SoloPackage()
        self.current_session = None
        self.settings = _load_settings()

        self.central = QStackedWidget()
        self.setCentralWidget(self.central)

        self.home_page = HomePage(self)
        self.editor_page = EditorPage(self)
        self.practice_page = PracticePage(self)
        self.history_page = HistoryPage(self)
        self.more_page = MorePage(self)

        self.central.addWidget(self.home_page)
        self.central.addWidget(self.editor_page)
        self.central.addWidget(self.practice_page)
        self.central.addWidget(self.history_page)
        self.central.addWidget(self.more_page)
        self.central.setCurrentWidget(self.home_page)

        if self.settings.get("auto_check_update", True):
            QTimer.singleShot(1500, self._check_update)

        self.show()

    def go_to(self, page):
        try:
            if page is not self.practice_page and self.central.currentWidget() is self.practice_page:
                self.practice_page._stop_video()
        except Exception:
            pass
        self.central.setCurrentWidget(page)

    def closeEvent(self, event):
        if self.central.currentWidget() == self.practice_page:
            if not self.practice_page.request_exit():
                event.ignore()
                return
        event.accept()

    def _check_update(self):
        if getattr(self, "_updater", None) and self._updater.isRunning():
            return
        self._updater = UpdateChecker()
        self._updater.update_available.connect(self.show_update_dialog)
        self._updater.start()

    def show_update_dialog(self, info):
        dlg = QDialog(self)
        dlg.setWindowTitle("发现新版本")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setMinimumWidth(440)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"<b>发现新版本 SoloTalk 中考版 {info.get('version', '')}</b>"))
        notes = info.get("notes", "")
        if notes:
            tb = QTextEdit(notes)
            tb.setReadOnly(True)
            tb.setMaximumHeight(180)
            layout.addWidget(tb)

        def _go():
            url = info.get("url", "")
            if url:
                QDesktopServices.openUrl(QUrl(url))
            dlg.accept()

        btn_later = QPushButton("稍后提醒")
        btn_open = QPushButton("前往下载")
        btn_open.setStyleSheet("background:#3498db;color:white;font-weight:bold;")
        btn_later.clicked.connect(dlg.reject)
        btn_open.clicked.connect(_go)
        box = QHBoxLayout()
        box.addStretch(1)
        box.addWidget(btn_later)
        box.addWidget(btn_open)
        layout.addLayout(box)
        dlg.exec_()


# ========== 首页 ==========
class HomePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 18)
        layout.addStretch(1)
        title = QLabel("SoloTalk 中考版")
        title.setStyleSheet("font-size:42px; font-weight:bold; color:#2c3e50;")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("单机版听说模考编辑器 · 完全免费")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:16px; color:#7f8c8d; margin-bottom:30px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        btn_style = """
            QPushButton { font-size:20px; padding:18px 50px; border:2px solid #3498db;
                          border-radius:10px; background:white; color:#2c3e50; }
            QPushButton:hover { background:#ecf0f1; }
        """
        btn_editor = QPushButton("✏️  编辑模式")
        btn_editor.setStyleSheet(btn_style)
        btn_editor.clicked.connect(lambda: self.main.go_to(self.main.editor_page))
        btn_practice = QPushButton("🎧  练习模式")
        btn_practice.setStyleSheet(btn_style)
        btn_practice.setToolTip("可跳过 / 上一步，开头试音也能跳过")
        btn_practice.clicked.connect(lambda: self.load_and_start("practice"))
        btn_exam = QPushButton("📝  模考模式")
        btn_exam.setStyleSheet(btn_style)
        btn_exam.setToolTip("不可跳过 / 上一步，试音也不能跳过")
        btn_exam.clicked.connect(lambda: self.load_and_start("exam"))
        btn_history = QPushButton("📋  历史记录")
        btn_history.setStyleSheet(btn_style)
        btn_history.clicked.connect(lambda: self.main.go_to(self.main.history_page))
        layout.addWidget(btn_editor, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_practice, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_exam, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_history, alignment=Qt.AlignCenter)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        btn_more = QPushButton("⋯  更多")
        btn_more.setCursor(Qt.PointingHandCursor)
        btn_more.setStyleSheet(
            "QPushButton { font-size:14px; padding:8px 18px; border:1px solid #cfd8dc;"
            " border-radius:8px; background:white; color:#607d8b; }"
            "QPushButton:hover { background:#ecf0f1; color:#2c3e50; }"
        )
        btn_more.clicked.connect(lambda: self.main.go_to(self.main.more_page))
        bottom.addWidget(btn_more)
        bottom.addStretch(1)
        layout.addLayout(bottom)
        self.setLayout(layout)

    def load_and_start(self, mode):
        path, _ = QFileDialog.getOpenFileName(self, "选择 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if not path:
            return
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                with zf.open('data.json') as f:
                    data = json.load(f)
                temp_dir = tempfile.mkdtemp(prefix="solotalk_")
                zf.extractall(temp_dir)
                self.main.current_package.from_dict(data, base_dir=temp_dir)
                self.main.current_package.meta['temp_dir'] = temp_dir
            self.main.practice_page.pkg = self.main.current_package
            self.main.practice_page.set_mode(mode)
            self.main.go_to(self.main.practice_page)
            self.main.practice_page._check_and_prompt_progress()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败：{str(e)}")


# ========== 更多页 ==========
class MorePage(QWidget):
    REPO_URL = "https://github.com/FallingLighty/SoloTalk"
    RELEASES_URL = "https://github.com/FallingLighty/SoloTalk/releases"

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        left = QFrame()
        left.setFixedWidth(188)
        left.setStyleSheet("QFrame { background:#f7f9fb; border-right:1px solid #e6ebef; }")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        self.nav = QListWidget()
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setStyleSheet(
            "QListWidget { background:transparent; border:none; outline:none; padding:10px 0; }"
            "QListWidget::item { height:44px; margin:2px 10px; border-radius:8px; color:#55606b; font-size:14px; }"
            "QListWidget::item:selected { background:#e4eff9; color:#1f6fb2; }"
        )
        for txt in ["  ℹ️    关于", "  ⬆️    更新&下载", "  📌    使用须知"]:
            item = QListWidgetItem(txt)
            item.setSizeHint(QSize(0, 44))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav)
        lv.addWidget(self.nav, 1)

        foot = QWidget()
        fv = QVBoxLayout(foot)
        fv.setContentsMargins(18, 12, 18, 16)
        btn_back = QPushButton("返回主页")
        btn_back.setStyleSheet(
            "QPushButton { font-size:13px; padding:7px 0; border:1px solid #cfd8dc;"
            " border-radius:8px; background:white; color:#55606b; }"
            "QPushButton:hover { background:#f4f7f9; }"
        )
        btn_back.clicked.connect(lambda: self.main.go_to(self.main.home_page))
        fv.addWidget(btn_back)
        lv.addWidget(foot)

        root.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(26, 22, 26, 20)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_about())
        self.stack.addWidget(self._page_update())
        self.stack.addWidget(self._page_terms())
        rv.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self.nav.setCurrentRow(0)
        self.setLayout(root)

    def _on_nav(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _page_about(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignTop)
        t = QLabel("SoloTalk 中考版")
        t.setStyleSheet("font-size:26px; font-weight:bold; color:#2c3e50;")
        v.addWidget(t)
        v.addWidget(QLabel(f"版本 v{APP_VERSION}"))
        v.addWidget(QLabel("单机版英语听说模考编辑器 · 完全免费"))
        v.addWidget(QLabel(" "))
        v.addWidget(QLabel("作者：晖落然（FallingLighty）、cheng、咸鱼"))
        v.addWidget(QLabel("适用地区：佛山、中山、珠海、广州、湛江、茂名、阳江、清远、韶关、潮州、揭阳、云浮、梅州、江门（改革后）、惠州（改革后）、深圳（25分）、东莞（25分）"))
        v.addStretch(1)
        return w

    def _page_update(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignTop)
        t = QLabel("版本更新")
        t.setStyleSheet("font-size:20px; font-weight:bold;")
        v.addWidget(t)
        v.addWidget(QLabel(f"当前版本：SoloTalk 中考版 {APP_VERSION}"))
        row = QHBoxLayout()
        btn = QPushButton("检查更新")
        btn.setStyleSheet("background:#3498db; color:white; border:none; border-radius:6px; padding:8px 22px; font-weight:bold;")
        btn.clicked.connect(self.main._check_update)
        row.addWidget(btn)
        self.chk = QCheckBox("启动时自动检查更新")
        self.chk.setChecked(bool(self.main.settings.get("auto_check_update", True)))
        self.chk.toggled.connect(self._on_toggle)
        row.addWidget(self.chk)
        row.addStretch(1)
        v.addLayout(row)

        v.addWidget(QLabel("下载地址："))
        btn2 = QPushButton("前往 GitHub 发布页")
        btn2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.RELEASES_URL)))
        v.addWidget(btn2)
        v.addStretch(1)
        return w

    def _on_toggle(self, checked):
        self.main.settings["auto_check_update"] = bool(checked)
        _save_settings(self.main.settings)

    def _page_terms(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignTop)
        t = QLabel("使用须知 & 声明")
        t.setStyleSheet("font-size:20px; font-weight:bold;")
        v.addWidget(t)
        for line in [
            "1、录音识别与批改全部在本地完成，断网也能完整考完；",
            "2、联网时会自动启用更自然的在线朗读语音，并在启动时检查一次新版本；",
            "3、适用人群：想提前体验听说考试流程的学生；",
            "4、Part C 要点请用英文逗号隔开，否则无法识别；",
            "5、批改结果基于离线语音识别，仅供参考；",
            "6、评分分制（30/25）由题目作者在编辑模式中指定，随 .solo 包分发。",
        ]:
            lb = QLabel(line)
            lb.setWordWrap(True)
            v.addWidget(lb)
        v.addStretch(1)
        return w


# ========== 编辑模式 ==========
class EditorPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.pkg = self.main.current_package
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        top_bar = QHBoxLayout()
        self.name_edit = QLineEdit(self.pkg.meta.get("name", ""))
        self.name_edit.setPlaceholderText("题目包名称")
        self.author_edit = QLineEdit(self.pkg.meta.get("author", ""))
        self.author_edit.setPlaceholderText("题目作者（可选）")
        self.anonymous_check = QCheckBox("匿名")
        self.anonymous_check.setChecked(self.pkg.meta.get("anonymous", False))

        # 分制选择（随包保存）
        self.scheme_combo = QComboBox()
        for key, sc in SCORE_SCHEMES.items():
            self.scheme_combo.addItem(sc["name"], key)
        _cur = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
        _idx = self.scheme_combo.findData(_cur)
        if _idx >= 0:
            self.scheme_combo.setCurrentIndex(_idx)
        self.scheme_combo.setMinimumWidth(180)

        btn_new = QPushButton("新建")
        btn_open = QPushButton("打开 .solo")
        btn_save = QPushButton("保存")
        btn_back = QPushButton("返回主页")
        top_bar.addWidget(QLabel("名称："))
        top_bar.addWidget(self.name_edit)
        top_bar.addWidget(QLabel("作者："))
        top_bar.addWidget(self.author_edit)
        top_bar.addWidget(self.anonymous_check)
        top_bar.addWidget(QLabel("评分分制："))
        top_bar.addWidget(self.scheme_combo)
        top_bar.addWidget(btn_new)
        top_bar.addWidget(btn_open)
        top_bar.addWidget(btn_save)
        top_bar.addStretch()
        top_bar.addWidget(btn_back)
        btn_new.clicked.connect(self.new_package)
        btn_open.clicked.connect(self.open_package)
        btn_save.clicked.connect(self.save_package)
        btn_back.clicked.connect(lambda: self.main.go_to(self.main.home_page))
        layout.addLayout(top_bar)

        self.tabs = QTabWidget()
        self.partA_widget = PartAEditor(self.pkg)
        self.partB_widget = PartBEditor(self.pkg)
        self.partC_widget = PartCEditor(self.pkg)
        self.tabs.addTab(self.partA_widget, "Part A 模仿朗读")
        self.tabs.addTab(self.partB_widget, "Part B 信息获取")
        self.tabs.addTab(self.partC_widget, "Part C 信息转述及询问")
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def new_package(self):
        self.main.current_package = SoloPackage()
        self.pkg = self.main.current_package
        self.name_edit.setText("")
        self.author_edit.setText("")
        self.anonymous_check.setChecked(False)
        self.scheme_combo.setCurrentIndex(
            max(0, self.scheme_combo.findData(DEFAULT_SCHEME)))
        self.partA_widget.pkg = self.pkg
        self.partB_widget.pkg = self.pkg
        self.partC_widget.pkg = self.pkg
        self.partA_widget.refresh()
        self.partB_widget.refresh()
        self.partC_widget.refresh()

    def open_package(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if path:
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    with zf.open('data.json') as f:
                        data = json.load(f)
                    temp_dir = tempfile.mkdtemp(prefix="solotalk_")
                    zf.extractall(temp_dir)
                    self.pkg.from_dict(data, base_dir=temp_dir)
                    self.pkg.meta['temp_dir'] = temp_dir
                self.name_edit.setText(self.pkg.meta.get("name", ""))
                self.author_edit.setText(self.pkg.meta.get("author", ""))
                self.anonymous_check.setChecked(self.pkg.meta.get("anonymous", False))
                _s = str(self.pkg.meta.get("scheme", DEFAULT_SCHEME))
                _i = self.scheme_combo.findData(_s)
                if _i >= 0:
                    self.scheme_combo.setCurrentIndex(_i)
                self.partA_widget.refresh()
                self.partB_widget.refresh()
                self.partC_widget.refresh()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"打开失败：{str(e)}")

    def save_package(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if not path:
            return
        self.pkg.meta["name"] = self.name_edit.text() or "Untitled"
        self.pkg.meta["author"] = ("匿名" if self.anonymous_check.isChecked()
                                   else self.author_edit.text())
        self.pkg.meta["anonymous"] = self.anonymous_check.isChecked()
        self.pkg.meta["scheme"] = self.scheme_combo.currentData() or DEFAULT_SCHEME
        self.partA_widget.save_to_pkg()
        self.partB_widget.save_to_pkg()
        self.partC_widget.save_to_pkg()
        try:
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('data.json', json.dumps(self.pkg.to_dict(), indent=2, ensure_ascii=False))
                audio_files, seen = [], set()
                def _add(p):
                    if p and os.path.exists(p) and p not in seen:
                        seen.add(p)
                        audio_files.append(p)
                _add(self.pkg.partA_audio_path)
                for seg in self.pkg.partB_secA:
                    _add(seg.get("audio_path"))
                _add(self.pkg.partB_secB.get("audio_path"))
                _add(self.pkg.partC_secA.get("audio_path"))
                for ap in audio_files:
                    zf.write(ap, os.path.basename(ap))
                mm = self.pkg.partC_secA.get("mindmap_image")
                if mm and os.path.exists(mm):
                    zf.write(mm, os.path.basename(mm))
            QMessageBox.information(self, "成功", f"题目包已保存至 {path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))


class PartAEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItems(["💻电脑 TTS 朗读", "上传本地音频"])
        self.source_combo.currentIndexChanged.connect(self.toggle_source)
        layout.addRow("短文音频来源：", self.source_combo)

        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("短文文本（电脑朗读）")
        layout.addRow("短文文本：", self.tts_edit)

        self.audio_label = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        audio_box = QHBoxLayout()
        audio_box.addWidget(self.audio_label)
        audio_box.addWidget(self.audio_btn)
        layout.addRow("音频文件：", audio_box)

        self.hidden_edit = QTextEdit()
        self.hidden_edit.setPlaceholderText("原文（隐藏，仅用于批改）")
        layout.addRow("原文(隐藏)：", self.hidden_edit)

        self.setLayout(layout)
        self.toggle_source()

    def toggle_source(self):
        is_tts = self.source_combo.currentIndex() == 0
        self.tts_edit.setVisible(is_tts)
        self.audio_label.setVisible(not is_tts)
        self.audio_btn.setVisible(not is_tts)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self.pkg.partA_audio_path = path
            self.audio_label.setText(os.path.basename(path))

    def save_to_pkg(self):
        self.pkg.partA_audio_source_type = "tts" if self.source_combo.currentIndex() == 0 else "audio"
        self.pkg.partA_tts_text = self.tts_edit.toPlainText()
        self.pkg.partA_hidden_text = self.hidden_edit.toPlainText()

    def refresh(self):
        if self.pkg.partA_audio_source_type == "audio":
            self.source_combo.setCurrentIndex(1)
            self.audio_label.setText(os.path.basename(self.pkg.partA_audio_path)
                                     if self.pkg.partA_audio_path else "未选择音频")
        else:
            self.source_combo.setCurrentIndex(0)
        self.tts_edit.setPlainText(self.pkg.partA_tts_text)
        self.hidden_edit.setPlainText(self.pkg.partA_hidden_text)
        self.toggle_source()


class PartBEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout()
        tabs = QTabWidget()
        self.secA_widget = PartBSecAEditor(self.pkg)
        self.secB_widget = PartBSecBEditor(self.pkg)
        tabs.addTab(self.secA_widget, "Section A 听选信息")
        tabs.addTab(self.secB_widget, "Section B 回答问题")
        main_layout.addWidget(tabs)
        self.setLayout(main_layout)

    def save_to_pkg(self):
        self.secA_widget.save_to_pkg()
        self.secB_widget.save_to_pkg()

    def refresh(self):
        self.secA_widget.refresh()
        self.secB_widget.refresh()


class PartBSecAEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.segment_widgets = []
        self.segment_audio_paths = [None, None, None]
        self.setup_ui()

    def _make_audio_row(self):
        label = QLabel("未选择音频")
        label.setStyleSheet("color:#666;")
        btn_choose = QPushButton("选择音频")
        btn_clear = QPushButton("清除")
        row = QHBoxLayout()
        row.addWidget(label)
        row.addWidget(btn_choose)
        row.addWidget(btn_clear)
        return row, label, btn_choose, btn_clear

    def setup_ui(self):
        scroll = QScrollArea()
        widget = QWidget()
        layout = QVBoxLayout()
        self.segment_widgets = []
        for seg_idx in range(3):
            grp = QGroupBox(f"对话/独白 {seg_idx + 1}")
            seg_layout = QVBoxLayout()
            src_combo = QComboBox()
            src_combo.addItems(["💻电脑 TTS", "上传音频"])
            tts_edit = QTextEdit()
            tts_edit.setPlaceholderText("听力原文（TTS朗读）")
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel("音频来源："))
            hbox.addWidget(src_combo)
            seg_layout.addLayout(hbox)
            seg_layout.addWidget(tts_edit)

            a_row, a_label, a_btn, a_clear = self._make_audio_row()
            a_btn.clicked.connect(lambda _, i=seg_idx, lb=a_label: self._choose_audio(i, lb))
            a_clear.clicked.connect(lambda _, i=seg_idx, lb=a_label: self._clear_audio(i, lb))
            seg_layout.addLayout(a_row)

            q_widgets = []
            for q_idx in range(2):
                q_grp = QGroupBox(f"问题{q_idx + 1}")
                q_layout = QFormLayout()
                q_edit = QLineEdit(); q_edit.setPlaceholderText("英文问题")
                optA = QLineEdit(); optA.setPlaceholderText("A. ...")
                optB = QLineEdit(); optB.setPlaceholderText("B. ...")
                optC = QLineEdit(); optC.setPlaceholderText("C. ...")
                correct_edit = QLineEdit(); correct_edit.setPlaceholderText("正确答案文本（隐藏）")
                q_layout.addRow("问题：", q_edit)
                q_layout.addRow("选项A：", optA)
                q_layout.addRow("选项B：", optB)
                q_layout.addRow("选项C：", optC)
                q_layout.addRow("正确答案：", correct_edit)
                q_grp.setLayout(q_layout)
                seg_layout.addWidget(q_grp)
                q_widgets.append({"q_edit": q_edit, "optA": optA, "optB": optB,
                                  "optC": optC, "correct_edit": correct_edit})
            grp.setLayout(seg_layout)
            layout.addWidget(grp)
            self.segment_widgets.append({
                "src_combo": src_combo, "tts_edit": tts_edit,
                "audio_lbl": a_label, "q_widgets": q_widgets,
            })
        widget.setLayout(layout)
        scroll.setWidget(widget)
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def _choose_audio(self, seg_idx, label):
        path, _ = QFileDialog.getOpenFileName(self, f"选择对话{seg_idx + 1}音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self.segment_audio_paths[seg_idx] = path
            label.setText(os.path.basename(path))

    def _clear_audio(self, seg_idx, label):
        self.segment_audio_paths[seg_idx] = None
        label.setText("未选择音频")

    def save_to_pkg(self):
        self.pkg.partB_secA = []
        for seg_idx, w in enumerate(self.segment_widgets):
            seg = {
                "audio_source_type": "tts" if w["src_combo"].currentIndex() == 0 else "audio",
                "tts_text": w["tts_edit"].toPlainText(),
                "audio_path": self.segment_audio_paths[seg_idx],
                "questions": [],
            }
            for qw in w["q_widgets"]:
                seg["questions"].append({
                    "question_text": qw["q_edit"].text(),
                    "options": [qw["optA"].text(), qw["optB"].text(), qw["optC"].text()],
                    "correct_option_text": qw["correct_edit"].text(),
                })
            self.pkg.partB_secA.append(seg)

    def refresh(self):
        while len(self.pkg.partB_secA) < 3:
            self.pkg.partB_secA.append({
                "audio_source_type": "tts", "tts_text": "", "audio_path": None,
                "questions": [{"question_text": "", "options": ["", "", ""],
                               "correct_option_text": ""} for _ in range(2)]
            })
        for seg_idx, w in enumerate(self.segment_widgets):
            seg = self.pkg.partB_secA[seg_idx]
            self.segment_audio_paths[seg_idx] = seg.get("audio_path")
            w["src_combo"].setCurrentIndex(1 if seg.get("audio_source_type") == "audio" else 0)
            w["audio_lbl"].setText(os.path.basename(seg["audio_path"])
                                   if seg.get("audio_path") else "未选择音频")
            w["tts_edit"].setPlainText(seg.get("tts_text", ""))
            for q_idx, qw in enumerate(w["q_widgets"]):
                if q_idx < len(seg.get("questions", [])):
                    q = seg["questions"][q_idx]
                    qw["q_edit"].setText(q.get("question_text", ""))
                    opts = q.get("options", ["", "", ""])
                    qw["optA"].setText(opts[0] if len(opts) > 0 else "")
                    qw["optB"].setText(opts[1] if len(opts) > 1 else "")
                    qw["optC"].setText(opts[2] if len(opts) > 2 else "")
                    qw["correct_edit"].setText(q.get("correct_option_text", ""))
                else:
                    qw["q_edit"].clear()
                    qw["optA"].clear(); qw["optB"].clear(); qw["optC"].clear()
                    qw["correct_edit"].clear()


class PartBSecBEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self._audio_path = None
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout()
        self.src_combo = QComboBox()
        self.src_combo.addItems(["💻电脑 TTS", "上传音频"])
        layout.addRow("独白音频来源：", self.src_combo)
        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("独白文本（TTS朗读）")
        layout.addRow("独白文本：", self.tts_edit)
        self.audio_lbl = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        hbox = QHBoxLayout()
        hbox.addWidget(self.audio_lbl)
        hbox.addWidget(self.audio_btn)
        layout.addRow("音频文件：", hbox)

        self.q_widgets = []
        for i in range(4):
            grp = QGroupBox(f"问题{i + 1}")
            inner = QFormLayout()
            q_edit = QLineEdit(); q_edit.setPlaceholderText("英文问题")
            hid_edit = QLineEdit(); hid_edit.setPlaceholderText("标准答案（隐藏）")
            inner.addRow("问题：", q_edit)
            inner.addRow("答案：", hid_edit)
            grp.setLayout(inner)
            layout.addRow(grp)
            self.q_widgets.append((q_edit, hid_edit))
        self.setLayout(layout)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择独白音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self._audio_path = path
            self.audio_lbl.setText(os.path.basename(path))

    def save_to_pkg(self):
        self.pkg.partB_secB["audio_source_type"] = "tts" if self.src_combo.currentIndex() == 0 else "audio"
        self.pkg.partB_secB["tts_text"] = self.tts_edit.toPlainText()
        self.pkg.partB_secB["audio_path"] = self._audio_path
        self.pkg.partB_secB["questions"] = []
        for q_edit, hid_edit in self.q_widgets:
            self.pkg.partB_secB["questions"].append({
                "question_text": q_edit.text(),
                "hidden_answer": hid_edit.text(),
            })

    def refresh(self):
        secB = self.pkg.partB_secB
        self._audio_path = secB.get("audio_path")
        self.src_combo.setCurrentIndex(1 if secB.get("audio_source_type") == "audio" else 0)
        self.audio_lbl.setText(os.path.basename(secB["audio_path"]) if secB.get("audio_path") else "未选择音频")
        self.tts_edit.setPlainText(secB.get("tts_text", ""))
        questions = secB.get("questions", [])
        for i, (q_edit, hid_edit) in enumerate(self.q_widgets):
            if i < len(questions):
                q_edit.setText(questions[i].get("question_text", ""))
                hid_edit.setText(questions[i].get("hidden_answer", ""))
            else:
                q_edit.clear(); hid_edit.clear()


class PartCEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        tabs = QTabWidget()
        self.secA_widget = PartCSecAEditor(self.pkg)
        self.secB_widget = PartCSecBEditor(self.pkg)
        tabs.addTab(self.secA_widget, "Section A 信息转述")
        tabs.addTab(self.secB_widget, "Section B 询问信息")
        layout.addWidget(tabs)
        self.setLayout(layout)

    def save_to_pkg(self):
        self.secA_widget.save_to_pkg()
        self.secB_widget.save_to_pkg()

    def refresh(self):
        self.secA_widget.refresh()
        self.secB_widget.refresh()


class PartCSecAEditor(QWidget):
    """Part C Section A 编辑：含思维导图图片上传。"""

    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self._audio_path = None
        self._mindmap_path = None

        outer = QVBoxLayout()

        form = QFormLayout()
        self.src_combo = QComboBox()
        self.src_combo.addItems(["💻电脑 TTS", "上传音频"])
        form.addRow("听力内容来源：", self.src_combo)
        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("听力材料全文（TTS朗读）")
        form.addRow("全文：", self.tts_edit)

        self.audio_lbl = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        hbox = QHBoxLayout()
        hbox.addWidget(self.audio_lbl)
        hbox.addWidget(self.audio_btn)
        form.addRow("音频文件：", hbox)

        self.key_points_edit = QTextEdit()
        self.key_points_edit.setPlaceholderText("要点提示（显示在屏幕上，如中文关键词）")
        self.key_points_edit.setMaximumHeight(80)
        form.addRow("要点提示：", self.key_points_edit)

        self.hidden_points_edit = QTextEdit()
        self.hidden_points_edit.setPlaceholderText("答案要点（隐藏，英文逗号分隔，用于批改）")
        self.hidden_points_edit.setMaximumHeight(80)
        form.addRow("答案要点：", self.hidden_points_edit)
        outer.addLayout(form)

        mm_group = QGroupBox("思维导图（图片，Part C 转述阶段显示）")
        mm_layout = QVBoxLayout()

        mm_top = QHBoxLayout()
        self.mindmap_lbl = QLabel("未选择思维导图")
        self.mindmap_lbl.setStyleSheet("color:#666;")
        self.mindmap_btn = QPushButton("选择图片")
        self.mindmap_btn.clicked.connect(self.upload_mindmap)
        self.mindmap_clear_btn = QPushButton("清除")
        self.mindmap_clear_btn.clicked.connect(self.clear_mindmap)
        mm_top.addWidget(QLabel("图片文件："))
        mm_top.addWidget(self.mindmap_lbl, 1)
        mm_top.addWidget(self.mindmap_btn)
        mm_top.addWidget(self.mindmap_clear_btn)
        mm_layout.addLayout(mm_top)

        self.mindmap_preview = QLabel()
        self.mindmap_preview.setMinimumHeight(220)
        self.mindmap_preview.setAlignment(Qt.AlignCenter)
        self.mindmap_preview.setStyleSheet(
            "border:1px dashed #bdc3c7; background:#fafafa; color:#95a5a6;")
        self.mindmap_preview.setText("（思维导图预览，建议使用 PNG/JPG 格式）")
        mm_layout.addWidget(self.mindmap_preview, 1)

        mm_group.setLayout(mm_layout)
        outer.addWidget(mm_group, 1)

        self.setLayout(outer)
        self._refresh_mindmap_ui()

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "",
                                              "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if path:
            self._audio_path = path
            self.audio_lbl.setText(os.path.basename(path))

    def upload_mindmap(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择思维导图图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self._mindmap_path = path
            self._refresh_mindmap_ui()

    def clear_mindmap(self):
        self._mindmap_path = None
        self._refresh_mindmap_ui()

    def _refresh_mindmap_ui(self):
        if self._mindmap_path and os.path.isfile(self._mindmap_path):
            self.mindmap_lbl.setText(os.path.basename(self._mindmap_path))
            pix = QPixmap(self._mindmap_path)
            if not pix.isNull():
                w = max(self.mindmap_preview.width(), 600)
                h = max(self.mindmap_preview.height(), 220)
                self.mindmap_preview.setPixmap(
                    pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.mindmap_preview.setText("")
            else:
                self.mindmap_preview.setPixmap(QPixmap())
                self.mindmap_preview.setText("（图片无法解析，请换 PNG/JPG 再试）")
        else:
            self.mindmap_lbl.setText("未选择思维导图")
            self.mindmap_preview.setPixmap(QPixmap())
            self.mindmap_preview.setText("（思维导图预览，建议使用 PNG/JPG 格式）")

    def save_to_pkg(self):
        self.pkg.partC_secA["audio_source_type"] = "tts" if self.src_combo.currentIndex() == 0 else "audio"
        self.pkg.partC_secA["tts_text"] = self.tts_edit.toPlainText()
        self.pkg.partC_secA["audio_path"] = self._audio_path
        self.pkg.partC_secA["key_points"] = self.key_points_edit.toPlainText()
        self.pkg.partC_secA["hidden_answer_points"] = self.hidden_points_edit.toPlainText()
        self.pkg.partC_secA["mindmap_image"] = self._mindmap_path

    def refresh(self):
        secA = self.pkg.partC_secA
        self._audio_path = secA.get("audio_path")
        self.src_combo.setCurrentIndex(1 if secA.get("audio_source_type") == "audio" else 0)
        self.audio_lbl.setText(os.path.basename(secA["audio_path"]) if secA.get("audio_path") else "未选择音频")
        self.tts_edit.setPlainText(secA.get("tts_text", ""))
        self.key_points_edit.setPlainText(secA.get("key_points", ""))
        self.hidden_points_edit.setPlainText(secA.get("hidden_answer_points", ""))
        self._mindmap_path = secA.get("mindmap_image")
        self._refresh_mindmap_ui()


class PartCSecBEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        layout = QFormLayout()
        self.situation_edit = QTextEdit()
        self.situation_edit.setPlaceholderText("情境描述（如：你希望了解更多关于活动的情况）")
        layout.addRow("情境描述：", self.situation_edit)
        self.q_widgets = []
        for i in range(2):
            grp = QGroupBox(f"询问{i + 1}")
            inner = QFormLayout()
            cn_edit = QLineEdit(); cn_edit.setPlaceholderText("中文提示（如：询问活动开始时间）")
            hid_edit = QLineEdit(); hid_edit.setPlaceholderText("标准提问（英文，隐藏）")
            inner.addRow("中文提示：", cn_edit)
            inner.addRow("标准提问：", hid_edit)
            grp.setLayout(inner)
            layout.addRow(grp)
            self.q_widgets.append((cn_edit, hid_edit))
        self.setLayout(layout)

    def save_to_pkg(self):
        self.pkg.partC_secB["situation"] = self.situation_edit.toPlainText()
        self.pkg.partC_secB["questions"] = []
        for cn_edit, hid_edit in self.q_widgets:
            self.pkg.partC_secB["questions"].append({
                "cn_prompt": cn_edit.text(),
                "hidden_question": hid_edit.text(),
            })

    def refresh(self):
        secB = self.pkg.partC_secB
        self.situation_edit.setPlainText(secB.get("situation", ""))
        questions = secB.get("questions", [])
        for i, (cn_edit, hid_edit) in enumerate(self.q_widgets):
            if i < len(questions):
                cn_edit.setText(questions[i].get("cn_prompt", ""))
                hid_edit.setText(questions[i].get("hidden_question", ""))
            else:
                cn_edit.clear(); hid_edit.clear()


# ========== 练习 / 模考页面 ==========
class PracticePage(QWidget):
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
        scheme_name = _get_scheme(self.scheme_key)["name"]
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

    # ---------- TTS 管理 ----------
    def _start_tts(self, text, signal=None, force_fallback=False):
        self._cancel_tts()
        self._tts_stop_event = threading.Event()
        self._tts_thread = threading.Thread(
            target=self._tts_runner, args=(text, signal, force_fallback))
        self._tts_thread.daemon = True
        self._tts_thread.start()

    def _tts_runner(self, text, signal, force_fallback=False):
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
        tts_speak_blocking(text, self._tts_stop_event)
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

    # ---------- Part A ----------
    def _run_part_a(self):
        self._current_phase = "partA"
        self._step_index = 0
        self._exec_partA_step()

    def _exec_partA_step(self):
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

    # ---------- Part B ----------
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

    def _exec_partB_step(self):
        self._update_nav_buttons()
        if self._b_step >= len(self._b_moments):
            self._run_part_c()
            return
        m = self._b_moments[self._b_step]
        t = m["t"]

        if t == "intro":
            self.signal_update_display.emit(m["main"], m["sub"])
            self._start_tts(m["sub"], None)
            self._set_tts_callback(self._next_partB_step)

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

    # ---------- Part C ----------
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
            self._start_tts(
                "你将听到一段介绍。请根据所听到的内容和提示，在60秒钟内转述内容，包含全部要点。",
                None)
            self._set_tts_callback(self._next_partC_step)
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
            self._start_tts(
                "你希望了解更多信息，请根据以下提示提两个问题。每个问题有15秒钟的准备时间和8秒钟的提问时间。",
                None)
            self._set_tts_callback(lambda: self._show_secB_prepare(0))
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
        if self._current_phase == "partA":
            self._next_partA_step()
        elif self._current_phase == "partB":
            self._next_partB_step()
        elif self._current_phase == "partC":
            self._next_partC_step()

    # ---------- 通用音频 ----------
    def _play_audio_by_source(self, source_type, tts_text, audio_path, callback):
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
        path = os.path.join("material", "di.mp3")
        resolved = _resolve_resource_file(path)
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

    @pyqtSlot(str, str)
    def _update_display(self, main, sub):
        self.main_label.setText(main)
        self.sub_label.setText(sub)
        self.text_display.setPlainText(sub if sub else main)

    # ---------- 录音 ----------
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
        if not self._is_recording:
            return
        self._stop_recording()
        phase = self._current_phase
        if phase == "partA":
            self.session.partA_recording = self._save_recording("PartA")

    # ---------- 跳过 / 上一步 ----------
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

    # ---------- 批改 ----------
    def _on_exam_finished(self):
        self._exam_active = False
        self.start_btn.setEnabled(True)
        self._stop_video()
        self._update_nav_buttons()
        self._restore_window()
        self._unblock_windows_key()
        self._clear_progress()
        if self.mode == "exam":
            QMessageBox.information(self, "模考完成", "模考结束，即将进行离线批改。")
        else:
            QMessageBox.information(self, "练习完成", "练习结束，即将进行离线批改。")
        self.run_evaluation()

    def run_evaluation(self):
        vosk_model = load_vosk_model()
        if not vosk_model:
            QMessageBox.warning(self, "批改", "Vosk 模型不可用，录音已保存，稍后可重新批改。")
            self._save_history()
            return
        self._perform_evaluation(vosk_model)
        self._save_history()
        sc = self.session.evaluation.get("scores", {})
        QMessageBox.information(
            self, "批改完成",
            f"本次得分：{sc.get('total', 0)} / {sc.get('total_max', 0)}"
            f"（{sc.get('scheme_name', '')}）\n\n"
            f"练习记录与参考批改已保存至历史记录。")

    def _perform_evaluation(self, vosk_model):
        self.session.evaluation = evaluate_recordings(self.session, self.pkg, vosk_model)
        self.session.evaluation["scores"] = compute_scores(
            self.session.evaluation, self.scheme_key)

    def _save_history(self):
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


# ========== 批改函数 ==========
def evaluate_recordings(session, pkg, vosk_model, existing_eval=None, selection=None):
    """对一次练习会话做离线批改。
    Part A：Levenshtein WER
    Part B SecA：Jaccard 与正确选项文本比对
    Part B SecB：Jaccard 与标准答案比对
    Part C SecA：关键词覆盖
    Part C SecB：Jaccard 与标准提问比对
    """
    eval_result = dict(existing_eval) if existing_eval else {}
    _all = (selection is None)

    # Part A
    if _all or selection.get('partA'):
        if session.partA_recording:
            hyp = recognize_audio_file(session.partA_recording, vosk_model)
            wer, acc = levenshtein_wer(pkg.partA_hidden_text, hyp)
            eval_result['partA'] = {'recognized': hyp, 'wer': wer, 'accuracy': acc}
        else:
            eval_result['partA'] = {'recognized': '', 'wer': 1.0, 'accuracy': 0.0}

    # Part B SecA
    old_a = eval_result.get('partB_secA', [])
    new_a = []
    rec_idx = 0
    for seg_idx, seg in enumerate(pkg.partB_secA):
        for q_idx, q in enumerate(seg.get("questions", [])[:2]):
            if _all or (selection and selection.get('partB_secA')):
                if rec_idx < len(session.partB_secA_recordings):
                    rec = session.partB_secA_recordings[rec_idx]
                    hyp = recognize_audio_file(rec, vosk_model) if rec else ""
                    correct_text = q.get("correct_option_text", "")
                    sim = jaccard_similarity(correct_text, hyp) if hyp else 0.0
                    new_a.append({"seg": seg_idx + 1, "q": q_idx + 1,
                                  "recognized": hyp, "correct": correct_text,
                                  "similarity": sim})
                else:
                    new_a.append({"seg": seg_idx + 1, "q": q_idx + 1,
                                  "recognized": "", "correct": "",
                                  "similarity": 0.0})
            else:
                new_a.append(old_a[rec_idx] if rec_idx < len(old_a) else
                             {"seg": seg_idx + 1, "q": q_idx + 1, "similarity": 0.0})
            rec_idx += 1
    eval_result['partB_secA'] = new_a

    # Part B SecB
    old_b = eval_result.get('partB_secB', [])
    new_b = []
    for i, q in enumerate(pkg.partB_secB.get("questions", [])):
        if _all or (selection and selection.get('partB_secB')):
            if i < len(session.partB_secB_recordings) and session.partB_secB_recordings[i]:
                rec = session.partB_secB_recordings[i]
                hyp = recognize_audio_file(rec, vosk_model)
                ref = q.get("hidden_answer", "")
                sim = jaccard_similarity(ref, hyp) if hyp else 0.0
                new_b.append({"q": i + 1, "recognized": hyp,
                              "correct": ref, "similarity": sim})
            else:
                new_b.append({"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
        else:
            new_b.append(old_b[i] if i < len(old_b) else
                         {"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
    eval_result['partB_secB'] = new_b

    # Part C SecA
    if _all or selection.get('partC_secA'):
        if session.partC_secA_recording:
            hyp = recognize_audio_file(session.partC_secA_recording, vosk_model)
            found, total, _ = keyword_coverage(hyp, pkg.partC_secA.get("hidden_answer_points", ""))
            eval_result['partC_secA'] = {'recognized': hyp,
                                          'coverage': f"{found}/{total}",
                                          'found': found, 'total': total}
        else:
            eval_result['partC_secA'] = {'recognized': '', 'coverage': '0/0',
                                          'found': 0, 'total': 0}

    # Part C SecB
    old_c = eval_result.get('partC_secB', [])
    new_c = []
    for i, q in enumerate(pkg.partC_secB.get("questions", [])):
        if _all or (selection and selection.get('partC_secB')):
            if i < len(session.partC_secB_recordings) and session.partC_secB_recordings[i]:
                rec = session.partC_secB_recordings[i]
                hyp = recognize_audio_file(rec, vosk_model)
                ref = q.get("hidden_question", "")
                sim = jaccard_similarity(ref, hyp) if hyp else 0.0
                new_c.append({"q": i + 1, "recognized": hyp,
                              "correct": ref, "similarity": sim})
            else:
                new_c.append({"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
        else:
            new_c.append(old_c[i] if i < len(old_c) else
                         {"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
    eval_result['partC_secB'] = new_c

    return eval_result


# ========== 历史记录页面 ==========
class HistoryPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.view_detail)
        self.btn_reeval = QPushButton("重新批改选中记录")
        self.btn_reeval.clicked.connect(self.reevaluate_selected)
        self.btn_delete = QPushButton("删除选中记录")
        self.btn_delete.clicked.connect(self.delete_selected)
        btn_back = QPushButton("返回主页")
        btn_back.clicked.connect(lambda: self.main.go_to(self.main.home_page))
        layout.addWidget(QLabel("练习历史记录（双击查看详情）"))
        layout.addWidget(self.list_widget)
        layout.addWidget(self.btn_reeval)
        layout.addWidget(self.btn_delete)
        layout.addWidget(btn_back)
        self.setLayout(layout)

    def showEvent(self, event):
        self.load_history()
        super().showEvent(event)

    def load_history(self):
        self.list_widget.clear()
        if not os.path.exists(HISTORY_DIR):
            return
        files = sorted(Path(HISTORY_DIR).glob("history_*.json"), reverse=True)
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                sc = (data.get('evaluation') or {}).get('scores') or {}
                score_txt = (f"  [{sc.get('total', 0)}/{sc.get('total_max', 0)}]"
                             if sc else "")
                item_text = f"{data.get('package', '?')}  {data.get('timestamp', '')}{score_txt}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, str(f))
                self.list_widget.addItem(item)
            except Exception:
                pass

    def delete_selected(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        path = current_item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        reply = QMessageBox.question(self, "确认删除", "确定要删除该历史记录吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                os.remove(path)
                self.load_history()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败：{str(e)}")

    def reevaluate_selected(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        path = current_item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            QMessageBox.critical(self, "错误", "历史记录文件损坏")
            return
        recs = data.get('recordings', {})
        pkg_dict = data.get('package_data', {})
        temp_pkg = SoloPackage()
        temp_pkg.from_dict(pkg_dict)

        sess = PracticeSession(data.get('package', ''))
        sess.partA_recording = recs.get('partA')
        sess.partB_secA_recordings = recs.get('partB_secA', [])
        sess.partB_secB_recordings = recs.get('partB_secB', [])
        sess.partC_secA_recording = recs.get('partC_secA')
        sess.partC_secB_recordings = recs.get('partC_secB', [])

        vosk_model = load_vosk_model()
        if not vosk_model:
            QMessageBox.warning(self, "错误", "Vosk 模型不可用，无法重新批改")
            return
        scheme_key = data.get('scheme_key') or temp_pkg.meta.get('scheme', DEFAULT_SCHEME)
        data['evaluation'] = evaluate_recordings(sess, temp_pkg, vosk_model)
        data['evaluation']['scores'] = compute_scores(data['evaluation'], scheme_key)
        data['scheme_key'] = str(scheme_key)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        QMessageBox.information(self, "完成", "重新批改已完成")
        self.load_history()

    def view_detail(self, item):
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        detail = f"题目包：{data.get('package', '')}\n时间：{data.get('timestamp', '')}\n\n录音文件：\n"
        rec = data.get('recordings', {})
        detail += f"Part A: {rec.get('partA', '')}\n"
        for i, r in enumerate(rec.get('partB_secA', []) or []):
            detail += f"Part B SecA #{i + 1}: {r}\n"
        for i, r in enumerate(rec.get('partB_secB', []) or []):
            detail += f"Part B SecB #{i + 1}: {r}\n"
        detail += f"Part C SecA: {rec.get('partC_secA', '')}\n"
        for i, r in enumerate(rec.get('partC_secB', []) or []):
            detail += f"Part C SecB #{i + 1}: {r}\n\n批改结果：\n"

        ev = data.get('evaluation', {})
        sc = ev.get('scores')
        if sc:
            detail += (f"\n【总分】{sc.get('total', 0)} / "
                       f"{sc.get('total_max', 0)}"
                       f"  （{sc.get('scheme_name', '')}）\n")
            d = sc.get('detail', {})
            for k, label in [("partA", "Part A 模仿朗读"),
                             ("partB_secA", "Part B SecA 听选信息"),
                             ("partB_secB", "Part B SecB 回答问题"),
                             ("partC_secA", "Part C SecA 短文复述"),
                             ("partC_secB", "Part C SecB 提问")]:
                if k in d:
                    detail += (f"  {label}: {d[k].get('score', 0)} / "
                               f"{d[k].get('max', 0)}\n")
            detail += "\n"

        if 'partA' in ev:
            detail += (f"Part A 准确率: {ev['partA'].get('accuracy', 0) * 100:.1f}%  "
                       f"WER: {ev['partA'].get('wer', 0):.2f}\n")
        if 'partC_secA' in ev:
            detail += f"Part C 转述要点覆盖: {ev['partC_secA'].get('coverage', '')}\n"
        detail += "\n批改结果基于离线语音识别，仅供参考。"

        dlg = QDialog(self)
        dlg.setWindowTitle("练习详情")
        dlg.resize(720, 640)
        layout = QVBoxLayout(dlg)
        tb = QTextEdit()
        tb.setReadOnly(True)
        tb.setPlainText(detail)
        layout.addWidget(tb)

        mm_copy = data.get("mindmap_copy")
        if mm_copy and os.path.exists(mm_copy):
            mm_lbl = QLabel()
            mm_lbl.setAlignment(Qt.AlignCenter)
            pix = QPixmap(mm_copy)
            if not pix.isNull():
                mm_lbl.setPixmap(pix.scaled(640, 260, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))
                layout.addWidget(QLabel("思维导图："))
                layout.addWidget(mm_lbl)

        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()


def load_vosk_model():
    if not VOSK_AVAILABLE:
        return None
    if not os.path.exists(MODEL_PATH):
        return None
    return Model(MODEL_PATH)


# ========== 更新检查 ==========
UPDATE_INFO_URLS = [
    "https://api.github.com/repos/FallingLighty/SoloTalk/contents/version.json?ref=main",
    "https://cdn.jsdelivr.net/gh/FallingLighty/SoloTalk@main/version.json",
    "https://raw.githubusercontent.com/FallingLighty/SoloTalk/main/version.json",
]
CHANNEL = "mobile" if hasattr(sys, "getandroidapilevel") else "desktop"


class UpdateChecker(QThread):
    update_available = pyqtSignal(dict)

    def run(self):
        data = None
        for url in UPDATE_INFO_URLS:
            try:
                _sep = "&" if "?" in url else "?"
                _url = f"{url}{_sep}t={int(time.time())}"
                req = urllib.request.Request(
                    _url, headers={"User-Agent": f"SoloTalk/{APP_VERSION}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    text = resp.read().decode("utf-8")
                parsed = json.loads(text)
                if isinstance(parsed, dict) and parsed.get("encoding") == "base64" and "content" in parsed:
                    import base64
                    parsed = json.loads(base64.b64decode(parsed["content"]).decode("utf-8"))
                if not (isinstance(parsed, dict) and ("desktop" in parsed or "mobile" in parsed)):
                    raise ValueError("version.json 结构异常")
                data = parsed
                break
            except Exception as e:
                print(f"[UPDATE] 该源不可用: {url} ({e})")
        if data is None:
            return
        try:
            info = data.get(CHANNEL, data.get("desktop", {}))
            if not info:
                return
            latest = str(info.get("version", ""))
            if latest and self._is_newer(latest, APP_VERSION):
                self.update_available.emit({
                    "version": latest,
                    "notes": info.get("notes", ""),
                    "url": info.get("url", ""),
                })
        except Exception as e:
            print(f"[UPDATE] 解析失败: {e}")

    @staticmethod
    def _is_newer(latest, current):
        def _t(v):
            return tuple(int(x) for x in str(v).split(".") if x.strip().isdigit())
        try:
            return _t(latest) > _t(current)
        except Exception:
            return False


# ========== 主入口 ==========
if __name__ == "__main__":
    print("=" * 60)
    print(f"SoloTalk 中考版 v{APP_VERSION}")
    print(f"Vosk: {MODEL_PATH} {'√' if os.path.isdir(MODEL_PATH) else '✗ 未找到'}")
    print(f"TTS : edge-tts {'√ 可用' if EDGE_TTS_AVAILABLE else '✗ 未安装，将用系统 SAPI5'}")
    print(f"分制: {', '.join(k + '=' + v['name'] for k, v in SCORE_SCHEMES.items())}")
    print("=" * 60)

    app = QApplication(sys.argv)
    _app_icon = _resolve_resource_file("xixi.ico")
    if _app_icon:
        app.setWindowIcon(QIcon(_app_icon))
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow { background: #f5f6fa; }
        QLabel { color: #2c3e50; }
        QPushButton { font-size:16px; padding:10px 20px; border-radius:6px; background:#ecf0f1; border:1px solid #bdc3c7; }
        QPushButton:hover { background:#dcdde1; }
        QTextEdit, QLineEdit { border:1px solid #bdc3c7; border-radius:4px; padding:6px; }
    """)
    window = MainWindow()
    sys.exit(app.exec_())
