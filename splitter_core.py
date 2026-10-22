# -*- coding: utf-8 -*-
"""
녹음/영상 파일 분할 핵심 로직 (UI와 분리)

- 최대 max_seg 초 단위로 자른다.
- 각 분할 지점은 [이전 지점 + max_seg - search, 이전 지점 + max_seg] 구간에서
  가장 조용한 순간을 골라 정한다.
- 영상을 그대로 자를 때는 그 구간의 키프레임 중 가장 조용한 곳을 고른다.
- 재압축 없이(스트림 복사) 자르므로 음질/화질 손실이 없고 빠르다.
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

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".wma",
              ".aiff", ".aif", ".amr", ".mka"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".wmv", ".flv",
              ".ts", ".mts", ".m2ts", ".3gp"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS

# 소리만 뽑을 때: 원래 코덱 → 그대로 담을 확장자 (없으면 m4a로 다시 인코딩)
AUDIO_COPY_EXT = {"aac": ".m4a", "alac": ".m4a", "mp3": ".mp3", "flac": ".flac",
                  "opus": ".opus", "vorbis": ".ogg"}

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


def probe(ffmpeg, path):
    """길이, 영상 유무, 오디오 코덱을 알아낸다."""
    r = _run([ffmpeg, "-hide_banner", "-i", path])
    err = r.stderr.decode("utf-8", "ignore")
    info = {"duration": 0.0, "has_video": False, "has_audio": False, "acodec": None}
    for line in err.splitlines():
        m = re.search(r"Stream #\d+:\d+.*?: (Video|Audio): (\w+)", line)
        if not m:
            continue
        if m.group(1) == "Video" and "attached pic" not in line:
            info["has_video"] = True
        elif m.group(1) == "Audio" and not info["has_audio"]:
            info["has_audio"] = True
            info["acodec"] = m.group(2)
    if not info["has_audio"] and not info["has_video"]:
        raise SplitError("오디오나 영상이 들어 있는 파일이 아닙니다.")

    m = re.search(r"Duration:\s*(\d+:\d+:\d+(?:\.\d+)?)", err)
    if m and _hms(m.group(1)) > 0:
        info["duration"] = _hms(m.group(1))
    else:  # 길이 정보가 없는 파일: 끝까지 읽어서 측정
        r = _run([ffmpeg, "-hide_banner", "-i", path, "-f", "null", "-"])
        times = re.findall(r"time=(\d+:\d+:\d+(?:\.\d+)?)", r.stderr.decode("utf-8", "ignore"))
        if not times:
            raise SplitError("파일 길이를 알 수 없습니다.")
        info["duration"] = _hms(times[-1])
    return info


# ---------- 소리 분석 ----------
def window_energy(ffmpeg, path, start, length):
    """구간의 10ms 단위 에너지와 250ms 이동평균을 돌려준다."""
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
    energy = []
    for i in range(n):
        seg = samples[i * fl:(i + 1) * fl]
        energy.append(sum(s * s for s in seg) / fl)
    w = max(1, min(SMOOTH_MS // FRAME_MS, n))
    pref = [0.0]
    for e in energy:
        pref.append(pref[-1] + e)
    smooth = [(pref[i + w] - pref[i]) / w for i in range(max(0, n - w + 1))]
    return energy, smooth, w


def quiet_cut(energy, smooth, w, start, length):
    """가장 조용한 시점 (오디오용)"""
    if len(smooth) < 3:
        return start + length
    best = min(smooth)
    tol = best * 1.05 + 1.0
    idx = max(i for i, v in enumerate(smooth) if v <= tol)   # 비슷하면 최대 길이에 가까운 쪽
    sub = energy[idx: idx + w]
    k = idx + min(range(len(sub)), key=lambda j: (sub[j], -j))
    return min(start + (k + 0.5) * FRAME_MS / 1000.0, start + length)


def keyframes(ffmpeg, path, start, length):
    """구간 안의 영상 키프레임 시각들"""
    r = _run([ffmpeg, "-hide_banner", "-skip_frame", "nokey",
              "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", path,
              "-map", "0:v:0", "-an", "-vf", "showinfo", "-f", "null", "-"])
    ts = re.findall(r"pts_time:\s*(-?[\d.]+)", r.stderr.decode("utf-8", "ignore"))
    return sorted({round(start + float(t), 3) for t in ts
                   if 0.05 < float(t) <= length + 0.001})


def keyframe_cut(energy, smooth, w, start, kfs):
    """키프레임들 중 가장 조용한 곳 (영상용)"""
    if not smooth:
        return kfs[-1]
    scored = []
    for kf in kfs:
        i = int((kf - start) * 1000 / FRAME_MS) - w // 2
        i = max(0, min(len(smooth) - 1, i))
        scored.append((smooth[i], kf))
    best = min(s for s, _ in scored)
    tol = best * 1.05 + 1.0
    return max(kf for s, kf in scored if s <= tol)


# ---------- 전체 처리 ----------
def split_file(path, max_seg=300.0, search=30.0, subfolder=True, audio_only=False,
               ffmpeg=None, log=print, progress=lambda f: None):
    """path 파일을 자른다. (결과 폴더, 조각 수)를 돌려준다. (화면 버전용)"""
    r = split(path, max_seg=max_seg, search=search, subfolder=subfolder,
              audio_only=audio_only, ffmpeg=ffmpeg, log=log, progress=progress)
    return r["output_dir"], r["count"]


def split(path, max_seg=300.0, search=30.0, subfolder=True, audio_only=False,
          out_dir=None, dry_run=False, ffmpeg=None, log=print, progress=lambda f: None):
    """path 파일을 자르고 결과를 dict로 돌려준다.
    max_seg: 조각 최대 길이(초), search: 조용한 곳을 찾는 범위(초)
    audio_only: 영상 파일이면 소리만 뽑아서 자른다.
    out_dir: 결과 폴더를 직접 지정 (없으면 원본 옆, subfolder면 '원본이름_분할')
    dry_run: 분할 지점만 계산하고 파일은 만들지 않는다.
    log(str): 진행 메시지, progress(0~1): 이 파일의 진행률"""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise SplitError("ffmpeg를 찾을 수 없습니다.")
    search = max(0.0, min(search, max_seg - 1))

    path = os.path.abspath(path)
    folder, name = os.path.split(path)
    base, ext = os.path.splitext(name)

    info = probe(ffmpeg, path)
    duration = info["duration"]
    keep_video = info["has_video"] and not audio_only
    if not keep_video and not info["has_audio"]:
        raise SplitError("소리가 없는 영상입니다.")

    # 출력 방식 정하기
    reencode_audio = False
    if keep_video:
        maps = ["-map", "0:v:0", "-map", "0:a?"]
        out_ext = ext
        kind, mode = "영상", "video"
    elif info["has_video"]:            # 영상에서 소리만
        maps = ["-map", "0:a:0"]
        out_ext = AUDIO_COPY_EXT.get(info["acodec"])
        if not out_ext:
            out_ext, reencode_audio = ".m4a", True
        kind, mode = "소리만", "audio_only"
    else:                              # 원래 오디오 파일
        maps = ["-map", "0:a:0"]
        out_ext = ext
        kind, mode = "오디오", "audio"
    log(f"전체 길이 {fmt(duration)} · {kind}")

    expected = max(1, int(duration // max_seg))
    cuts, pos = [], 0.0
    while duration - pos > max_seg:
        ws = pos + max_seg - search
        if keep_video:
            kfs = keyframes(ffmpeg, path, ws, search) if search > 0 else []
            if not kfs:  # 범위 안에 키프레임이 없으면 범위를 넓혀서 마지막 키프레임
                kfs = keyframes(ffmpeg, path, pos + 1, max_seg - 1)
            if kfs:
                if info["has_audio"] and search > 0 and kfs[0] >= ws:
                    e, s, w = window_energy(ffmpeg, path, ws, search)
                    cut = keyframe_cut(e, s, w, ws, kfs)
                else:
                    cut = kfs[-1]
            else:
                cut = pos + max_seg
                log("  (이 구간엔 자를 수 있는 키프레임이 없어 조금 길어질 수 있어요)")
        elif search > 0:
            e, s, w = window_energy(ffmpeg, path, ws, search)
            cut = quiet_cut(e, s, w, ws, search)
        else:
            cut = pos + max_seg
        if cut <= pos + 0.5 or duration - cut < MIN_LAST:
            break
        cuts.append(cut)
        log(f"  {len(cuts):>2}번째 분할 지점 {fmt(cut)}  (조각 {fmt(cut - pos)})")
        pos = cut
        progress(min(0.8, 0.8 * len(cuts) / expected))

    count = len(cuts) + 1
    digits = max(2, len(str(count)))
    if out_dir:
        out_dir = os.path.abspath(out_dir)
    else:
        out_dir = os.path.join(folder, f"{base}_분할") if subfolder else folder
    bounds = [0.0] + cuts + [duration]
    result = {
        "input": path, "duration": round(duration, 3), "mode": mode,
        "output_dir": out_dir, "count": count, "dry_run": bool(dry_run),
        "pieces": [{
            "index": i + 1,
            "path": os.path.join(out_dir, f"{base}_{i + 1:0{digits}d}{out_ext}"),
            "start": round(bounds[i], 3), "end": round(bounds[i + 1], 3),
            "duration": round(bounds[i + 1] - bounds[i], 3),
        } for i in range(count)],
    }
    if dry_run:
        log(f"미리보기: {count}개 조각 (파일은 만들지 않음)")
        progress(1.0)
        return result
    os.makedirs(out_dir, exist_ok=True)

    # 같은 이름의 예전 조각 정리 (새 결과와 섞이지 않게)
    pat = re.compile(re.escape(base) + r"_\d{2,}" + re.escape(out_ext) + r"$")
    for f in os.listdir(out_dir):
        if pat.match(f) and os.path.join(out_dir, f) != path:
            os.remove(os.path.join(out_dir, f))

    log(f"{count}개로 자르는 중...")
    esc = lambda s: s.replace("%", "%%")
    pattern = os.path.join(esc(out_dir), esc(base) + f"_%0{digits}d" + esc(out_ext))
    common = [ffmpeg, "-hide_banner", "-v", "error", "-y", "-i", path] + maps + \
             ["-map_metadata", "0", "-sn", "-dn"]
    seg = ["-f", "segment", "-segment_start_number", "1", "-reset_timestamps", "1"]
    # 키프레임 시각에서 정확히 끊기도록 아주 조금 앞당겨 전달
    seg += (["-segment_times", ",".join(f"{max(0.001, c - 0.002):.3f}" for c in cuts)] if cuts
            else ["-segment_time", "999999"])

    if reencode_audio:
        codec = ["-c:a", "aac", "-b:a", "192k"]
    else:
        codec = ["-c", "copy"]
    r = _run(common + codec + seg + [pattern])
    if r.returncode != 0 and not reencode_audio:
        log("이 형식은 그대로 복사가 안 돼서 다시 인코딩합니다. 조금 더 걸려요.")
        r = _run(common + seg + [pattern])
    if r.returncode != 0:
        raise SplitError(r.stderr.decode("utf-8", "ignore").strip()[-300:])
    progress(1.0)
    log(f"완료: {count}개 파일")
    return result


def fmt(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m:02d}:{s:04.1f}"
