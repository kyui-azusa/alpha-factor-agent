"""manim-review 公共底座 —— ReviewBase(所有卡片/画图 helper)+ 章节自动装配。

不要直接渲染本文件;它被 review_main.py 和各 sections/sNN_*.py 共享 import。
规则:中文一律 Text(font=CJK);⚠️ MathTex 里禁止中文;颜色=含义;停顿用 read_time(绝不封顶 1 秒)。
CJK 字体:跑 scripts/check_env.py,把它打印的那一行抄到下面。
"""
import glob
import importlib.util
import json
import os
from pathlib import Path

from manim import *
import numpy as np

CJK = "PingFang SC"          # ← check_env.py 会告诉你该写什么(非 mac 改成 Noto Sans CJK SC 等)
BG = "#10131a"
FG = "#edf2f7"
DIM = GREY_B
BLUE = BLUE_B
ORANGE = ORANGE
GREEN = GREEN_B
RED = RED_B
YELLOW = YELLOW
PURPLE = PURPLE_B


# ====================================================================== #
#  章节自动发现 + 装配:加一章 = 丢一个 sections/sNN_*.py,主文件不用改。      #
# ====================================================================== #
def load_sections(main_file):
    """按文件名排序加载 sections/s*.py。每个文件必须有 NAME(str) 和 build(s)。"""
    base = Path(main_file).resolve().parent
    mods = []
    for path in sorted(glob.glob(str(base / "sections" / "s*.py"))):
        name = Path(path).stem
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "NAME") or not hasattr(mod, "build"):
            raise ValueError(f"{path} 缺少 NAME 或 build(s) —— 每章文件都要定义这两个。")
        mods.append(mod)
    if not mods:
        raise ValueError(f"在 {base/'sections'} 下没找到 s*.py 章节文件。")
    return mods


