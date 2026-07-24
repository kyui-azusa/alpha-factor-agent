"""把 Manim 长视频切成首屏要用的三个产物(海报 / 环境预告 / 可播放全片)。

首屏放的不是全片:6 分钟的讲解片直接自动播放既费流量又没人看完。
分三层:
  poster.jpg  —— 首帧,秒出,视频还没到就先占住位,不留白洞
  teaser.mp4  —— 静音循环的"环境预告":从全片挑三个有动作的片段接成一条,
                 交叉淡入淡出,首尾也淡接所以循环看不出缝。只做氛围,不承担信息
  demo.mp4    —— 全片,+faststart(moov 前置)才能边下边播;点了才加载

为什么要挑片段:Manim 每讲完一点会停 5 秒(page_hold),随便截一段十有八九是静止画面,
放在首屏像张坏掉的图。BEATS 是按"这一段真的有东西在动"手挑的。

    python scripts/make_hero_media.py
    python scripts/make_hero_media.py --src <别的视频> --out platform/dist
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "videos/alpha_storyboard_process/media/videos/review_main/720p30/ReviewVideo.mp4"
OUT = REPO / "platform/media"

# (起点秒, 时长秒) —— 三个有动作的节拍,合起来讲清"这片子在讲什么"
BEATS = [
    (13.5, 5.0),    # s01 收益被拆成几笔账,最后剩下 alpha
    (124.5, 5.0),   # s03 日度 Rank IC 的噪声线一路长出来
    (303.5, 5.0),   # s06 四步闭环:LLM 提想法,代码做裁判
]
XFADE = 0.7         # 节拍之间的交叉淡入淡出
TEASER_W = 960      # 首屏预告不需要 720p,一半分辨率省一半体积
POSTER_AT = 2.5     # 海报取这一秒:落在第一个节拍中间,画面干净


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode:
        sys.exit(f"ffmpeg 失败:\n{' '.join(args)}\n{proc.stderr[-2000:]}")


ENCODE = [
    "-an",                                   # 环境循环必须静音,否则浏览器不给自动播放
    "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p",
    "-crf", "30", "-preset", "slow", "-g", "50",
    "-movflags", "+faststart",
]


def build_montage(src: Path, dst: Path) -> float:
    """三段按 xfade 接成一条。返回时长。"""
    seg = BEATS[0][1]
    inputs: list[str] = []
    for start, dur in BEATS:
        inputs += ["-ss", f"{start}", "-t", f"{dur}", "-i", str(src)]

    chains = [
        f"[{i}:v]scale={TEASER_W}:-2,fps=25,setsar=1,format=yuv420p[v{i}]"
        for i in range(len(BEATS))
    ]
    prev, offset = "v0", seg - XFADE
    for i in range(1, len(BEATS)):
        tag = f"x{i}"
        chains.append(f"[{prev}][v{i}]xfade=transition=fade:duration={XFADE}:offset={offset:.2f}[{tag}]")
        prev = tag
        offset += seg - XFADE

    run(["ffmpeg", "-v", "error", *inputs,
         "-filter_complex", ";".join(chains), "-map", f"[{prev}]", *ENCODE, str(dst), "-y"])
    return len(BEATS) * seg - (len(BEATS) - 1) * XFADE


def build_teaser(src: Path, out: Path, tmp: Path) -> None:
    """做成真正的无缝循环:把片尾叠回片头交叉淡入,而不是两头淡黑。

    两头淡黑虽然也能接上,但首帧就是全黑 —— 海报取不到画面,加载时首屏是个黑洞。
    尾叠头之后没有黑场,首帧即完整画面,海报直接用它。
    """
    montage = tmp / "montage.mp4"
    total = build_montage(src, montage)
    d, body_end = XFADE, total - XFADE
    chains = [
        f"[0:v]trim=0:{d},setpts=PTS-STARTPTS[head]",
        f"[0:v]trim={d}:{body_end},setpts=PTS-STARTPTS[body]",
        f"[0:v]trim={body_end}:{total},setpts=PTS-STARTPTS[tail]",
        # 片尾压在片头上淡过去 → 这一段既是结尾也是开头,循环点看不出来
        f"[tail][head]xfade=transition=fade:duration={d}:offset=0[seam]",
        "[seam][body]concat=n=2:v=1:a=0[out]",
    ]
    run(["ffmpeg", "-v", "error", "-i", str(montage),
         "-filter_complex", ";".join(chains), "-map", "[out]", *ENCODE, str(out), "-y"])


def main() -> None:
    ap = argparse.ArgumentParser(description="生成首屏视频三件套")
    ap.add_argument("--src", default=str(SRC), help="Manim 渲染出的全片")
    ap.add_argument("--out", default=str(OUT), help="产物目录")
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    if not src.exists():
        sys.exit(f"找不到源视频 {src} —— 先渲染 Manim,或用 --src 指定")
    if not shutil.which("ffmpeg"):
        sys.exit("需要 ffmpeg:brew install ffmpeg")
    out.mkdir(parents=True, exist_ok=True)

    tmp = out / ".tmp"
    tmp.mkdir(exist_ok=True)
    try:
        build_teaser(src, out / "teaser.mp4", tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 海报取预告里一帧干净的画面(不取首帧:首帧正处在循环接缝的交叉淡化中,是重影)。
    # 海报与视频首帧对不上没关系 —— 页面上视频是叠在海报之上淡入的,不会闪。
    run(["ffmpeg", "-v", "error", "-ss", str(POSTER_AT), "-i", str(out / "teaser.mp4"),
         "-frames:v", "1", "-q:v", "4", str(out / "poster.jpg"), "-y"])

    # 全片:只搬运不重编码,单纯把 moov 挪到文件头
    run(["ffmpeg", "-v", "error", "-i", str(src), "-c", "copy",
         "-movflags", "+faststart", str(out / "demo.mp4"), "-y"])

    print(f"✔ 首屏视频三件套 → {out.relative_to(REPO)}")
    for name in ("poster.jpg", "teaser.mp4", "demo.mp4"):
        size = (out / name).stat().st_size
        print(f"  {name:<12} {size / 1024:>8.0f} KB")


if __name__ == "__main__":
    main()
