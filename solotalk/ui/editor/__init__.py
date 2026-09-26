# -*- coding: utf-8 -*-
"""编辑模式：题目包编辑界面的各个子编辑器。

    page.EditorPage          顶部工具栏（名称/署名/分制/新建/打开/保存）+ 三个 Part 页签
    part_a.PartAEditor       Part A 模仿朗读
    part_b.PartBEditor       Part B 信息获取（SecA 听选信息 / SecB 回答问题）
    part_c.PartCEditor       Part C 信息转述及询问（SecA 转述 / SecB 询问）
"""

from .page import EditorPage
from .part_a import PartAEditor
from .part_b import PartBEditor, PartBSecAEditor, PartBSecBEditor
from .part_c import PartCEditor, PartCSecAEditor, PartCSecBEditor

__all__ = [
    "EditorPage",
    "PartAEditor",
    "PartBEditor",
    "PartBSecAEditor",
    "PartBSecBEditor",
    "PartCEditor",
    "PartCSecAEditor",
    "PartCSecBEditor",
]
