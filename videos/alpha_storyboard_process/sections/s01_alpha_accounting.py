from review_base import *

NAME = "收益记账:alpha在哪"
COLOR = GREEN


def _block(label, width, color):
    rect = Rectangle(width=width, height=0.66, stroke_color=color, fill_color=color, fill_opacity=0.2)
    txt = Text(label, font=CJK, font_size=18, color=FG).move_to(rect)
    txt.scale_to_fit_width(max(width - 0.18, 0.42))
    return VGroup(rect, txt)


def build(s):
    bar = s.title_bar("先把收益拆成几笔账", COLOR)
    title = Text("组合收益", font=CJK, font_size=24, color=FG).move_to(UP * 1.55)
    beta = _block("大盘 beta", 2.1, ORANGE)
    industry = _block("行业", 1.55, ORANGE)
    style = _block("市值风格", 1.7, ORANGE)
    alpha = _block("alpha", 0.9, GREEN)
    stack = VGroup(beta, industry, style, alpha).arrange(RIGHT, buff=0).move_to(UP * 0.78)
    brace = Brace(stack, UP, color=DIM)
    s.play(FadeIn(title), GrowFromCenter(brace), LaggedStartMap(FadeIn, stack, lag_ratio=0.18), run_time=1.2)
    s.wait(s.read_time("组合收益先不是本事,要先拆成公共账目和残余。"))

    for part, line in [
        (beta, "大盘这笔钱,指数基金就能买到。"),
        (industry, "行业这笔钱,不是个股 alpha。"),
        (style, "市值风格这笔钱,也要先记到公共账。"),
    ]:
        note = Text(line, font=CJK, font_size=22, color=ORANGE).to_edge(DOWN, buff=0.52)
        s.play(part.animate.shift(DOWN * 1.55).set_opacity(0.34), FadeIn(note), run_time=0.7)
        s.wait(s.read_time(line))
        s.play(FadeOut(note), run_time=0.25)

    alpha_box = SurroundingRectangle(alpha, color=GREEN, buff=0.08)
    alpha_note = Text("剩余无法归因的部分 = alpha", font=CJK, font_size=26, color=GREEN).next_to(alpha, DOWN, buff=0.55)
    left = Text("公共账目,人人可得", font=CJK, font_size=22, color=ORANGE).move_to(LEFT * 3.1 + DOWN * 0.95)
    right = Text("残余,靠假说去抢", font=CJK, font_size=22, color=GREEN).move_to(RIGHT * 2.6 + DOWN * 0.95)
    arr = Arrow(left.get_right(), right.get_left(), buff=0.22, color=DIM)
    s.play(Create(alpha_box), FadeIn(alpha_note), FadeIn(left), FadeIn(right), Create(arr), run_time=0.9)
    s.wait(s.read_time("alpha 是扣完公共账目之后的残余,是结果,不是原因。"))
    s.clear(bar, title, brace, stack, alpha_box, alpha_note, left, right, arr)

    bar = s.title_bar("再把直觉写成公式", COLOR)
    formula = s.derive_formula(
        [
            r"R_p",
            r"R_p = \beta R_m",
            r"R_p = \beta R_m + I + S",
            r"R_p = \beta R_m + I + S + \alpha",
            r"\alpha = R_p - \beta R_m - I - S",
        ],
        captions=["先看到组合收益", "先扣大盘", "再扣行业和风格", "最后剩 alpha", "alpha 是记账残余"],
        color=YELLOW,
    )
    s.page_hold(3.2)
    s.clear(bar, formula)
    s.recap_card(["alpha 是扣完所有公共账目后剩下的钱:是结果,不是原因。"], COLOR)
