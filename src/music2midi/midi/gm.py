"""General MIDI program numbers and stem-to-instrument mapping."""

# Subset of GM programs the generator prompt and transcriber reference.
GM_PROGRAMS = {
    "Acoustic Grand Piano": 0,
    "Electric Piano": 4,
    "Harpsichord": 6,
    "Glockenspiel": 9,
    "Music Box": 10,
    "Acoustic Guitar (nylon)": 24,
    "Acoustic Guitar (steel)": 25,
    "Electric Guitar (clean)": 27,
    "Overdriven Guitar": 29,
    "Acoustic Bass": 32,
    "Fingered Bass": 33,
    "Picked Bass": 34,
    "Violin": 40,
    "Cello": 42,
    "String Ensemble": 48,
    "Choir Aahs": 52,
    "Trumpet": 56,
    "Tenor Sax": 66,
    "Flute": 73,
    "Pan Flute": 75,
    "Synth Lead (square)": 80,
    "Synth Pad (warm)": 89,
}

# GM percussion pitches (channel 10), used for is_drum tracks.
DRUM_KICK = 36
DRUM_SNARE = 38
DRUM_HIHAT_CLOSED = 42
DRUM_HIHAT_OPEN = 46
DRUM_CRASH = 49
DRUM_RIDE = 51

# Default instrument per Demucs stem.
STEM_PROGRAMS = {
    "vocals": GM_PROGRAMS["Choir Aahs"],
    "bass": GM_PROGRAMS["Fingered Bass"],
    "other": GM_PROGRAMS["Acoustic Grand Piano"],
}

STEM_NAMES = {
    "vocals": "Vocals",
    "bass": "Bass",
    "other": "Accompaniment",
    "drums": "Drums",
}
