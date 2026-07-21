from review_base import *

NAME = "第一部分:项目在做什么"
COLOR = BLUE


def _box(label, body, color, width=2.35, height=1.18):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.08,
        stroke_color=color,
        stroke_width=2.2,
        fill_color=color,
        fill_opacity=0.08,
    )
    title = Text(label, font=CJK, font_size=22, color=color)
    detail = Text(body, font=CJK, font_size=15, color=FG, line_spacing=0.76)
    detail.scale_to_fit_width(width - 0.34)
    group = VGroup(title, detail).arrange(DOWN, buff=0.1).move_to(box)
    return VGroup(box, group)


def _arrow_between(left, right, color=DIM):
    return Arrow(
        left.get_right(),
        right.get_left(),
        buff=0.16,
        color=color,
        stroke_width=3,
        max_tip_length_to_length_ratio=0.12,
    )


def build(s):
    bar = s.title_bar("我们在做的不是选股黑箱,而是可解释 Alpha 因子智能体", COLOR)

    nodes = VGroup(
        _box("LLM", "提出经济假设\n生成候选表达式", BLUE),
        _box("规则校验", "字段可得\n防重复/防未来", YELLOW),
        _box("纯代码回测", "IC/ICIR\n成本后收益", GREEN),
        _box("反馈", "读结果\n改进假设", ORANGE),
    ).arrange(RIGHT, buff=0.48).shift(UP * 0.48)

    arrows = VGroup(*[_arrow_between(nodes[i], nodes[i + 1]) for i in range(3)])
    loop = CurvedArrow(
        nodes[3].get_bottom() + DOWN * 0.08,
        nodes[0].get_bottom() + DOWN * 0.08,
        angle=-TAU / 4,
        color=ORANGE,
        stroke_width=3,
    )
    loop_label = Text("结果反馈给下一轮", font=CJK, font_size=19, color=ORANGE).next_to(loop, DOWN, buff=0.06)

    s.play(LaggedStartMap(FadeIn, nodes, shift=UP * 0.12, lag_ratio=0.16), run_time=1.2)
    s.play(LaggedStartMap(Create, arrows, lag_ratio=0.25), run_time=1.0)
    s.play(Create(loop), FadeIn(loop_label), run_time=0.8)

    token = Dot(nodes[0].get_center(), color=YELLOW, radius=0.08)
    s.play(FadeIn(token), run_time=0.2)
    route = [nodes[1].get_center(), nodes[2].get_center(), nodes[3].get_center(), nodes[0].get_center()]
    for point in route:
        s.play(token.animate.move_to(point), run_time=0.65)

    rule = Text(
        "核心边界:LLM 只负责想法和解释;所有数值结论必须由确定性程序计算。",
        font=CJK,
        font_size=23,
        color=GREEN,
    ).to_edge(DOWN, buff=0.5)
    rule.scale_to_fit_width(10.8)
    s.play(FadeIn(rule), run_time=0.5)
    s.wait(s.read_time(rule.text))
    s.clear(bar, nodes, arrows, loop, loop_label, token, rule)

    bar = s.title_bar("交付主线:M0-M3 先做可信底座,M4-M6 再接入智能体", COLOR)
    ax = s.small_axes(x_range=(0, 6, 1), y_range=(0, 10, 2), x_len=8.2, y_len=3.2)
    ax.move_to(DOWN * 0.18)
    labels = s.reveal_axes(
        ax,
        "Milestone 进度 M0-M6",
        "横轴是项目推进顺序:先配置和数据,再因子、回测、LLM、闭环、汇总。",
        "可信度/可复现程度",
        "纵轴代表证据强度:单测、样本外和报告越完整,结论越能被成员复核。",
    )

    xs = np.arange(7)
    confidence = np.array([1.2, 2.8, 4.1, 6.7, 7.4, 8.4, 9.2])
    curve = s.grow_series(ax, confidence, GREEN, run_time=4.2, xs=xs)
    m3 = s.callout(ax, 3, 6.7, "M3:回测纯代码\n可信底座成型", GREEN, UP)
    m6 = s.callout(ax, 6, 9.2, "M6:解释卡片\n汇总交付", YELLOW, LEFT)
    s.page_hold(4.2)
    s.clear(bar, ax, labels, curve, m3, m6)

    s.recap_card(
        [
            "项目目标:生成有经济解释、可计算、可复核的 A 股 Alpha 因子。",
            "成员共识:先证明工程正确,再讨论模型聪不聪明。",
        ],
        COLOR,
    )
