"""music2midi command line interface.

Heavy dependencies (torch/demucs/basic-pitch, anthropic network calls) are
imported lazily inside each command so the core commands work without the
optional extras installed.
"""

from pathlib import Path
from typing import Optional

import typer

from . import __version__, config

app = typer.Typer(
    name="music2midi",
    help="Transcribe audio to MIDI, render piano-roll videos, generate songs with Claude.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"music2midi {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass


@app.command()
def demo(
    output: Path = typer.Option(Path("demo.mid"), "--output", "-o", help="Output MIDI path."),
) -> None:
    """Write the built-in two-track demo song as a MIDI file."""
    from .midi.examples import build_demo_song

    song = build_demo_song()
    song.save_midi(output)
    typer.echo(f"Wrote demo song ({len(song.tracks)} tracks) to {output}")


@app.command()
def visualize(
    midi_file: Path = typer.Argument(..., exists=True, readable=True, help="Input .mid file."),
    output: Path = typer.Option(Path("out.mp4"), "--output", "-o", help="Output video path."),
    fps: int = typer.Option(config.DEFAULT_FPS, help="Frames per second."),
    resolution: str = typer.Option(
        f"{config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}", help="Video size, e.g. 1920x1080."
    ),
    colors: Optional[str] = typer.Option(
        None, help='Comma-separated hex colors per track, e.g. "#4FC3F7,#81C784".'
    ),
    lookahead: float = typer.Option(
        config.DEFAULT_LOOKAHEAD_S, help="Seconds of upcoming notes visible above the keyboard."
    ),
    soundfont: Optional[Path] = typer.Option(None, help="SoundFont (.sf2) for audio synthesis."),
    no_audio: bool = typer.Option(False, "--no-audio", help="Render a silent video."),
) -> None:
    """Render a MIDI file as a Synthesia-style falling-notes piano video."""
    from .visualize.renderer import render_video

    try:
        width, height = (int(p) for p in resolution.lower().split("x"))
    except ValueError:
        typer.secho(f"Invalid --resolution '{resolution}', expected WIDTHxHEIGHT.", fg="red")
        raise typer.Exit(code=2)
    palette = config.DEFAULT_PALETTE
    if colors:
        palette = [c.strip() for c in colors.split(",") if c.strip()]

    render_video(
        midi_path=midi_file,
        output_path=output,
        width=width,
        height=height,
        fps=fps,
        lookahead_s=lookahead,
        palette=palette,
        with_audio=not no_audio,
        soundfont=soundfont,
    )
    typer.echo(f"Wrote video to {output}")


@app.command()
def generate(
    prompt: str = typer.Argument(..., help="Song description (Vietnamese or English)."),
    output: Path = typer.Option(Path("song.mid"), "--output", "-o", help="Output MIDI path."),
    bars: int = typer.Option(16, min=1, max=config.MAX_BARS, help="Approximate song length in bars."),
    model: str = typer.Option(config.DEFAULT_MODEL, help="Anthropic model ID."),
    render_video: bool = typer.Option(
        False, "--render-video", help="Also render a piano video next to the MIDI file."
    ),
    save_json: bool = typer.Option(
        True, "--save-json/--no-save-json", help="Write the editable song JSON next to the MIDI."
    ),
) -> None:
    """Generate a new song from a text description using Claude."""
    from .generate.llm import generate_song

    song = generate_song(prompt=prompt, bars=bars, model=model)
    song.save_midi(output)
    typer.echo(f"Wrote '{song.title}' ({len(song.tracks)} tracks) to {output}")

    if save_json:
        json_path = output.with_suffix(".json")
        json_path.write_text(song.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"Wrote editable JSON to {json_path}")

    if render_video:
        from .visualize.renderer import render_video as _render

        video_path = output.with_suffix(".mp4")
        _render(midi_path=output, output_path=video_path)
        typer.echo(f"Wrote video to {video_path}")


@app.command()
def transcribe(
    audio_file: Path = typer.Argument(..., exists=True, readable=True, help="Input mp3/wav file."),
    output: Path = typer.Option(Path("song.mid"), "--output", "-o", help="Output MIDI path."),
    stems: str = typer.Option(
        "vocals,bass,other", help="Comma-separated stems to transcribe (vocals,drums,bass,other)."
    ),
    drums: str = typer.Option("skip", help="Drum handling: 'skip' or 'onset' (rough)."),
    no_separate: bool = typer.Option(
        False, "--no-separate", help="Skip Demucs; transcribe the full mix as one piano track."
    ),
) -> None:
    """Transcribe an audio file into a multi-instrument MIDI file."""
    from .transcribe.pipeline import transcribe_audio

    song = transcribe_audio(
        audio_path=audio_file,
        stems=[s.strip() for s in stems.split(",") if s.strip()],
        drums_mode=drums,
        separate=not no_separate,
    )
    song.save_midi(output)
    total = sum(len(t.notes) for t in song.tracks)
    typer.echo(f"Wrote {total} notes across {len(song.tracks)} tracks to {output}")


@app.command()
def pipeline(
    audio_file: Path = typer.Argument(..., exists=True, readable=True, help="Input mp3/wav file."),
    output: Path = typer.Option(Path("out.mp4"), "--output", "-o", help="Output video path."),
    stems: str = typer.Option("vocals,bass,other", help="Stems to transcribe."),
    drums: str = typer.Option("skip", help="Drum handling: 'skip' or 'onset'."),
    no_separate: bool = typer.Option(False, "--no-separate", help="Skip Demucs separation."),
    fps: int = typer.Option(config.DEFAULT_FPS, help="Frames per second."),
    resolution: str = typer.Option(f"{config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}"),
    soundfont: Optional[Path] = typer.Option(None, help="SoundFont (.sf2) for audio synthesis."),
    no_audio: bool = typer.Option(False, "--no-audio", help="Render a silent video."),
) -> None:
    """Transcribe audio and render the piano video in one step."""
    from .transcribe.pipeline import transcribe_audio
    from .visualize.renderer import render_video

    song = transcribe_audio(
        audio_path=audio_file,
        stems=[s.strip() for s in stems.split(",") if s.strip()],
        drums_mode=drums,
        separate=not no_separate,
    )
    midi_path = output.with_suffix(".mid")
    song.save_midi(midi_path)
    typer.echo(f"Wrote MIDI to {midi_path}")

    width, height = (int(p) for p in resolution.lower().split("x"))
    render_video(
        midi_path=midi_path,
        output_path=output,
        width=width,
        height=height,
        fps=fps,
        with_audio=not no_audio,
        soundfont=soundfont,
    )
    typer.echo(f"Wrote video to {output}")


if __name__ == "__main__":
    app()
