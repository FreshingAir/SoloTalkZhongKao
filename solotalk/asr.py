# -*- coding: utf-8 -*-
"""离线语音识别（Vosk）。

Vosk 未安装或模型缺失时本模块仍可导入，相关函数返回 None / 空串，
上层据此提示“录音已保存，稍后可重新批改”。
"""

import os
import json
import wave

from .config import MODEL_PATH, SAMPLE_RATE

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False


def load_vosk_model():
    """加载 Vosk 模型；不可用时返回 None。"""
    if not VOSK_AVAILABLE:
        return None
    if not os.path.exists(MODEL_PATH):
        return None
    return Model(MODEL_PATH)


def recognize_audio_file(filepath, model):
    """识别单个 wav 文件，返回文本；格式不符/失败时返回提示串或空串。"""
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
