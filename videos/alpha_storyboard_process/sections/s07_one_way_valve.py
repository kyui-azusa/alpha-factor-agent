from review_base import *

NAME = "信息单向阀"
COLOR = GREEN


def build(s):
    bar = s.title_bar("测试集只盖章,不参与决策", COLOR)
    base = Line(LEFT * 5.0, RIGHT * 5.0, color=DIM, stroke_width=4).move_to(UP * 0.45)
    split = base.point_from_proportion(0.58)
    train = Rectangle(width=5.8, height=0.72, fill_color=BLUE, fill_opacity=0.17, stroke_color=BLUE).move_to((base.get_left() + split) / 2)
    test = Rectangle(width=4.2, height=0.72, fill_color=GREY_E, fill_opacity=0.28, stroke_color=DIM).move_to((split + base.get_right()) / 2)
    train_txt = Text("训练段:细节全开", font=CJK, font_size=23, color=BLUE).move_to(train)
    test_txt = Text("测试段:封存", font=CJK, font_size=23, color=DIM).move_to(test)
    split_line = Line(split + DOWN * 0.62, split + UP * 0.62, color=YELLOW, stroke_width=4)
    s.play(Create(base), FadeIn(train), FadeIn(test), FadeIn(train_txt), FadeIn(test_txt), Create(split_line), run_time=1.0)
    forward = Arrow(train.get_right() + DOWN * 0.8, test.get_left() + DOWN * 0.8, buff=0.16, color=GREEN, stroke_width=6)
    ftxt = Text("带着所学去赴考", font=CJK, font_size=22, color=GREEN).next_to(forward, DOWN, buff=0.12)
    s.play(Create(forward), FadeIn(ftxt), run_time=0.7)
    s.wait(s.read_time("训练的知识可以流向测试,这是正常考试。"))
    back = Arrow(test.get_left() + UP * 0.92, train.get_right() + UP * 0.92, buff=0.16, color=RED, stroke_width=5)
    cross = VGroup(
        Line(back.get_center() + UL * 0.28, back.get_center() + DR * 0.28, color=RED, stroke_width=7),
        Line(back.get_center() + DL * 0.28, back.get_center() + UR * 0.28, color=RED, stroke_width=7),
    )
    leak = Text("哪怕只瞟一眼,泄漏就已完成", font=CJK, font_size=24, color=RED).to_edge(DOWN, buff=0.55)
    s.play(Create(back), run_time=0.55)
    s.play(Create(cross), FadeIn(leak), run_time=0.55)
    s.wait(s.read_time(leak.text))
    s.clear(bar, base, train, test, train_txt, test_txt, split_line, forward, ftxt, back, cross, leak)

    bar = s.title_bar("漏斗就是最终结论的形状", COLOR)
    levels = [
        ("生成 N 个假说", 6.5, BLUE),
        ("训练段过 m 个", 4.3, YELLOW),
        ("样本外站住 k 个", 2.2, GREEN),
    ]
    funnels = VGroup()
    y = 1.15
    for label, width, color in levels:
        shape = Polygon(
            LEFT * width / 2 + UP * 0.33,
            RIGHT * width / 2 + UP * 0.33,
            RIGHT * (width * 0.42) + DOWN * 0.33,
            LEFT * (width * 0.42) + DOWN * 0.33,
            stroke_color=color,
            fill_color=color,
            fill_opacity=0.13,
        )
        txt = Text(label, font=CJK, font_size=25, color=color).move_to(shape)
        group = VGroup(shape, txt).move_to(UP * y)
        funnels.add(group)
        y -= 1.05
    s.play(LaggedStartMap(FadeIn, funnels, shift=DOWN * 0.12, lag_ratio=0.22), run_time=1.3)
    s.page_hold(5.5)
    s.clear(bar, funnels)
    s.recap_card(["限制信息的时间范围,不限制段内粒度;测试集只做一件事:给结论盖章。"], COLOR)
