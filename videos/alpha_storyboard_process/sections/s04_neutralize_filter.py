from review_base import *

NAME = "中性化·带阻滤波"
COLOR = ORANGE


def _industry_points(ax):
    groups = [(-1.45, 0.9), (-0.45, -0.55), (0.55, 0.45), (1.45, -0.15)]
    dots = VGroup()
    targets = []
    for base_x, offset in groups:
        for k in range(7):
            x = base_x + (k - 3) * 0.07
            y = offset + 0.18 * np.sin(k * 1.6 + base_x)
            dot = Dot(ax.c2p(x, y), radius=0.043, color=ORANGE)
            dots.add(dot)
            targets.append(ax.c2p(x, y - offset))
    return dots, targets


def build(s):
    bar = s.title_bar("中性化:把公共频率滤掉", COLOR)
    ax = s.small_axes(x_range=(-2, 2, 1), y_range=(-1.8, 1.8, 0.9), x_len=8.8, y_len=3.6).move_to(DOWN * 0.05)
    labels = s.reveal_axes(
        ax,
        "行业分组后的股票",
        "横轴把股票按行业团块排开,不是时间。",
        "原始因子分",
        "纵轴先混着行业、市值和真正信号。",
    )
    zero = DashedLine(ax.c2p(-2, 0), ax.c2p(2, 0), color=YELLOW, stroke_width=2.5)
    dots, targets = _industry_points(ax)
    s.play(Create(zero), LaggedStartMap(FadeIn, dots, lag_ratio=0.02), run_time=1.4)
    co1 = s.callout(ax, -1.45, 0.9, "行业团块整体偏高", ORANGE, UP)
    s.wait(s.read_time("原始因子里有行业频率,先不能让银行股和芯片股直接互相压过。"))
    arrows = VGroup(*[Arrow(dot.get_center(), target, buff=0.05, color=DIM, stroke_width=1.4, max_tip_length_to_length_ratio=0.16) for dot, target in zip(dots, targets)])
    s.play(FadeIn(arrows), run_time=0.6)
    s.play(*[dot.animate.move_to(target).set_color(BLUE) for dot, target in zip(dots, targets)], run_time=1.7)
    co2 = s.callout(ax, 1.45, 0.1, "拉回零轴:同台比较", GREEN, UP)
    s.page_hold(3.0)
    s.clear(bar, ax, labels, zero, dots, co1, arrows, co2)

    bar = s.title_bar("留下和公共成分正交的残差", COLOR)
    formula = s.derive_formula(
        [
            r"f",
            r"f = a \cdot Industry + b \cdot log(MV) + \epsilon",
            r"f^{neutral} = \epsilon",
        ],
        captions=["先看原始因子", "拆成行业、市值和残差", "只留下残差"],
        color=YELLOW,
        font_size=40,
    )
    s.page_hold(2.6)
    s.clear(bar, formula)
    s.recap_card(["中性化 = 滤掉行业频率与市值频率的带阻滤波器。"], COLOR)
