# -*- coding: utf-8 -*-
"""全局常量与评分分制配置。"""

from .paths import resolve_model_dir

# ========== 全局配置 ==========
APP_VERSION = "2.1"
MODEL_PATH = resolve_model_dir("vosk-model-small-en-us-0.15")
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


def get_scheme(key):
    """按 key 取分制配置，非法 key 回退到默认分制。"""
    return SCORE_SCHEMES.get(str(key), SCORE_SCHEMES[DEFAULT_SCHEME])
