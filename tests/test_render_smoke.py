import subprocess
from pathlib import Path

import pytest

from music2midi.midi.examples import build_demo_song
from music2midi.visualize.video import find_ffmpeg


@pytest.fixture(scope="module")
def ffmpeg() -> str:
    try:
        return find_ffmpeg()
    except Exception:
        pytest.skip("no ffmpeg available")


def test_render_tiny_video(tmp_path: Path, ffmpeg: str):
    from music2midi.visualize.renderer import render_video

    midi_path = tmp_path / "demo.mid"
    build_demo_song().save_midi(midi_path)

    out = render_video(
        midi_path,
        tmp_path / "demo.mp4",
        width=320,
        height=180,
        fps=15,
        with_audio=False,
    )
    assert out.exists() and out.stat().st_size > 1000

    # The file must decode cleanly end to end.
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(out), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
