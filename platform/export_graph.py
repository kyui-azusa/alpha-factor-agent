"""把方法依赖图导出成独立 SVG,供 PPT 与论文使用(PLATFORM_V2_SPEC §2.7)。

一鱼三吃的落地点:同一份 graph.yaml 与同一套布局代码,产出站点交互图 / PPT 一页 / 论文配图。

    python platform/export_graph.py --out figures/method_graph.svg
    python platform/export_graph.py --theme light --out figures/method_graph_light.svg

PPT:PowerPoint 原生支持 SVG,直接插入。
论文:LaTeX 的 \\includegraphics 不吃 SVG,先转一次:
    rsvg-convert -f pdf -o figures/method_graph.pdf figures/method_graph.svg
    # 或 inkscape --export-type=pdf figures/method_graph.svg
"""
from __future__ import annotations

import argparse
from pathlib import Path

import graph as graph_mod


def main() -> None:
    parser = argparse.ArgumentParser(description="导出方法依赖图为独立 SVG")
    parser.add_argument("--out", default="figures/method_graph.svg", help="输出路径(相对仓库根)")
    parser.add_argument("--theme", choices=["dark", "light"], default="dark",
                        help="配色。论文用 light,幻灯片深色底用 dark")
    args = parser.parse_args()

    g = graph_mod.load_graph()
    if not graph_mod.is_dag(g):
        raise SystemExit("graph.yaml 有环,拒绝导出")
    laid = graph_mod.layout(g)
    svg = graph_mod.render_svg(g, laid, standalone=True, theme=args.theme)

    repo_root = Path(__file__).resolve().parent.parent
    out = repo_root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")

    print(f"✔ {len(g.nodes)} 节点 / {len(g.edges)} 边 → {out.relative_to(repo_root)}")
    print(f"  画布 {laid['width']}×{laid['height']}  主题 {args.theme}")
    print("  LaTeX 用需先转 PDF:")
    print(f"    rsvg-convert -f pdf -o {out.with_suffix('.pdf').relative_to(repo_root)} {out.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
