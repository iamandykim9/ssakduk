# 싹둑 | 무료 녹음·영상 자동 분할

긴 녹음 파일과 영상을 원하는 길이로, **말이 끊기지 않는 조용한 지점에서** 자동으로 잘라 줍니다.

**완전 무료 · 광고 없음 · 회원가입 없음 · 파일이 서버로 올라가지 않음**

- 🌐 **온라인 버전**: https://iamandykim9.github.io/ssakduk/ — 설치 없이 브라우저에서 바로
- 💾 **오프라인 버전 (Windows)**: [Ssakduk-Windows.zip 받기](https://github.com/iamandykim9/ssakduk/releases/latest/download/Ssakduk-Windows.zip) — 인터넷 없이, 큰 파일도
- 🤖 **명령어 · AI 도구용**: `pip install "git+https://github.com/iamandykim9/ssakduk"` → `ssakduk 파일 --max 5` ([설명서](skills/ssakduk/SKILL.md))

## 이렇게 잘라요

- 최대 길이(기본 5분)를 넘지 않게 자르되, 그 직전 범위(기본 30초) 안에서 **가장 조용한 순간**을 골라 자릅니다.
- **다시 압축하지 않아서** 음질·화질 손실이 없고 빠릅니다. 1시간 20분짜리 녹음(130MB)이 10초 안팎.
- 영상은 **영상 그대로** 자르거나, **소리만 뽑아서** 자를 수 있어요.
- 결과: `회의.m4a` → `회의_01.m4a`, `회의_02.m4a` … (온라인 버전은 zip으로)
- 지원 형식: m4a, mp3, wav, flac, aac, ogg, opus, wma, mp4, mov, mkv, webm, avi 등

## 명령어로 쓰기

ffmpeg가 설치된 PC에서 (Windows·Mac·Linux):

```bash
pip install "git+https://github.com/iamandykim9/ssakduk"
ssakduk 회의.m4a                        # 5분 이하, 조용한 지점에서
ssakduk 강의.mp4 --max 10 --audio-only  # 영상에서 소리만 뽑아 10분 이하로
ssakduk 녹음폴더/ --out 결과/ --json     # 폴더 통째로, 결과를 JSON으로
ssakduk 회의.m4a --dry-run              # 파일은 안 만들고 분할 지점만 확인
```

Python 없는 Windows에서는 [Releases](https://github.com/iamandykim9/ssakduk/releases/latest)의 `ssakduk-cli.exe`를 같은 방식으로 쓰면 됩니다(ffmpeg 포함).

**AI 도구(Claude Code, Codex, Gemini CLI 등)** 에서는 "싹둑으로 이 녹음 5분씩 잘라줘"라고 하면 됩니다. 도구가 읽을 설명서는 [`skills/ssakduk/SKILL.md`](skills/ssakduk/SKILL.md)에 있고, `--json` 결과로 조각 파일 경로와 시간을 정확히 받아갈 수 있어요. Claude Code에서는 이 폴더를 `~/.claude/skills/ssakduk/`에 복사하면 스킬로 바로 인식됩니다.

## 구조

| 경로 | 내용 |
|---|---|
| `splitter_core.py` | 분할 알고리즘 (화면·명령어 버전 공용) |
| `ssakduk_cli.py` | 명령어 버전 (`ssakduk`) |
| `app.py` | 오프라인 버전 화면 (tkinter) |
| `web/` | 온라인 버전 (ffmpeg.wasm, 브라우저 안에서 처리) |
| `skills/ssakduk/SKILL.md` | AI 도구용 사용 설명서 |
| `.github/workflows/build.yml` | 테스트 후 Windows zip과 `ssakduk-cli.exe`를 Releases에 올림 |
| `.github/workflows/pages.yml` | 온라인 버전을 GitHub Pages에 배포 |

`main` 브랜치에 올리면 위 두 작업이 자동으로 실행됩니다. 서버비는 들지 않습니다.

## 라이선스

GPL-3.0. 파일 처리에 [FFmpeg](https://ffmpeg.org)(GPL)와 [ffmpeg.wasm](https://github.com/ffmpegwasm/ffmpeg.wasm)을 사용합니다.
