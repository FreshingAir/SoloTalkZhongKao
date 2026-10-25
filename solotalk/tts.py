# -*- coding: utf-8 -*-
"""语音合成：优先使用 edge-tts 神经语音，不可用时回退系统 SAPI5。

朗读会按文本语言自动挑选音色：中文用中文音色，英文用英文音色。
Part B 听选信息的双角色对话用行首标记区分说话人：
以 "W:" 开头的行用女声，以 "M:" 开头的行用男声，标记本身不会被朗读。
中英混排（例如“题目作者：张三”）会先按语言切段，各段用对应音色合成后再拼接。

对外接口：
    EDGE_TTS_AVAILABLE    是否为可用的在线语音
    detect_language()     判断文本语言（"zh" / "en"）
    split_by_language()   按语言切分中英混排文本
    split_by_speaker()    按 "W:" / "M:" 标记切分对话
    build_voice_plan()    生成 [(语言, 性别, 文本)] 朗读计划
    tts_generate_audio()  生成 mp3 文件，失败返回 False
    speak_blocking()      用系统语音朗读（阻塞，可被 stop_event 打断）
"""

import os
import re
import time
import shutil
import hashlib
import tempfile
import threading

import pyttsx3

from .config import TTS_TIMEOUT

try:
    import edge_tts as _edge_tts
    EDGE_TTS_AVAILABLE = True
except Exception:
    EDGE_TTS_AVAILABLE = False

# 在线神经音色：按语言 + 性别选择；F 女声，M 男声
TTS_EDGE_VOICE = "en-US-JennyNeural"          # 兼容旧调用：英文女声
TTS_EDGE_VOICE_EN = "en-US-JennyNeural"
TTS_EDGE_VOICE_ZH = "zh-CN-XiaoxiaoNeural"
EDGE_VOICES = {
    "en": {"F": "en-US-JennyNeural", "M": "en-US-GuyNeural"},
    "zh": {"F": "zh-CN-XiaoxiaoNeural", "M": "zh-CN-YunxiNeural"},
}

TTS_EDGE_DIR = os.path.join(tempfile.gettempdir(), "solotalk_tts")

# 系统 SAPI5 音色匹配关键词：先按“语言 + 性别”匹配，再退回按语言匹配
SAPI_VOICE_KEYS = {
    ("en", "F"): ("zira", "jenny", "aria", "hazel", "susan", "female"),
    ("en", "M"): ("david", "mark", "guy", "george", "james", "ryan", "male"),
    ("zh", "F"): ("huihui", "xiaoxiao", "xiaoyi", "yaoyao", "female"),
    ("zh", "M"): ("kangkang", "yunxi", "yunyang", "male"),
}
SAPI_LANG_KEYS = {
    "zh": ("zh-cn", "chinese", "mandarin", "普通话", "简体中文"),
    "en": ("en-us", "english"),
}

