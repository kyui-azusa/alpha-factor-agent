"""首屏方法片封面:同一构图,通过 POSTER_THEME 导出亮暗两版静帧。

通常由 ``python scripts/make_hero_media.py`` 调用,无需单独执行。
"""
import os

from manim import (
    Circle,
    DOWN,
    LEFT,
    Line,
    ORIGIN,
    RIGHT,
    RoundedRectangle,
    Scene,
    Text,
    UP,
    VGroup,
)

CJK = "PingFang SC"


class HeroPoster(Scene):
    """方法片的静态主题封面。"""

    def construct(self):
        light = os.environ.get("POSTER_THEME", "dark").lower() == "light"
        bg = "#f6f7fb" if light else "#10131a"
        ink = "#171b26" if light else "#edf2f7"
        muted = "#626b7c" if light else "#99a3b3"
        line = "#d9deea" if light else "#343b49"
        surface = "#ffffff" if light else "#171c26"
        teal = "#0891a9" if light else "#22d3ee"
        green = "#16835c" if light else "#4ade80"
        orange = "#c86617" if light else "#fb923c"
        purple = "#6d4bd1" if light else "#a78bfa"

        self.camera.background_color = bg

        eyebrow = Text("METHOD FILM  /  05:56", font="Menlo", font_size=19, color=teal)
        eyebrow.to_edge(UP, buff=0.58).to_edge(LEFT, buff=0.72)

        title = Text(
            "可解释 Alpha\n因子生成智能体",
            font=CJK,
            font_size=48,
            weight="BOLD",
            color=ink,
            line_spacing=0.88,
        )
        title.next_to(eyebrow, DOWN, aligned_edge=LEFT, buff=0.48)

        subtitle = Text(
            "先讲出道理,再让代码裁决",
            font=CJK,
            font_size=25,
            color=green,
        )
        subtitle.next_to(title, DOWN, aligned_edge=LEFT, buff=0.38)

        rule = Line(LEFT, RIGHT, color=line, stroke_width=2).set_width(5.0)
        rule.next_to(subtitle, DOWN, aligned_edge=LEFT, buff=0.48)

        guard = Text(
            "PIT 对齐  ·  横截面  ·  Rank IC  ·  样本外滚动",
            font=CJK,
            font_size=18,
            color=muted,
        )
        guard.next_to(rule, DOWN, aligned_edge=LEFT, buff=0.34)

        left = VGroup(eyebrow, title, subtitle, rule, guard)
        left.shift(LEFT * 0.16 + DOWN * 0.02)

        panel = RoundedRectangle(
            width=5.1,
            height=5.9,
            corner_radius=0.14,
            fill_color=surface,
            fill_opacity=1,
            stroke_color=line,
            stroke_width=2,
        ).move_to(RIGHT * 4.0 + DOWN * 0.02)

        loop_label = Text("可信闭环", font=CJK, font_size=22, weight="BOLD", color=ink)
        loop_label.move_to(panel.get_top() + DOWN * 0.52).align_to(panel, LEFT).shift(RIGHT * 0.5)

        steps = [
            ("01", "LLM 提想法", teal),
            ("02", "规则编译", purple),
            ("03", "确定性回测", orange),
            ("04", "样本外裁决", green),
        ]
        rows = VGroup()
        for number, label, color in steps:
            dot = Circle(radius=0.27, fill_color=color, fill_opacity=1, stroke_width=0)
            number_text = Text(number, font="Menlo", font_size=13, color=bg, weight="BOLD").move_to(dot)
            step_text = Text(label, font=CJK, font_size=23, color=ink)
            row = VGroup(dot, number_text, step_text)
            dot.move_to(ORIGIN)
            number_text.move_to(dot)
            step_text.next_to(dot, RIGHT, buff=0.28)
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.53)
        rows.move_to(panel.get_center() + UP * 0.03).shift(LEFT * 0.12)

        connectors = VGroup()
        for current, following in zip(rows[:-1], rows[1:]):
            connectors.add(
                Line(
                    current[0].get_bottom(),
                    following[0].get_top(),
                    color=line,
                    stroke_width=3,
                )
            )

        boundary = RoundedRectangle(
            width=4.1,
            height=0.62,
            corner_radius=0.1,
            fill_color=orange,
            fill_opacity=0.09 if light else 0.13,
            stroke_color=orange,
            stroke_width=1.8,
        )
        boundary.move_to(panel.get_bottom() + UP * 0.52)
        boundary_text = Text("LLM 不碰回测", font=CJK, font_size=18, weight="BOLD", color=orange)
        boundary_text.move_to(boundary)

        self.add(left, panel, loop_label, connectors, rows, boundary, boundary_text)
