# -*- coding: utf-8 -*-
"""싹둑 명령어 버전 — 녹음·영상을 조용한 지점에서 최대 길이 이하로 자른다.

예)
  ssakduk 회의.m4a                       # 5분 이하, 4:30~5:00 중 가장 조용한 곳에서
  ssakduk 강의.mp4 --max 10 --audio-only # 영상에서 소리만 뽑아 10분 이하로
  ssakduk 녹음폴더/ --out 결과/ --json   # 폴더 통째로, 결과를 JSON으로
  ssakduk 회의.m4a --dry-run --json      # 파일은 만들지 않고 분할 지점만 확인
"""

import argparse
import json
import os
import sys

import splitter_core as core

__version__ = "1.1.0"


def collect(inputs):
    files, missing = [], []
    for p in inputs:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in sorted(os.listdir(p))
                      if os.path.splitext(f)[1].lower() in core.MEDIA_EXTS]
        elif os.path.isfile(p):
            files.append(p)
        else:
            missing.append(p)
    return files, missing


def build_parser():
    ap = argparse.ArgumentParser(
        prog="ssakduk",
        description="녹음·영상 파일을 조용한 지점에서 최대 길이 이하로 무손실 분할합니다.",
        epilog="결과 파일 이름: 원본이름_01.확장자, 원본이름_02.확장자 ... "
               "기본 저장 위치: 원본 옆 '원본이름_분할' 폴더",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", metavar="파일또는폴더",
                    help="자를 파일들. 폴더를 주면 안의 녹음·영상 파일을 모두 자름")
    ap.add_argument("--max", type=float, default=5.0, metavar="분",
                    help="조각 최대 길이(분). 기본 5. 소수 가능 (예: 0.5 = 30초)")
    ap.add_argument("--search", type=float, default=30.0, metavar="초",
                    help="최대 길이 직전 이 범위 안에서 가장 조용한 곳을 찾음(초). "
                         "기본 30. 0이면 정확히 최대 길이마다 자름")
    ap.add_argument("--audio-only", action="store_true",
                    help="영상 파일이면 소리만 뽑아서 자름 (aac→m4a, mp3→mp3 등)")
    ap.add_argument("--out", metavar="폴더",
                    help="결과를 이 폴더에 저장 (기본: 원본 옆 '원본이름_분할')")
    ap.add_argument("--no-subfolder", action="store_true",
                    help="'원본이름_분할' 폴더를 만들지 않고 원본과 같은 폴더에 저장")
    ap.add_argument("--dry-run", action="store_true",
                    help="파일을 만들지 않고 분할 지점만 계산")
    ap.add_argument("--json", action="store_true",
                    help="결과를 JSON으로 표준출력에 출력 (진행 메시지는 표준에러로)")
    ap.add_argument("--quiet", "-q", action="store_true", help="진행 메시지 숨김")
    ap.add_argument("--ffmpeg", metavar="경로", help="사용할 ffmpeg 실행 파일 경로")
    ap.add_argument("--version", action="version", version=f"ssakduk {__version__}")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)

    if args.max <= 0:
        print("오류: --max 는 0보다 커야 합니다.", file=sys.stderr)
        return 2
    max_seg = args.max * 60
    if max_seg < 2:
        print("오류: --max 가 너무 짧습니다 (2초 이상).", file=sys.stderr)
        return 2

    ffmpeg = args.ffmpeg or core.find_ffmpeg()
    if not ffmpeg:
        print("오류: ffmpeg를 찾을 수 없습니다. ffmpeg를 설치하거나 --ffmpeg 로 경로를 지정하세요.\n"
              "  Windows: winget install Gyan.FFmpeg   macOS: brew install ffmpeg   "
              "Ubuntu: sudo apt install ffmpeg", file=sys.stderr)
        return 2

    files, missing = collect(args.inputs)
    out_stream = sys.stderr if args.json else sys.stdout

    def log(msg):
        if not args.quiet:
            print(msg, file=out_stream, flush=True)

    results, errors = [], []
    for p in missing:
        errors.append({"input": os.path.abspath(p), "error": "파일이나 폴더가 없습니다."})
        log(f"✖ 없음: {p}")
    if not files and not missing:
        errors.append({"input": None, "error": "자를 녹음·영상 파일이 없습니다."})
        log("✖ 자를 녹음·영상 파일이 없습니다.")

    for f in files:
        log(f"▶ {f}")
        try:
            r = core.split(f, max_seg=max_seg, search=args.search,
                           subfolder=not args.no_subfolder, audio_only=args.audio_only,
                           out_dir=args.out, dry_run=args.dry_run, ffmpeg=ffmpeg,
                           log=lambda s: log("   " + s))
            results.append(r)
            if not args.json and not args.quiet:
                log(f"   → {r['output_dir']}")
        except Exception as e:
            errors.append({"input": os.path.abspath(f), "error": str(e)})
            log(f"   ✖ 실패: {e}")

    if args.json:
        print(json.dumps({"ok": not errors, "results": results, "errors": errors},
                         ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
