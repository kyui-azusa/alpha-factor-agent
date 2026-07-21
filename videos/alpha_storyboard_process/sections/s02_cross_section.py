from review_base import *

NAME = "横截面转向"
COLOR = BLUE


def build(s):
    bar = s.title_bar("不要先问一只股票明天怎样", COLOR)
    left_center = LEFT * 3.55 + DOWN * 0.18
    right_center = RIGHT * 3.25 + DOWN * 0.18
    left_tag = Text("时间序列视角", font=CJK, font_size=22, color=RED).move_to(LEFT * 3.55 + UP * 2.36)
    ax1 = s.small_axes(x_range=(0, 60, 20), y_range=(-3, 3, 1), x_len=4.95, y_len=2.85).move_to(left_center)
    s.play(FadeIn(left_tag, shift=DOWN * 0.08), run_time=0.35)
    labels1 = s.reveal_axes(
        ax1,
        "时间",
        "横轴是一只股票自己的历史,一天一天往后走。",
        "日收益",
        "纵轴是这只股票当天涨跌,噪声非常大。",
    )
    xs = np.arange(61)
    noise = 0.9 * np.sin(xs * 0.7) + 0.55 * np.sin(xs * 1.8)
    curve = s.grow_series(ax1, noise, RED, run_time=3.6, xs=xs)
    co1 = s.callout(ax1, 38, noise[38], "单只股票\n噪声太大", RED, UP)
    s.wait(s.read_time("单只股票的明天太吵,不是本项目的评价方式。"))

    turn = VGroup(
        Text("换观察对象", font=CJK, font_size=24, color=YELLOW),
        Text("从单只股票时间线\n到同一天全市场排名", font=CJK, font_size=17, color=FG, line_spacing=0.82),
    ).arrange(DOWN, buff=0.12).move_to(ORIGIN + UP * 1.62)
    arrow = CurvedArrow(LEFT * 0.52 + UP * 0.88, RIGHT * 0.52 + UP * 0.88, angle=-PI / 2, color=YELLOW)
    s.play(FadeIn(turn), Create(arrow), run_time=0.8)
    s.wait(s.read_time("这里不是把图真的旋转九十度,而是换评价口径:不预测一只股票明天涨跌,改为比较今天一篮子股票谁更强。"))

    right_tag = Text("横截面排序视角", font=CJK, font_size=22, color=GREEN).move_to(RIGHT * 3.25 + UP * 2.36)
    ax2 = s.small_axes(x_range=(-2, 2, 1), y_range=(-2, 2, 1), x_len=4.85, y_len=2.85).move_to(right_center)
    s.play(FadeIn(right_tag, shift=DOWN * 0.08), run_time=0.35)
    labels2 = s.reveal_axes(
        ax2,
        "当日因子分",
        "横轴是同一天所有股票的信号强弱。",
        "未来收益排名",
        "纵轴是之后一段时间谁表现更靠前。",
    )
    xvals = np.linspace(-1.7, 1.7, 34)
    yvals = 0.42 * xvals + 0.34 * np.sin(np.arange(34) * 1.7)
    dots = VGroup(*[Dot(ax2.c2p(x, y), radius=0.045, color=BLUE) for x, y in zip(xvals, yvals)])
    trend = ax2.plot(lambda x: 0.42 * x, x_range=[-1.7, 1.7], color=GREEN, stroke_width=3)
    s.play(LaggedStartMap(FadeIn, dots, lag_ratio=0.025), run_time=1.1)
    s.play(Create(trend), run_time=1.0)
    co2 = s.callout(ax2, 1.25, 0.52, "横截面:排名对了就行", GREEN, UP)
    s.page_hold(3.0)
    s.clear(bar, left_tag, ax1, labels1, curve, co1, turn, arrow, right_tag, ax2, labels2, dots, trend, co2)
    s.recap_card(["时间序列预测'明天',因子投资预测'今天谁比谁强'。"], COLOR)
