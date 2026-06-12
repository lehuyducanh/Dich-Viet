# 🎛️ Music Producer Simulator

Hệ thống giả lập quy trình sản xuất của một **music producer chuyên nghiệp**:

> **Input**: một bản nhạc cơ bản (MIDI hoặc sheet/MusicXML) — giai điệu + hợp âm đơn giản.
> **Output**: một bản nhạc hoàn chỉnh, sôi động, theo **theme tùy chỉnh** bạn yêu cầu — sử dụng **LLM (Claude)** làm "bộ não producer" kết hợp **kho template genre build sẵn**.

```
MIDI / MusicXML ──▶ Phân tích nhạc lý ──▶ LLM Producer Brain ──▶ Arranger ──▶ MIDI + WAV
                    (key, harmonic        (đọc brief + chọn      (drums, bass,   (synth engine
                     rhythm, chords 7th,   template, lập kế        pad, arp,       nội bộ, không
                     melody, tempo)        hoạch arrangement)      lead, FX)       cần DAW)
```

## Cài đặt

```bash
pip install -r requirements.txt        # mido (+ anthropic nếu dùng LLM)
export ANTHROPIC_API_KEY=sk-ant-...    # tùy chọn — không có key vẫn chạy được (rule-based)
```

## Sử dụng nhanh

```bash
# Tạo file demo input (8 bars Am-F-C-G + melody)
python examples/make_demo_input.py

# Sản xuất bản remix theo theme — LLM tự chọn template, tempo, arrangement
python -m music_producer remix examples/demo_input.mid \
    --theme "EDM sôi động cho festival, drop thật mạnh, 128bpm" \
    -o output.mid

# Không có API key? Dùng rule-based planner
python -m music_producer remix input.mid --theme "lofi chill để học bài" --no-llm

# Xem kho template
python -m music_producer templates

# Phân tích input (key, chords, melody)
python -m music_producer analyze input.mid

# Bounce thêm file .wav bằng synth engine nội bộ — KHÔNG cần DAW/soundfont
python -m music_producer remix input.mid -t "synthwave retro" --audio

# (tùy chọn) bounce qua fluidsynth + GM soundfont nếu bạn thích âm thanh GM
python -m music_producer remix input.mid -t "synthwave retro" --fluidsynth
```

### Remix nhạc truyền thống (ví dụ: Happy Birthday → EDM 180 giây)

```bash
# 1. Tạo input từ bản nhạc gốc (melody + hợp âm cơ bản là đủ)
python examples/make_happy_birthday.py          # -> examples/happy_birthday.mid

# 2. Remix với theme + thời lượng mục tiêu
python -m music_producer remix examples/happy_birthday.mid \
    --theme "EDM sôi động cho tiệc sinh nhật, drop thật mạnh, vui tươi" \
    --duration 180 \
    -o hbd_edm.mid --audio                      # -> hbd_edm.mid + hbd_edm.wav (~180s)
```

`--duration` co giãn arrangement theo đúng thời lượng (giữ tỉ lệ intro/build/drop, làm tròn theo 2 bars, phần dư dồn vào drop — như một bản edit thật). Với bản nhạc gốc bất kỳ: bạn chỉ cần file MIDI chứa melody + hợp âm (tự ký âm trong MuseScore/DAW, hoặc tải MIDI có sẵn), hệ thống lo phần còn lại — kể cả bài gốc nhịp 3/4 thì nên ký âm lại sang 4/4 trước khi remix sang thể loại 4/4 như EDM.

### Python API

```python
from music_producer import produce

analysis, plan, song = produce(
    "input.mid",
    theme="trap 808 thật dark, năng lượng cao",
    output_path="output.mid",
    audio_path="output.wav",   # tùy chọn: bounce WAV bằng engine nội bộ
)
print(plan.notes)  # lý do producer chọn cách sản xuất này
```

## Kiến trúc

