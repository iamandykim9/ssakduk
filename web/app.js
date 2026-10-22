// 싹둑 온라인 버전 — 모든 처리는 브라우저 안(ffmpeg.wasm)에서 이루어지고 파일은 어디에도 올라가지 않는다.
import { FFmpeg, FFFSType } from "./vendor/ffmpeg/index.js";
import { Zip, ZipPassThrough } from "./vendor/fflate.js";

// ===== 분할 설정 (오프라인 버전 splitter_core.py 와 같은 알고리즘) =====
const ANALYSIS_RATE = 8000;
const FRAME_MS = 10;
const SMOOTH_MS = 250;
const MIN_LAST = 1.0;
const BIG_FILE = 1.2 * 1024 ** 3;

const AUDIO_COPY_EXT = { aac: ".m4a", alac: ".m4a", mp3: ".mp3", flac: ".flac", opus: ".opus", vorbis: ".ogg" };

const $ = (id) => document.getElementById(id);
const els = {
  drop: $("drop"), pick: $("pick"), list: $("list"), start: $("start"), clear: $("clear"),
  maxMin: $("maxMin"), searchSec: $("searchSec"), hint: $("hint"), engine: $("engine"),
};
const jobs = [];   // {file, el, state, pieces, zipName}
let busy = false;
let ffmpeg = null;
let logBuf = [];
let onProgress = null;

// ---------- 설정 기억 ----------
function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem("ssakduk") || "{}");
    if (s.maxMin) els.maxMin.value = s.maxMin;
    if (s.searchSec !== undefined) els.searchSec.value = s.searchSec;
    if (s.vmode) document.querySelector(`input[name=vmode][value=${s.vmode}]`).checked = true;
  } catch { /* 저장소를 못 쓰는 환경이면 기본값 */ }
}
function saveSettings() {
  try {
    localStorage.setItem("ssakduk", JSON.stringify({
      maxMin: els.maxMin.value, searchSec: els.searchSec.value, vmode: vmode(),
    }));
  } catch { /* 무시 */ }
}
const vmode = () => document.querySelector("input[name=vmode]:checked").value;

function updateHint() {
  const m = Number(els.maxMin.value) || 5;
  const s = Math.min(Number(els.searchSec.value) || 0, m * 60 - 1);
  els.hint.textContent = s > 0
    ? `각 조각은 ${fmtLong(m * 60 - s)} ~ ${fmtLong(m * 60)} 사이에서 가장 조용한 지점에서 잘려요.`
    : `정확히 ${fmtLong(m * 60)}마다 잘라요.`;
  saveSettings();
}

// ---------- 파일 목록 ----------
function addFiles(files) {
  if (busy) return;
  for (const file of files) {
    if (jobs.some((j) => j.file.name === file.name && j.file.size === file.size)) continue;
    const el = document.createElement("li");
    el.className = "item";
    el.innerHTML = `
      <div class="item-head"><span class="item-name"></span><span class="item-meta"></span></div>
      <div class="item-status">대기 중</div>
      <div class="bar" hidden><i></i></div>
      <div class="result"></div>`;
    el.querySelector(".item-name").textContent = file.name;
    el.querySelector(".item-meta").textContent = fmtSize(file.size);
    const job = { file, el, state: "wait", pieces: [] };
    if (file.size > BIG_FILE) {
      setStatus(job, "큰 파일이라 브라우저에서는 실패할 수 있어요. 안 되면 아래 오프라인 버전을 써 주세요.", "warn");
    }
    jobs.push(job);
    els.list.append(el);
  }
  refreshButtons();
}

function refreshButtons() {
  els.start.disabled = busy || !jobs.some((j) => j.state === "wait" || j.state === "fail");
  els.clear.disabled = busy;
}

function setStatus(job, text, kind = "") {
  const s = job.el.querySelector(".item-status");
  s.textContent = text;
  s.className = "item-status" + (kind ? " " + kind : "");
}
function setBar(job, f) {
  const bar = job.el.querySelector(".bar");
  bar.hidden = false;
  bar.firstElementChild.style.width = `${Math.round(Math.max(0, Math.min(1, f)) * 100)}%`;
}

// ---------- ffmpeg ----------
async function getFFmpeg() {
  if (ffmpeg) return ffmpeg;
  els.engine.textContent = "처리 엔진 준비 중… (처음 한 번 약 31MB, 다음부터는 바로 시작)";
  const f = new FFmpeg();
  f.on("log", ({ message }) => logBuf.push(message));
  f.on("progress", ({ progress }) => onProgress && onProgress(progress));
  const base = new URL("vendor/core/", location.href).href;
  await f.load({ coreURL: base + "ffmpeg-core.js", wasmURL: base + "ffmpeg-core.wasm" });
  await f.createDir("/in");
  await f.createDir("/out");
  els.engine.textContent = "";
  ffmpeg = f;
  return f;
}

