"""装配器 —— 把 sections/sNN_*.py 自动拼成一条 ReviewVideo(一个 Scene、一条视频)。

完整渲染:   manim -qm --disable_caching review_main.py ReviewVideo
单章快渲:   ONLY=02 manim -qm --disable_caching review_main.py ReviewVideo   # 只渲第 02 章、跳过片头
自检(推荐):scripts/selfcheck.sh review_main.py ReviewVideo

加一章 = 在 sections/ 丢一个 sNN_*.py(含 NAME 和 build(s)),本文件不用改。
只需改 TITLE / SUBTITLE,和 review_base.py 里的 CJK 一行。
"""
import os

from review_base import BG, ReviewBase, load_sections


class ReviewVideo(ReviewBase):
    TITLE = "Alpha Factor Agent:成员使用流程"
    SUBTITLE = "主线:项目目标 → 可信原理 → 每天怎么协作"

    def construct(self):
        self.camera.background_color = BG
        mods = load_sections(__file__)
        self.sections = [m.NAME for m in mods]      # 片头路线图从各章 NAME 自动生成
        only = os.environ.get("ONLY", "")
        if not only.strip():                        # 片头只在完整渲染时出现
            self.dynamic_toc()
        self.run_sections(mods, only)