| Module | Vai trò |
|---|---|
| `midi_io.py` | Đọc MIDI (mido) và MusicXML/MXL: ties, grace notes, transpose, metronome, voices, **chord symbols `<harmony>`** → `Song` |
| `analysis.py` | Phát hiện key (Krumhansl-Schmuckler); **hợp âm theo nửa bar** với bộ chất lượng mở rộng (maj/min/dim/sus4/maj7/min7/dom7), xử lý đảo phách (anticipation), hysteresis chống đổi hợp âm giả, merge thành **harmonic rhythm** thực; trích xuất melody → `SongAnalysis` |
| `producer_brain.py` | **LLM brain** (Claude `claude-opus-4-8`, structured JSON output) đọc bản phân tích + brief của bạn → `ProductionPlan`. Fallback `RuleBasedBrain` khi offline |
| `template_library.py` + `templates/*.json` | Kho template genre: tempo range, drum grid 16-step theo mức năng lượng, style bassline, nhạc cụ GM, **sound design patches**, arrangement mặc định |
| `generators.py` | Sinh từng layer bám theo harmonic rhythm (hợp âm đổi giữa bar vẫn đúng): drums (grid), bass (9 styles), pad (voicing + 9th), arp, melody/lead (tile melody gốc), FX riser |
| `arrangement.py` | Lắp các section theo plan: intro → verse → build → drop → breakdown → ... |
| `humanize.py` | Swing, micro-timing, velocity jitter (deterministic) |
| `renderer.py` | Xuất Standard MIDI File; tùy chọn bounce WAV qua FluidSynth |
| `sound_design.py` + `synth_engine.py` | **Synth engine nội bộ** (numpy DSP): subtractive synth (saw/supersaw/square/triangle/sine, unison detune, sub-osc, lowpass, ADSR), drums tổng hợp (kick sweep, snare/clap/hats từ noise), **sidechain pump theo kick thật**, delay ping-pong sync tempo, reverb FFT-convolution, vinyl crackle cho lofi, limiter → WAV stereo 16-bit |

## Kho template có sẵn

| Template | Thể loại | Tempo | Hợp với theme |
|---|---|---|---|
| `edm` | EDM / Big Room Festival | 126–130 | sôi động, festival, party |
| `house` | Deep / Classic House | 120–125 | groovy, club, dance |
| `trap` | Trap / Hip-hop | 135–150 | 808, dark, rap |
| `lofi` | Lo-fi Chill Hop | 75–90 | chill, học bài, thư giãn |
| `synthwave` | Synthwave / Retrowave | 100–112 | retro, 80s, hoài niệm |
| `dnb` | Drum & Bass / Liquid | 170–176 | nhanh, dồn dập, adrenaline |

**Thêm genre mới**: chỉ cần thả một file JSON vào `music_producer/templates/` (hoặc dùng `--template-dir`), không cần sửa code. Xem `templates/edm.json` làm mẫu — drum pattern là grid 16 ký tự (`x` accent, `o` normal, `s` soft, `.` nghỉ).

## LLM Producer Brain hoạt động thế nào?

1. Bản nhạc input được phân tích thành bản tóm tắt như một lead sheet: key, tempo, chord progression, melody.
2. Claude nhận: bản phân tích + catalog template + **brief của bạn** (tiếng Việt hoặc tiếng Anh).
3. Claude trả về **JSON có schema cố định** (structured outputs): template, tempo, transpose, energy, và arrangement từng section (tên, số bars, energy, layers).
4. Plan được validate/clamp lại trước khi đưa vào arranger — LLM không bao giờ chạm trực tiếp vào MIDI.

## Tests

```bash
python -m pytest tests/ -v
```

## Tùy chỉnh sound design

Mỗi template có thể override patch của từng layer trong JSON — không cần sửa code:

```json
"sound_design": {
  "bass":  {"osc": "sine", "sub": true, "release": 0.5, "sidechain": 0.9},
  "lead":  {"osc": "supersaw", "voices": 7, "detune": 0.35, "cutoff": 9500},
  "drums": {"gain": 1.0, "reverb": 0.1},
  "_master": {"vinyl": 0.6, "cutoff": 7500}
}
```

Các tham số patch: `osc` (saw/supersaw/square/triangle/sine/noise), `voices`, `detune`, `octave`, `sub`, `cutoff`, `attack/decay/sustain/release`, `gain`, `pan`, `width` (stereo Haas), `delay`, `reverb`, `sidechain`. Mặc định cho từng layer ở `sound_design.py`.

## Giới hạn hiện tại

- Synth engine nội bộ hướng tới chất lượng demo/preview tốt — bản phát hành thương mại vẫn nên đưa file MIDI vào DAW với synth/sample chuyên nghiệp để mix-master.
- Hợp âm phát hiện ở độ phân giải nửa bar; hòa thanh đổi nhanh hơn (mỗi beat) sẽ được làm tròn về nửa bar gần nhất.
- MusicXML: chưa hỗ trợ `score-timewise`, repeat/volta, và dynamics chi tiết.
