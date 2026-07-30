#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
widgets.py — 红外学习采集台 复用 UI 组件（tkinter / ttk）

仅在主线程调用这些组件的方法（后台线程通过 queue + after 通知主线程后再调用）。
"""

import tkinter as tk
from tkinter import ttk

# 第十三节：四/六种状态配色（深色主题下保证对比度）
PHASE_COLORS = {
    "IDLE":       {"bg": "#2b2b2b", "fg": "#bbbbbb"},   # 灰
    "PREPARING":  {"bg": "#5a3d00", "fg": "#ffd27f"},   # 橙
    "LEARNING":   {"bg": "#7a0000", "fg": "#ff6b6b"},   # 红/高亮
    "SAVING":     {"bg": "#003a5a", "fg": "#7fd4ff"},   # 蓝
    "SUCCESS":    {"bg": "#0b5d1e", "fg": "#9bffb0"},   # 绿
    "FAILED":     {"bg": "#7a0000", "fg": "#ff8a8a"},   # 红
}

PHASE_TEXT = {
    "IDLE":      "尚未开始：请先设置状态并点击“开始本次采集”",
    "PREPARING": "正在检查模块，请先不要按遥控器",
    "LEARNING":  "现在按遥控器！只短按一次。",
    "SAVING":    "已收到数据，正在校验和保存，请不要再按",
    "SUCCESS":   "本次采集成功，已保存，未回放",
    "FAILED":    "本次采集失败，请查看原因后手动重试",
}


class BigStatusLabel(tk.Label):
    """超大醒目状态标签，按 phase 切换底色与文字。"""

    def __init__(self, master, **kw):
        kw.setdefault("font", ("Microsoft YaHei", 18, "bold"))
        kw.setdefault("anchor", "center")
        kw.setdefault("relief", "ridge")
        kw.setdefault("wraplength", 560)
        kw.setdefault("padx", 8)
        kw.setdefault("pady", 10)
        super().__init__(master, **kw)
        self.set_phase("IDLE")

    def set_phase(self, phase):
        c = PHASE_COLORS.get(phase, PHASE_COLORS["IDLE"])
        self.configure(bg=c["bg"], fg=c["fg"])
        self.configure(text=PHASE_TEXT.get(phase, phase))


class ScrolledLog(tk.Frame):
    """带滚动条的日志文本框。"""

    def __init__(self, master, height=10, **kw):
        super().__init__(master, **kw)
        self.text = tk.Text(self, height=height, state="disabled",
                            bg="#1e1e1e", fg="#d0d0d0",
                            font=("Consolas", 9))
        self.scroll = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

    def append(self, msg):
        self.text.configure(state="normal")
        self.text.insert("end", msg + "\n")
        self.text.configure(state="disabled")
        self.text.see("end")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


def make_combo(master, label, values, default, width=14):
    """返回 (frame, StringVar)。"""
    f = ttk.Frame(master)
    ttk.Label(f, text=label, width=10, anchor="e").pack(side="left", padx=2)
    var = tk.StringVar(value=default)
    cb = ttk.Combobox(f, textvariable=var, values=values,
                      width=width, state="readonly")
    cb.pack(side="left", padx=2)
    return f, var


def make_entry(master, label, default, width=16):
    f = ttk.Frame(master)
    ttk.Label(f, text=label, width=10, anchor="e").pack(side="left", padx=2)
    var = tk.StringVar(value=default)
    e = ttk.Entry(f, textvariable=var, width=width)
    e.pack(side="left", padx=2)
    return f, var
