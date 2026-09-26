# -*- coding: utf-8 -*-
"""SoloTalk 中考版 —— 单机版听说模考编辑器。

包内分层（自底向上，依赖只允许向下）：

    paths            运行环境与资源定位（DLL、日志、诊断、工作目录）
    config           全局常量与分制配置
    settings         用户设置读写
    win_key_blocker  Windows 徽标键屏蔽
    tts              语音合成（edge-tts + SAPI5 回退）
    asr              Vosk 离线识别
    scoring          评分算法与分数换算
    models           数据模型（SoloPackage / PracticeSession）
    evaluation       一次练习会话的离线批改
    updater          版本更新检查
    ui               界面层（各页面 + practice 子包）

程序入口见项目根目录的 ``main.py``。
"""
