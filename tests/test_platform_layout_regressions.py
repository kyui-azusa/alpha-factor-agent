from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLE = (ROOT / "platform" / "static" / "style.css").read_text(encoding="utf-8")
BUILD = (ROOT / "platform" / "build.py").read_text(encoding="utf-8")
DIST = (ROOT / "platform" / "dist" / "index.html").read_text(encoding="utf-8")


def test_hero_film_stays_inside_main_column():
    """首屏视频是主体内容,不能在桌面断点被推成侧栏或探出版心。"""
    hero_block = STYLE.split("/* ---------- 首屏视频 ----------", 1)[1].split(".film-stage", 1)[0]

    assert "grid-template-columns" not in hero_block
    assert "margin-right" not in hero_block
    assert ".film { margin: 28px auto 0; max-width: 100%; }" in hero_block
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1.02fr)" not in DIST
    assert "margin-right: calc(-1 * max(0px" not in DIST


def test_graph_sticky_is_not_disabled_by_short_desktop_viewports():
    """Windows Edge/Chrome 常见可用高度偏矮,sticky 不能再被高度门槛整段关掉。"""
    assert "graph-wrap:has(.graph-stage.with-panel)" not in STYLE
    assert ".graph-wrap.has-trace" in STYLE
    assert "(min-height: 760px)" not in STYLE
    assert "(prefers-reduced-motion: no-preference)" not in STYLE
    assert "var canStick = window.matchMedia('(min-width: 820px)');" in BUILD
    assert "graph-wrap:has(.graph-stage.with-panel)" not in DIST
    assert "(min-height: 760px)" not in DIST
    assert "var canStick = window.matchMedia('(min-width: 820px)');" in DIST