async function run(args) {
  // 로그 수준은 엔진 안에서 이전 실행 값이 남으므로 매번 명시한다
  if (!args.includes("-v")) args = ["-v", "info", ...args];
  logBuf = [];
  const code = await ffmpeg.exec(args);
  return { code, log: logBuf.join("\n") };
}

const hms = (s) => { const [h, m, x] = s.split(":"); return +h * 3600 + +m * 60 + parseFloat(x); };

async function probe(input) {
  const { log } = await run(["-hide_banner", "-i", input]);
  const info = { duration: 0, hasVideo: false, hasAudio: false, acodec: null };
  for (const line of log.split("\n")) {
    const m = line.match(/Stream #\d+:\d+.*?: (Video|Audio): (\w+)/);
    if (!m) continue;
    if (m[1] === "Video" && !line.includes("attached pic")) info.hasVideo = true;
    else if (m[1] === "Audio" && !info.hasAudio) { info.hasAudio = true; info.acodec = m[2]; }
  }
  if (!info.hasAudio && !info.hasVideo) throw new Error("오디오나 영상이 들어 있는 파일이 아니에요.");
  const d = log.match(/Duration:\s*(\d+:\d+:\d+(?:\.\d+)?)/);
  if (d && hms(d[1]) > 0) info.duration = hms(d[1]);
  else {
    const r = await run(["-hide_banner", "-i", input, "-f", "null", "-"]);
    const t = [...r.log.matchAll(/time=(\d+:\d+:\d+(?:\.\d+)?)/g)];
    if (!t.length) throw new Error("파일 길이를 알 수 없어요.");
    info.duration = hms(t[t.length - 1][1]);
  }
  return info;
}

async function windowEnergy(input, start, length) {
  await run(["-hide_banner", "-v", "error", "-ss", start.toFixed(3), "-t", length.toFixed(3),
    "-i", input, "-map", "0:a:0", "-ac", "1", "-ar", String(ANALYSIS_RATE),
    "-f", "s16le", "-acodec", "pcm_s16le", "/w.raw"]);
  let bytes;
  try { bytes = await ffmpeg.readFile("/w.raw"); await ffmpeg.deleteFile("/w.raw"); }
  catch { bytes = new Uint8Array(0); }
  const samples = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength >> 1);
  const fl = (ANALYSIS_RATE * FRAME_MS) / 1000;
  const n = Math.floor(samples.length / fl);
  const energy = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (let j = i * fl, e = j + fl; j < e; j++) s += samples[j] * samples[j];
    energy[i] = s / fl;
  }
  const w = Math.max(1, Math.min(SMOOTH_MS / FRAME_MS, n));
  const smooth = [];
  let acc = 0;
  for (let i = 0; i < n; i++) {
    acc += energy[i];
    if (i >= w) acc -= energy[i - w];
    if (i >= w - 1) smooth.push(acc / w);
  }
  return { energy, smooth, w };
}

function quietCut({ energy, smooth, w }, start, length) {
  if (smooth.length < 3) return start + length;
  const best = Math.min(...smooth);
  const tol = best * 1.05 + 1;
  let idx = 0;
  smooth.forEach((v, i) => { if (v <= tol) idx = i; });   // 비슷하면 최대 길이에 가까운 쪽
  let k = idx, kv = Infinity;
  for (let j = idx; j < Math.min(idx + w, energy.length); j++) {
    if (energy[j] <= kv) { kv = energy[j]; k = j; }
  }
  return Math.min(start + ((k + 0.5) * FRAME_MS) / 1000, start + length);
}

async function keyframes(input, start, length) {
  const { log } = await run(["-hide_banner", "-skip_frame", "nokey", "-ss", start.toFixed(3),
    "-t", length.toFixed(3), "-i", input, "-map", "0:v:0", "-an", "-vf", "showinfo", "-f", "null", "-"]);
  const set = new Set();
  for (const m of log.matchAll(/pts_time:\s*(-?[\d.]+)/g)) {
    const t = parseFloat(m[1]);
    if (t > 0.05 && t <= length + 0.001) set.add(Math.round((start + t) * 1000) / 1000);
  }
  return [...set].sort((a, b) => a - b);
}

