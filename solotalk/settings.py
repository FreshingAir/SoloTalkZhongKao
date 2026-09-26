# -*- coding: utf-8 -*-
"""用户设置（solotalk_settings.json）读写。"""

import os
import sys
import json

from .config import SETTINGS_FILE
from .paths import BASE_DIR, SCRIPT_DIR, resolve_resource_file


def load_settings():
    """读取用户设置，失败或无文件时返回空字典。"""
    try:
        path = resolve_resource_file(SETTINGS_FILE) or SETTINGS_FILE
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"[SETTINGS] 读取失败: {e}")
    return {}


def save_settings(data):
    """把设置写回程序根目录，成功返回 True。"""
    try:
        if getattr(sys, "frozen", False):
            path = os.path.join(BASE_DIR, SETTINGS_FILE)
        else:
            path = os.path.join(SCRIPT_DIR, SETTINGS_FILE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[SETTINGS] 保存失败: {e}")
        return False