# 中日韩文字与中文标点（含全角标点）
_CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]')
# 只把西文字母判为英文：数字跟随上下文，避免“50秒”被拆成三段
_LATIN_RE = re.compile(r'[A-Za-z]')
# 句末标点：中文标点后可直接切分，英文标点后需跟空白再切分
_SENT_SPLIT_RE = re.compile(r'(?<=[。！？；…])\s*|(?<=[.!?;:])\s+')
# 可朗读字符：纯标点片段（如中英混排末尾的“。”）交给 edge-tts 会返回空音频
_SPEAKABLE_RE = re.compile(r'[0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
# 行首说话人标记：W:/M:（兼容全角冒号与多余空格）
_SPEAKER_RE = re.compile(r'^\s*([WMwm])\s*[:：]\s*')

# 朗读音频缓存：同一文本（含分角色信息）只合成一次。文件长期保留，
# 下次练习同一题目可直接复用（跳过、返回主页都不会删除），按“最近使用”限量清理。
_CACHE_PREFIX = "cache_v2_"
_CACHE_MAX_FILES = 200
_CACHE_MAX_AGE = 30 * 24 * 3600


def detect_language(text):
    """判断文本语言：含中日韩文字即视为中文，否则视为英文。"""
    if text and _CJK_RE.search(text):
        return "zh"
    return "en"


def split_by_language(text):
    """把中英混排文本切成 [(lang, chunk), ...]，保持原有顺序。

    中文（含中文标点）归为 "zh"，西文归为 "en"；空白等中性字符跟随前一段，
    以免把句子拆散。返回结果已去掉纯空白片段。
    """
    segments = []
    cur_lang = None
    buf = []
    for ch in text or "":
        if _CJK_RE.match(ch):
            lang = "zh"
        elif _LATIN_RE.match(ch):
            lang = "en"
        else:
            lang = cur_lang or "en"
        if lang != cur_lang and buf:
            segments.append((cur_lang, "".join(buf)))
            buf = []
        cur_lang = lang
        buf.append(ch)
    if buf:
        segments.append((cur_lang, "".join(buf)))
    return [(lang, chunk) for lang, chunk in segments if chunk.strip()]


def split_by_speaker(text):
    """按行首 "W:" / "M:" 标记切分双角色对话。

    返回 [(gender, chunk), ...]，gender 为 "F"（W: 女声）/"M"（M: 男声）；
    没有标记的行延续上一句的角色。文本里完全没有标记时返回 [(None, 原文)]。
    """
    lines = (text or "").splitlines()
    if not any(_SPEAKER_RE.match(ln) for ln in lines):
        return [(None, text)]

    blocks = []
    cur_gender = None
    for ln in lines:
        m = _SPEAKER_RE.match(ln)
        if m:
            cur_gender = "F" if m.group(1).upper() == "W" else "M"
            content = ln[m.end():].strip()
        else:
            content = ln.strip()
        if not content:
            continue
        if blocks and blocks[-1][0] == cur_gender:
            blocks[-1][1] = blocks[-1][1] + " " + content
        else:
            blocks.append([cur_gender, content])
    return [(gender, chunk) for gender, chunk in blocks]


def build_voice_plan(text, dialogue=True):
    """生成朗读计划 [(lang, gender, chunk), ...]。

    dialogue=True 时识别 "W:" / "M:" 说话人标记并分别用女声 / 男声；
    每段内部再按语言切分，相邻且语言与性别相同的片段会合并。
    """
    blocks = split_by_speaker(text) if dialogue else [(None, text)]
    plan = []
    for gender, block in blocks:
        for lang, chunk in split_by_language(block):
            if plan and plan[-1][0] == lang and plan[-1][1] == gender:
                plan[-1][2] = plan[-1][2] + " " + chunk
            else:
                plan.append([lang, gender, chunk])
    return [(lang, gender, chunk) for lang, gender, chunk in plan
            if _SPEAKABLE_RE.search(chunk)]


def _edge_voice(lang, gender=None):
    """按语言与性别取在线音色，缺省回退到该语言的默认（女声）音色。"""
    table = EDGE_VOICES.get(lang) or EDGE_VOICES["en"]
    return table.get(gender) or table["F"]


def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _cache_key(text, dialogue):
    raw = ("v2|D1|" if dialogue else "v2|D0|") + (text or "")
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _cache_path(key):
    return os.path.join(TTS_EDGE_DIR, _CACHE_PREFIX + key + ".mp3")


def tts_cached_path(text, dialogue=True):
    """返回该文本对应的朗读音频路径：文件已存在即为合成过，可直接播放。

    音频存放在临时目录并长期保留（按“最近使用”限量清理），
    这样跳过朗读、或下次练习同一题目时都能直接复用，无需重新联网合成。
    """
    try:
        os.makedirs(TTS_EDGE_DIR, exist_ok=True)
    except Exception:
        pass
    return _cache_path(_cache_key(text, dialogue))


def _touch(path):
    """刷新文件的访问时间，清理缓存时视为“最近使用”。"""
    try:
        now = time.time()
        os.utime(path, (now, now))
    except Exception:
        pass


def _load_cache(key, out_path):
    src = _cache_path(key)
    if os.path.isfile(src) and os.path.getsize(src) > 0:
        try:
            if os.path.abspath(src) != os.path.abspath(out_path):
                shutil.copyfile(src, out_path)
            _touch(src)
            return True
        except Exception:
            return False
    return False


def _save_cache(key, out_path):
    try:
        os.makedirs(TTS_EDGE_DIR, exist_ok=True)
        dst = _cache_path(key)
        if os.path.abspath(dst) != os.path.abspath(out_path):
            shutil.copyfile(out_path, dst)
    except Exception:
        pass


def _prune_cache():
    """清理过期与超量的合成缓存，避免临时目录无限膨胀。"""
    try:
        entries = []
        for name in os.listdir(TTS_EDGE_DIR):
            if not name.startswith(_CACHE_PREFIX) or not name.endswith(".mp3"):
                continue
            path = os.path.join(TTS_EDGE_DIR, name)
            try:
                entries.append((os.path.getmtime(path), path))
            except Exception:
                continue
        now = time.time()
        stale = [p for t, p in entries if now - t > _CACHE_MAX_AGE]
        fresh = sorted((t, p) for t, p in entries if now - t <= _CACHE_MAX_AGE)
        if len(fresh) > _CACHE_MAX_FILES:
            stale += [p for _, p in fresh[:len(fresh) - _CACHE_MAX_FILES]]
        for path in stale:
            _safe_remove(path)
    except Exception:
        pass


def tts_generate_audio(text, out_path, dialogue=True):
    """用 edge-tts 生成语音文件；不可用或失败时返回 False（由调用方回退）。

    dialogue=True 时按 "W:" / "M:" 标记用女声 / 男声朗读；
    各片段用对应音色合成后拼接为一个 mp3。生成的音频会保留在缓存中，
    下次练习同一题目可直接复用，无需重新联网合成。
    """
    if not EDGE_TTS_AVAILABLE or not (text and text.strip()):
        return False

    plan = build_voice_plan(text, dialogue)
    if not plan:
        return False

    key = _cache_key(text, dialogue)
    if _load_cache(key, out_path):
        return True

    part_files = []
    try:
        import asyncio

        async def _gen_one(chunk, voice, path):
            com = _edge_tts.Communicate(chunk, voice=voice)
            await asyncio.wait_for(com.save(path), timeout=TTS_TIMEOUT)

        if len(plan) == 1:
            lang, gender, chunk = plan[0]
            asyncio.run(_gen_one(chunk, _edge_voice(lang, gender), out_path))
        else:
            async def _gen_all():
                for idx, (lang, gender, chunk) in enumerate(plan):
                    tmp = "%s.part%d.mp3" % (out_path, idx)
                    await _gen_one(chunk, _edge_voice(lang, gender), tmp)
                    part_files.append(tmp)

            asyncio.run(_gen_all())
            # edge-tts 输出参数一致，按帧拼接即可连续播放
            with open(out_path, "wb") as out:
                for tmp in part_files:
                    with open(tmp, "rb") as f:
                        out.write(f.read())

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            _save_cache(key, out_path)
            _prune_cache()
            return True
        _safe_remove(out_path)
        return False
    except Exception as e:
        print(f"edge-tts 失败，回退系统语音: {e}")
        _safe_remove(out_path)
        return False
    finally:
        for tmp in part_files:
            _safe_remove(tmp)


def split_sentences(text):
    """按句末标点切分（中英文标点都支持），便于系统语音逐句朗读并被及时打断。"""
    parts = _SENT_SPLIT_RE.split((text or "").strip())
    return [p.strip() for p in parts if p and p.strip()]


def _match_voice_id(voices, keys):
    for key in keys:
        for v in voices:
            vid = str(getattr(v, 'id', '') or '')
            name = str(getattr(v, 'name', '') or '')
            if key in (vid + " " + name).lower():
                return getattr(v, 'id', None)
    return None


def _pick_sapi_voice_id(engine, lang, gender=None):
    """在系统已安装音色里挑一个匹配“语言 + 性别”的音色，找不到时退回同语言音色。"""
    try:
        voices = engine.getProperty('voices') or []
    except Exception:
        return None
    voice_id = _match_voice_id(voices, SAPI_VOICE_KEYS.get((lang, gender), ()))
    if voice_id:
        return voice_id
    return _match_voice_id(voices, SAPI_LANG_KEYS.get(lang, ()))


def speak_blocking(text, stop_event=None, dialogue=True):
    """使用系统 SAPI5 语音阻塞朗读，按语言 / 说话人切换音色，可被 stop_event 打断。"""
    if not (text and text.strip()):
        return
    plan = build_voice_plan(text, dialogue)
    if not plan:
        return

    engine = None
    finished = threading.Event()
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 140)
        engine.setProperty('volume', 1.0)

        if stop_event:
            def stop_monitor():
                while not finished.is_set():
                    if stop_event.wait(0.2):
                        try:
                            engine.stop()
                        except Exception:
                            pass
                        return
            threading.Thread(target=stop_monitor, daemon=True).start()

        for lang, gender, chunk in plan:
            if stop_event and stop_event.is_set():
                break
            voice_id = _pick_sapi_voice_id(engine, lang, gender)
            if voice_id:
                try:
                    engine.setProperty('voice', voice_id)
                except Exception:
                    pass
            for sent in (split_sentences(chunk) or [chunk]):
                if stop_event and stop_event.is_set():
                    break
                engine.say(sent)
                engine.runAndWait()
                if stop_event and stop_event.is_set():
                    break
                time.sleep(0.1)
    except Exception as e:
        print(f"TTS error: {e}")
    finally:
        finished.set()
        if engine:
            try:
                engine.stop()
                del engine
            except Exception:
                pass