function keyframeCut({ smooth, w }, start, kfs) {
  if (!smooth.length) return kfs[kfs.length - 1];
  const scored = kfs.map((kf) => {
    let i = Math.floor(((kf - start) * 1000) / FRAME_MS) - Math.floor(w / 2);
    i = Math.max(0, Math.min(smooth.length - 1, i));
    return [smooth[i], kf];
  });
  const best = Math.min(...scored.map((s) => s[0]));
  const tol = best * 1.05 + 1;
  return Math.max(...scored.filter((s) => s[0] <= tol).map((s) => s[1]));
}

// ---------- 한 파일 처리 ----------
async function processJob(job, maxSeg, search, audioOnly) {
  const { file } = job;
  const dot = file.name.lastIndexOf(".");
  const base = dot > 0 ? file.name.slice(0, dot) : file.name;
  const ext = dot > 0 ? file.name.slice(dot).toLowerCase() : "";

  await getFFmpeg();
  setStatus(job, "파일 읽는 중…");
  setBar(job, 0.02);
  await ffmpeg.mount(FFFSType.WORKERFS, { files: [file] }, "/in");
  const input = "/in/" + file.name;
  try {
    const info = await probe(input);
    const keepVideo = info.hasVideo && !audioOnly;
    if (!keepVideo && !info.hasAudio) throw new Error("소리가 없는 영상이에요.");

    let maps, outExt, reencode = false;
    if (keepVideo) { maps = ["-map", "0:v:0", "-map", "0:a?"]; outExt = ext || ".mp4"; }
    else if (info.hasVideo) {
      maps = ["-map", "0:a:0"];
      outExt = AUDIO_COPY_EXT[info.acodec];
      if (!outExt) { outExt = ".m4a"; reencode = true; }
    } else { maps = ["-map", "0:a:0"]; outExt = ext || ".m4a"; }

    // 1) 분할 지점 찾기
    const duration = info.duration;
    const expected = Math.max(1, Math.floor(duration / maxSeg));
    const cuts = [];
    let pos = 0;
    while (duration - pos > maxSeg) {
      setStatus(job, `조용한 지점 찾는 중… (${cuts.length + 1}/${expected})`);
      const ws = pos + maxSeg - search;
      let cut;
      if (keepVideo) {
        let kfs = search > 0 ? await keyframes(input, ws, search) : [];
        if (!kfs.length) kfs = await keyframes(input, pos + 1, maxSeg - 1);
        if (kfs.length) {
          if (info.hasAudio && search > 0 && kfs[0] >= ws) {
            cut = keyframeCut(await windowEnergy(input, ws, search), ws, kfs);
          } else cut = kfs[kfs.length - 1];
        } else cut = pos + maxSeg;
      } else if (search > 0) {
        cut = quietCut(await windowEnergy(input, ws, search), ws, search);
      } else cut = pos + maxSeg;
      if (cut <= pos + 0.5 || duration - cut < MIN_LAST) break;
      cuts.push(cut);
      pos = cut;
      setBar(job, 0.05 + 0.55 * Math.min(1, cuts.length / expected));
    }

    // 2) 실제 자르기 (재압축 없이)
    const count = cuts.length + 1;
    const digits = Math.max(2, String(count).length);
    setStatus(job, `${count}개로 자르는 중…`);
    const args = ["-hide_banner", "-v", "error", "-y", "-i", input, ...maps, "-map_metadata", "0", "-sn", "-dn",
      ...(reencode ? ["-c:a", "aac", "-b:a", "192k"] : ["-c", "copy"]),
      "-f", "segment", "-segment_start_number", "1", "-reset_timestamps", "1",
      ...(cuts.length ? ["-segment_times", cuts.map((c) => Math.max(0.001, c - 0.002).toFixed(3)).join(",")]
                      : ["-segment_time", "999999"]),
      `/out/p_%04d${outExt}`];
    onProgress = (p) => setBar(job, 0.6 + 0.35 * Math.max(0, Math.min(1, p)));
    let r = await run(args);
    onProgress = null;
    if (r.code !== 0) throw new Error("자르기에 실패했어요. " + lastLine(r.log));

    // 3) 결과 꺼내기
    const names = (await ffmpeg.listDir("/out")).filter((e) => !e.isDir).map((e) => e.name).sort();
    if (!names.length) throw new Error("결과 파일이 만들어지지 않았어요.");
    job.pieces = [];
    for (let i = 0; i < names.length; i++) {
      const data = await ffmpeg.readFile("/out/" + names[i]);
      await ffmpeg.deleteFile("/out/" + names[i]);
      const name = `${base}_${String(i + 1).padStart(digits, "0")}${outExt}`;
      job.pieces.push({ name, blob: new Blob([data]) });
    }
    job.zipName = `${base}_분할.zip`;
    return { count: names.length, cuts, duration };
  } finally {
    try { await ffmpeg.unmount("/in"); } catch { /* 무시 */ }
  }
}

