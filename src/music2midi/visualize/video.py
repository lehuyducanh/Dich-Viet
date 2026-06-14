"""ffmpeg discovery and raw-frame video encoding."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def find_ffmpeg() -> str:
    """Prefer the system ffmpeg; fall back to the binary bundled with imageio-ffmpeg."""
    system = shutil.which("ffmpeg")
    if system:
        return system
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


class FrameWriter:
    """Pipes raw RGB frames into an ffmpeg process encoding H.264."""

    def __init__(self, output_path: str | Path, width: int, height: int, fps: int):
        self.output_path = Path(output_path)
        cmd = [
            find_ffmpeg(),
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            str(self.output_path),
        ]
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame_bytes: bytes) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(frame_bytes)

    def close(self) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.close()
        ret = self._proc.wait()
        if ret != 0:
            raise RuntimeError(f"ffmpeg exited with code {ret}")

    def __enter__(self) -> "FrameWriter":
        return self

    def __exit__(self, *exc) -> None:
        if exc[0] is None:
            self.close()
        else:
            self._proc.kill()


def mux_audio(video_path: Path, audio_path: Path, output_path: Path, audio_offset_s: float) -> None:
    """Mux a wav track into a video, delaying audio by `audio_offset_s` (lead-in)."""
    cmd = [
        find_ffmpeg(),
        "-y",
        "-loglevel", "error",
        "-i", str(video_path),
        "-itsoffset", str(audio_offset_s),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
