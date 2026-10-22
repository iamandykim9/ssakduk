# AGENTS.md — guide for AI coding agents

## Using ssakduk to split a recording

If you were asked to split an audio/video file, read `skills/ssakduk/SKILL.md`.
Short version:

```bash
pip install "git+https://github.com/iamandykim9/ssakduk"   # needs ffmpeg on PATH
ssakduk input.m4a --max 5 --json -q                        # pieces ≤ 5 min, cut at quiet points
```

## Working on this repository

| Path | What it is |
|---|---|
| `splitter_core.py` | Splitting algorithm (shared by GUI and CLI). `split()` returns a result dict. |
| `ssakduk_cli.py` | Command-line entry point (`ssakduk`). |
| `app.py` | Windows desktop GUI (tkinter + tkinterdnd2). |
| `web/` | Browser version (ffmpeg.wasm). `web/app.js` mirrors the algorithm in `splitter_core.py`; keep them in sync. |
| `skills/ssakduk/SKILL.md` | Instructions for agents using the CLI. |
| `.github/workflows/build.yml` | Tests, builds the Windows zip and `ssakduk-cli.exe`, publishes the `latest` release. |
| `.github/workflows/pages.yml` | Deploys `web/` to GitHub Pages. |

Test locally (needs ffmpeg):

```bash
pip install -e .
ssakduk some_recording.m4a --dry-run --json
```

The user-facing language is Korean. Keep the product free, ad-free, signup-free,
and serverless (all processing on the user's machine).
