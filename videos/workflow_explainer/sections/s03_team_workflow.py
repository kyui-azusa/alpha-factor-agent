from review_base import *

NAME = "第三部分:成员使用流程"
COLOR = ORANGE


def _step_card(num, title, body, color):
    box = RoundedRectangle(
        width=2.75,
        height=1.22,
        corner_radius=0.08,
        stroke_color=color,
        stroke_width=2.0,
        fill_color=color,
        fill_opacity=0.08,
    )
    badge = Circle(radius=0.17, color=color, fill_opacity=1)
    n = Text(str(num), font=CJK, font_size=17, color=BG).move_to(badge)
    t = Text(title, font=CJK, font_size=20, color=color)
    b = Text(body, font=CJK, font_size=14, color=FG, line_spacing=0.75)
    b.scale_to_fit_width(2.35)
    text = VGroup(t, b).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
    row = VGroup(VGroup(badge, n), text).arrange(RIGHT, buff=0.16).move_to(box)
    return VGroup(box, row)


def _connect(a, b, color=DIM):
    return Arrow(
        a.get_right(),
        b.get_left(),
        buff=0.12,
        color=color,
        stroke_width=2.7,
        max_tip_length_to_length_ratio=0.11,
    )


def build(s):
    bar = s.title_bar("成员每天怎么用:从目标到可复核产物", COLOR)

    steps = VGroup(
        _step_card(1, "领任务", "看 /goal 与\nBUILD_SPEC", BLUE),
        _step_card(2, "做一小块", "按 Milestone\n改代码/文档", YELLOW),
        _step_card(3, "跑验证", "pytest +\n报告/抽帧", GREEN),
        _step_card(4, "沉淀", "因子卡片/\n答辩材料", ORANGE),
    ).arrange(RIGHT, buff=0.34).shift(UP * 0.55)
    arrows = VGroup(*[_connect(steps[i], steps[i + 1]) for i in range(3)])

    s.play(LaggedStartMap(FadeIn, steps, shift=UP * 0.1, lag_ratio=0.16), run_time=1.1)
    s.play(LaggedStartMap(Create, arrows, lag_ratio=0.2), run_time=0.8)

    cursor = Dot(steps[0].get_center(), color=YELLOW, radius=0.085)
    s.play(FadeIn(cursor), run_time=0.2)
    for target in steps[1:]:
        s.play(cursor.animate.move_to(target.get_center()), run_time=0.55)

    feedback = CurvedArrow(
        steps[3].get_bottom() + DOWN * 0.05,
        steps[0].get_bottom() + DOWN * 0.05,
        angle=-TAU / 4,
        color=ORANGE,
        stroke_width=3,
    )
    feedback_text = Text("反馈和新问题回到任务池", font=CJK, font_size=20, color=ORANGE).next_to(feedback, DOWN, buff=0.08)
    s.play(Create(feedback), FadeIn(feedback_text), run_time=0.75)

    rule = Text(
        "每个成员都只需要保证:自己交付的那一小块可以被别人复现。",
        font=CJK,
        font_size=24,
        color=GREEN,
    ).to_edge(DOWN, buff=0.46)
    rule.scale_to_fit_width(10.8)
    s.play(FadeIn(rule), run_time=0.5)
    s.wait(s.read_time(rule.text))
    s.clear(bar, steps, arrows, cursor, feedback, feedback_text, rule)

    bar = s.title_bar("五天压缩线:先把可信底座打穿,再展示闭环", COLOR)
    ax = s.small_axes(x_range=(0, 5, 1), y_range=(0, 10, 2), x_len=8.2, y_len=3.1)
    ax.move_to(DOWN * 0.12)
    labels = s.reveal_axes(
        ax,
        "Day 1 到 Day 5",
        "横轴是剩余交付时间,每天都要留下可运行、可解释的证据。",
        "交付完成度",
        "纵轴不是工作量,而是可演示程度:测试、报告、卡片越齐,越接近答辩包。",
    )
    days = np.arange(6)
    base = np.array([1.0, 2.7, 5.2, 7.0, 8.5, 9.4])
    curve = s.grow_series(ax, base, GREEN, run_time=4.0, xs=days)
    call1 = s.callout(ax, 3, 7.0, "M0-M3\n必须真实有测试", GREEN, UP)
    call2 = s.callout(ax, 5, 9.4, "Defense Bundle\n代码+报告+说明", YELLOW, LEFT)
    s.page_hold(4.0)
    s.clear(bar, ax, labels, curve, call1, call2)

    bar = s.title_bar("成员分工:每个输出都回到同一条证据链", COLOR)
    rows = VGroup(
        _step_card("A", "数据/对齐", "维护 schema\n和 pit_merge", BLUE),
        _step_card("B", "因子/回测", "基线因子\nIC/换手/成本", GREEN),
        _step_card("C", "LLM/闭环", "结构化输出\n缓存与 mock", PURPLE),
        _step_card("D", "材料/反馈", "报告卡片\nissue intake", ORANGE),
    ).arrange_in_grid(rows=2, cols=2, buff=(0.65, 0.48)).shift(UP * 0.12)
    center = RoundedRectangle(
        width=2.9,
        height=0.82,
        corner_radius=0.08,
        stroke_color=YELLOW,
        stroke_width=2.2,
        fill_color=YELLOW,
        fill_opacity=0.08,
    ).to_edge(DOWN, buff=0.75)
    center_text = Text("同一条主线:假设 → 判断 → 可解释交付", font=CJK, font_size=20, color=YELLOW).move_to(center)
    links = VGroup(*[Line(card.get_bottom(), center.get_top(), color=DIM, stroke_width=1.8) for card in rows])
    s.play(LaggedStartMap(FadeIn, rows, shift=UP * 0.1, lag_ratio=0.12), run_time=1.0)
    s.play(LaggedStartMap(Create, links, lag_ratio=0.08), FadeIn(center), FadeIn(center_text), run_time=0.8)
    s.wait(s.read_time("同一条主线:假设判断可解释交付"))
    s.clear(bar, rows, links, center, center_text)

    s.recap_card(
        [
            "用法:看 /goal 定方向,按 BUILD_SPEC 拿小任务,每步用测试和报告关门。",
            "协作原则:问题进任务池,成果进 evidence,最终统一成答辩包。",
        ],
        COLOR,
    )
