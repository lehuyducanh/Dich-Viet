"""Instrumental style presets for the song generator.

Each preset captures the "DNA" of a style — scale/mode, tempo range, a General
MIDI instrument palette, harmonic vocabulary, rhythmic/textural feel, and a
visualizer color palette. The presets steer the LLM via `prompt_block()` and
supply per-style defaults (tempo, colors) to the CLI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StylePreset:
    id: str
    name: str
    group: str
    aliases: tuple[str, ...]
    scale: str
    tempo: tuple[int, int]
    time_signature: str
    instruments: tuple[tuple[str, int], ...]  # (label, GM program); first = lead/melody
    bass: tuple[str, int]
    drums: bool
    harmony: str
    texture: str
    palette: tuple[str, ...] = field(default=("#4FC3F7", "#81C784", "#FFB74D"))

    @property
    def default_tempo(self) -> int:
        return (self.tempo[0] + self.tempo[1]) // 2

    def prompt_block(self) -> str:
        instr = "; ".join(f"{label} (GM program {gm})" for label, gm in self.instruments)
        bass_label, bass_gm = self.bass
        drum_note = (
            " Include a drum track with is_drum=true using GM percussion pitches."
            if self.drums
            else " No drum track."
        )
        return (
            f"STYLE: {self.name}\n"
            f"- Scale / mode: {self.scale}\n"
            f"- Tempo: around {self.default_tempo} bpm "
            f"(range {self.tempo[0]}-{self.tempo[1]}); time signature {self.time_signature}\n"
            f"- Instruments (use these GM programs): {instr}; "
            f"bass: {bass_label} (GM program {bass_gm}).{drum_note}\n"
            f"- Harmony: {self.harmony}\n"
            f"- Texture & feel: {self.texture}\n"
            "Compose idiomatically in this style; let the instruments and scale define the character."
        )


def _p(**kw) -> StylePreset:
    return StylePreset(**kw)


# ---------------------------------------------------------------------------
# Registry. Grouped roughly: World/Folk, Cinematic, Electronic, Classical, Jazz.
# ---------------------------------------------------------------------------

_PRESETS: tuple[StylePreset, ...] = (
    # --- World / Folk ---
    _p(
        id="russian_folk", name="Dân ca Nga (Russian Folk)", group="World / Folk",
        aliases=("dan ca nga", "dân ca nga", "russian", "nga", "balalaika", "bayan"),
        scale="E or A harmonic minor", tempo=(96, 132), time_signature="3/4",
        instruments=(("Accordion/Bayan", 21), ("Nylon Guitar (balalaika)", 24)),
        bass=("Acoustic Bass", 32), drums=False,
        harmony="i-VI-III-VII with a raised leading tone (harmonic minor V); sudden minor/major shifts",
        texture="waltz oom-pah (bass on 1, chords on 2-3), fast ornaments, melancholic-then-lively",
        palette=("#E57373", "#FFB74D", "#FFF176"),
    ),
    _p(
        id="chinese_classical", name="Nhạc cổ Trung Quốc (Chinese Classical)", group="World / Folk",
        aliases=("trung quoc", "trung quốc", "chinese", "guzheng", "pipa", "co trung hoa"),
        scale="major pentatonic (gong mode)", tempo=(60, 96), time_signature="4/4",
        instruments=(("Dizi flute", 73), ("Guzheng/Koto", 107), ("Erhu/Fiddle", 110)),
        bass=("Koto (low)", 107), drums=False,
        harmony="no functional harmony; open fifths and pentatonic clusters, drone-like",
        texture="largely monophonic melody with grace-note slides and bends, sparse, lots of space",
        palette=("#E53935", "#FFB300", "#FF7043"),
    ),
    _p(
        id="nordic_folk", name="Dân ca Bắc Âu (Nordic Folk)", group="World / Folk",
        aliases=("bac au", "bắc âu", "nordic", "scandinav", "nyckelharpa", "viking"),
        scale="Dorian or Aeolian mode", tempo=(80, 112), time_signature="4/4",
        instruments=(("Fiddle", 110), ("String Ensemble", 48)),
        bass=("Cello drone", 42), drums=False,
        harmony="modal drones, i-VII and i-VI, open fifths",
        texture="sustained drone under an ornamented fiddle melody; cold, wistful, hypnotic",
        palette=("#4FC3F7", "#B0BEC5", "#80DEEA"),
    ),
    _p(
        id="japanese_traditional", name="Nhạc Nhật truyền thống (Japanese Traditional)",
        group="World / Folk",
        aliases=("nhat ban", "nhật bản", "japanese", "koto", "shakuhachi", "gagaku"),
        scale="In / Hirajoshi pentatonic", tempo=(52, 84), time_signature="4/4",
        instruments=(("Shakuhachi flute", 77), ("Koto", 107)),
        bass=("Koto (low)", 107), drums=False,
        harmony="static pentatonic, fourths and fifths, no Western cadences",
        texture="ma (negative space), slow phrases, pitch bends and breathy gestures",
        palette=("#5C6BC0", "#E57373", "#CFD8DC"),
    ),
    _p(
        id="celtic", name="Celtic / Ireland", group="World / Folk",
        aliases=("celtic", "ireland", "irish", "ai len", "ai-len", "tin whistle"),
        scale="Mixolydian or Dorian mode", tempo=(96, 132), time_signature="6/8",
        instruments=(("Tin whistle", 78), ("Orchestral Harp", 46), ("Fiddle", 110)),
        bass=("Acoustic Bass", 32), drums=False,
        harmony="modal, I-VII-IV, drone-friendly",
        texture="jig (6/8) or reel feel, fast rolls and ornaments, lilting and bright",
        palette=("#66BB6A", "#FFD54F", "#4DB6AC"),
    ),
    _p(
        id="middle_eastern", name="Trung Đông / Ả Rập (Middle Eastern)", group="World / Folk",
        aliases=("trung dong", "trung đông", "a rap", "ả rập", "arabic", "middle east", "oud"),
        scale="Hijaz maqam (Phrygian dominant feel)", tempo=(80, 120), time_signature="4/4",
        instruments=(("Ney flute", 73), ("Oud/Sitar", 104)),
        bass=("Oud (low)", 104), drums=True,
        harmony="modal around a tonic with the Hijaz augmented-second; pedal tone",
        texture="improvisatory melody with semitone leans, hand-drum (darbuka) groove, ornamented",
        palette=("#FFB300", "#8D6E63", "#D84315"),
    ),
    _p(
        id="latin_bossa", name="Latin / Bossa Nova", group="World / Folk",
        aliases=("latin", "bossa", "bossa nova", "samba", "brazil"),
        scale="major/minor with jazz color", tempo=(110, 132), time_signature="4/4",
        instruments=(("Nylon Guitar", 24), ("Electric Piano", 4), ("Vibraphone", 11)),
        bass=("Acoustic Bass", 32), drums=True,
        harmony="maj7/m7/9 chords, ii-V motion, smooth voice leading",
        texture="bossa clave, gentle syncopation, soft brushed percussion, relaxed",
        palette=("#4DB6AC", "#FFD54F", "#FF8A65"),
    ),
    _p(
        id="flamenco", name="Flamenco (Spanish)", group="World / Folk",
        aliases=("flamenco", "tay ban nha", "tây ban nha", "spanish", "spain"),
        scale="Phrygian / Phrygian dominant", tempo=(96, 140), time_signature="4/4",
        instruments=(("Nylon Guitar", 24), ("Nylon Guitar (rasgueado)", 24)),
        bass=("Nylon Guitar (low)", 24), drums=True,
        harmony="Andalusian cadence (Am-G-F-E), Phrygian dominant on E",
        texture="rasgueado strumming bursts, palmas hand-claps, passionate and rhythmic",
        palette=("#E53935", "#FF7043", "#212121"),
    ),
    # --- Cinematic / Ambient ---
    _p(
        id="space_ambient", name="Âm hưởng không gian (Space Ambient)", group="Cinematic",
        aliases=("khong gian", "không gian", "space", "vu tru", "vũ trụ", "cosmic", "interstellar"),
        scale="minor add9 / Lydian, suspended", tempo=(50, 72), time_signature="4/4",
        instruments=(("Piano", 0), ("Warm Pad", 89), ("String Ensemble", 48)),
        bass=("Synth Pad (low)", 89), drums=False,
        harmony="suspended and add9 chords, slow harmonic rhythm, unresolved",
        texture="very slow, long sustained notes, wide spacing, floating and weightless",
        palette=("#5C6BC0", "#26C6DA", "#7E57C2"),
    ),
    _p(
        id="epic_cinematic", name="Epic Cinematic (Hùng tráng)", group="Cinematic",
        aliases=("epic", "cinematic", "hung trang", "hùng tráng", "soundtrack", "trailer"),
        scale="natural minor, heroic", tempo=(80, 112), time_signature="4/4",
        instruments=(("String Ensemble", 48), ("Brass/Trumpet", 56), ("Choir Aahs", 52)),
        bass=("Timpani + low strings", 47), drums=True,
        harmony="i-VI-III-VII power progression, strong cadences at the climax",
        texture="ostinato that builds in layers to a big crescendo, then resolves",
        palette=("#FFB300", "#FF7043", "#FFEE58"),
    ),
    _p(
        id="minimal_ambient", name="Ambient tối giản (Minimal Ambient)", group="Cinematic",
        aliases=("toi gian", "tối giản", "minimal", "minimalist", "glass", "eno", "meditation"),
        scale="diatonic / modal", tempo=(60, 92), time_signature="4/4",
        instruments=(("Piano", 0), ("Warm Pad", 89)),
        bass=("Pad (low)", 89), drums=False,
        harmony="a few chords cycling, gradual additive change",
        texture="repeating arpeggio cells shifting slowly, meditative and steady",
        palette=("#90A4AE", "#80CBC4", "#A5D6A7"),
    ),
    _p(
        id="horror_suspense", name="Kinh dị / Hồi hộp (Horror / Suspense)", group="Cinematic",
        aliases=("kinh di", "kinh dị", "horror", "hoi hop", "hồi hộp", "suspense", "thriller"),
        scale="chromatic / octatonic, dissonant", tempo=(48, 96), time_signature="4/4",
        instruments=(("Tremolo Strings", 44), ("Prepared Piano", 0)),
        bass=("Contrabass cluster", 43), drums=False,
        harmony="tone clusters, tritones, minor-second stabs, no resolution",
        texture="tremolo swells, sudden stabs, unsettling silences, creeping tension",
        palette=("#B71C1C", "#37474F", "#616161"),
    ),
    # --- Electronic ---
    _p(
        id="edm_house", name="EDM / House", group="Electronic",
        aliases=("edm", "house", "dance", "club", "festival"),
        scale="natural minor or major", tempo=(122, 128), time_signature="4/4",
        instruments=(("Saw Synth Lead", 81), ("Synth Pad", 89)),
        bass=("Synth Bass", 38), drums=True,
        harmony="vi-IV-I-V or i-VI-III-VII loops",
        texture="four-on-the-floor kick, build-and-drop, arpeggiated synths, sidechain pump feel",
        palette=("#E040FB", "#18FFFF", "#76FF03"),
    ),
    _p(
        id="lofi", name="Lo-fi / Chillhop", group="Electronic",
        aliases=("lofi", "lo-fi", "lo fi", "chillhop", "chill", "study beats"),
        scale="major/minor with jazz color", tempo=(70, 90), time_signature="4/4",
        instruments=(("Electric Piano", 4), ("Vibraphone", 11)),
        bass=("Finger Bass", 33), drums=True,
        harmony="maj7/m9 chords, ii-V, smooth and mellow",
        texture="swung 8ths, laid-back groove, soft drums, warm and nostalgic",
        palette=("#F48FB1", "#80CBC4", "#FFE0B2"),
    ),
    _p(
        id="synthwave", name="Synthwave / Retro 80s", group="Electronic",
        aliases=("synthwave", "retrowave", "retro", "80s", "outrun", "vaporwave"),
        scale="natural minor", tempo=(100, 116), time_signature="4/4",
        instruments=(("Synth Lead", 80), ("Synth Pad", 89)),
        bass=("Synth Bass (arp)", 39), drums=True,
        harmony="i-VI-III-VII, nostalgic and driving",
        texture="arpeggiated bassline, gated-reverb feel, bright analog leads, neon nostalgia",
        palette=("#FF4081", "#7C4DFF", "#18FFFF"),
    ),
    _p(
        id="chiptune", name="Chiptune / 8-bit", group="Electronic",
        aliases=("chiptune", "8-bit", "8bit", "8 bit", "nes", "game boy", "retro game"),
        scale="major, bright", tempo=(130, 168), time_signature="4/4",
        instruments=(("Square Lead", 80), ("Square Lead 2", 80)),
        bass=("Synth Bass (triangle)", 38), drums=True,
        harmony="fast I-V-vi-IV with broken-chord fills",
        texture="rapid arpeggios standing in for chords, tight and energetic, video-game feel",
        palette=("#00E676", "#FF1744", "#FFEA00"),
    ),
    _p(
        id="trap", name="Trap / Hip-hop instrumental", group="Electronic",
        aliases=("trap", "hip hop", "hip-hop", "808", "drill"),
        scale="natural / harmonic minor, dark", tempo=(130, 150), time_signature="4/4",
        instruments=(("Bell/Pluck", 9), ("Piano", 0)),
        bass=("808 Synth Bass", 38), drums=True,
        harmony="dark minor loops, sparse",
        texture="half-time feel, gliding 808 bass, fast hi-hat rolls, sparse haunting melody",
        palette=("#7C4DFF", "#212121", "#D500F9"),
    ),
    # --- Classical / Art ---
    _p(
        id="baroque", name="Baroque (Bach)", group="Classical",
        aliases=("baroque", "bach", "harpsichord", "fugue", "co dien baroque"),
        scale="major/minor, functional", tempo=(72, 120), time_signature="4/4",
        instruments=(("Harpsichord", 6), ("Church Organ", 19)),
        bass=("Cello continuo", 42), drums=False,
        harmony="functional tonality, sequences, suspensions, clear cadences",
        texture="two- to three-voice counterpoint, steady motion, trills and ornaments",
        palette=("#D7CCC8", "#FFD54F", "#8D6E63"),
    ),
    _p(
        id="romantic", name="Lãng mạn (Romantic — Chopin/Liszt)", group="Classical",
        aliases=("lang man", "lãng mạn", "romantic", "chopin", "liszt", "nocturne"),
        scale="major/minor, chromatic", tempo=(60, 108), time_signature="4/4",
        instruments=(("Piano", 0),),
        bass=("Piano (low)", 0), drums=False,
        harmony="rich chromatic harmony, secondary dominants, 7th/9th chords",
        texture="rubato, rolled chords, singing melody, wide dynamic swells, expressive",
        palette=("#C62828", "#FFB300", "#AD1457"),
    ),
    _p(
        id="impressionist", name="Ấn tượng (Impressionist — Debussy/Ravel)", group="Classical",
        aliases=("an tuong", "ấn tượng", "impressionist", "debussy", "ravel"),
        scale="whole-tone and pentatonic", tempo=(56, 100), time_signature="4/4",
        instruments=(("Piano", 0), ("Orchestral Harp", 46)),
        bass=("Piano (low)", 0), drums=False,
        harmony="9th/11th/added-note chords, parallel motion, unresolved colors",
        texture="blurred pedal washes, dreamy and impression, floating rhythm",
        palette=("#4DD0E1", "#B39DDB", "#80DEEA"),
    ),
    _p(
        id="tango", name="Tango (Piazzolla)", group="Classical",
        aliases=("tango", "piazzolla", "bandoneon", "argentina"),
        scale="natural / harmonic minor", tempo=(100, 124), time_signature="4/4",
        instruments=(("Tango Accordion/Bandoneon", 23), ("Piano", 0), ("String Ensemble", 48)),
        bass=("Acoustic Bass", 32), drums=False,
        harmony="dramatic minor with strong dominants, chromatic passing chords",
        texture="marcato rhythm with sharp accents, sudden rubato, passionate and theatrical",
        palette=("#D32F2F", "#212121", "#BDBDBD"),
    ),
    # --- Jazz / Blues ---
    _p(
        id="jazz_ballad", name="Jazz Ballad / Swing", group="Jazz",
        aliases=("jazz", "swing", "ballad", "bebop"),
        scale="major/jazz-minor modes", tempo=(60, 96), time_signature="4/4",
        instruments=(("Piano", 0), ("Tenor Sax", 66)),
        bass=("Acoustic Bass (walking)", 32), drums=True,
        harmony="extended ii-V-I, tritone subs, 9/11/13 chords",
        texture="swing 8ths, walking bass, comped chords, brushed ride, smoky",
        palette=("#FFB300", "#1A237E", "#FFD740"),
    ),
    _p(
        id="blues", name="Blues", group="Jazz",
        aliases=("blues",),
        scale="blues scale (minor pentatonic + b5)", tempo=(60, 104), time_signature="4/4",
        instruments=(("Piano", 0), ("Overdriven Guitar", 29)),
        bass=("Finger Bass", 33), drums=True,
        harmony="12-bar I-IV-V dominant 7th chords",
        texture="shuffle/swing groove, blue notes, call-and-response phrasing",
        palette=("#3949AB", "#00897B", "#FFB300"),
    ),
    _p(
        id="ragtime", name="Ragtime", group="Jazz",
        aliases=("ragtime", "rag", "joplin", "stride"),
        scale="major", tempo=(88, 112), time_signature="4/4",
        instruments=(("Piano", 0),),
        bass=("Piano stride (low)", 0), drums=False,
        harmony="I-IV-V with secondary dominants, stride patterns",
        texture="stride left hand (bass note then chord), syncopated right-hand melody, no swing",
        palette=("#A1887F", "#E57373", "#FFF8E1"),
    ),
)

STYLES: dict[str, StylePreset] = {p.id: p for p in _PRESETS}


def list_styles() -> list[StylePreset]:
    return list(_PRESETS)


def get_style(style_id: str) -> StylePreset:
    """Look up by id or any alias. Raises KeyError (with the catalog) if unknown."""
    key = style_id.strip().lower()
    if key in STYLES:
        return STYLES[key]
    for preset in _PRESETS:
        if key == preset.id or key in (a.lower() for a in preset.aliases):
            return preset
    available = ", ".join(STYLES)
    raise KeyError(f"Unknown style '{style_id}'. Available: {available}")


def detect_style(text: str) -> StylePreset | None:
    """Best-effort detection of a style from free-text (VI/EN) by alias match.

    Aliases are matched on word boundaries so short ones (e.g. 'nga') don't
    trigger inside unrelated words.
    """
    low = text.lower()
    for preset in _PRESETS:
        for alias in preset.aliases:
            if re.search(rf"\b{re.escape(alias.lower())}\b", low):
                return preset
    return None
