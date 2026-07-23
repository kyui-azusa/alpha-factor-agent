"""从同一 Manim 场景导出首屏亮暗封面,保留现有正片。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENE = ROOT / "videos" / "alpha_storyboard_process" / "hero_poster.py"
MEDIA = ROOT / "platform" / "media"
VIDEO = MEDIA / "demo.mp4"


def render(theme: str) -> Path:
    output_name = f"poster-{theme}"
    with tempfile.TemporaryDirectory(prefix="alpha-poster-") as tmp:
        env = os.environ.copy()
        env["POSTER_THEME"] = theme
        subprocess.run(
            [
                "manim",
                "-ql",
                "-s",
                "--format=png",
                "-r",
                "1280,720",
                "--media_dir",
                tmp,
                "--output_file",
                output_name,
                str(SCENE),
                "HeroPoster",
            ],
            cwd=SCENE.parent,
            env=env,
            check=True,
        )
        candidates = list(Path(tmp).rglob(f"{output_name}.png"))
        if len(candidates) != 1:
            raise RuntimeError(f"Manim 输出异常:{candidates}")
        target = MEDIA / f"{output_name}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(candidates[0]),
                "-q:v",
                "2",
                str(target),
            ],
            check=True,
        )
    return target


def main() -> None:
    if not shutil.which("manim") or not shutil.which("ffmpeg"):
        raise RuntimeError("生成封面需要 manim 与 ffmpeg")
    if not VIDEO.exists():
        raise FileNotFoundError(f"正片不存在:{VIDEO}")
    MEDIA.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        path = render(theme)
        print(f"生成 {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
