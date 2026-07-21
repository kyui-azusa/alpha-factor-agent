from review_base import *

NAME = "四步闭环"
COLOR = PURPLE


def _node(title, body, color):
    box = RoundedRectangle(width=2.18, height=1.08, corner_radius=0.08, stroke_color=color, fill_color=color, fill_opacity=0.09)
    t = Text(title, font=CJK, font_size=21, color=color)
    b = Text(body, font=CJK, font_size=15, color=FG, line_spacing=0.8)
    b.scale_to_fit_width(1.82)
    return VGroup(box, VGroup(t, b).arrange(DOWN, buff=0.08).move_to(box))


def build(s):
    bar = s.title_bar("LLM 提想法,代码做裁判", COLOR)
    positions = [LEFT * 3.0 + UP * 1.0, RIGHT * 3.0 + UP * 1.0, RIGHT * 3.0 + DOWN * 1.18, LEFT * 3.0 + DOWN * 1.18]
    gen = _node("生成", "LLM\n经济假设", BLUE).move_to(positions[0])
    val = _node("校验", "规则 + 语义\n字段/重复", GREEN).move_to(positions[1])
    bt = _node("回测", "无 LLM\nIC/成本", GREEN).move_to(positions[2])
    fb = _node("反馈", "LLM\n读结果", BLUE).move_to(positions[3])
    nodes = VGroup(gen, val, bt, fb)
    arrows = VGroup(
        Arrow(gen.get_right(), val.get_left(), buff=0.2, color=DIM),
        Arrow(val.get_bottom(), bt.get_top(), buff=0.2, color=DIM),
        Arrow(bt.get_left(), fb.get_right(), buff=0.2, color=DIM),
        Arrow(fb.get_top(), gen.get_bottom(), buff=0.2, color=DIM),
    )
    lock = Text("锁", font=CJK, font_size=26, color=YELLOW).move_to(bt.get_center() + RIGHT * 0.78 + UP * 0.28)
    no_llm = Text("数值生杀大权在确定性代码手里", font=CJK, font_size=25, color=YELLOW).to_edge(DOWN, buff=0.55)
    for node in nodes:
        s.play(FadeIn(node, shift=UP * 0.1), run_time=0.45)
    s.play(LaggedStartMap(Create, arrows, lag_ratio=0.18), run_time=1.0)
    for node in [gen, val, bt, fb]:
        glow = SurroundingRectangle(node, color=YELLOW, buff=0.08)
        s.play(Create(glow), run_time=0.32)
        if node is bt:
            s.play(FadeIn(lock), FadeIn(no_llm), run_time=0.5)
            s.wait(s.read_time("回测节点带锁:这里不允许 LLM 参与任何数值计算。"))
        s.play(FadeOut(glow), run_time=0.22)
    s.page_hold(3.0)
    s.clear(bar, nodes, arrows, lock, no_llm)
    s.recap_card(["LLM 管语义空间,代码管数值空间:不许既当运动员又当裁判。"], COLOR)
