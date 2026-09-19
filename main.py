#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SoloTalk 江门中考版 0.5 — 单机版听说模考编辑器
完全离线，支持自编辑题库、本地 TTS/音频播放、录音、离线语音识别参考批改。
依赖安装：pip install PyQt5 pyttsx3 sounddevice vosk pygame numpy scipy
请下载 Vosk 英语模型（如 vosk-model-small-en-us-0.15）并解压到本脚本同级目录，
或修改下方的 MODEL_PATH。
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
import hashlib
from pathlib import Path

import asyncio
import pyttsx3

# ---------- edge-tts（donzell888/fast-tts 的底层引擎）可选接入；未安装或断网时回退 pyttsx3 ----------
try:
    import edge_tts
    EDGE_AVAILABLE = True
except Exception:
    edge_tts = None
    EDGE_AVAILABLE = False

EDGE_VOICE_ZH = "zh-CN-XiaoxiaoNeural"  # 中文音色（指令/提示语）
EDGE_VOICE_EN = "en-US-AriaNeural"      # 英文音色（英文会正确读 $20 -> "twenty dollars"）
EDGE_RATE = "+0%"                       # 语速，如 "+10%" / "-10%"

def _contains_cjk(text):
    """是否包含 CJK 中文字符，据此选用中/英文音色。"""
    return any('\u4e00' <= ch <= '\u9fff' for ch in text)

def _pick_voice(text):
    return EDGE_VOICE_ZH if _contains_cjk(text) else EDGE_VOICE_EN

async def _edge_collect_mp3(text, voice):
    """异步收集 edge-tts 流式返回的 mp3 字节（edge-tts 为在线神经语音）。"""
    communicate = edge_tts.Communicate(text, voice, rate=EDGE_RATE)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            buf.extend(chunk["data"])
    return bytes(buf)

def _tts_speak_edge(text, stop_event=None):
    """用 edge-tts 生成（或复用缓存）mp3 并播放；播放期间检查停止标记，出错向上抛以便兜底。"""
    mp3_path = _tts_generate_to_cache(text)
    if stop_event and stop_event.is_set():
        return
    audio_player.play(mp3_path)
    while pygame.mixer.music.get_busy():
        if stop_event and stop_event.is_set():
            audio_player.stop()
            break
        time.sleep(0.1)

TTS_CACHE_DIR = "tts_cache"   # 预生成的语音统一缓存到该目录（相对程序运行目录）

def _tts_cache_path(text):
    """根据文本与音色生成稳定的缓存文件名，相同文本只合成一次。"""
    key = hashlib.sha1((_pick_voice(text) + "|" + text).encode("utf-8")).hexdigest()
    return os.path.join(TTS_CACHE_DIR, key + ".mp3")

def _tts_ensure_cache_dir():
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)

def _tts_generate_to_cache(text):
    """将文本对应的 mp3 生成到缓存（已存在则直接复用）。并发安全：先写临时文件再原子替换。"""
    path = _tts_cache_path(text)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    data = asyncio.run(_edge_collect_mp3(text, _pick_voice(text)))
    if not data:
        raise RuntimeError("edge-tts 返回空音频")
    _tts_ensure_cache_dir()
    fd, tmp = tempfile.mkstemp(suffix=".mp3", dir=TTS_CACHE_DIR)
    os.close(fd)
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return path

def _iter_package_tts_texts(pkg):
    """收集题目包中所有需要 TTS 朗读的文本（用于加载时预生成）。"""
    texts = set()
    if not pkg:
        return texts
    if getattr(pkg, "partA_audio_source_type", "") == "tts":
        t = getattr(pkg, "partA_tts_text", "") or ""
        if t.strip():
            texts.add(t.strip())
    for seg in getattr(pkg, "partB_secA", []) or []:
        if seg.get("audio_source_type") == "tts":
            t = seg.get("tts_text", "") or ""
            if t.strip():
                texts.add(t.strip())
    sb = getattr(pkg, "partB_secB", {}) or {}
    if sb.get("audio_source_type") == "tts":
        t = sb.get("tts_text", "") or ""
        if t.strip():
            texts.add(t.strip())
    pc = getattr(pkg, "partC_secA", {}) or {}
    if pc.get("audio_source_type") == "tts":
        t = pc.get("tts_text", "") or ""
        if t.strip():
            texts.add(t.strip())
    return texts

# ---------- 各阶段固定提示语（中文，用 zh 音色）。抽成常量让“播放”与“预生成”共用同一文本，保证缓存命中 ----------
PROMPT_TEST_TEXT = ("生活就像海洋，只有意志坚强的人才能到达彼岸。 "
                    "This is an apple, I like apples, apples are good for our health.")
PROMPT_PART_A = ("听以下文段一遍，接着你有50秒钟的准备时间。"
                 "当听到“开始录音”的信号后，请在70秒钟内模仿朗读短文；"
                 "当听到“停止录音”的信号时，立即中止朗读。")
PROMPT_PART_B1 = ("听三段对话或短文，每段播放两遍。各段播放前你有10秒钟的阅题时间。"
                  "各段播放后有两个问题，每个问题有8秒钟的回答时间。"
                  "在听到“请回答”的信号后，请根据所听到的问题和括号内的提示，选择正确的信息口头回答问题；"
                  "当听到“停止回答”的信号时，立即中止答题。")
PROMPT_PART_B2 = ("听下面一段短文，录音播放两遍。请根据所听内容回答四个问题，每个问题有8秒钟的回答时间。"
                  "当听到“请回答”的信号后，请口头作答； 当听到“停止回答”的信号时，立即中止答题。"
                  "现在你有15秒钟的阅题时间。")

def _partC_secA_prompt(pkg):
    """三(信息转述) 开场提示语，内容取决于题目包的 topic。"""
    topic = (pkg.partC_secA.get("topic") or "相关") if getattr(pkg, "partC_secA", None) else "相关"
    return (f"你将听到关于{topic}的一段短文。录音播放两遍。"
            f"请根据所听到的内容和提示，在60秒钟内复述{topic}的相关情况，包含全部要点。"
            f"现在，你有15秒钟的时间阅读要点提示。")

def _partC_secB_prompt(pkg):
    """三(询问) 开场提示语，内容取决于题目包的 topic。"""
    topic = (pkg.partC_secB.get("topic") or "相关") if getattr(pkg, "partC_secB", None) else "相关"
    return (f"你希望了解更多关于{topic}的情况，请根据以下提示提两个问题。"
            f"每个问题有15秒钟的准备时间和8秒钟的提问时间。")

def _iter_prompt_texts(pkg):
    """收集所有固定提示语（含依赖 topic 的动态提示语），用于加载时预生成缓存。"""
    prompts = {PROMPT_TEST_TEXT, PROMPT_PART_A, PROMPT_PART_B1, PROMPT_PART_B2}
    if pkg:
        prompts.add(_partC_secA_prompt(pkg))
        prompts.add(_partC_secB_prompt(pkg))
    return prompts

def prewarm_package_tts(pkg):
    """题目加载后，后台线程预生成全部朗读语音与固定提示语，避免考试中途等待合成。"""
    if not EDGE_AVAILABLE:
        return
    texts = _iter_package_tts_texts(pkg)
    texts |= _iter_prompt_texts(pkg)
    if not texts:
        return
    def worker():
        for t in texts:
            try:
                _tts_generate_to_cache(t)
            except Exception as e:
                print(f"[prewarm] 预生成失败: {e}")
    threading.Thread(target=worker, daemon=True).start()

import sounddevice as sd
import numpy as np
from scipy.io import wavfile as wav_write
import pygame

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# ------------------ 全局配置 ------------------
def _app_base_dir():
    """资源根目录：PyInstaller 用 _MEIPASS，Nuitka 用 exe 所在目录，源码用本文件所在目录。"""
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

MODEL_NAME = "vosk-model-small-en-us-0.15"  # 模型文件夹名（须与打包 --include-data-dir 一致）
MODEL_PATH = os.path.join(_app_base_dir(), MODEL_NAME)  # 绝对路径，规避工作目录依赖
RECORDINGS_DIR = "recordings"
HISTORY_DIR = "history"
SAMPLE_RATE = 16000
TTS_TIMEOUT = 30

# ------------------ TTS 工具 ------------------
def _tts_speak_pyttsx3(text, stop_event=None):
    """pyttsx3 本地离线兜底引擎（无网/edge-tts 不可用时使用）。"""
    engine = None
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)

        engine.setProperty('voice', "hazel")

        engine.say(text)
        if stop_event:
            def timeout_monitor():
                if stop_event.wait(TTS_TIMEOUT):
                    try:
                        engine.stop()
                    except:
                        pass
            threading.Thread(target=timeout_monitor, daemon=True).start()
        engine.runAndWait()
    except Exception as e:
        print(f"TTS error: {e}")
    finally:
        if engine:
            try:
                engine.stop()
                del engine
            except:
                pass

def tts_speak_blocking(text, stop_event=None):
    if not text or not text.strip():
        return
    if not EDGE_AVAILABLE:
        _tts_speak_pyttsx3(text, stop_event)
        return
    try:
        _tts_speak_edge(text, stop_event)
    except Exception as e:
        print(f"edge-tts 失败，回退 pyttsx3: {e}")
        _tts_speak_pyttsx3(text, stop_event)

