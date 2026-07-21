from review_base import *

NAME = "第二部分:基本原理"
COLOR = GREEN


def _timeline_marker(x, label, color):
    dot = Dot(x, color=color, radius=0.075)
    txt = Text(label, font=CJK, font_size=18, color=color).next_to(dot, DOWN, buff=0.16)
    return VGroup(dot, txt)


def build(s):
    bar = s.title_bar("可信原则一:Point-in-Time,公告日之前不能使用财报字段", COLOR)

    line = NumberLine(
        x_range=[0, 10, 1],
        length=9.2,
        include_numbers=False,
        color=DIM,
        include_tip=True,
    ).shift(DOWN * 0.35)
    report = _timeline_marker(line.n2p(2), "报告期\n2020Q4", BLUE)
    today = _timeline_marker(line.n2p(5), "T日\n因子计算", YELLOW)
    announce = _timeline_marker(line.n2p(7), "公告日\nann_date", GREEN)
    future_zone = Rectangle(width=2.15, height=1.75, stroke_width=0, fill_color=RED, fill_opacity=0.12)
    future_zone.move_to((line.n2p(6.9) + line.n2p(9.1)) / 2 + UP * 0.35)
    future_label = Text("T日看不见", font=CJK, font_size=21, color=RED).move_to(future_zone)

    s.play(Create(line), run_time=0.7)
    s.play(FadeIn(report), FadeIn(today), FadeIn(announce), run_time=0.8)
    s.play(FadeIn(future_zone), FadeIn(future_label), run_time=0.5)

    cursor = Triangle(color=YELLOW, fill_opacity=1).scale(0.16).rotate(PI).next_to(today[0], UP, buff=0.16)
    field = RoundedRectangle(
        width=2.35,
        height=0.72,
        corner_radius=0.08,
        stroke_color=RED,
        fill_color=RED,
        fill_opacity=0.08,
    ).next_to(announce, UP, buff=0.48)
    field_text = Text("最新财报字段", font=CJK, font_size=18, color=RED).move_to(field)
    block = Cross(VGroup(field, field_text), stroke_color=RED, stroke_width=5)
    note = Text("pit_merge 必须挡住这条未来信息", font=CJK, font_size=24, color=GREEN).to_edge(DOWN, buff=0.45)
    note.scale_to_fit_width(10.5)
    s.play(FadeIn(cursor), FadeIn(field), FadeIn(field_text), run_time=0.5)
    s.play(Create(block), FadeIn(note), run_time=0.8)
    s.wait(s.read_time(note.text))
    s.clear(bar, line, report, today, announce, future_zone, future_label, cursor, field, field_text, block, note)

    bar = s.title_bar("可信原则二:因子、收益、报告都由确定性代码计算", COLOR)
    s.derive_formula(
        steps=[
            r"F_{i,T}=g(X_{i,T})",
            r"X_{i,T}=\{x_{i,r}:\operatorname{ann}(x_{i,r})\le T\}",
            r"IC_T=\rho_{rank}(F_{i,T},R_{i,T\to T+h})",
            r"NetReturn=LongShort-Turnover\times Cost",
        ],
        captions=[
            "因子是一个可执行函数,不是一段主观描述。",
            "输入集合只允许包含 T 日已经公告的数据。",
            "评价用未来收益,但它只在回测评价阶段出现。",
            "最后还要扣换手和交易成本,不能只看毛收益。",
        ],
        color=YELLOW,
        font_size=40,
    )
    s.clear()

    bar = s.title_bar("可信原则三:训练和验证按日期滚动,不随机打乱", COLOR)
    ax = s.small_axes(x_range=(0, 12, 2), y_range=(0, 4, 1), x_len=8.5, y_len=2.8)
    ax.move_to(DOWN * 0.25)
    labels = s.reveal_axes(
        ax,
        "交易日期",
        "横轴是时间,金融样本有先后顺序;过去不能借用未来的信息。",
        "评估窗口",
        "纵轴只是把训练、样本外和滚动窗口分层画出来,方便看边界。",
    )
    train = Rectangle(width=3.9, height=0.5, fill_color=BLUE, fill_opacity=0.55, stroke_width=0)
    test1 = Rectangle(width=1.55, height=0.5, fill_color=GREEN, fill_opacity=0.55, stroke_width=0)
    test2 = Rectangle(width=1.55, height=0.5, fill_color=GREEN, fill_opacity=0.55, stroke_width=0)
    train.move_to(ax.c2p(2.4, 2.1))
    test1.move_to(ax.c2p(5.4, 2.1))
    test2.move_to(ax.c2p(7.0, 1.2))
    train_t = Text("训练/基线", font=CJK, font_size=18, color=FG).move_to(train)
    test1_t = Text("样本外", font=CJK, font_size=17, color=BG).move_to(test1)
    test2_t = Text("滚动样本外", font=CJK, font_size=15, color=BG).move_to(test2)
    boundary = DashedLine(ax.c2p(4.5, 0), ax.c2p(4.5, 3.4), color=YELLOW, dash_length=0.16)
    boundary_t = Text("train_end", font=CJK, font_size=19, color=YELLOW).next_to(boundary, UP, buff=0.1)

    s.play(FadeIn(train), FadeIn(train_t), Create(boundary), FadeIn(boundary_t), run_time=0.8)
    s.play(FadeIn(test1), FadeIn(test1_t), run_time=0.6)
    s.play(FadeIn(test2), FadeIn(test2_t, shift=RIGHT * 0.12), run_time=0.6)
    warning = Text("禁止随机打乱:时间顺序本身就是约束。", font=CJK, font_size=24, color=RED).to_edge(DOWN, buff=0.45)
    s.play(FadeIn(warning), run_time=0.5)
    s.wait(s.read_time(warning.text))
    s.clear(bar, ax, labels, train, train_t, test1, test1_t, test2, test2_t, boundary, boundary_t, warning)

    s.recap_card(
        [
            "三条底线:ann_date <= T、按日期样本外、回测里绝不调用 LLM。",
            "合成数据只验证工程正确;真实研究结论等待聚源数据。",
        ],
        COLOR,
    )
