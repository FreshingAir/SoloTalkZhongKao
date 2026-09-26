# -*- coding: utf-8 -*-
"""版本更新检查（多源回退，后台线程执行）。"""

import sys
import time
import json
import urllib.request

from PyQt5.QtCore import QThread, pyqtSignal

from .config import APP_VERSION

UPDATE_INFO_URLS = [
    "https://api.github.com/repos/FallingLighty/SoloTalk/contents/version.json?ref=main",
    "https://cdn.jsdelivr.net/gh/FallingLighty/SoloTalk@main/version.json",
    "https://raw.githubusercontent.com/FallingLighty/SoloTalk/main/version.json",
]
CHANNEL = "mobile" if hasattr(sys, "getandroidapilevel") else "desktop"


class UpdateChecker(QThread):
    """按顺序尝试各更新源，发现新版本时发出 update_available 信号。"""

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
