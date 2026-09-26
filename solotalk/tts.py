# -*- coding: utf-8 -*-
"""语音合成：优先使用 edge-tts 神经语音，不可用时回退系统 SAPI5。

对外接口：
    EDGE_TTS_AVAILABLE  是否为可用的在线语音
    tts_generate_audio() 生成 mp3 文件，失败返回 False
    speak_blocking()     用系统语音朗读（阻塞，可被 stop_event 打断）
"""

import os
import time
import tempfile
import threading

import pyttsx3

from .config import TTS_TIMEOUT

try:
    import edge_tts as _edge_tts
    EDGE_TTS_AVAILABLE = True
except Exception:
    EDGE_TTS_AVAILABLE = False

TTS_EDGE_VOICE = "en-US-JennyNeural"
TTS_EDGE_DIR = os.path.join(tempfile.gettempdir(), "solotalk_tts")


def tts_generate_audio(text, out_path):
    """用 edge-tts 生成语音文件；不可用或失败时返回 False（由调用方回退）。"""
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


def split_sentences(text):
    """按句末标点切分，便于系统语音逐句朗读并被及时打断。"""
    import re
    parts = re.split(r'(?<=[.!?;:])\s+', text.strip())
    return [p for p in parts if p.strip()]


def speak_blocking(text, stop_event=None):
    """使用系统 SAPI5 语音阻塞朗读，stop_event 置位后尽快停止。"""
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
        for sent in (split_sentences(text) or [text]):
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
