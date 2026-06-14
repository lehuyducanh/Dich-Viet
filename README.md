# music2midi

CLI tool ba-trong-một cho âm nhạc:

1. **Transcribe** — dịch file nhạc (mp3/wav) thành file MIDI đa nhạc cụ (Demucs tách stem + Basic Pitch nhận diện nốt).
2. **Visualize** — render MIDI thành video piano "nốt rơi" kiểu Synthesia (bàn phím 88 phím, mỗi nhạc cụ một màu, phím sáng khi nốt chạm).
3. **Generate** — mô tả bài nhạc bằng lời (tiếng Việt hoặc tiếng Anh), Claude sinh bản nhạc mới thành MIDI.

## Cài đặt

```bash
# Core (generate + visualize)
pip install -e .

# Thêm khả năng transcribe (nặng — cài torch CPU trước để tránh kéo bản CUDA ~2GB)
pip install torch torchaudio torchcodec --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[transcribe]"
```

Lưu ý:
- `torchcodec` cần thư viện FFmpeg hệ thống (`apt-get install ffmpeg`).
- Nếu pip báo lỗi `install_layout` khi build sdist (setuptools bản Debian), thêm cờ `--use-pep517`.
- Lần chạy transcribe đầu tiên sẽ tải checkpoint htdemucs (~80 MB) về `~/.cache`.

```bash
```

Yêu cầu Python >= 3.10 và < 3.12 (giới hạn của basic-pitch).

### System dependencies (tùy chọn nhưng nên có)

- **ffmpeg** — nếu không có, tool tự dùng binary đóng gói sẵn từ `imageio-ffmpeg`.
- **fluidsynth + soundfont GM** — để video có tiếng. Nếu thiếu, video render câm kèm cảnh báo.

```bash
sudo apt-get install ffmpeg fluidsynth fluid-soundfont-gm
```

### API key (cho lệnh generate)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Sử dụng

```bash
# Dịch nhạc thành MIDI đa nhạc cụ
music2midi transcribe song.mp3 -o song.mid

# Render video piano visual
music2midi visualize song.mid -o song.mp4

# Dịch + render một bước
music2midi pipeline song.mp3 -o song.mp4

# Sinh bài hát mới bằng Claude
music2midi generate "nhạc bolero buồn, piano và guitar, 80 bpm" -o song.mid --render-video

# Sinh theo phong cách định sẵn (24 preset: dân ca Nga, nhạc cổ Trung Quốc,
# EDM, lo-fi, epic cinematic, lãng mạn cổ điển, jazz, flamenco, ...)
music2midi styles                         # liệt kê tất cả phong cách
music2midi generate "một giai điệu buồn" --style chinese_classical -o song.mid --render-video
# Phong cách cũng được tự nhận từ mô tả: "nhạc dân ca Nga vui" -> russian_folk

# Bài demo built-in để thử nhanh
music2midi demo -o demo.mid
music2midi visualize demo.mid -o demo.mp4
```

Chạy `music2midi --help` hoặc `music2midi <lệnh> --help` để xem đầy đủ tùy chọn.
