# -*- coding: utf-8 -*-
"""
녹음 파일 분할 핵심 로직 (UI와 분리)

- 최대 max_seg 초 단위로 자른다.
- 각 분할 지점은 [이전 지점 + max_seg - search, 이전 지점 + max_seg] 구간에서
  가장 조용한 순간을 골라 정한다.
- 재압축 없이(스트림 복사) 자르므로 음질 손실이 없고 빠르다.
"""

import array
import os
import re
import shutil
import subprocess
import sys

ANALYSIS_RATE = 8000   # 소리 분석용 샘플레이트 (결과 파일에는 영향 없음)
FRAME_MS = 10          # 음량 측정 단위(ms)
SMOOTH_MS = 250        # 이 길이만큼 계속 조용한 곳을 우선 → '말 사이 쉬는 틈'을 찾음
MIN_LAST = 1.0         # 마지막 조각이 이보다 짧으면 앞 조각에 붙임(초)

AUDIO_EXTS = {
    ".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".wma",
    ".aiff", ".aif", ".amr", ".3gp", ".mp4", ".webm", ".mkv", ".mka",
}

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class SplitError(Exception):
    pass


# ---------- ffmpeg ----------
def find_ffmpeg():
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(getattr(sys, "_MEIPASS", ""))           # exe 안에 묶인 ffmpeg
        dirs.append(os.path.dirname(sys.executable))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for d in dirs:
        p = os.path.join(d, exe)
        if d and os.path.isfile(p):
            return p
    return shutil.which("ffmpeg")


def _run(cmd):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)


def _hms(s):
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def get_duration(ffmpeg, path):
    r = _run([ffmpeg, "-hide_banner", "-i", path])
    err = r.stderr.decode("utf-8", "ignore")
    m = re.search(r"Duration:\s*(\d+:\d+:\d+(?:\.\d+)?)", err)
    if m and _hms(m.group(1)) > 0:
        return _hms(m.group(1))
    if "Audio:" not in err:
        raise SplitError("오디오가 들어 있는 파일이 아닙니다.")
    # 길이 정보가 없는 파일: 끝까지 읽어서 측정
    r = _run([ffmpeg, "-hide_banner", "-i", path, "-map", "0:a:0", "-f", "null", "-"])
    times = re.findall(r"time=(\d+:\d+:\d+(?:\.\d+)?)", r.stderr.decode("utf-8", "ignore"))
    if not times:
        raise SplitError("파일 길이를 알 수 없습니다.")
    return _hms(times[-1])


# ---------- 가장 조용한 지점 ----------
def quietest_point(ffmpeg, path, start, length):
    r = _run([ffmpeg, "-hide_banner", "-v", "error",
              "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", path,
              "-map", "0:a:0", "-ac", "1", "-ar", str(ANALYSIS_RATE),
              "-f", "s16le", "-acodec", "pcm_s16le", "-"])
    samples = array.array("h")
    samples.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()

    fl = ANALYSIS_RATE * FRAME_MS // 1000
    n = len(samples) // fl
    if n < 3:
        return start + length

    energy = []
    for i in range(n):
        seg = samples[i * fl:(i + 1) * fl]
        energy.append(sum(s * s for s in seg) / fl)

    w = max(1, min(SMOOTH_MS // FRAME_MS, n))
    pref = [0.0]
    for e in energy:
        pref.append(pref[-1] + e)
    smooth = [(pref[i + w] - pref[i]) / w for i in range(n - w + 1)]

    best = min(smooth)
    tol = best * 1.05 + 1.0
    idx = max(i for i, v in enumerate(smooth) if v <= tol)   # 비슷하면 5분에 가까운 쪽

    sub = energy[idx: idx + w]
    k = idx + min(range(len(sub)), key=lambda j: (sub[j], -j))
    return min(start + (k + 0.5) * FRAME_MS / 1000.0, start + length)


# ---------- 전체 처리 ----------
def split_file(path, max_seg=300.0, search=30.0, subfolder=True,
               ffmpeg=None, log=print, progress=lambda f: None):
    """path 파일을 자른다. 결과 폴더 경로를 돌려준다.
    log(str): 진행 메시지, progress(0~1): 이 파일의 진행률"""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise SplitError("ffmpeg를 찾을 수 없습니다.")
    search = max(0.0, min(search, max_seg - 1))

    path = os.path.abspath(path)
    folder, name = os.path.split(path)
    base, ext = os.path.splitext(name)

    duration = get_duration(ffmpeg, path)
    log(f"전체 길이 {fmt(duration)}")
    expected = max(1, int(duration // max_seg))

    cuts, pos = [], 0.0
    while duration - pos > max_seg:
        if search > 0:
            cut = quietest_point(ffmpeg, path, pos + max_seg - search, search)
        else:
            cut = pos + max_seg
        if duration - cut < MIN_LAST:
            break
        cuts.append(cut)
        log(f"  {len(cuts):>2}번째 분할 지점 {fmt(cut)}  (조각 {fmt(cut - pos)})")
        pos = cut
        progress(min(0.8, 0.8 * len(cuts) / expected))

    count = len(cuts) + 1
    digits = max(2, len(str(count)))
    out_dir = os.path.join(folder, f"{base}_분할") if subfolder else folder
    os.makedirs(out_dir, exist_ok=True)

    # 같은 이름의 예전 조각 정리 (새 결과와 섞이지 않게)
    pat = re.compile(re.escape(base) + r"_\d{2,}" + re.escape(ext) + r"$")
    for f in os.listdir(out_dir):
        if pat.match(f) and os.path.join(out_dir, f) != path:
            os.remove(os.path.join(out_dir, f))

    log(f"{count}개로 자르는 중...")
    esc = lambda s: s.replace("%", "%%")
    pattern = os.path.join(esc(out_dir), esc(base) + f"_%0{digits}d" + esc(ext))
    common = [ffmpeg, "-hide_banner", "-v", "error", "-y", "-i", path,
              "-map", "0:a:0", "-map_metadata", "0"]
    seg = ["-f", "segment", "-segment_start_number", "1", "-reset_timestamps", "1"]
    seg += (["-segment_times", ",".join(f"{c:.3f}" for c in cuts)] if cuts
            else ["-segment_time", "999999"])

    r = _run(common + ["-c", "copy"] + seg + [pattern])
    if r.returncode != 0:
        log("이 형식은 그대로 복사가 안 돼서 다시 인코딩합니다.")
        r = _run(common + seg + [pattern])
        if r.returncode != 0:
            raise SplitError(r.stderr.decode("utf-8", "ignore").strip()[-300:])
    progress(1.0)
    log(f"완료: {count}개 파일")
    return out_dir


def fmt(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m:02d}:{s:04.1f}"