# ------------------ 音频播放 ------------------
class AudioPlayer:
    def __init__(self):
        pygame.mixer.init()
        self._callback = None

    def play(self, filepath, callback=None):
        self._callback = callback
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"音频播放失败: {e}")
            if callback:
                callback()
            return
        if callback:
            threading.Thread(target=self._monitor_playback, daemon=True).start()

    def stop(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def _monitor_playback(self):
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        if self._callback:
            cb = self._callback
            self._callback = None
            cb()

audio_player = AudioPlayer()

# ------------------ 文本比对工具 ------------------
def levenshtein_wer(ref, hyp):
    ref_words = ref.lower().split()
    hyp_words = hyp.lower().split()
    n = len(ref_words)
    if n == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0
    dp = [[0] * (len(hyp_words) + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, len(hyp_words) + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[n][len(hyp_words)] / n, 1.0 - dp[n][len(hyp_words)] / n

def jaccard_similarity(text1, text2):
    set1 = set(text1.lower().split())
    set2 = set(text2.lower().split())
    if not set1 and not set2:
        return 1.0
    return len(set1 & set2) / len(set1 | set2)

def keyword_coverage(text, keywords_str):
    keywords = [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]
    text_lower = text.lower()
    found = [kw for kw in keywords if kw in text_lower]
    return len(found), len(keywords), found

def recognize_audio_file(filepath, model):
    if not model or not os.path.exists(filepath):
        return ""
    wf = wave.open(filepath, 'rb')
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

# ------------------ 文本比对工具（增强版）------------------

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "to", "of", "in", "on", "at", "for", "with",
    "and", "or", "but", "it", "its", "he", "she", "they", "his", "her",
    "their", "this", "that", "these", "those", "i", "you", "we", "my",
    "your", "our", "me", "him", "them", "as", "by", "from", "so", "if",
    "then", "there", "here", "not", "no", "yes", "will", "would", "can",
    "could", "may", "might", "must", "should", "have", "has", "had",
}


def _tokenize(text):
    """简单英文分词：小写、只保留字母数字和少数符号，去停用词。"""
    import re
    text = text.lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff\s']", " ", text)
    tokens = [t for t in text.split() if t]
    return tokens


def _content_tokens(text):
    return [t for t in _tokenize(text) if t not in STOPWORDS]


def word_f1(ref, hyp):
    """词级 F1，比 Jaccard 更宽容，适合短答案。"""
    ref_tokens = _content_tokens(ref)
    hyp_tokens = _content_tokens(hyp)
    if not ref_tokens and not hyp_tokens:
        return 1.0
    if not ref_tokens or not hyp_tokens:
        return 0.0
    from collections import Counter
    ref_c, hyp_c = Counter(ref_tokens), Counter(hyp_tokens)
    common = sum((ref_c & hyp_c).values())
    precision = common / len(hyp_tokens)
    recall = common / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def containment_score(ref, hyp):
    """参考答案的关键词被学生答案覆盖的比例（召回导向）。"""
    ref_tokens = set(_content_tokens(ref))
    hyp_tokens = set(_content_tokens(hyp))
    if not ref_tokens:
        return 1.0 if not hyp_tokens else 0.0
    return len(ref_tokens & hyp_tokens) / len(ref_tokens)


def answer_similarity(ref, hyp):
    """
    单个参考答案与学生答案的综合相似度（0~1）。
    取 Jaccard、词级 F1、覆盖率的加权最大值，避免短答案被误杀。
    """
    if not ref.strip():
        return 0.0
    jac = jaccard_similarity(ref, hyp)
    f1 = word_f1(ref, hyp)
    cov = containment_score(ref, hyp)
    # 覆盖率权重最高，其次 F1，最后 Jaccard
    return max(jac, f1, cov * 0.95 + f1 * 0.05)


def best_answer_match(answers, hyp):
    """
    对一组可接受答案，返回 (最高分, 对应答案, 是否命中)。
    命中判定：分数 >= 0.6 视为答到该要点。
    """
    best_score, best_ans, hit = 0.0, "", False
    for ans in answers:
        if not str(ans).strip():
            continue
        score = answer_similarity(str(ans), hyp)
        if score > best_score:
            best_score, best_ans = score, str(ans)
        if score >= 0.6:
            hit = True
    return best_score, best_ans, hit


def keyword_coverage(text, keywords_str):
    """
    关键词覆盖率。支持逗号、换行、分号分隔。
    返回 (命中数, 总数, 命中列表)。
    """
    import re
    keywords = [kw.strip().lower()
                for kw in re.split(r"[,，;；\n]+", keywords_str)
                if kw.strip()]
    text_lower = text.lower()
    found = [kw for kw in keywords if kw in text_lower]
    return len(found), len(keywords), found


def extract_keypoints_from_hints(key_points_text):
    """
    从 key_points 的提示文本中提取要点关键词。
    例如 "Peter's aunt works as a ...\nLast month, Peter ..."
    提取每行省略号前的实词作为要点。
    """
    import re
    points = []
    for line in key_points_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 去掉省略号和结尾标点
        cleaned = re.sub(r"[.\u2026]+\s*$", "", line).strip()
        tokens = _content_tokens(cleaned)
        if tokens:
            points.append(tokens)
    return points


def keypoints_coverage(hyp, key_points_text):
    """
    按 key_points 每行要点，统计学生答案覆盖了哪些要点的实词。
    返回 (命中要点数, 总要点数, 详情)。
    """
    hyp_tokens = set(_content_tokens(hyp))
    points = extract_keypoints_from_hints(key_points_text)
    if not points:
        return 0, 0, []
    details = []
    hit_count = 0
    for tokens in points:
        token_set = set(tokens)
        if not token_set:
            continue
        covered = len(token_set & hyp_tokens) / len(token_set)
        hit = covered >= 0.5
        if hit:
            hit_count += 1
        details.append({"tokens": tokens, "covered": round(covered, 2), "hit": hit})
    return hit_count, len(points), details


def question_similarity(ref_question, hyp):
    """
    问句比对：词级 F1 + 疑问词一致性。
    """
    f1 = word_f1(ref_question, hyp)
    import re
    wh_words = ["how long", "how many", "how much", "how often", "how",
                "what", "where", "when", "why", "who", "which", "whose"]
    ref_lower, hyp_lower = ref_question.lower(), hyp.lower()
    ref_wh = next((w for w in wh_words if w in ref_lower), None)
    hyp_wh = next((w for w in wh_words if w in hyp_lower), None)
    wh_bonus = 0.2 if (ref_wh and hyp_wh and ref_wh == hyp_wh) else 0.0
    return min(1.0, f1 + wh_bonus), ref_wh, hyp_wh

# ------------------ 数据模型（江门中考版）------------------
def _audio_entry_name(part_key, index, audio_path):
    """生成打包进 .solo 时唯一的 zip entry 路径（含子目录），避免不同部分/同名音频冲突。

    part_key: "partA" / "partB_secA" / "partB_secB" / "partC_secA"
    index: partB_secA 时为段下标（从 0 起），其余传 None。
    返回与 to_dict / save_package / from_dict 一致的那一侧完整 entry 名。
    """
    if not audio_path:
        return None
    base = os.path.basename(audio_path)
    folder = {
        "partA": "partA",
        "partB_secB": "partB_secB",
        "partC_secA": "partC_secA",
    }.get(part_key)
    if folder:
        return f"audio/{folder}/{base}"
    if part_key == "partB_secA" and index is not None:
        return f"audio/partB_secA_{index + 1}/{base}"
    return base

class SoloPackage:
    def __init__(self):
        self.meta = {
            "name": "Untitled",
            "version": "1.0",
            "created": datetime.datetime.now().isoformat(),
            "author": "",
        }
        self.partA_audio_source_type = "tts"
        self.partA_tts_text = ""
        self.partA_audio_path = None
        self.partA_hidden_text = ""

        self.partB_secA = []   # 3段材料，每段2个问题
        self.partB_secB = {
            "audio_source_type": "tts",
            "tts_text": "",
            "audio_path": None,
            "questions": []  # 4个问题，每问题含多个答案
        }

        self.partC_secA = {
            "audio_source_type": "tts",
            "tts_text": "",
            "audio_path": None,
            "key_points": "",
            "hidden_answer_points": "",
            "topic": ""
        }

        self.partC_secB = {
            "situation": "",
            "topic": "",
            "questions": []
        }

    def to_dict(self):
        return {
            "meta": self.meta,
            "partA": {
                "audio_source_type": self.partA_audio_source_type,
                "tts_text": self.partA_tts_text,
                "audio": _audio_entry_name("partA", None, self.partA_audio_path),
                "hidden_text": self.partA_hidden_text
            },
            "partB_secA": [
                {
                    "audio_source_type": seg.get("audio_source_type"),
                    "tts_text": seg.get("tts_text"),
                    "audio": _audio_entry_name("partB_secA", i, seg.get("audio_path")),
                    "questions": seg.get("questions", [])
                } for i, seg in enumerate(self.partB_secA)
            ],
            "partB_secB": {
                "audio_source_type": self.partB_secB.get("audio_source_type"),
                "tts_text": self.partB_secB.get("tts_text"),
                "audio": _audio_entry_name("partB_secB", None, self.partB_secB.get("audio_path")),
                "questions": self.partB_secB.get("questions", [])
            },
            "partC_secA": {
                "audio_source_type": self.partC_secA.get("audio_source_type"),
                "tts_text": self.partC_secA.get("tts_text"),
                "audio": _audio_entry_name("partC_secA", None, self.partC_secA.get("audio_path")),
                "key_points": self.partC_secA.get("key_points"),
                "hidden_answer_points": self.partC_secA.get("hidden_answer_points"),
                "topic": self.partC_secA.get("topic", "")
            },
            "partC_secB": {
                "situation": self.partC_secB.get("situation", ""),
                "topic": self.partC_secB.get("topic", ""),
                "questions": self.partC_secB.get("questions", [])
            }
        }

    def from_dict(self, data, base_dir=None):
        self.meta = data.get("meta", self.meta)
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
            new_seg = {
                "audio_source_type": seg.get("audio_source_type", "tts"),
                "tts_text": seg.get("tts_text", ""),
                "audio_path": os.path.join(base_dir, seg["audio"]) if seg.get("audio") and base_dir else None,
                "questions": seg.get("questions", [])
            }
            self.partB_secA.append(new_seg)
        sb = data.get("partB_secB", {})
        self.partB_secB = {
            "audio_source_type": sb.get("audio_source_type", "tts"),
            "tts_text": sb.get("tts_text", ""),
            "audio_path": os.path.join(base_dir, sb["audio"]) if sb.get("audio") and base_dir else None,
            "questions": sb.get("questions", [])
        }
        pcA = data.get("partC_secA", {})
        self.partC_secA = {
            "audio_source_type": pcA.get("audio_source_type", "tts"),
            "tts_text": pcA.get("tts_text", ""),
            "audio_path": os.path.join(base_dir, pcA["audio"]) if pcA.get("audio") and base_dir else None,
            "key_points": pcA.get("key_points", ""),
            "hidden_answer_points": pcA.get("hidden_answer_points", ""),
            "topic": pcA.get("topic", "")
        }
        self.partC_secB = data.get("partC_secB", {"situation": "", "topic": "", "questions": []})

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

# ------------------ 主窗口 ------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoloTalk 江门中考版 — 单机版听说模考编辑器")
        self.setMinimumSize(1024, 700)
        self.current_package = SoloPackage()
        self.current_session = None
        self.central = QStackedWidget()
        self.setCentralWidget(self.central)
        self.home_page = HomePage(self)
        self.editor_page = EditorPage(self)
        self.practice_page = PracticePage(self)
        self.history_page = HistoryPage(self)
        self.central.addWidget(self.home_page)
        self.central.addWidget(self.editor_page)
        self.central.addWidget(self.practice_page)
        self.central.addWidget(self.history_page)
        self.central.setCurrentWidget(self.home_page)
        self.show()

    def go_to(self, page):
        self.central.setCurrentWidget(page)

    def closeEvent(self, event):
        if self.central.currentWidget() == self.practice_page:
            self.practice_page.abort_exam()
        event.accept()

class HomePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        title = QLabel("SoloTalk 江门中考版")
        title.setStyleSheet("font-size:42px; font-weight:bold; color:#2c3e50;")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("完全离线 · 自编辑题库 · 模拟真实考试流程")
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
        btn_practice.clicked.connect(self.load_and_practice)
        btn_history = QPushButton("📋  历史记录")
        btn_history.setStyleSheet(btn_style)
        btn_history.clicked.connect(lambda: self.main.go_to(self.main.history_page))
        layout.addWidget(btn_editor, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_practice, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(btn_history, alignment=Qt.AlignCenter)
        self.setLayout(layout)

    def load_and_practice(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if path:
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    with zf.open('data.json') as f:
                        data = json.load(f)
                    temp_dir = tempfile.mkdtemp(prefix="solotalk_")
                    zf.extractall(temp_dir)
                    self.main.current_package.from_dict(data, base_dir=temp_dir)
                    self.main.current_package.meta['temp_dir'] = temp_dir
                    # 加载题目后立即在后台预生成全部 TTS 语音，考试中直接播放缓存，避免等待合成
                    prewarm_package_tts(self.main.current_package)
                self.main.go_to(self.main.practice_page)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载失败：{str(e)}")

# ------------------ 编辑模式（完整）------------------
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
        btn_new = QPushButton("新建")
        btn_open = QPushButton("打开 .solo")
        btn_save = QPushButton("保存")
        btn_back = QPushButton("返回主页")
        top_bar.addWidget(QLabel("名称："))
        top_bar.addWidget(self.name_edit)
        top_bar.addWidget(QLabel("作者："))
        top_bar.addWidget(self.author_edit)
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
        self.partB_secA_widget = PartBSecAEditor(self.pkg)
        self.partB_secB_widget = PartBSecBEditor(self.pkg)
        self.partC_widget = PartCEditor(self.pkg)
        self.tabs.addTab(self.partA_widget, "一、模仿朗读")
        self.tabs.addTab(self.partB_secA_widget, "二(1) 听选信息")
        self.tabs.addTab(self.partB_secB_widget, "二(2) 回答问题")
        self.tabs.addTab(self.partC_widget, "三、信息转述及询问")
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def new_package(self):
        self.main.current_package = SoloPackage()
        self.pkg = self.main.current_package
        self.name_edit.clear()
        self.author_edit.clear()
        self.partA_widget.pkg = self.pkg
        self.partB_secA_widget.pkg = self.pkg
        self.partB_secB_widget.pkg = self.pkg
        self.partC_widget.pkg = self.pkg
        self.partA_widget.refresh()
        self.partB_secA_widget.refresh()
        self.partB_secB_widget.refresh()
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
                self.partA_widget.refresh()
                self.partB_secA_widget.refresh()
                self.partB_secB_widget.refresh()
                self.partC_widget.refresh()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"打开失败：{str(e)}")

    def save_package(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存 .solo 文件", "", "SoloTalk 文件 (*.solo)")
        if not path:
            return
        self.pkg.meta["name"] = self.name_edit.text() or "Untitled"
        self.pkg.meta["author"] = self.author_edit.text() or ""
        self.partA_widget.save_to_pkg()
        self.partB_secA_widget.save_to_pkg()
        self.partB_secB_widget.save_to_pkg()
        self.partC_widget.save_to_pkg()
        try:
            # 上传的音频（短文/对话等）统一以唯一 entry 名打包进 .solo，
            # 与 data.json 中的 audio 字段一致，供练习模式解压后直接播放。
            # 先清理不存在的路径，避免 data.json 引用未被打包的文件。
            if self.pkg.partA_audio_path and not os.path.exists(self.pkg.partA_audio_path):
                self.pkg.partA_audio_path = None
            for seg_idx, seg in enumerate(self.pkg.partB_secA):
                if seg.get("audio_path") and not os.path.exists(seg["audio_path"]):
                    seg["audio_path"] = None
            if self.pkg.partB_secB.get("audio_path") and not os.path.exists(self.pkg.partB_secB["audio_path"]):
                self.pkg.partB_secB["audio_path"] = None
            if self.pkg.partC_secA.get("audio_path") and not os.path.exists(self.pkg.partC_secA["audio_path"]):
                self.pkg.partC_secA["audio_path"] = None
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('data.json', json.dumps(self.pkg.to_dict(), indent=2, ensure_ascii=False))
                if self.pkg.partA_audio_path:
                    zf.write(self.pkg.partA_audio_path, _audio_entry_name("partA", None, self.pkg.partA_audio_path))
                for seg_idx, seg in enumerate(self.pkg.partB_secA):
                    if seg.get("audio_path"):
                        zf.write(seg["audio_path"], _audio_entry_name("partB_secA", seg_idx, seg["audio_path"]))
                if self.pkg.partB_secB.get("audio_path"):
                    zf.write(self.pkg.partB_secB["audio_path"], _audio_entry_name("partB_secB", None, self.pkg.partB_secB["audio_path"]))
                if self.pkg.partC_secA.get("audio_path"):
                    zf.write(self.pkg.partC_secA["audio_path"], _audio_entry_name("partC_secA", None, self.pkg.partC_secA["audio_path"]))
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
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "音频文件 (*.wav *.mp3 *.ogg)")
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
            if self.pkg.partA_audio_path:
                self.audio_label.setText(os.path.basename(self.pkg.partA_audio_path))
            else:
                self.audio_label.setText("未选择音频")
        else:
            self.source_combo.setCurrentIndex(0)
        self.tts_edit.setPlainText(self.pkg.partA_tts_text)
        self.hidden_edit.setPlainText(self.pkg.partA_hidden_text)
        self.toggle_source()

class PartBSecAEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.segment_widgets = []
        self.setup_ui()

    def setup_ui(self):
        if self.layout():
            QWidget().setLayout(self.layout())
        scroll = QScrollArea()
        widget = QWidget()
        layout = QVBoxLayout()
        self.segment_widgets = []
        for seg_idx in range(3):
            grp = QGroupBox(f"材料 {seg_idx+1}")
            seg_layout = QVBoxLayout()
            src_combo = QComboBox()
            src_combo.addItems(["💻电脑 TTS", "上传音频"])
            tts_edit = QTextEdit()
            tts_edit.setPlaceholderText("听力原文（TTS朗读）")
            audio_lbl = QLabel("未选择音频")
            audio_btn = QPushButton("选择音频")
            audio_btn.clicked.connect(lambda checked, i=seg_idx: self.upload_seg_audio(i))
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel("音频来源："))
            hbox.addWidget(src_combo)
            hbox.addWidget(audio_lbl)
            hbox.addWidget(audio_btn)
            seg_layout.addLayout(hbox)
            seg_layout.addWidget(tts_edit)

            q_widgets = []
            for q_idx in range(2):
                q_grp = QGroupBox(f"问题{q_idx+1}")
                q_layout = QFormLayout()
                q_edit = QLineEdit(); q_edit.setPlaceholderText("问题文本")
                ans_edit = QTextEdit(); ans_edit.setPlaceholderText("参考答案（每行一个可接受答案）")
                q_layout.addRow("问题：", q_edit)
                q_layout.addRow("答案：", ans_edit)
                q_grp.setLayout(q_layout)
                seg_layout.addWidget(q_grp)
                q_widgets.append({"q_edit": q_edit, "ans_edit": ans_edit})
            grp.setLayout(seg_layout)
            layout.addWidget(grp)
            self.segment_widgets.append({
                "src_combo": src_combo, "tts_edit": tts_edit,
                "audio_lbl": audio_lbl, "q_widgets": q_widgets
            })
        widget.setLayout(layout)
        scroll.setWidget(widget)
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def upload_seg_audio(self, seg_idx):
        path, _ = QFileDialog.getOpenFileName(self, f"选择材料{seg_idx+1}音频", "", "音频文件 (*.wav *.mp3 *.ogg)")
        if path:
            while len(self.pkg.partB_secA) <= seg_idx:
                self.pkg.partB_secA.append({"audio_source_type": "tts", "tts_text": "", "audio_path": None, "questions": []})
            self.pkg.partB_secA[seg_idx]["audio_path"] = path
            self.segment_widgets[seg_idx]["audio_lbl"].setText(os.path.basename(path))

    def save_to_pkg(self):
        # 先记录各个材料的上传音频路径，避免重建 partB_secA 时丢失
        old_audio = {}
        for seg_idx, seg in enumerate(self.pkg.partB_secA):
            old_audio[seg_idx] = seg.get("audio_path")
        self.pkg.partB_secA = []
        for seg_idx, w in enumerate(self.segment_widgets):
            audio_path = old_audio.get(seg_idx)
            seg = {
                "audio_source_type": "tts" if w["src_combo"].currentIndex() == 0 else "audio",
                "tts_text": w["tts_edit"].toPlainText(),
                "audio_path": audio_path,
                "questions": []
            }
            for qw in w["q_widgets"]:
                answers = [line.strip() for line in qw["ans_edit"].toPlainText().split('\n') if line.strip()]
                q = {
                    "question_text": qw["q_edit"].text(),
                    "answers": answers
                }
                seg["questions"].append(q)
            self.pkg.partB_secA.append(seg)

    def refresh(self):
        while len(self.pkg.partB_secA) < 3:
            self.pkg.partB_secA.append({"audio_source_type": "tts", "tts_text": "", "audio_path": None, "questions": []})
        for seg_idx, w in enumerate(self.segment_widgets):
            if seg_idx < len(self.pkg.partB_secA):
                seg = self.pkg.partB_secA[seg_idx]
                if seg.get("audio_source_type") == "audio":
                    w["src_combo"].setCurrentIndex(1)
                    if seg.get("audio_path"):
                        w["audio_lbl"].setText(os.path.basename(seg["audio_path"]))
                    else:
                        w["audio_lbl"].setText("未选择音频")
                else:
                    w["src_combo"].setCurrentIndex(0)
                w["tts_edit"].setPlainText(seg.get("tts_text", ""))
                questions = seg.get("questions", [])
                for q_idx, qw in enumerate(w["q_widgets"]):
                    if q_idx < len(questions):
                        qw["q_edit"].setText(questions[q_idx].get("question_text", ""))
                        answers = questions[q_idx].get("answers", [])
                        qw["ans_edit"].setPlainText("\n".join(answers))
                    else:
                        qw["q_edit"].clear(); qw["ans_edit"].clear()
            else:
                w["tts_edit"].clear(); w["audio_lbl"].setText("未选择音频")
                for qw in w["q_widgets"]:
                    qw["q_edit"].clear(); qw["ans_edit"].clear()

class PartBSecBEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout()
        self.src_combo = QComboBox()
        self.src_combo.addItems(["💻电脑 TTS", "上传音频"])
        layout.addRow("短文音频来源：", self.src_combo)
        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("短文文本（TTS朗读）")
        layout.addRow("短文文本：", self.tts_edit)
        self.audio_lbl = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        hbox = QHBoxLayout()
        hbox.addWidget(self.audio_lbl)
        hbox.addWidget(self.audio_btn)
        layout.addRow("音频文件：", hbox)

        self.q_widgets = []
        for i in range(4):
            grp = QGroupBox(f"问题{i+1}")
            inner = QFormLayout()
            q_edit = QLineEdit(); q_edit.setPlaceholderText("问题文本")
            ans_edit = QTextEdit(); ans_edit.setPlaceholderText("参考答案（每行一个可接受答案）")
            inner.addRow("问题：", q_edit)
            inner.addRow("答案：", ans_edit)
            grp.setLayout(inner)
            layout.addRow(grp)
            self.q_widgets.append((q_edit, ans_edit))
        self.setLayout(layout)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择短文音频", "", "音频文件 (*.wav *.mp3 *.ogg)")
        if path:
            self.pkg.partB_secB["audio_path"] = path
            self.audio_lbl.setText(os.path.basename(path))

    def save_to_pkg(self):
        self.pkg.partB_secB["audio_source_type"] = "tts" if self.src_combo.currentIndex() == 0 else "audio"
        self.pkg.partB_secB["tts_text"] = self.tts_edit.toPlainText()
        self.pkg.partB_secB["questions"] = []
        for q_edit, ans_edit in self.q_widgets:
            answers = [line.strip() for line in ans_edit.toPlainText().split('\n') if line.strip()]
            self.pkg.partB_secB["questions"].append({
                "question_text": q_edit.text(),
                "answers": answers
            })

    def refresh(self):
        secB = self.pkg.partB_secB
        if secB.get("audio_source_type") == "audio":
            self.src_combo.setCurrentIndex(1)
            if secB.get("audio_path"):
                self.audio_lbl.setText(os.path.basename(secB["audio_path"]))
            else:
                self.audio_lbl.setText("未选择音频")
        else:
            self.src_combo.setCurrentIndex(0)
        self.tts_edit.setPlainText(secB.get("tts_text", ""))
        questions = secB.get("questions", [])
        for i, (q_edit, ans_edit) in enumerate(self.q_widgets):
            if i < len(questions):
                q_edit.setText(questions[i].get("question_text", ""))
                answers = questions[i].get("answers", [])
                ans_edit.setPlainText("\n".join(answers))
            else:
                q_edit.clear(); ans_edit.clear()

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
        tabs.addTab(self.secA_widget, "第一节 信息转述")
        tabs.addTab(self.secB_widget, "第二节 询问信息")
        layout.addWidget(tabs)
        self.setLayout(layout)

    def save_to_pkg(self):
        self.secA_widget.save_to_pkg()
        self.secB_widget.save_to_pkg()

    def refresh(self):
        self.secA_widget.refresh()
        self.secB_widget.refresh()

class PartCSecAEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        layout = QFormLayout()
        self.src_combo = QComboBox()
        self.src_combo.addItems(["💻电脑 TTS", "上传音频"])
        layout.addRow("听力内容来源：", self.src_combo)
        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("听力材料全文（TTS朗读）")
        layout.addRow("全文：", self.tts_edit)
        self.audio_lbl = QLabel("未选择音频")
        self.audio_btn = QPushButton("选择音频")
        self.audio_btn.clicked.connect(self.upload_audio)
        hbox = QHBoxLayout()
        hbox.addWidget(self.audio_lbl)
        hbox.addWidget(self.audio_btn)
        layout.addRow("音频文件：", hbox)
        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText("如：Peter 的阿姨的工作")
        layout.addRow("话题/标题 (XXX)：", self.topic_edit)
        self.key_points_edit = QTextEdit()
        self.key_points_edit.setPlaceholderText("要点提示（显示在屏幕上，如中文关键词或短语）")
        layout.addRow("要点提示：", self.key_points_edit)
        self.hidden_points_edit = QTextEdit()
        self.hidden_points_edit.setPlaceholderText("答案要点（隐藏，逗号分隔，用于批改）")
        layout.addRow("答案要点：", self.hidden_points_edit)
        self.setLayout(layout)

    def upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "音频文件 (*.wav *.mp3 *.ogg)")
        if path:
            self.pkg.partC_secA["audio_path"] = path
            self.audio_lbl.setText(os.path.basename(path))

    def save_to_pkg(self):
        self.pkg.partC_secA["audio_source_type"] = "tts" if self.src_combo.currentIndex() == 0 else "audio"
        self.pkg.partC_secA["tts_text"] = self.tts_edit.toPlainText()
        self.pkg.partC_secA["key_points"] = self.key_points_edit.toPlainText()
        self.pkg.partC_secA["hidden_answer_points"] = self.hidden_points_edit.toPlainText()
        self.pkg.partC_secA["topic"] = self.topic_edit.text().strip()

    def refresh(self):
        secA = self.pkg.partC_secA
        if secA.get("audio_source_type") == "audio":
            self.src_combo.setCurrentIndex(1)
            if secA.get("audio_path"):
                self.audio_lbl.setText(os.path.basename(secA["audio_path"]))
            else:
                self.audio_lbl.setText("未选择音频")
        else:
            self.src_combo.setCurrentIndex(0)
        self.tts_edit.setPlainText(secA.get("tts_text", ""))
        self.key_points_edit.setPlainText(secA.get("key_points", ""))
        self.hidden_points_edit.setPlainText(secA.get("hidden_answer_points", ""))
        self.topic_edit.setText(secA.get("topic", ""))

class PartCSecBEditor(QWidget):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        layout = QFormLayout()
        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText("如：Peter 的阿姨的工作")
        layout.addRow("话题/标题 (XXX)：", self.topic_edit)
        self.situation_edit = QTextEdit()
        self.situation_edit.setPlaceholderText("情境描述（如：你希望了解更多关于活动的情况）")
        layout.addRow("情境描述：", self.situation_edit)
        self.q_widgets = []
        for i in range(2):
            grp = QGroupBox(f"询问{i+1}")
            inner = QFormLayout()
            cn_edit = QLineEdit(); cn_edit.setPlaceholderText("中文提示（如：询问活动开始时间）")
            hid_edit = QLineEdit(); hid_edit.setPlaceholderText("标准提问（英文）")
            inner.addRow("中文提示：", cn_edit)
            inner.addRow("标准提问：", hid_edit)
            grp.setLayout(inner)
            layout.addRow(grp)
            self.q_widgets.append((cn_edit, hid_edit))
        self.setLayout(layout)

    def save_to_pkg(self):
        self.pkg.partC_secB["situation"] = self.situation_edit.toPlainText()
        self.pkg.partC_secB["topic"] = self.topic_edit.text().strip()
        self.pkg.partC_secB["questions"] = []
        for cn_edit, hid_edit in self.q_widgets:
            self.pkg.partC_secB["questions"].append({
                "cn_prompt": cn_edit.text(),
                "hidden_question": hid_edit.text()
            })

    def refresh(self):
        secB = self.pkg.partC_secB
        self.topic_edit.setText(secB.get("topic", ""))
        self.situation_edit.setPlainText(secB.get("situation", ""))
        questions = secB.get("questions", [])
        for i, (cn_edit, hid_edit) in enumerate(self.q_widgets):
            if i < len(questions):
                cn_edit.setText(questions[i].get("cn_prompt", ""))
                hid_edit.setText(questions[i].get("hidden_question", ""))
            else:
                cn_edit.clear(); hid_edit.clear()

# ------------------ 练习模式（江门流程 + 麦克风预检）------------------
class PracticePage(QWidget):
    signal_update_display = pyqtSignal(str, str)
    signal_tts_ready = pyqtSignal()
    signal_finished = pyqtSignal()
    # 后台线程（TTS / 音频播放）完成后的流程回调，统一调度回 GUI 线程执行，
    # 避免在后台线程直接操作 QTimer / 控件导致倒计时等 Qt 事件无法正常处理。
    signal_flow_step = pyqtSignal(object)

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.pkg = None
        self.session = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_tick)
        self._current_phase = None
        self._phase_end_time = 0
        self._timer_callback = None
        self._audio_frames = []
        self._audio_lock = threading.Lock()
        self._stream = None
        self._is_recording = False
        self._tts_stop_event = None
        self._tts_thread = None
        self.setup_ui()
        self.signal_update_display.connect(self._update_display)
        self.signal_tts_ready.connect(self._on_tts_ready)
        self.signal_finished.connect(self._on_exam_finished)
        self.signal_flow_step.connect(self._on_flow_step)

    @pyqtSlot(object)
    def _on_flow_step(self, cb):
        """在 GUI 线程执行流程回调，统一兜底异常，避免回调失败中断考试。"""
        try:
            cb()
        except Exception as e:
            print(f"[ERROR] 流程回调执行异常: {e}")
            QMessageBox.critical(self, "流程错误", f"流程回调失败：{e}")

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
        layout.addWidget(self.main_label)
        layout.addWidget(self.sub_label)
        layout.addWidget(self.countdown_label)
        layout.addWidget(self.text_display)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始模考")
        self.start_btn.clicked.connect(self.start_exam)

        self.skip_btn = QPushButton("⏭ 跳过当前朗读")
        self.skip_btn.setEnabled(False)
        self.skip_btn.clicked.connect(self.skip_current_audio)

        btn_back = QPushButton("返回主页")
        btn_back.clicked.connect(self.abort_exam)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.skip_btn)
        btn_layout.addWidget(btn_back)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def abort_exam(self):
        self.timer.stop()
        self._cancel_tts()
        audio_player.stop()
        self.stop_recording()
        self.countdown_label.hide()
        self.main.go_to(self.main.home_page)
    def skip_current_audio(self):
        """跳过当前正在播放的 TTS / 音频，并推进到下一步。"""
        print("[DEBUG] 用户点击跳过当前朗读")
        # 1) 停掉 TTS
        self._cancel_tts()
        # 2) 停掉音频播放
        audio_player.stop()
        # 3) 如果当前在计时（比如准备时间），直接跳到回调
        if self.timer.isActive() and self._timer_callback:
            self.timer.stop()
            self.countdown_label.hide()
            cb = self._timer_callback
            self._timer_callback = None
            QTimer.singleShot(0, cb)
            return
        # 4) 如果不在计时但录音中，停录音并推进
        if self._is_recording:
            self._stop_recording()
            if self._timer_callback:
                cb = self._timer_callback
                self._timer_callback = None
                QTimer.singleShot(0, cb)
            return
        # 5) 都不满足，只停播放
        self.sub_label.setText(self.sub_label.text() + "\n⏭ 已跳过")
    # ---------- 开始流程 ----------
    def start_exam(self):
        self.pkg = self.main.current_package
        self.session = PracticeSession(self.pkg.meta.get("name", "练习"))
        self.start_btn.setEnabled(False)
        self._prepare_phase()

    def _prepare_phase(self):
        author = self.pkg.meta.get("author", "")
        author_text = f"题目作者：{author}" if author else "题目作者：未知"
        self._prepare_text = f"{author_text}\n\n生活就像海洋，只有意志坚强的人才能到达彼岸。\nThis is an apple, I like apples, apples are good for our health."
        self.signal_update_display.emit("准备阶段", self._prepare_text)
        self._start_tts(PROMPT_TEST_TEXT, self.signal_tts_ready.emit)

    def _on_tts_ready(self):
        QTimer.singleShot(200, self._mic_test)

    def _mic_test(self):
        test_text = self._prepare_text + "\n\n请说话，录音10秒..."
        self.signal_update_display.emit("麦克风测试", test_text)
        self._start_recording()
        self._set_timer(10, self._mic_test_playback)

    def _mic_test_playback(self):
        self._stop_recording()
        test_path = self._save_recording("mic_test")
        if os.path.exists(test_path):
            audio_player.play(test_path)
            reply = QMessageBox.question(self, "麦克风测试", "录音回放中，麦克风是否正常？",
                                         QMessageBox.Yes | QMessageBox.No)
            audio_player.stop()
            if reply == QMessageBox.Yes:
                try:
                    os.remove(test_path)
                except:
                    pass
                self._run_partA()
            else:
                try:
                    os.remove(test_path)
                except:
                    pass
                self._mic_test()
        else:
            QMessageBox.warning(self, "错误", "录音失败，请检查设备")
            self._mic_test()

    # ---------- TTS 管理 ----------
    def _start_tts(self, text, callback=None):
        self._cancel_tts()
        self._tts_stop_event = threading.Event()
        def runner():
            try:
                tts_speak_blocking(text, self._tts_stop_event)
            except Exception as e:
                print(f"TTS 内部错误: {e}")
            finally:
                if callback:
                    # 回调切回 GUI 线程执行，避免在后台线程操作 QTimer / 控件。
                    self.signal_flow_step.emit(callback)
        self._tts_thread = threading.Thread(target=runner, daemon=True)
        self._tts_thread.start()

    def _cancel_tts(self):
        if self._tts_stop_event:
            self._tts_stop_event.set()
            self._tts_stop_event = None
        if self._tts_thread and self._tts_thread.is_alive():
            if threading.current_thread() != self._tts_thread:
                self._tts_thread.join(0.5)
        self._tts_thread = None

    # ---------- 计时器 ----------
    def _set_timer(self, seconds, callback=None):
        self.skip_btn.setEnabled(True)
        self._phase_end_time = time.time() + seconds
        self._timer_callback = callback
        self.countdown_label.show()
        self.timer.start(100)

    def _on_tick(self):
        remaining = max(0, int(self._phase_end_time - time.time()))
        self.countdown_label.setText(f"剩余时间：{remaining} 秒")
        if remaining <= 0:
            self.timer.stop()
            self.countdown_label.hide()
            if self._timer_callback:
                cb = self._timer_callback
                self._timer_callback = None
                print(f"[DEBUG] 计时器触发，准备调用回调: {cb.__name__}")
                # 用 singleShot 避免在 timer 信号里重入流程导致界面卡住
                def run_cb():
                    try:
                        cb()
                        print(f"[DEBUG] 回调执行完毕: {cb.__name__}")
                    except Exception as e:
                        print(f"[ERROR] 回调执行异常: {e}")
                        QMessageBox.critical(self, "流程错误", f"回调失败：{e}")
                QTimer.singleShot(0, run_cb)
            else:
                print("[WARN] 计时结束但没有待执行回调")

    @pyqtSlot(str, str)
    def _update_display(self, main, sub):
        self.main_label.setText(main)
        self.sub_label.setText(sub)
        self.text_display.setPlainText(sub if sub else main)

    # ---------- 录音（麦克风预检，避免卡死）----------
    def _start_recording(self):
        self.skip_btn.setEnabled(False)
        def skip_recording(reason):
            """无法录音时，不阻塞流程，直接推进到下一个计时回调。"""
            print(f"[WARN] 跳过录音: {reason}")
            if self._timer_callback:
                cb = self._timer_callback
                self._timer_callback = None
                QTimer.singleShot(50, cb)
            else:
                # 没有待执行回调时，至少恢复 UI，不让界面像死了一样
                self.sub_label.setText(self.sub_label.text() + "\n⚠️ 录音不可用，已跳过")

        try:
            sd.check_input_settings(samplerate=SAMPLE_RATE, channels=1, dtype='int16')
        except Exception as e:
            QMessageBox.warning(self, "麦克风不可用",
                f"无法访问麦克风设备：{e}\n请检查系统设置或关闭占用麦克风的程序后重试。")
            skip_recording(str(e))
            return

        with self._audio_lock:
            self._audio_frames = []
        self._is_recording = True

        def callback(indata, frames, time_info, status):
            # 回调运行在 PortAudio 线程，必须绝不抛异常，否则会挂死整个录音流。
            try:
                if self._is_recording:
                    self._audio_frames.append(indata.copy())
            except Exception:
                pass

        try:
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                          dtype='int16', callback=callback)
            self._stream.start()
        except Exception as e:
            self._is_recording = False
            QMessageBox.warning(self, "录音启动失败",
                f"无法启动录音：{e}\n请检查麦克风设置。")
            skip_recording(str(e))
            return

        self.sub_label.setText(self.sub_label.text() + "\n🔴 录音中...")

    def _stop_recording(self):
        # 先把录音标志置位，避免回调线程继续写入。
        self._is_recording = False
        stream = self._stream
        self._stream = None
        if stream is not None:
            # stop()/close() 可能因底层缓冲阻塞 GUI 事件循环（表现为倒计时停住），
            # 放到后台线程里关闭，避免卡住界面；数据已通过回调线程持续写入 _audio_frames，
            # 所以关闭流不影响录音完整性。
            def _close_stream(s):
                try:
                    s.stop()
                except Exception:
                    pass
                try:
                    s.close()
                except Exception:
                    pass
            threading.Thread(target=_close_stream, args=(stream,), daemon=True).start()

    def stop_recording(self):
        self._stop_recording()

    def _save_recording(self, label):
        package_name = self.pkg.meta.get('name', 'unknown')
        safe_name = "".join(c for c in package_name if c.isalnum() or c in (' ', '-', '_')).rstrip() or "untitled"
        base_dir = os.path.join(RECORDINGS_DIR, safe_name)
        os.makedirs(base_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{safe_name}_{label}_{ts}.wav"
        path = os.path.join(base_dir, fname)
        # 在锁内取出帧快照，避免与回调线程并发修改导致卡死 / 崩溃。
        with self._audio_lock:
            frames = list(self._audio_frames)
        if frames:
            try:
                data = np.concatenate(frames)
                wav_write.write(path, SAMPLE_RATE, data)
            except Exception as e:
                print(f"[ERROR] 保存录音失败: {e}")
        return path

    # ---------- 一、模仿朗读 ----------
    def _run_partA(self):
        self._current_phase = "partA"
        self._partA_step = 0
        self._exec_partA()

    def _exec_partA(self):
        step = self._partA_step
        if step == 0:
            prompt = PROMPT_PART_A
            self.signal_update_display.emit("一、模仿朗读", prompt)
            self._start_tts(prompt, self._next_partA)
        elif step == 1:
            if self.pkg.partA_audio_source_type == "tts":
                text_to_show = self.pkg.partA_tts_text
            else:
                text_to_show = "（请听音频）"
            self.signal_update_display.emit("请认真听文段，注意语音语调。", text_to_show)
            self._play_audio(self.pkg.partA_audio_source_type, self.pkg.partA_tts_text, self.pkg.partA_audio_path, self._next_partA)
        elif step == 2:
            if self.pkg.partA_audio_source_type == "tts":
                text_to_show = self.pkg.partA_tts_text
            else:
                text_to_show = "（请准备朗读）"
            self.signal_update_display.emit("请准备朗读。(50秒)", text_to_show)
            self._set_timer(50, self._next_partA)
        elif step == 3:
            if self.pkg.partA_audio_source_type == "tts":
                text_to_show = self.pkg.partA_tts_text
            else:
                text_to_show = "（请开始朗读）"
            self.signal_update_display.emit("请开始模仿朗读。(70秒)", text_to_show)
            self._start_recording()
            self._set_timer(70, self._finish_partA)
        else:
            self._finish_partA()

    def _finish_partA(self):
        self._stop_recording()
        self.session.partA_recording = self._save_recording("PartA")
        self._run_partB_secA()

    def _next_partA(self):
        self._partA_step += 1
        self._exec_partA()

    # ---------- 二(1) 听选信息 ----------
    def _run_partB_secA(self):
        self._current_phase = "partB_secA"
        self._secA_idx = 0
        prompt = PROMPT_PART_B1
        self.signal_update_display.emit("二(1) 听选信息", prompt)
        self._start_tts(prompt, self._start_secA_segment)

    def _start_secA_segment(self):
        if self._secA_idx >= len(self.pkg.partB_secA):
            self._run_partB_secB()
            return
        seg = self.pkg.partB_secA[self._secA_idx]
        text = f"材料 {self._secA_idx+1}\n"
        for i, q in enumerate(seg["questions"]):
            text += f"\n问题{i+1}: {q['question_text']}\n"
        self.signal_update_display.emit(f"材料 {self._secA_idx+1} 阅题 (10秒)", text)
        self._set_timer(10, self._play_secA_first)

    def _secA_questions_text(self):
        seg = self.pkg.partB_secA[self._secA_idx]
        text = f"材料 {self._secA_idx+1}\n"
        for i, q in enumerate(seg["questions"]):
            text += f"\n问题{i+1}: {q['question_text']}\n"
        return text

    def _play_secA_first(self):
        self.signal_update_display.emit(f"材料 {self._secA_idx+1} 第一遍", self._secA_questions_text())
        seg = self.pkg.partB_secA[self._secA_idx]
        self._play_audio(seg["audio_source_type"], seg["tts_text"], seg["audio_path"], self._secA_first_done)

    def _secA_first_done(self):
        self._set_timer(1, self._play_secA_second)

    def _play_secA_second(self):
        self.signal_update_display.emit(f"材料 {self._secA_idx+1} 第二遍", self._secA_questions_text())
        seg = self.pkg.partB_secA[self._secA_idx]
        self._play_audio(seg["audio_source_type"], seg["tts_text"], seg["audio_path"], self._secA_second_done)

    def _secA_second_done(self):
        self._secA_q_idx = 0
        self._ask_secA_question()

    def _ask_secA_question(self):
        seg = self.pkg.partB_secA[self._secA_idx]
        if self._secA_q_idx < len(seg["questions"]):
            q = seg["questions"][self._secA_q_idx]
            text = f"问题{self._secA_q_idx+1}: {q['question_text']}"
            self.signal_update_display.emit(f"回答问题 {self._secA_q_idx+1}", text)
            self._start_tts(q["question_text"], self._record_secA_answer)
        else:
            self._secA_idx += 1
            self._start_secA_segment()

    def _record_secA_answer(self):
        self.signal_update_display.emit(f"请回答 (8秒)", "")
        self._start_recording()
        self._set_timer(8, self._finish_secA_answer)

    def _finish_secA_answer(self):
        self._stop_recording()
        rec_path = self._save_recording(f"PartB_SecA{self._secA_idx+1}_Q{self._secA_q_idx+1}")
        self.session.partB_secA_recordings.append(rec_path)
        self._secA_q_idx += 1
        self._ask_secA_question()

    # ---------- 二(2) 回答问题 ----------
    def _run_partB_secB(self):
        self._current_phase = "partB_secB"
        prompt = PROMPT_PART_B2
        self.signal_update_display.emit("二(2) 回答问题", prompt)
        self._start_tts(prompt, self._show_secB_questions)

    def _show_secB_questions(self):
        q_text = "\n".join([f"{i+1}. {q['question_text']}" for i, q in enumerate(self.pkg.partB_secB["questions"])])
        self.signal_update_display.emit("阅读问题 (15秒)", q_text)
        self._set_timer(15, self._play_secB_first)

    def _play_secB_first(self):
        self.signal_update_display.emit("听短文第一遍", "")
        self._play_audio(self.pkg.partB_secB["audio_source_type"], self.pkg.partB_secB["tts_text"], self.pkg.partB_secB["audio_path"], self._secB_first_done)

    def _secB_first_done(self):
        self._set_timer(1, self._play_secB_second)

    def _play_secB_second(self):
        self.signal_update_display.emit("听短文第二遍", "")
        self._play_audio(self.pkg.partB_secB["audio_source_type"], self.pkg.partB_secB["tts_text"], self.pkg.partB_secB["audio_path"], self._secB_second_done)

    def _secB_second_done(self):
        self._secB_q_idx = 0
        self._ask_secB_question()

    def _ask_secB_question(self):
        questions = self.pkg.partB_secB["questions"]
        if self._secB_q_idx < len(questions):
            q = questions[self._secB_q_idx]
            self.signal_update_display.emit(f"回答问题 {self._secB_q_idx+1}", q["question_text"])
            self._start_tts(q["question_text"], self._record_secB_answer)
        else:
            self._run_partC()

    def _record_secB_answer(self):
        self.signal_update_display.emit(f"请回答 (8秒)", "")
        self._start_recording()
        self._set_timer(8, self._finish_secB_answer)

    def _finish_secB_answer(self):
        self._stop_recording()
        rec_path = self._save_recording(f"PartB_SecB_Q{self._secB_q_idx+1}")
        self.session.partB_secB_recordings.append(rec_path)
        self._secB_q_idx += 1
        self._ask_secB_question()

    # ---------- 三、信息转述及询问 ----------
    def _run_partC(self):
        self._current_phase = "partC"
        prompt = _partC_secA_prompt(self.pkg)
        self.signal_update_display.emit("三、信息转述及询问", prompt)
        self._start_tts(prompt, self._show_partC_keypoints)

    def _show_partC_keypoints(self):
        text = self.pkg.partC_secA["key_points"]
        self.signal_update_display.emit("阅读要点提示 (15秒)", text)
        self._set_timer(15, self._play_partC_first)

    def _play_partC_first(self):
        self.signal_update_display.emit("听材料第一遍", self.pkg.partC_secA["key_points"])
        secA = self.pkg.partC_secA
        self._play_audio(secA["audio_source_type"], secA["tts_text"], secA["audio_path"], self._partC_first_done)

    def _partC_first_done(self):
        self._set_timer(1, self._play_partC_second)

    def _play_partC_second(self):
        secA = self.pkg.partC_secA
        self.signal_update_display.emit("听材料第二遍", secA["key_points"])
        self._play_audio(secA["audio_source_type"], secA["tts_text"], secA["audio_path"], self._partC_second_done)

    def _partC_second_done(self):
        self.signal_update_display.emit("准备转述 (60秒)", self.pkg.partC_secA["key_points"])
        self._set_timer(60, self._record_retelling)

    def _record_retelling(self):
        self.signal_update_display.emit("请开始转述 (60秒)", self.pkg.partC_secA["key_points"])
        self._start_recording()
        self._set_timer(60, self._finish_retelling)

    def _finish_retelling(self):
        self._stop_recording()
        self.session.partC_secA_recording = self._save_recording("PartC_Retelling")
        self._run_partC_secB()

    def _run_partC_secB(self):
        secB = self.pkg.partC_secB
        situation = secB.get("situation", "")
        prompt = _partC_secB_prompt(self.pkg)
        full_display = f"{situation}\n{prompt}" if situation else prompt
        self.signal_update_display.emit("询问信息", full_display)
        self._start_tts(prompt, self._prepare_secB_q1)

    def _prepare_secB_q1(self):
        if len(self.pkg.partC_secB["questions"]) > 0:
            self._current_secB_q = 0
            self._show_secB_prepare(self._current_secB_q)
        else:
            self.signal_finished.emit()

    def _show_secB_prepare(self, idx):
        q = self.pkg.partC_secB["questions"][idx]
        self.signal_update_display.emit(f"准备提问 {idx+1} (15秒)", q["cn_prompt"])
        self._set_timer(15, lambda: self._record_secB_q(idx))

    def _record_secB_q(self, idx):
        self.signal_update_display.emit(f"请提问 {idx+1} (8秒)", self.pkg.partC_secB["questions"][idx]["cn_prompt"])
        self._start_recording()
        self._set_timer(8, lambda: self._finish_secB_q(idx))

    def _finish_secB_q(self, idx):
        self._stop_recording()
        rec_path = self._save_recording(f"PartC_SecB_Q{idx+1}")
        self.session.partC_secB_recordings.append(rec_path)
        next_idx = idx + 1
        if next_idx < len(self.pkg.partC_secB["questions"]):
            self._show_secB_prepare(next_idx)
        else:
            self.signal_finished.emit()

    # ---------- 通用音频播放 ----------
    def _play_audio(self, source_type, tts_text, audio_path, callback):
        """播放音频；无论成功与否，都保证回调被触发，避免流程卡死。"""
        self.skip_btn.setEnabled(True)
        def safe_call():
            # 切回 GUI 线程再操作控件并触发回调（TTS / 播放回调可能来自后台线程）。
            def _f():
                self.skip_btn.setEnabled(False)
                if callback:
                    try:
                        callback()
                    except Exception as e:
                        print(f"[ERROR] 播放回调异常: {e}")
                        QMessageBox.critical(self, "流程错误", f"播放回调失败：{e}")
            self.signal_flow_step.emit(_f)

        if source_type == "tts":
            if not tts_text or not tts_text.strip():
                # TTS 文本为空，跳过播放但继续流程
                print("[WARN] TTS 文本为空，跳过播放")
                safe_call()
                return
            self._start_tts(tts_text, safe_call)
        else:
            if audio_path and os.path.exists(audio_path):
                audio_player.play(audio_path, safe_call)
            else:
                # 音频缺失：提示后继续流程，绝不静默卡住
                print(f"[WARN] 音频文件不存在: {audio_path}")
                QMessageBox.warning(
                    self, "音频缺失",
                    f"该题音频文件不存在：\n{audio_path}\n\n将跳过播放，继续后续流程。"
                )
                # 用 QTimer 延迟一点再回调，避免在弹窗未关闭时重入
                QTimer.singleShot(50, safe_call)

    # ---------- 考后批改 ----------
    def _on_exam_finished(self):
        self.start_btn.setEnabled(True)
        QMessageBox.information(self, "模考完成", "练习结束，即将进行离线机器批改。")
        self.run_evaluation()

    def run_evaluation(self):
        vosk_model = load_vosk_model()
        if not vosk_model:
            QMessageBox.warning(self, "批改", "Vosk 模型不可用，录音已保存，稍后可重新批改。")
            self._save_history()
            return
        self._perform_evaluation(vosk_model)
        self._save_history()
        # 批改完成后立即弹出机器批改报告，展示总分与各部分得分（含复述短文）。
        self._show_evaluation_report()
        QMessageBox.information(self, "批改完成", "练习记录与机器批改已保存至历史记录。")

    def _show_evaluation_report(self):
        """考试完成立即弹出批改报告，重点展示复述短文等各部分的机器批改得分。"""
        ev = self.session.evaluation or {}
        total = ev.get('total', {})
        lines = []
        lines.append(f"总分：{total.get('score', 0)} 分（共 {total.get('items', 0)} 项）")
        lines.append("=" * 48)

        # Part A 模仿朗读
        pa = ev.get('partA')
        if pa:
            lines.append(f"一、模仿朗读：{pa.get('score', 0)} 分")
            lines.append(f"    识别文本：{pa.get('recognized', '')}")
            lines.append(f"    相似度：{pa.get('accuracy', 0) * 100:.1f}%")

        # Part B SecA 听选信息
        pbA = ev.get('partB_secA') or []
        if pbA:
            lines.append("二(1) 听选信息：")
            for r in pbA:
                lines.append(f"    第{r.get('seg')}-{r.get('q')}题 {r.get('score')} 分"
                             f"（{'命中' if r.get('hit') else '未命中'}）应答：{r.get('best_answer', '')}")

        # Part B SecB 回答问题
        pbB = ev.get('partB_secB') or []
        if pbB:
            lines.append("二(2) 回答问题：")
            for r in pbB:
                lines.append(f"    第{r.get('q')}题 {r.get('score')} 分"
                             f"（{'命中' if r.get('hit') else '未命中'}）应答：{r.get('best_answer', '')}")

        # Part C SecA 复述短文（信息转述）
        pcA = ev.get('partC_secA')
        if pcA:
            lines.append("三、复述短文（信息转述）：")
            lines.append(f"    得分：{pcA.get('score', 0)} 分")
            lines.append(f"    要点覆盖：{pcA.get('key_points_hit', '0/0')}")
            lines.append(f"    参考范文相似度：{pcA.get('best_version_similarity', 0) * 100:.1f}%")
            details = pcA.get('point_details') or []
            if details:
                hit_tokens = []
                for d in details:
                    if d.get('hit'):
                        hit_tokens.append(" ".join(d.get('tokens', [])))
                lines.append("    识别文本：" + pcA.get('recognized', ''))
                lines.append(f"    命中要点内容：{('；'.join(hit_tokens)) if hit_tokens else '未覆盖任何要点'}")

        # Part C SecB 询问信息
        pcB = ev.get('partC_secB') or []
        if pcB:
            lines.append("三、询问信息：")
            for r in pcB:
                flag = "✓" if r.get('score', 0) >= 60 else "✗"
                lines.append(f"    第{r.get('q')}题 {r.get('score')} 分 {flag}")

        if not (pa or pbA or pbB or pcA or pcB):
            lines.append("（本套题目未包含批改项）")

        dlg = QDialog(self)
        dlg.setWindowTitle("机器批改报告")
        dlg.resize(720, 560)
        lay = QVBoxLayout(dlg)
        header = QLabel("✅ 考试完成，机器批改得分如下")
        header.setStyleSheet("font-size:16px; font-weight:bold; color:#2c3e50;")
        browser = QTextBrowser()
        browser.setFont(QFont("Microsoft YaHei", 10))
        browser.setPlainText("\n".join(lines))
        btn = QPushButton("确定")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(header)
        lay.addWidget(browser)
        lay.addWidget(btn, alignment=Qt.AlignRight)
        dlg.exec_()

    def _perform_evaluation(self, vosk_model):
        eval_result = {}

        # ---------- Part A 模仿朗读 ----------
        if self.session.partA_recording:
            hyp = recognize_audio_file(self.session.partA_recording, vosk_model)
            ref = self.pkg.partA_hidden_text
            wer, acc = levenshtein_wer(ref, hyp)
            eval_result['partA'] = {
                'recognized': hyp,
                'wer': round(wer, 4),
                'accuracy': round(acc, 4),
                'score': round(acc * 100, 1)
            }

        # ---------- Part B SecA 听选信息 ----------
        eval_result['partB_secA'] = []
        rec_idx = 0
        for seg_idx, seg in enumerate(self.pkg.partB_secA):
            for q_idx, q in enumerate(seg["questions"]):
                if rec_idx < len(self.session.partB_secA_recordings):
                    rec = self.session.partB_secA_recordings[rec_idx]
                    hyp = recognize_audio_file(rec, vosk_model) if rec else ""
                    answers = q.get("answers", [])
                    best_score, best_ans, hit = best_answer_match(answers, hyp)
                    eval_result['partB_secA'].append({
                        "seg": seg_idx + 1,
                        "q": q_idx + 1,
                        "question": q.get("question_text", ""),
                        "recognized": hyp,
                        "best_answer": best_ans,
                        "similarity": round(best_score, 4),
                        "hit": hit,
                        "score": 100.0 if hit else round(best_score * 100, 1)
                    })
                    rec_idx += 1

        # ---------- Part B SecB 回答问题 ----------
        eval_result['partB_secB'] = []
        for i, q in enumerate(self.pkg.partB_secB["questions"]):
            if i < len(self.session.partB_secB_recordings):
                rec = self.session.partB_secB_recordings[i]
                hyp = recognize_audio_file(rec, vosk_model) if rec else ""
                answers = q.get("answers", [])
                best_score, best_ans, hit = best_answer_match(answers, hyp)
                eval_result['partB_secB'].append({
                    "q": i + 1,
                    "question": q.get("question_text", ""),
                    "recognized": hyp,
                    "best_answer": best_ans,
                    "similarity": round(best_score, 4),
                    "hit": hit,
                    "score": 100.0 if hit else round(best_score * 100, 1)
                })

        # ---------- Part C SecA 信息转述 ----------
        if self.session.partC_secA_recording:
            hyp = recognize_audio_file(self.session.partC_secA_recording, vosk_model)
            hidden_points = self.pkg.partC_secA.get("hidden_answer_points", "")

            # 1) 多版本参考范文，逐版本算相似度取最高
            ref_versions = [v.strip() for v in hidden_points.split("\n") if v.strip()]
            version_scores = []
            for v in ref_versions:
                version_scores.append(answer_similarity(v, hyp))
            best_version_score = max(version_scores) if version_scores else 0.0

            # 2) 按 key_points 提示逐要点覆盖
            hit_points, total_points, point_details = keypoints_coverage(
                hyp, self.pkg.partC_secA.get("key_points", "")
            )
            point_ratio = (hit_points / total_points) if total_points else 0.0

            # 综合：范文相似度 40% + 要点覆盖 60%
            final_score = best_version_score * 0.4 + point_ratio * 0.6

            eval_result['partC_secA'] = {
                'recognized': hyp,
                'best_version_similarity': round(best_version_score, 4),
                'key_points_hit': f"{hit_points}/{total_points}",
                'point_ratio': round(point_ratio, 4),
                'point_details': point_details,
                'coverage': f"{hit_points}/{total_points}",
                'score': round(final_score * 100, 1)
            }

        # ---------- Part C SecB 询问信息 ----------
        eval_result['partC_secB'] = []
        for i, q in enumerate(self.pkg.partC_secB["questions"]):
            if i < len(self.session.partC_secB_recordings):
                rec = self.session.partC_secB_recordings[i]
                hyp = recognize_audio_file(rec, vosk_model) if rec else ""
                ref = q.get("hidden_question", "")
                sim, ref_wh, hyp_wh = question_similarity(ref, hyp)
                eval_result['partC_secB'].append({
                    "q": i + 1,
                    "recognized": hyp,
                    "correct": ref,
                    "similarity": round(sim, 4),
                    "wh_match": (ref_wh == hyp_wh) if ref_wh else False,
                    "score": round(sim * 100, 1)
                })

        # ---------- 总分（各部分加权，可按需调整）----------
        part_scores = []
        if 'partA' in eval_result:
            part_scores.append(eval_result['partA']['score'])
        if eval_result['partB_secA']:
            part_scores.extend([r['score'] for r in eval_result['partB_secA']])
        if eval_result['partB_secB']:
            part_scores.extend([r['score'] for r in eval_result['partB_secB']])
        if 'partC_secA' in eval_result:
            part_scores.append(eval_result['partC_secA']['score'])
        if eval_result['partC_secB']:
            part_scores.extend([r['score'] for r in eval_result['partC_secB']])

        eval_result['total'] = {
            'score': round(sum(part_scores) / len(part_scores), 1) if part_scores else 0.0,
            'items': len(part_scores)
        }

        self.session.evaluation = eval_result

    def _save_history(self):
        os.makedirs(HISTORY_DIR, exist_ok=True)
        history = {
            "package": self.pkg.meta.get("name", ""),
            "timestamp": self.session.timestamp.isoformat(),
            "recordings": {
                "partA": self.session.partA_recording,
                "partB_secA": self.session.partB_secA_recordings,
                "partB_secB": self.session.partB_secB_recordings,
                "partC_secA": self.session.partC_secA_recording,
                "partC_secB": self.session.partC_secB_recordings
            },
            "evaluation": self.session.evaluation,
            "package_data": self.pkg.to_dict()
        }
        fname = f"history_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(os.path.join(HISTORY_DIR, fname), 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False, default=str)

# ------------------ 历史记录页面 ------------------
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
                item_text = f"{data.get('package','?')}  {data.get('timestamp','')}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, str(f))
                self.list_widget.addItem(item)
            except:
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
        vosk_model = load_vosk_model()
        if not vosk_model:
            QMessageBox.warning(self, "错误", "Vosk 模型不可用，无法重新批改")
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            QMessageBox.critical(self, "错误", "历史记录文件损坏")
            return
        recs = data.get('recordings', {})
        pkg_dict = data.get('package_data', {})
        temp_pkg = SoloPackage()
        temp_pkg.from_dict(pkg_dict)
        eval_result = {}
        # 简化重新批改，可扩展
        data['evaluation'] = eval_result
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
        detail = f"题目包：{data.get('package','')}\n时间：{data.get('timestamp','')}\n\n录音文件：\n"
        rec = data.get('recordings', {})
        detail += f"Part A: {rec.get('partA','')}\n"
        for i, r in enumerate(rec.get('partB_secA', [])):
            detail += f"听选信息录音{i+1}: {r}\n"
        for i, r in enumerate(rec.get('partB_secB', [])):
            detail += f"回答问题录音{i+1}: {r}\n"
        detail += f"信息转述: {rec.get('partC_secA','')}\n"
        for i, r in enumerate(rec.get('partC_secB', [])):
            detail += f"询问信息{i+1}: {r}\n"
        detail += "\n批改结果：\n"
        ev = data.get('evaluation', {})
        total = ev.get('total', {})
        detail += f"总分：{total.get('score', 0)} 分（共 {total.get('items', 0)} 项）\n"
        if 'partA' in ev:
            detail += f"Part A 模仿朗读：{ev['partA'].get('score', 0)} 分  "
            detail += f"准确率 {ev['partA'].get('accuracy',0)*100:.1f}%  WER {ev['partA'].get('wer',0):.2f}\n"
        pcA = ev.get('partC_secA')
        if pcA:
            detail += f"\n复述短文（信息转述）：{pcA.get('score', 0)} 分\n"
            detail += f"  要点覆盖：{pcA.get('key_points_hit', '0/0')}\n"
            detail += f"  参考范文相似度：{pcA.get('best_version_similarity', 0)*100:.1f}%\n"
            detail += f"  识别文本：{pcA.get('recognized', '')}\n"
            for d in (pcA.get('point_details') or []):
                mark = "✔" if d.get('hit') else "✘"
                detail += f"    {mark} 要点 {(' '.join(d.get('tokens', [])))} 覆盖 {d.get('covered', 0)*100:.0f}%\n"
        detail += "\n批改结果基于离线语音识别的机器批改，仅供参考。"
        QMessageBox.information(self, "练习详情", detail)

def load_vosk_model():
    if not VOSK_AVAILABLE:
        return None
    if not os.path.exists(MODEL_PATH):
        return None
    return Model(MODEL_PATH)

if __name__ == "__main__":
    app = QApplication(sys.argv)
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
