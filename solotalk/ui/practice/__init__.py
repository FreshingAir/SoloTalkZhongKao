# -*- coding: utf-8 -*-
"""练习 / 模考页面。

PracticePage 由若干职责单一的 Mixin 组合而成，避免单文件过长：

    page.PracticePage        页面骨架、状态机调度、试音、计时器、导航、退出
    audio.AudioMixin         TTS 生成与 pygame 音频播放
    recording.RecordingMixin 麦克风录音与 wav 落盘
    progress.ProgressMixin   未完成进度的保存 / 恢复
    evaluation_flow.EvaluationMixin 考试结束后的离线批改与历史记录落盘
    part_a.PartAMixin        Part A 模仿朗读流程
    part_b.PartBMixin        Part B 信息获取流程
    part_c.PartCMixin        Part C 信息转述及询问流程

Mixin 之间不互相调用，只通过 self 访问 PracticePage 的状态与其它方法，
因此组合顺序不影响行为。
"""

from .page import PracticePage

__all__ = ["PracticePage"]
