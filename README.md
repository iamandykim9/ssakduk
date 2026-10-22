# 싹둑 | 무료 녹음·영상 자동 분할

긴 녹음 파일과 영상을 원하는 길이로, **말이 끊기지 않는 조용한 지점에서** 자동으로 잘라 줍니다.

**완전 무료 · 광고 없음 · 회원가입 없음 · 파일이 서버로 올라가지 않음**

- 🌐 **온라인 버전**: https://iamandykim9.github.io/ssakduk/ — 설치 없이 브라우저에서 바로
- 💾 **오프라인 버전 (Windows)**: [Ssakduk-Windows.zip 받기](https://github.com/iamandykim9/ssakduk/releases/latest/download/Ssakduk-Windows.zip) — 인터넷 없이, 큰 파일도

## 이렇게 잘라요

- 최대 길이(기본 5분)를 넘지 않게 자르되, 그 직전 범위(기본 30초) 안에서 **가장 조용한 순간**을 골라 자릅니다.
- **다시 압축하지 않아서** 음질·화질 손실이 없고 빠릅니다. 1시간 20분짜리 녹음(130MB)이 10초 안팎.
- 영상은 **영상 그대로** 자르거나, **소리만 뽑아서** 자를 수 있어요.
- 결과: `회의.m4a` → `회의_01.m4a`, `회의_02.m4a` … (온라인 버전은 zip으로)
- 지원 형식: m4a, mp3, wav, flac, aac, ogg, opus, wma, mp4, mov, mkv, webm, avi 등

## 구조

| 경로 | 내용 |
|---|---|
| `splitter_core.py` | 분할 알고리즘 (오프라인 버전) |
| `app.py` | 오프라인 버전 화면 (tkinter) |
| `web/` | 온라인 버전 (ffmpeg.wasm, 브라우저 안에서 처리) |
| `.github/workflows/build.yml` | 테스트 후 Windows exe를 zip으로 묶어 Releases에 올림 |
| `.github/workflows/pages.yml` | 온라인 버전을 GitHub Pages에 배포 |

`main` 브랜치에 올리면 위 두 작업이 자동으로 실행됩니다. 서버비는 들지 않습니다.

## 라이선스

GPL-3.0. 파일 처리에 [FFmpeg](https://ffmpeg.org)(GPL)와 [ffmpeg.wasm](https://github.com/ffmpegwasm/ffmpeg.wasm)을 사용합니다.