function showResult(job, res) {
  const box = job.el.querySelector(".result");
  box.innerHTML = "";
  const btn = document.createElement("button");
  btn.className = "primary small-btn";
  btn.type = "button";
  btn.textContent = `zip으로 받기 (${res.count}개)`;
  btn.onclick = () => downloadZip(job, btn);
  box.append(btn);

  const det = document.createElement("details");
  det.innerHTML = "<summary>하나씩 받기</summary>";
  for (const p of job.pieces) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(p.blob);
    a.download = p.name;
    a.textContent = `${p.name} (${fmtSize(p.blob.size)})`;
    det.append(a);
  }
  box.append(det);
}

async function downloadZip(job, btn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "zip 만드는 중…";
  try {
    const parts = [];
    const zip = new Zip((err, chunk) => { if (err) throw err; parts.push(chunk); });
    for (const p of job.pieces) {
      const entry = new ZipPassThrough(p.name);   // 이미 압축된 파일이라 다시 압축하지 않음(빠름)
      zip.add(entry);
      entry.push(new Uint8Array(await p.blob.arrayBuffer()), true);
    }
    zip.end();
    const url = URL.createObjectURL(new Blob(parts, { type: "application/zip" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = job.zipName;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    alert("zip을 만들지 못했어요. '하나씩 받기'를 이용해 주세요.\n" + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

// ---------- 실행 ----------
async function startAll() {
  if (busy) return;
  const maxSeg = Math.max(1, Number(els.maxMin.value) || 5) * 60;
  const search = Math.max(0, Math.min(Number(els.searchSec.value) || 0, maxSeg - 1));
  const audioOnly = vmode() === "audio";
  saveSettings();
  busy = true;
  refreshButtons();
  for (const job of jobs) {
    if (job.state !== "wait" && job.state !== "fail") continue;
    job.state = "run";
    const t0 = performance.now();
    try {
      const res = await processJob(job, maxSeg, search, audioOnly);
      job.state = "done";
      setBar(job, 1);
      setStatus(job, `완료 · ${res.count}개 조각 · ${((performance.now() - t0) / 1000).toFixed(0)}초`);
      showResult(job, res);
    } catch (e) {
      job.state = "fail";
      const oom = /memory|abort|OOM|out of bounds/i.test(String(e && e.message));
      setStatus(job, oom
        ? "브라우저 메모리가 부족해요. 아래 오프라인 버전을 쓰면 큰 파일도 자를 수 있어요."
        : "실패: " + (e && e.message ? e.message : e), "bad");
      if (ffmpeg) { try { ffmpeg.terminate(); } catch { /* 무시 */ } ffmpeg = null; }
    }
  }
  busy = false;
  refreshButtons();
}

function clearAll() {
  if (busy) return;
  for (const j of jobs) j.el.querySelectorAll("a[href^=blob]").forEach((a) => URL.revokeObjectURL(a.href));
  jobs.length = 0;
  els.list.innerHTML = "";
  refreshButtons();
}

// ---------- 도우미 ----------
function fmtSize(b) {
  return b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(2) + "GB"
       : b >= 1024 ** 2 ? (b / 1024 ** 2).toFixed(1) + "MB" : Math.ceil(b / 1024) + "KB";
}
function fmtLong(t) {
  const m = Math.floor(t / 60), s = Math.round(t % 60);
  return s ? (m ? `${m}분 ${s}초` : `${s}초`) : `${m}분`;
}
const lastLine = (log) => (log.trim().split("\n").pop() || "").slice(0, 200);

// ---------- 이벤트 ----------
els.pick.addEventListener("change", () => { addFiles(els.pick.files); els.pick.value = ""; });
["dragenter", "dragover"].forEach((t) => els.drop.addEventListener(t, (e) => {
  e.preventDefault(); els.drop.classList.add("over");
}));
["dragleave", "drop"].forEach((t) => els.drop.addEventListener(t, () => els.drop.classList.remove("over")));
els.drop.addEventListener("drop", (e) => { e.preventDefault(); e.stopPropagation(); addFiles(e.dataTransfer.files); });
els.drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.pick.click(); } });
// 드롭 영역 밖에 떨어뜨려도 브라우저가 파일을 열어버리지 않게
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files); });
els.start.addEventListener("click", startAll);
els.clear.addEventListener("click", clearAll);
[els.maxMin, els.searchSec].forEach((i) => i.addEventListener("input", updateHint));
document.querySelectorAll("input[name=vmode]").forEach((i) => i.addEventListener("change", saveSettings));
window.addEventListener("beforeunload", (e) => { if (busy) { e.preventDefault(); e.returnValue = ""; } });

loadSettings();
updateHint();
refreshButtons();
