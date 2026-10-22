---
name: ssakduk
description: Split long audio or video recordings into pieces no longer than a maximum length, cutting at the quietest moment so speech isn't chopped mid-word. Lossless (no re-encoding) and fast. Use when a recording must be split into chunks — e.g. before sending to a speech-to-text or AI service with a length/size limit, or to share a long lecture/meeting in parts. 녹음·영상 파일을 조용한 지점에서 N분 이하로 자를 때 사용.
---

# ssakduk (싹둑) — split recordings at quiet points

`ssakduk` cuts audio/video files into pieces of **at most `--max` minutes**.
Each cut is placed at the quietest moment inside the last `--search` seconds
before the limit (default: between 4:30 and 5:00), so words are not cut in half.
Streams are copied, not re-encoded: no quality loss, and an 80-minute 130 MB
m4a splits in about 8 seconds.

## Install

Requires **ffmpeg** on PATH (or pass `--ffmpeg PATH`) and Python 3.8+.

```bash
pip install "git+https://github.com/iamandykim9/ssakduk"
# or without installing:
uvx --from "git+https://github.com/iamandykim9/ssakduk" ssakduk --help
```

ffmpeg: `winget install Gyan.FFmpeg` (Windows) · `brew install ffmpeg` (macOS) · `sudo apt install ffmpeg` (Debian/Ubuntu).

Windows without Python: download `ssakduk-cli.exe` from
https://github.com/iamandykim9/ssakduk/releases/latest — ffmpeg is bundled, use it exactly like `ssakduk`.

## Usage

```bash
ssakduk FILE_OR_DIR... [--max MIN] [--search SEC] [--audio-only]
        [--out DIR] [--no-subfolder] [--dry-run] [--json] [-q] [--ffmpeg PATH]
```

| Option | Meaning | Default |
|---|---|---|
| `--max MIN` | Maximum piece length in minutes (decimals OK: `0.5` = 30 s) | `5` |
| `--search SEC` | Look for the quietest point in the last SEC seconds before the limit. `0` = cut exactly every `--max` | `30` |
| `--audio-only` | For video input, extract and split only the audio (aac→.m4a, mp3→.mp3, opus→.opus, other→re-encoded .m4a) | off |
| `--out DIR` | Write pieces to DIR | `<input dir>/<name>_분할/` |
| `--no-subfolder` | Write pieces next to the input instead of `<name>_분할/` | off |
| `--dry-run` | Compute cut points only, write nothing | off |
| `--json` | Print a JSON result to stdout; progress goes to stderr | off |
| `-q` | Hide progress messages | off |

A directory argument processes every audio/video file directly inside it.
Output names are `<name>_01.<ext>`, `<name>_02.<ext>`, … (zero-padded, at least 2 digits).
Re-running on the same input replaces earlier pieces of that input in the output folder.

Supported: m4a mp3 wav flac aac ogg opus wma aiff amr mka mp4 mov m4v mkv webm avi wmv flv ts mts m2ts 3gp.

## Recommended agent workflow

1. Run with `--json -q` and parse stdout.
2. Check `ok`; read pieces from `results[].pieces[].path` in order.
3. To plan before writing files (e.g. to tell the user how many pieces there will be), use `--dry-run --json`.

```bash
ssakduk meeting.m4a --max 10 --out chunks --json -q
```

```json
{
  "ok": true,
  "results": [{
    "input": "/abs/meeting.m4a", "duration": 4800.0, "mode": "audio",
    "output_dir": "/abs/chunks", "count": 9, "dry_run": false,
    "pieces": [
      {"index": 1, "path": "/abs/chunks/meeting_01.m4a", "start": 0.0, "end": 594.1, "duration": 594.1}
    ]
  }],
  "errors": []
}
```

`mode` is `audio`, `video` (video kept), or `audio_only`. `start`/`end` are seconds in the
original file (planned cut points; actual boundaries may differ by a few milliseconds).
On failure `errors[]` holds `{"input", "error"}`.

Exit codes: `0` all succeeded · `1` at least one file failed · `2` bad arguments or ffmpeg not found.

## Behaviour to know

- Pieces never exceed `--max`, except video where no keyframe exists in the window (rare); the cut then falls on the next keyframe.
- When keeping video, cuts can only land on keyframes (usually every 1–2 s), so the cut is the quietest keyframe in the window.
- Total duration and size of the pieces equal the original (stream copy).
- Cutting for speech-to-text: a common choice is `--max` just under the service's limit, e.g. `--max 9.5` for a 10-minute limit. For a file-size limit, pick `--max` from the bitrate: minutes ≈ limit_MB × 8 / (kbps × 0.06).
- Everything runs locally; nothing is uploaded.

No-install alternative for humans: https://iamandykim9.github.io/ssakduk/ (runs in the browser, results as zip).
