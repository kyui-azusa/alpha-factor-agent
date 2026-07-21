from review_base import *

NAME = "pit_merge防穿越"
COLOR = RED


def build(s):
    bar = s.title_bar("财报不是报告期一到就可见", COLOR)
    line = NumberLine(x_range=[0, 100, 20], length=9.8, color=DIM, include_tip=False).move_to(DOWN * 0.1)
    s.play(Create(line), run_time=0.8)
    rp = line.n2p(28)
    ann = line.n2p(62)
    rp_tick = VGroup(Line(rp + DOWN * 0.18, rp + UP * 0.34, color=YELLOW, stroke_width=4), Text("report_period\n3-31", font=CJK, font_size=18, color=YELLOW, line_spacing=0.8).next_to(rp, UP, buff=0.42))
    ann_tick = VGroup(Line(ann + DOWN * 0.18, ann + UP * 0.34, color=GREEN, stroke_width=4), Text("ann_date\n4-25", font=CJK, font_size=18, color=GREEN, line_spacing=0.8).next_to(ann, UP, buff=0.42))
    zone = Rectangle(width=ann[0] - rp[0], height=0.58, fill_color=RED, fill_opacity=0.22, stroke_width=0).move_to((rp + ann) / 2 + DOWN * 0.02)
    s.play(FadeIn(rp_tick), run_time=0.5)
    s.wait(s.read_time("报告期只是账本截止日,不是市场已经知道。"))
    s.play(FadeIn(ann_tick), run_time=0.5)
    s.play(FadeIn(zone), run_time=0.55)
    leak = Text("4-1~4-24 用这份财报 = 时间穿越", font=CJK, font_size=24, color=RED).to_edge(DOWN, buff=0.58)
    s.play(FadeIn(leak), run_time=0.45)
    s.wait(s.read_time(leak.text))

    box = Square(side_length=0.28, color=BLUE, fill_color=BLUE, fill_opacity=0.85).move_to(line.n2p(8) + DOWN * 0.52)
    label = Text("回测日 T", font=CJK, font_size=18, color=BLUE).next_to(box, DOWN, buff=0.12)
    attach = Text("财报挂接", font=CJK, font_size=20, color=GREEN).next_to(ann_tick, RIGHT, buff=0.45)
    s.play(FadeIn(box), FadeIn(label), run_time=0.35)
    s.play(box.animate.move_to(line.n2p(50) + DOWN * 0.52), label.animate.next_to(line.n2p(50) + DOWN * 0.52, DOWN, buff=0.12), run_time=1.1)
    no = Text("还不能用", font=CJK, font_size=22, color=RED).next_to(box, UP, buff=0.25)
    s.play(FadeIn(no), run_time=0.3)
    s.wait(s.read_time("只要 T 还没到公告日,这条财报就不在信息集里。"))
    s.play(FadeOut(no), box.animate.move_to(line.n2p(64) + DOWN * 0.52), label.animate.next_to(line.n2p(64) + DOWN * 0.52, DOWN, buff=0.12), run_time=1.0)
    s.play(box.animate.set_color(GREEN), FadeIn(attach), run_time=0.5)
    crash = Text("暴雷剧情:按 report_period 对齐会提前躲开坏消息", font=CJK, font_size=23, color=RED).to_edge(DOWN, buff=0.52)
    s.play(Transform(leak, crash), run_time=0.7)
    s.page_hold(4.0)
    s.clear(bar, line, rp_tick, ann_tick, zone, leak, box, label, attach)
    s.recap_card(["回测第一美德不是收益高,是诚实还原每个时刻的信息集:T 日只用 ann_date <= T。"], COLOR)
