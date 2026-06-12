# 🎛️ Music Producer Simulator

Hệ thống giả lập quy trình sản xuất của một **music producer chuyên nghiệp**:

> **Input**: một bản nhạc cơ bản (MIDI hoặc sheet/MusicXML) — giai điệu + hợp âm đơn giản.
> **Output**: một bản nhạc hoàn chỉnh, sôi động, theo **theme tùy chỉnh** bạn yêu cầu — sử dụng **LLM (Claude)** làm "bộ não producer" kết hợp **kho template genre build sẵn**.

```
MIDI / MusicXML ──▶ Phân tích nhạc lý ──▶ LLM Producer Brain ──▶ Arranger ──▶ MIDI hoàn chỉnh
                    (key, chords,         (đọc brief + chọn      (drums, bass,   (+ WAV nếu có
                     melody, tempo)        template, lập kế        pad, arp,       fluidsynth)
                                           hoạch arrangement)      lead, FX)
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

# Bounce thêm file .wav (cần fluidsynth + GM soundfont)
python -m music_producer remix input.mid -t "synthwave retro" --audio
```

### Python API

```python
from music_producer import produce

analysis, plan, song = produce(
    "input.mid",
    theme="trap 808 thật dark, năng lượng cao",
    output_path="output.mid",
)
print(plan.notes)  # lý do producer chọn cách sản xuất này
```

## Kiến trúc

| Module | Vai trò |
|---|---|
| `midi_io.py` | Đọc MIDI (mido) và MusicXML/MXL cơ bản → `Song` |
| `analysis.py` | Phát hiện key (Krumhansl-Schmuckler), hợp âm theo từng bar, trích xuất melody → `SongAnalysis` |
| `producer_brain.py` | **LLM brain** (Claude `claude-opus-4-8`, structured JSON output) đọc bản phân tích + brief của bạn → `ProductionPlan`. Fallback `RuleBasedBrain` khi offline |
| `template_library.py` + `templates/*.json` | Kho template genre: tempo range, drum grid 16-step theo mức năng lượng, style bassline, nhạc cụ GM, arrangement mặc định |
| `generators.py` | Sinh từng layer: drums (grid), bass (9 styles), pad (voicing + 9th), arp, melody/lead (tile melody gốc), FX riser |
| `arrangement.py` | Lắp các section theo plan: intro → verse → build → drop → breakdown → ... |
| `humanize.py` | Swing, micro-timing, velocity jitter (deterministic) |
| `renderer.py` | Xuất Standard MIDI File; tùy chọn bounce WAV qua FluidSynth |

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

## Giới hạn hiện tại

- Output là MIDI General MIDI — chất lượng âm thanh cuối phụ thuộc soundfont/DAW của bạn; đưa file vào DAW để mix với synth thật là bước tiếp theo tự nhiên.
- Phát hiện hợp âm theo bar (1 hợp âm/bar), đủ tốt cho nhạc pop/điện tử, chưa xử lý đảo phách hòa thanh phức tạp.
- MusicXML hỗ trợ mức cơ bản (notes, chords, time/tempo).
