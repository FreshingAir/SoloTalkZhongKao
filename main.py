#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SoloTalk 中考版 2.1 — 单机版听说模考编辑器（广州中考题型）

依赖安装：pip install PyQt5 pyttsx3 sounddevice vosk pygame numpy edge-tts
（edge-tts 为高质量神经语音，需联网；未安装或断网时自动回退系统 SAPI5 语音）

Vosk 英语模型请下载并解压到本脚本同级目录，或修改 solotalk/config.py 中的 MODEL_PATH。

题型：Part A 模仿朗读 / Part B 听选+回答 / Part C 信息转述+询问
评分：Levenshtein WER / Jaccard / keyword_coverage
分制：30分制 / 25分制，由编辑模式指定并随 .solo 包保存

本文件只做三件事：初始化运行环境、创建 QApplication、显示主窗口。
具体实现按职责拆分在 ``solotalk`` 包内，详见包内各模块文档字符串。
"""

import os
import sys

# 必须最先导入：注册 DLL 目录、安装诊断日志与异常钩子、切换工作目录
from solotalk import paths  # noqa: F401  (导入即产生副作用，勿删)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from solotalk.config import APP_VERSION, MODEL_PATH, SCORE_SCHEMES
from solotalk.paths import resolve_resource_file
from solotalk.tts import EDGE_TTS_AVAILABLE
from solotalk.ui.main_window import MainWindow

# 兼容旧代码/脚本从 main 直接引用这些名字
from solotalk.models import PracticeSession, SoloPackage  # noqa: F401
from solotalk.scoring import compute_scores  # noqa: F401
from solotalk.evaluation import evaluate_recordings  # noqa: F401

STYLE_SHEET = """
    QMainWindow { background: #f5f6fa; }
    QLabel { color: #2c3e50; }
    QPushButton { font-size:16px; padding:10px 20px; border-radius:6px; background:#ecf0f1; border:1px solid #bdc3c7; }
    QPushButton:hover { background:#dcdde1; }
    QTextEdit, QLineEdit { border:1px solid #bdc3c7; border-radius:4px; padding:6px; }
"""


def print_startup_banner():
    print("=" * 60)
    print(f"SoloTalk 中考版 v{APP_VERSION}")
    print(f"Vosk: {MODEL_PATH} {'√' if os.path.isdir(MODEL_PATH) else '✗ 未找到'}")
    print(f"TTS : edge-tts {'√ 可用' if EDGE_TTS_AVAILABLE else '✗ 未安装，将用系统 SAPI5'}")
    print(f"分制: {', '.join(k + '=' + v['name'] for k, v in SCORE_SCHEMES.items())}")
    print("=" * 60)


def main():
    """程序入口：创建 QApplication 并进入事件循环，返回退出码。"""
    print_startup_banner()

    app = QApplication(sys.argv)
    _app_icon = resolve_resource_file("xixi.ico")
    if _app_icon:
        app.setWindowIcon(QIcon(_app_icon))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()  # noqa: F841  (持有引用，防止被回收)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
