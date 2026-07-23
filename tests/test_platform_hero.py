"""首屏视频的发布边界与生成结果。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = REPO_ROOT / "platform"
sys.path.insert(0, str(PLATFORM_DIR))

import build as build_mod  # noqa: E402


def test_render_film_uses_native_inline_player():
    html = build_mod.render_film(
        {
            "label": "方法讲解",
            "status": "过程稿",
            "title": "演示",
            "duration": "5:56",
            "summary": "摘要",
            "poster_dark": "media/poster-dark.jpg",
            "poster_light": "media/poster-light.jpg",
            "video": "media/demo.mp4",
        }
    )

    assert 'class="film-player"' in html
    assert "controls playsinline" in html
    assert 'preload="metadata"' in html
    assert 'poster="media/poster-dark.jpg"' in html
    assert 'data-poster-dark="media/poster-dark.jpg"' in html
    assert 'data-poster-light="media/poster-light.jpg"' in html
    assert "data-film-open" not in html
    assert "film-box" not in html
    assert "teaser.mp4" not in html


def test_load_hero_film_fails_closed_without_public(monkeypatch, tmp_path):
    hero = tmp_path / "hero.md"
    hero.write_text(
        "---\npublic: false\nposter_dark: missing-dark.jpg\n"
        "poster_light: missing-light.jpg\nvideo: missing.mp4\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_mod, "HERO_FILE", hero)

    assert build_mod.load_hero_film() == {}


def test_load_hero_film_requires_public_media(monkeypatch, tmp_path):
    hero = tmp_path / "hero.md"
    hero.write_text(
        "---\npublic: true\nposter_dark: missing-dark.jpg\n"
        "poster_light: missing-light.jpg\nvideo: missing.mp4\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_mod, "HERO_FILE", hero)
    monkeypatch.setattr(build_mod, "ROOT", tmp_path)

    with pytest.raises(FileNotFoundError, match="poster_dark"):
        build_mod.load_hero_film()


def test_copy_media_copies_both_posters_and_one_video(monkeypatch, tmp_path):
    root = tmp_path / "platform"
    dist = root / "dist"
    media = root / "media"
    media.mkdir(parents=True)
    for name in ("poster-dark.jpg", "poster-light.jpg", "demo.mp4"):
        (media / name).write_bytes(name.encode())
    monkeypatch.setattr(build_mod, "ROOT", root)
    monkeypatch.setattr(build_mod, "DIST", dist)

    copied = build_mod.copy_media(
        {
            "poster_dark": "media/poster-dark.jpg",
            "poster_light": "media/poster-light.jpg",
            "video": "media/demo.mp4",
        }
    )

    assert copied == [
        "media/poster-dark.jpg",
        "media/poster-light.jpg",
        "media/demo.mp4",
    ]
    assert all((dist / rel).exists() for rel in copied)


def test_theme_switch_only_updates_poster():
    assert "film.setAttribute('poster', next)" in build_mod.JS
    assert "film.setAttribute('src'" not in build_mod.JS
    assert ".load()" not in build_mod.JS
