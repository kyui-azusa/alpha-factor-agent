from review_base import *

NAME = "Rank IC与硬币偏置"
COLOR = BLUE


def build(s):
    bar = s.title_bar("微弱偏置要靠聚合显形", COLOR)
    upper_title = Text("日度 Rank IC: 单日噪声很大", font=CJK, font_size=22, color=BLUE).move_to(LEFT * 2.7 + UP * 2.55)
    ax = s.small_axes(x_range=(0, 120, 30), y_range=(-0.22, 0.22, 0.11), x_len=8.9, y_len=2.25).move_to(UP * 1.38)
    s.play(FadeIn(upper_title, shift=DOWN * 0.08), run_time=0.35)
    labels = s.reveal_axes(
        ax,
        "交易日",
        "每天用全市场横截面算一次 Rank IC。",
        "当日 Rank IC",
        "正负会乱跳,单日几乎看不出偏置。",
    )
    xs = np.arange(121)
    ic = 0.035 + 0.075 * np.sin(xs * 0.27) + 0.055 * np.sin(xs * 1.13)
    series = s.grow_series(ax, ic, BLUE, run_time=4.0, xs=xs)
    mean_line = DashedLine(ax.c2p(0, 0.05), ax.c2p(120, 0.05), color=YELLOW, stroke_width=3)
    mean_lab = Text("均值约 0.05", font=CJK, font_size=20, color=YELLOW).next_to(mean_line, UP, buff=0.08)
    co1 = s.callout(ax, 34, ic[34], "单日结论不稳", RED, DOWN)
    s.play(Create(mean_line), FadeIn(mean_lab), run_time=0.7)
    s.wait(s.read_time("IC=0.05 像一枚轻微偏置的硬币,要靠大量样本显形。"))

    separator = Line(LEFT * 5.15, RIGHT * 5.15, color="#2f3948", stroke_width=2).move_to(DOWN * 0.38)
    lower_title = Text("累计 IC: 同一批日度 IC 的时间聚合", font=CJK, font_size=22, color=GREEN).move_to(LEFT * 2.18 + DOWN * 0.82)
    s.play(Create(separator), FadeIn(lower_title, shift=DOWN * 0.08), run_time=0.45)

    ax2 = s.small_axes(x_range=(0, 120, 30), y_range=(-1, 7, 2), x_len=8.9, y_len=2.05).move_to(DOWN * 2.18)
    labels2 = s.reveal_axes(
        ax2,
        "交易日",
        "还是同一串日度 IC,现在看累积。",
        "累积 IC",
        "微小正偏置会在时间上慢慢堆出来。",
    )
    cum = np.cumsum(ic)
    cum_series = s.grow_series(ax2, cum, GREEN, run_time=3.5, xs=xs)
    co2 = s.callout(ax2, 104, cum[104], "聚合后偏置显形", GREEN, UP)
    s.page_hold(2.6)
    s.clear(bar, upper_title, ax, labels, series, mean_line, mean_lab, co1, separator, lower_title, ax2, labels2, cum_series, co2)

    bar = s.title_bar("稳定性比单日高低更重要", COLOR)
    formula = s.derive_formula(
        [r"IC_t = corr(rank(f_t), rank(R_{t+1}))", r"ICIR = {mean(IC_t) \over std(IC_t)}"],
        captions=["先逐日看横截面排序相关", "再看均值相对波动是否稳定"],
        color=YELLOW,
        font_size=38,
    )
    s.page_hold(2.6)
    s.clear(bar, formula)
    s.recap_card(["IC=0.05 是一枚 51.5:48.5 的硬币:alpha 是偏置,不是某次抛掷。"], COLOR)
