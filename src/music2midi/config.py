"""Project-wide defaults shared by the CLI commands."""

# LLM generation
DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000
MAX_BARS = 32
MAX_NOTES = 600

# Visualizer
DEFAULT_FPS = 60
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_LOOKAHEAD_S = 3.0
LEAD_IN_S = 1.0
TAIL_S = 2.0
KEYBOARD_HEIGHT_FRAC = 0.18

# Track color palette (track i -> palette[i % len]); blue/green first to match
# the Synthesia reference look.
DEFAULT_PALETTE = [
    "#4FC3F7",  # blue
    "#81C784",  # green
    "#FFB74D",  # orange
    "#E57373",  # red
    "#BA68C8",  # purple
    "#FFF176",  # yellow
]

# Audio synthesis
SOUNDFONT_SEARCH_PATHS = [
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/FluidR3_GM.sf2",
    "/usr/share/soundfonts/default.sf2",
    "/usr/local/share/soundfonts/FluidR3_GM.sf2",
]