class ReviewBase(Scene):
    """通用 helper:卡片 / 坐标轴 / 停顿 / 片头 / 章节循环。子类只填 construct。"""

    # 节奏:停顿 = 阅读时间,夹在 [READ_MIN, READ_MAX]。★绝不写 min(pause, 1.x) 封顶。
    READ_BASE, READ_PER, READ_MIN, READ_MAX = 1.6, 0.16, 3.0, 6.0
    TITLE = "课程名:期末复习全线"
    SUBTITLE = "一句话主线:从 … 到 …"

    def run_sections(self, mods, only=""):
        """依次跑各章 build(self);写出 sections_timeline.json 供 selfcheck 按章抽帧。
        only="03" 只渲第 03 章(配合 ONLY 环境变量做单章快渲)。"""
        only = only.strip().zfill(2) if only.strip() else ""
        timeline = []
        for mod in mods:
            num = mod.__name__[1:3]            # s03_xxx -> "03"
            if only and num != only:
                continue
            t0 = self.renderer.time
            mod.build(self)
            timeline.append({"name": mod.NAME, "file": mod.__name__,
                             "start": round(t0, 2), "end": round(self.renderer.time, 2)})
        try:
            Path("sections_timeline.json").write_text(
                json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def read_time(self, text_or_count):
        if isinstance(text_or_count, int):
            n = text_or_count
        elif isinstance(text_or_count, (list, tuple)):
            n = sum(len(str(x)) for x in text_or_count)
        else:
            n = len(str(text_or_count))
        return float(np.clip(self.READ_BASE + self.READ_PER * n, self.READ_MIN, self.READ_MAX))

    def page_hold(self, seconds=5.0):
        self.wait(seconds)

    def clear(self, *items):
        self.play(FadeOut(VGroup(*items) if items else Group(*self.mobjects)), run_time=0.45)

    def title_bar(self, title, color=FG):
        t = Text(title, font=CJK, font_size=34, color=color).to_edge(UP, buff=0.26)
        u = Line(LEFT, RIGHT).set_width(11.4).set_stroke("#3d4656", 2).next_to(t, DOWN, buff=0.12)
        self.play(FadeIn(t, shift=DOWN * 0.12), Create(u), run_time=0.65)
        return VGroup(t, u)

    def wrap_text(self, text, width=30):
        lines, cur, count = [], "", 0
        for ch in str(text):
            w = 0.55 if ord(ch) < 128 else 1
            if count + w > width and cur:
                lines.append(cur)
                cur, count = ch, w
            else:
                cur += ch
                count += w
        if cur:
            lines.append(cur)
        return "\n".join(lines)

    def card(self, title, body, color, width=3.55, height=2.2, fs=17, wrap=13):
        box = RoundedRectangle(width=width, height=height, corner_radius=0.08,
                               stroke_color=color, stroke_width=2.2,
                               fill_color=color, fill_opacity=0.07)
        tt = Text(title, font=CJK, font_size=22, color=color)
        bd = Text(self.wrap_text(body, wrap), font=CJK, font_size=fs, color=FG, line_spacing=0.74)
        for mob, max_w in ((tt, width - 0.35), (bd, width - 0.45)):
            if mob.width > max_w:
                mob.scale_to_fit_width(max_w)
        if bd.height > height - 0.82:
            bd.scale_to_fit_height(height - 0.82)
        inner = VGroup(tt, bd).arrange(DOWN, buff=0.14).move_to(box)
        return VGroup(box, inner)

    def lecture_card(self, title, bullets, color=GREEN):
        heading = Text(title, font=CJK, font_size=35, color=color).to_edge(UP, buff=0.76)
        box = RoundedRectangle(width=11.2, height=4.8, corner_radius=0.08,
                               stroke_color=color, stroke_width=2.2,
                               fill_color=color, fill_opacity=0.06).move_to(DOWN * 0.12)
        rows = VGroup()
        for i, line in enumerate(bullets, 1):
            mark = Text(str(i), font=CJK, font_size=21, color=BG)
            dot = Circle(radius=0.18, color=color, fill_opacity=1).add(mark)
            txt = Text(self.wrap_text(line, 42), font=CJK, font_size=24, color=FG, line_spacing=0.82)
            rows.add(VGroup(dot, txt).arrange(RIGHT, buff=0.22))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.36).move_to(box)
        self.play(FadeIn(heading), FadeIn(box), run_time=0.45)
        self.play(LaggedStartMap(FadeIn, rows, shift=RIGHT * 0.08, lag_ratio=0.12), run_time=0.7)
        self.wait(self.read_time(bullets))
        self.clear(heading, box, rows)

    def intro_card(self, topic, bullets, color=GREEN):
        """读图准备:先教怎么读下面这张图(横轴/纵轴/关键问题)。"""
        self.lecture_card("读图准备:" + topic, bullets, color)

    def recap_card(self, bullets, color=GREEN):
        """这一节怎么考:结论/判断。"""
        self.lecture_card("这一节怎么考", bullets, color)

    def example_card(self, topic, problem, answer, color=YELLOW):
        heading = Text("暂停例题:" + topic, font=CJK, font_size=32, color=color).to_edge(UP, buff=0.7)
        box = RoundedRectangle(width=11.25, height=4.35, corner_radius=0.08,
                               stroke_color=color, stroke_width=2.1,
                               fill_color=color, fill_opacity=0.06)
        p = Text("题:" + self.wrap_text(problem, 40), font=CJK, font_size=22, color=FG, line_spacing=0.82)
        a = Text("解:" + self.wrap_text(answer, 40), font=CJK, font_size=22, color=GREEN, line_spacing=0.82)
        hint = Text("例题页停留 3–6 秒,需要计算请暂停", font=CJK, font_size=18, color=DIM).to_edge(DOWN, buff=0.42)
        body = VGroup(p, a).arrange(DOWN, aligned_edge=LEFT, buff=0.38).move_to(box)
        self.play(FadeIn(heading), FadeIn(box), FadeIn(body), FadeIn(hint), run_time=0.55)
        self.wait(self.read_time(problem + answer))
        self.clear(heading, box, body, hint)

    def concept_frame(self, title, mechanism, extension, exam, color=GREEN, formula=None):
        """一页讲完 单点机制 → 多期延伸 → 用途/考试 三卡模板(可选底部公式)。"""
        bar = self.title_bar(title, color)
        cards = VGroup(
            self.card("① 单点机制", mechanism, color, 3.55, 2.72, 15, 12).move_to(LEFT * 3.95 + UP * 0.35),
            self.card("② 多期延伸", extension, color, 3.55, 2.72, 15, 12).move_to(UP * 0.35),
            self.card("③ 用途 / 考试判断", exam, color, 3.55, 2.72, 15, 12).move_to(RIGHT * 3.95 + UP * 0.35),
        )
        extras = VGroup()
        if formula:                       # formula:纯 LaTeX,别放中文
            extras.add(MathTex(formula, font_size=34, color=YELLOW).to_edge(DOWN, buff=0.8))
        self.play(LaggedStartMap(FadeIn, cards, shift=UP * 0.08, lag_ratio=0.16), run_time=1.0)
        if extras:
            self.play(Write(extras), run_time=0.9)
        self.wait(self.read_time(mechanism + extension + exam))
        self.page_hold()
        self.clear(bar, cards, extras)

    # ----- 画图原语:坐标轴 / 折线 / stem -----
    def small_axes(self, x_len=4.7, y_len=2.55, x_range=(0, 60, 20), y_range=(-2, 2, 1)):
        return Axes(x_range=list(x_range), y_range=list(y_range),
                    x_length=x_len, y_length=y_len,
                    axis_config={"include_tip": False, "color": DIM})

    def axis_labels(self, ax, x_text, y_text, font_size=15):
        xlab = Text(x_text, font=CJK, font_size=font_size, color=DIM).next_to(ax, DOWN, buff=0.06)
        ylab = Text(y_text, font=CJK, font_size=font_size, color=DIM).next_to(ax, LEFT, buff=0.08)
        return VGroup(xlab, ylab)

    def plot_series(self, ax, data, color, width=2.5, xs=None):
        xs = range(len(data)) if xs is None else xs
        return ax.plot_line_graph(list(xs), list(data), line_color=color,
                                  add_vertex_dots=False, stroke_width=width)

    def stems(self, ax, values, color, dx=0):
        g = VGroup()
        for k, v in enumerate(values):
            base, top = ax.c2p(k + dx, 0), ax.c2p(k + dx, v)
            g.add(VGroup(Line(base, top, color=color, stroke_width=5),
                         Dot(top, color=color, radius=0.055)))
        return g

    # ====== 图像优先的核心原语(这条 skill 的灵魂,别只堆卡片)======
    def reveal_axes(self, ax, x_label, x_note, y_label, y_note):
        """逐轴登场,给观众反应时间:先横轴(名字 + 来自哪里 + 现实中是什么,停),再纵轴(同样,停)。
        x_label/y_label = 短名(如 '到期价格 S_T');x_note/y_note = 一句话「来源/现实含义」。返回常驻轴标签。"""
        self.play(Create(ax.x_axis), run_time=0.8)
        xl = Text("横轴 = " + x_label, font=CJK, font_size=22, color=BLUE).next_to(ax.x_axis, DOWN, buff=0.22)
        self.play(FadeIn(xl, shift=UP * 0.1), run_time=0.4)
        xn = Text(self.wrap_text(x_note, 38), font=CJK, font_size=20, color=DIM, line_spacing=0.8).to_edge(DOWN, buff=0.3)
        self.play(FadeIn(xn), run_time=0.4)
        self.wait(self.read_time(x_label + x_note))
        self.play(FadeOut(xn), run_time=0.3)

        self.play(Create(ax.y_axis), run_time=0.8)
        yl = Text("纵轴 = " + y_label, font=CJK, font_size=22, color=ORANGE).next_to(ax.y_axis, UP, buff=0.18)
        self.play(FadeIn(yl, shift=RIGHT * 0.1), run_time=0.4)
        yn = Text(self.wrap_text(y_note, 38), font=CJK, font_size=20, color=DIM, line_spacing=0.8).to_edge(DOWN, buff=0.3)
        self.play(FadeIn(yn), run_time=0.4)
        self.wait(self.read_time(y_label + y_note))
        self.play(FadeOut(yn), run_time=0.3)
        return VGroup(xl, yl)

    def grow_series(self, ax, data, color, run_time=4.0, xs=None, trace=True):
        """动态出图:曲线从左到右一点点画出来,一个亮点沿线移动,让趋势「长」出来,而不是静态闪现。"""
        lg = self.plot_series(ax, data, color, xs=xs)
        path = lg["line_graph"]
        if trace:
            dot = Dot(color=YELLOW, radius=0.08).move_to(path.get_start())
            self.play(Create(lg), MoveAlongPath(dot, path), run_time=run_time, rate_func=linear)
            return VGroup(lg, dot)
        self.play(Create(lg), run_time=run_time)
        return lg

    def callout(self, ax, x, y, text, color=GREEN, direction=UP):
        """趋势到达关键点时,在图上弹出标注(盈亏平衡 / 拐点 / 阈值)。"""
        pt = Dot(ax.c2p(x, y), color=color, radius=0.085)
        lbl = Text(self.wrap_text(text, 14), font=CJK, font_size=20, color=color,
                   line_spacing=0.8).next_to(pt, direction, buff=0.18)
        self.play(GrowFromCenter(pt), FadeIn(lbl, shift=direction * 0.12), run_time=0.5)
        return VGroup(pt, lbl)

    def derive_formula(self, steps, captions=None, color=YELLOW, at=None, font_size=42):
        """公式动态推导:steps = LaTeX 列表,逐步 TransformMatchingTex 变形,每步停顿;
        captions[i] = 这步在做什么的一句中文(可选,简短)。⚠️ steps 里禁止中文。"""
        pos = ORIGIN if at is None else at
        m = MathTex(steps[0], color=color, font_size=font_size).move_to(pos)
        self.play(Write(m), run_time=0.9)
        cap = None
        if captions and captions[0]:
            cap = Text(captions[0], font=CJK, font_size=22, color=DIM).next_to(m, DOWN, buff=0.5)
            self.play(FadeIn(cap), run_time=0.4)
        self.wait(self.read_time(steps[0]))
        for i, s in enumerate(steps[1:], 1):
            m2 = MathTex(s, color=color, font_size=font_size).move_to(pos)
            self.play(TransformMatchingTex(m, m2), run_time=1.2)
            m = m2
            newcap = (Text(captions[i], font=CJK, font_size=22, color=DIM).next_to(m, DOWN, buff=0.5)
                      if captions and i < len(captions) and captions[i] else None)
            if cap and newcap:
                self.play(FadeOut(cap), FadeIn(newcap), run_time=0.4)
            elif newcap:
                self.play(FadeIn(newcap), run_time=0.4)
            elif cap:
                self.play(FadeOut(cap), run_time=0.3)
            cap = newcap
            self.wait(self.read_time(s))
        return VGroup(m, cap) if cap else m

    def dynamic_toc(self):
        """片头:学习路线图。需要 self.sections(节名列表)。"""
        title = Text(self.TITLE, font=CJK, font_size=40, color=FG).to_edge(UP, buff=0.55)
        subtitle = Text(self.SUBTITLE, font=CJK, font_size=25, color=GREEN).next_to(title, DOWN, buff=0.28)
        self.play(Write(title), FadeIn(subtitle), run_time=0.6)
        palette = [ORANGE, GREEN, BLUE, PURPLE, RED, YELLOW]
        rows = VGroup()
        for i, name in enumerate(self.sections):
            dot = Dot(color=palette[i % len(palette)], radius=0.055)
            txt = Text(name, font=CJK, font_size=21, color=FG)
            rows.add(VGroup(dot, txt).arrange(RIGHT, buff=0.14))
        per_col = int(np.ceil(len(rows) / 3))
        cols = VGroup(*[VGroup(*rows[c * per_col:(c + 1) * per_col]).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
                        for c in range(3)])
        cols.arrange(RIGHT, buff=0.65, aligned_edge=UP).move_to(DOWN * 0.1)
        self.play(LaggedStartMap(FadeIn, cols, shift=UP * 0.08, lag_ratio=0.05), run_time=0.8)
        self.wait(3.0)
        self.clear(title, subtitle, cols)
