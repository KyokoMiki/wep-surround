#!/usr/bin/env python3
"""WEP Web UI - 一键环绕声 Web 工作流 v1.5.0"""

import os, sys, subprocess, shutil, uuid, json, glob as glob_mod, time, atexit
from pathlib import Path
from datetime import datetime
import gradio as gr

SCRIPT_DIR = Path(__file__).parent.resolve()
SEPARATED_DIR = SCRIPT_DIR / "separated"
TMP_DIR = SCRIPT_DIR / "_wep_tmp"
OUTPUT_DIR = SCRIPT_DIR / "output"
CONFIG_FILE = SCRIPT_DIR / "wep_config.json"
TMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
SEPARATED_DIR.mkdir(exist_ok=True)

# ── 程序退出时自动清理 Gradio 临时文件 ─────────────────
import tempfile as _tempfile_mod
def _cleanup_gradio_temp_on_exit():
    gdir = Path(_tempfile_mod.gettempdir()) / "gradio"
    if gdir.exists():
        try: shutil.rmtree(gdir, ignore_errors=True)
        except: pass
atexit.register(_cleanup_gradio_temp_on_exit)

# ── 环境检测 ──────────────────────────────────────────────
GPU_LABEL = "未检测到"
try:
    import torch
    if torch.cuda.is_available():
        GPU_LABEL = f"NVIDIA {torch.cuda.get_device_name(0)}"
    elif hasattr(torch, 'hip') and torch.hip.is_available():
        GPU_LABEL = "AMD ROCm"
except: pass

FFMPEG_OK = True
try: subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
except: FFMPEG_OK = False

FDK_AAC = False
try:
    r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10)
    FDK_AAC = "libfdk_aac" in r.stdout
except: pass

PRESET_NAMES = {
    "Music": "🎵 音乐模式", "Movie": "🎬 电影模式",
    "Anime": "🎌 动漫模式", "PLIIx": "🔊 杜比模式",
}

# ── 分轨管理 ──────────────────────────────────────────
def scan_stems():
    """扫描 separated/ 目录，返回 [{label, model, name, path}] 列表"""
    results = []
    if not SEPARATED_DIR.exists():
        return results
    for model_dir in sorted(SEPARATED_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        for track_dir in sorted(model_dir.iterdir()):
            if not track_dir.is_dir():
                continue
            stem_files = list(track_dir.glob("*.wav")) + list(track_dir.glob("*.flac"))
            if stem_files:
                total_size = sum(f.stat().st_size for f in stem_files)
                size_mb = total_size / 1024 / 1024
                label = f"[{model_dir.name}] {track_dir.name} ({size_mb:.1f}MB)"
                results.append({
                    "label": label,
                    "model": model_dir.name,
                    "name": track_dir.name,
                    "path": str(track_dir),
                })
    return results

def get_stems_labels():
    """返回 [label] 列表用于 Dropdown"""
    return [s["label"] for s in scan_stems()]

def get_stem_info_by_label(label):
    """根据 Dropdown 选项的 label 返回分轨信息"""
    for s in scan_stems():
        if s["label"] == label:
            return s
    return None

def delete_stems(model_name, track_name):
    """删除指定分轨目录，返回 (success, msg)"""
    target = SEPARATED_DIR / model_name / track_name
    if not target.exists():
        return False, f"目录不存在：{target}"
    try:
        size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
        shutil.rmtree(target)
        # 清理空的模型目录
        model_dir = target.parent
        if model_dir.exists() and not any(model_dir.iterdir()):
            model_dir.rmdir()
        size_mb = size / 1024 / 1024
        return True, f"已删除 {track_name}（{size_mb:.1f}MB）"
    except Exception as e:
        return False, f"删除失败：{e}"

# ── 配置持久化 ──────────────────────────────────────────
def load_config():
    defaults = {
        "model": "htdemucs_ft", "preset": "Music",
        "sample_rate": "48000", "bit_depth": "24",
        "output_format": "wav", "channel_config": "7.1",
        "aac_bitrate": "512k", "precision": "fp16",
        "lfe_freq": "80", "loudnorm": "-14",
    }
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            defaults.update(saved)
        except: pass
    return defaults

def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except: pass

# ── 日志 + 进度追踪 ────────────────────────────────────
def _format_seconds(s):
    """格式化秒数为 X分钟Y秒"""
    s = int(s)
    if s < 60:
        return f"{s}秒"
    return f"{s//60}分{s%60}秒"

class PipelineState:
    def __init__(self, on_log=None):
        self.log_lines = []
        self.on_log = on_log
        self.current_progress = 0.0
        self.stage_desc = ""
        self.start_time = time.time()
        self.total_est_seconds = 0  # 预估总耗时（秒），由外部设置
    def _calc_eta(self):
        """基于预估总耗时计算剩余时间"""
        if self.total_est_seconds <= 0:
            return ""
        elapsed = time.time() - self.start_time
        remaining = self.total_est_seconds - elapsed
        if remaining <= 0:
            return "  即将完成"
        return f"  预计 {_format_seconds(remaining)}后完成"
    def get_eta_line(self):
        """获取当前 ETA 行（用于 UI 轮询时刷新，不追加到日志历史）"""
        if self.total_est_seconds <= 0:
            return ""
        eta = self._calc_eta()
        ts = datetime.now().strftime("%H:%M:%S")
        pct_str = f"[{self.current_progress*100:5.1f}%]"
        if self.stage_desc:
            return f"[{ts}] {pct_str} {self.stage_desc}{eta}"
        return f"[{ts}] {pct_str}{eta}"
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        # 自动附加进度条前缀
        if self.current_progress > 0:
            pct = f"[{self.current_progress*100:5.1f}%]"
            prefix = f"{pct} {self.stage_desc}" if self.stage_desc else pct
            line = f"[{ts}] {prefix} → {msg}"
        else:
            line = f"[{ts}] {msg}"
        print(line)
        self.log_lines.append(line)
        full = "\n".join(self.log_lines)
        if self.on_log:
            self.on_log(full)
        return full
    def progress(self, fraction, desc=""):
        """同时更新进度 + 推送日志（百分比 + ETA）"""
        self.current_progress = fraction
        self.stage_desc = desc
        eta = self._calc_eta()
        ts = datetime.now().strftime("%H:%M:%S")
        pct_str = f"[{fraction*100:5.1f}%]"
        if desc:
            line = f"[{ts}] {pct_str} {desc}"
        else:
            line = f"[{ts}] {pct_str}"
        if eta:
            line += eta
        # 追加到日志
        self.log_lines.append(line)
        full = "\n".join(self.log_lines)
        if self.on_log:
            self.on_log(full)

# ── 主流水线 ────────────────────────────────────────────
def run_pipeline(input_path, preset, model_name, sample_rate, bit_depth,
                 output_format, channel_config, aac_bitrate="512k",
                 precision="fp16", lfe_freq="80", loudnorm="-14",
                 existing_stems_dir=None,
                 progress=gr.Progress(), on_log=None, _state_ref=None):
    state = PipelineState(on_log=on_log)
    log = state.log
    if _state_ref is not None:
        _state_ref[0] = state

    fmt_map = {"flac": (".flac", "flac", "FLAC 无损"), "wav": (".wav", "pcm_s24le", "WAV/PCM"), "aac": (".m4a", "aac", "AAC/M4A")}
    out_ext, out_codec, fmt_desc = fmt_map.get(output_format, fmt_map["flac"])
    sr, bd = int(sample_rate), int(bit_depth)
    lfe_hz = int(lfe_freq)
    prec_label = "FP16 加速" if precision == "fp16" else "FP32 安全"

    # 已有分轨 → 跳过 AI 分离
    if existing_stems_dir:
        stems_dir = Path(existing_stems_dir)
        log(f"📂 使用已有分轨：{stems_dir.parent.name}/{stems_dir.name}")
        progress(0.45, desc="📂 加载已有分轨…")
        state.progress(0.45, "📂 加载已有分轨…")
        safe_name = stems_dir.name
    else:
        if not input_path:
            raise ValueError("请上传音频文件")
        input_path = Path(input_path)
        filename = input_path.stem
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ()[]__-—（）【】")

        # 拷贝到本地临时目录，绕过 Gradio 文件锁
        _copied_input = None
        if not str(input_path).startswith(str(SCRIPT_DIR)):
            ext = input_path.suffix
            _copied_input = TMP_DIR / f"{safe_name}{ext}"
            try:
                shutil.copy2(str(input_path), str(_copied_input))
                log(f"  📋 已拷贝到本地：{_copied_input.name}")
            except PermissionError:
                time.sleep(2)
                shutil.copy2(str(input_path), str(_copied_input))
                log(f"  📋 已拷贝到本地（延迟重试）：{_copied_input.name}")
            input_path = _copied_input

        log(f"📁 输入：{input_path.name}")
        log(f"🤖 模型：{model_name} | 🎚️ 预设：{PRESET_NAMES.get(preset, preset)} | ⚡ {prec_label}")
        log(f"📊 输出：{fmt_desc}{' @ '+aac_bitrate if output_format=='aac' else ''} @ {sr}Hz/{bd}bit | 🔊 声道：{channel_config}")
        log(f"🎚️ LFE 分频：{lfe_hz}Hz | 📏 响度目标：{loudnorm} LUFS")

        progress(0.05, desc="🔍 检测输入采样率…")
        state.progress(0.05, "🔍 检测输入采样率…")

        _demucs_input = str(input_path)
        _resampled_tmp = None
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(input_path)],
                capture_output=True, text=True, timeout=30
            )
            probe_data = json.loads(probe.stdout)
            input_sr = int(probe_data["streams"][0]["sample_rate"])
            log(f"  输入采样率：{input_sr} Hz")
            model_sr = 44100
            if input_sr > model_sr * 2:
                log(f"  🔄 预重采样：{input_sr} → {model_sr} Hz（避免 Demucs 在 {input_sr}Hz 下重采样开销）")
                progress(0.08, desc="🔄 预重采样中…")
                state.progress(0.08, "🔄 预重采样中…")
                _resampled_tmp = TMP_DIR / f"resampled_{uuid.uuid4().hex[:8]}.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(input_path),
                     "-ar", str(model_sr), "-c:a", "pcm_f32le", str(_resampled_tmp)],
                    check=True, capture_output=True, timeout=300
                )
                _demucs_input = str(_resampled_tmp)
                log(f"  ✓ 重采样完成 → {_resampled_tmp.name}")
        except Exception as e:
            log(f"  ⚠️ 采样率检测失败，使用原始文件：{e}")

        progress(0.1, desc="🎚️ AI 分离中…")
        state.progress(0.1, "🎚️ AI 分离中…")
        stems_dir = SEPARATED_DIR / model_name / safe_name
        if not stems_dir.exists() or not all((stems_dir / f"{s}.wav").exists() for s in ["bass","drums","other","vocals"]):
            import librosa
            try:
                duration = librosa.get_duration(path=str(input_path))
                # 实际测量：72.8min(4368s)→290s, 66.2min(3972s)→255s → 系数 ≈ 0.066
                total_est = duration * 0.066
                state.total_est_seconds = total_est
                log(f"  音频时长：{duration/60:.1f} 分钟，预计：{_format_seconds(total_est)}")
            except: pass
            import torch
            from demucs.pretrained import get_model
            from demucs.separate import load_track
            from demucs.apply import apply_model
            from demucs.audio import save_audio
            log(f"  Demucs: {prec_label} | segment=7 overlap=0.25 j=4")

            progress(0.12, desc="🎚️ 加载模型…")
            state.progress(0.12, "🎚️ 加载模型…")
            model = get_model(name=model_name)
            model.eval()

            progress(0.15, desc="🎚️ 加载音频…")
            state.progress(0.15, "🎚️ 加载音频…")
            wav = load_track(_demucs_input, model.audio_channels, model.samplerate)
            ref = wav.mean(0)
            wav -= ref.mean()
            wav /= ref.std()

            progress(0.18, desc="🎚️ AI 推理中（FP16）…")
            state.progress(0.18, "🎚️ AI 推理中…")
            if precision == "fp16":
                model = model.half()
                with torch.autocast('cuda', dtype=torch.float16):
                    sources = apply_model(model, wav[None], device='cuda', shifts=0,
                                          split=True, overlap=0.25, progress=False,
                                          num_workers=4, segment=7)[0]
            else:
                sources = apply_model(model, wav[None], device='cuda', shifts=0,
                                      split=True, overlap=0.25, progress=False,
                                      num_workers=4, segment=7)[0]

            progress(0.45, desc="🎚️ 保存分轨…")
            state.progress(0.45, "🎚️ 保存分轨…")
            sources *= ref.std()
            sources += ref.mean()

            stems_dir.mkdir(parents=True, exist_ok=True)
            for source, name in zip(sources, model.sources):
                save_audio(source, str(stems_dir / f"{name}.wav"),
                          samplerate=model.samplerate, as_float=True)
            log(f"  ✓ AI 分离完成（{prec_label}）")
            if not stems_dir.exists():
                candidates = list(SEPARATED_DIR.glob(f"{model_name}/*"))
                if candidates: stems_dir = max(candidates, key=lambda p: p.stat().st_mtime)
        else:
            log(f"  ✓ 发现已存在分轨，跳过 AI 分离")

    stems = {}
    for s in ["vocals","drums","bass","other"]:
        for ext in [".wav",".flac"]:
            p = stems_dir / f"{s}{ext}"
            if p.exists(): stems[s] = str(p); break
    if len(stems) < 4: raise FileNotFoundError(f"缺少分轨")

    preset_params = {
        "Music": {"centre_db":1,"decorr_l":15,"decorr_r":17},
        "Movie": {"centre_db":2,"decorr_l":10,"decorr_r":12},
        "Anime": {"centre_db":3,"decorr_l":12,"decorr_r":14},
        "PLIIx": {"centre_db":1,"decorr_l":20,"decorr_r":23},
    }
    p = preset_params.get(preset, preset_params["Music"])

    # Stage 2: 上混（并行化）
    progress(0.5, desc="🔊 环绕声上混…")
    state.progress(0.5, "🔊 环绕声上混…")
    temp_d = TMP_DIR / f"upmix_{uuid.uuid4().hex[:8]}"
    temp_d.mkdir(exist_ok=True)

    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        _jobs = []
        _ff = "ffmpeg"  # 基础命令（所有任务加 -threads 0 吃满 CPU）

        # FL/FR（独立任务）
        for side, ch in [("FL","c0"),("FR","c1")]:
            weights = {"vocals":0.30,"drums":0.25,"bass":0.25,"other":0.20}
            flt = ";".join([f"[{i}:a]pan=mono|c0={ch},volume={w}[{n}]" for i,(n,w) in enumerate([("v",weights["vocals"]),("d",weights["drums"]),("b",weights["bass"]),("o",weights["other"])])])
            mix = "[v][d][b][o]amix=inputs=4:duration=longest:normalize=0"
            _jobs.append({"cmd": [_ff,"-y","-v","error","-threads","0","-i",stems["vocals"],"-i",stems["drums"],"-i",stems["bass"],"-i",stems["other"],"-filter_complex",flt+";"+mix,"-ar",str(sr),"-c:a","pcm_s24le",str(temp_d/f"{side}.wav")],"name": side})

        # FC
        cg = 1.2 + p["centre_db"]*0.1
        _jobs.append({"cmd": [_ff,"-y","-v","error","-threads","0","-i",stems["vocals"],"-i",stems["other"],"-filter_complex",f"[0:a]pan=mono|c0=0.5*c0+0.5*c1,volume={cg}[v];[1:a]pan=mono|c0=0.5*c0+0.5*c1,volume=0.3[o];[v][o]amix=inputs=2:duration=longest:normalize=0","-ar",str(sr),"-c:a","pcm_s24le",str(temp_d/"FC.wav")],"name": "FC"})

        # LFE（分频点可选）
        _jobs.append({"cmd": [_ff,"-y","-v","error","-threads","0","-i",stems["bass"],"-i",stems["drums"],"-filter_complex",f"[0:a]lowpass=f={lfe_hz},volume=1.5,pan=mono|c0=0.5*c0+0.5*c1[b];[1:a]lowpass=f={lfe_hz},volume=0.8,pan=mono|c0=0.5*c0+0.5*c1[d];[b][d]amix=inputs=2:duration=longest:normalize=0","-ar",str(sr),"-c:a","pcm_s24le",str(temp_d/"LFE.wav")],"name": "LFE"})

        # 环绕声道
        dl, dr = f"{p['decorr_l']}|{p['decorr_l']}", f"{p['decorr_r']}|{p['decorr_r']}"
        surround_pairs = [("Ls","c0",dl),("Rs","c1",dr)]
        if channel_config == "7.1":
            surround_pairs += [("SL","c0","5|5"),("SR","c1","7|7")]

        for name, ch, delay in surround_pairs:
            _jobs.append({"cmd": [_ff,"-y","-v","error","-threads","0","-i",stems["drums"],"-i",stems["other"],"-filter_complex",f"[0:a]pan=mono|c0={ch},volume=0.7,adelay={delay}[d];[1:a]pan=mono|c0={ch},volume=0.6,adelay={delay}[o];[d][o]amix=inputs=2:duration=longest:normalize=0","-ar",str(sr),"-c:a","pcm_s24le",str(temp_d/f"{name}.wav")],"name": name})

        def _run_ffmpeg(job):
            try:
                subprocess.run(job["cmd"], check=True, capture_output=True)
                return (job["name"], True, None)
            except subprocess.CalledProcessError as e:
                return (job["name"], False, str(e.stderr or e))

        total_jobs = len(_jobs)
        ok = set()
        job_base_progress = 0.5
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_run_ffmpeg, j): j["name"] for j in _jobs}
            for fut in as_completed(futures):
                name, success, err = fut.result()
                if success:
                    ok.add(name)
                    pct = job_base_progress + (len(ok) / total_jobs) * 0.35
                    log(f"  ✓ 通道 {name} 完成（{len(ok)}/{total_jobs}）")
                    state.progress(pct, f"🔊 上混 {len(ok)}/{total_jobs} 通道…")
                else:
                    raise RuntimeError(f"上混通道 {name} 失败: {err}")

        log(f"  ✓ 上混完成（{len(ok)} 通道并行）")

        # 合并（loudnorm 目标值可选）
        progress(0.85, desc="📀 编码输出…")
        state.progress(0.85, "📀 编码输出…")
        suffix = f".{channel_config}" if channel_config != "stereo" else ""
        output_path = OUTPUT_DIR / f"{safe_name}{suffix}{out_ext}"
        lnorm = f"loudnorm=I={loudnorm}:TP=-1:LRA=11"

        if channel_config == "7.1":
            inputs = ["-i",str(temp_d/"FL.wav"),"-i",str(temp_d/"FR.wav"),"-i",str(temp_d/"FC.wav"),"-i",str(temp_d/"LFE.wav"),"-i",str(temp_d/"Ls.wav"),"-i",str(temp_d/"Rs.wav"),"-i",str(temp_d/"SL.wav"),"-i",str(temp_d/"SR.wav")]
            filter_c = f"[0:a][1:a][2:a][3:a][4:a][5:a][6:a][7:a]amerge=inputs=8,{lnorm}[aout]"
        elif channel_config == "5.1":
            inputs = ["-i",str(temp_d/"FL.wav"),"-i",str(temp_d/"FR.wav"),"-i",str(temp_d/"FC.wav"),"-i",str(temp_d/"LFE.wav"),"-i",str(temp_d/"Ls.wav"),"-i",str(temp_d/"Rs.wav")]
            filter_c = f"[0:a][1:a][2:a][3:a][4:a][5:a]amerge=inputs=6,{lnorm}[aout]"
        else:  # stereo
            inputs = ["-i",stems["vocals"],"-i",stems["drums"],"-i",stems["bass"],"-i",stems["other"]]
            filter_c = f"[0:a]volume=0.3[v];[1:a]volume=0.25[d];[2:a]volume=0.25[b];[3:a]volume=0.2[o];[v][d][b][o]amix=inputs=4:duration=longest:normalize=0,{lnorm}[aout]"

        if output_format == "wav": codec = ["-c:a",f"pcm_s{bd}le"]
        elif output_format == "flac": codec = ["-c:a","flac","-compression_level","8"]
        else:
            if FDK_AAC:
                codec = ["-c:a","libfdk_aac","-b:a",aac_bitrate]
                log(f"  🎵 AAC 编码器：libfdk_aac（高品质）")
            else:
                codec = ["-c:a","aac","-b:a",aac_bitrate]

        subprocess.run([_ff,"-y","-v","error","-threads","0"]+inputs+["-filter_complex",filter_c,"-map","[aout]","-ar",str(sr)]+codec+[str(output_path)],check=True,capture_output=True)

        # MIB2+ 兼容：WAV 多声道自动生成配套 M3U
        m3u_path = None
        master_m3u = None
        if output_format == "wav" and channel_config in ("5.1", "7.1"):
            m3u_path = output_path.with_suffix(".m3u")
            m3u_path.write_text(f"#EXTM3U\n{output_path.name}\n", encoding="utf-8")
            log(f"  📋 M3U：{m3u_path.name}  ← U 盘需同目录放置，MIB2+ 解锁 5.1 输出")
            master_m3u = OUTPUT_DIR / "5.1_playlist.m3u"
            existing = set()
            if master_m3u.exists():
                for line in master_m3u.read_text(encoding="utf-8").splitlines():
                    if line and not line.startswith("#"):
                        existing.add(line)
            if output_path.name not in existing:
                header = "#EXTM3U\n" if not master_m3u.exists() else ""
                with open(master_m3u, "a", encoding="utf-8") as f:
                    if header: f.write(header)
                    f.write(f"{output_path.name}\n")
                count = len(existing) + 1
                log(f"  📀 总播放列表：{master_m3u.name}（共 {count} 首）")
            else:
                log(f"  ℹ️ {output_path.name} 已在播放列表中，跳过追加")

        size_mb = output_path.stat().st_size / 1024 / 1024
        extra = f" + M3U" if m3u_path else ""
        if master_m3u: extra += f" + 播放列表({master_m3u.stat().st_size}B)"
        state.progress(1.0, "✅ 全部完成！")
        log(f"✅ 完成！{size_mb:.1f} MB{extra}")
        return str(output_path), "\n".join(state.log_lines)
    finally:
        shutil.rmtree(temp_d, ignore_errors=True)
        if not existing_stems_dir and '_resampled_tmp' in dir() and _resampled_tmp and _resampled_tmp.exists():
            try: _resampled_tmp.unlink()
            except: pass
        if not existing_stems_dir and '_copied_input' in dir() and _copied_input and _copied_input.exists():
            try: _copied_input.unlink()
            except: pass

# ── CSS ──────────────────────────────────────────────────
CSS = """body{background:#0a0a14}.gradio-container{max-width:900px!important}#header{text-align:center;padding:20px 0 5px}#header h1{font-size:2em;background:linear-gradient(135deg,#6366f1,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent}#gpu-badge{display:inline-block;background:#1a1a2e;color:#a5b4fc;padding:6px 18px;border-radius:20px;margin:8px 0;border:1px solid #312e81}.pipeline-bar{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;background:#0f0f1e;padding:14px;border-radius:12px;margin:12px 0;border:1px solid #1e1e3a}.pipe-step{background:#1e1e3f;color:#a5b4fc;padding:6px 14px;border-radius:8px;font-size:0.85em}.pipe-arrow{color:#6366f1;font-weight:bold}#run-btn{background:linear-gradient(135deg,#6366f1,#a855f7)!important;border:none!important;color:white!important;font-size:1.15em!important;padding:14px 0!important;border-radius:12px!important;width:100%!important}"""

# ── 构建界面 ────────────────────────────────────────────
def build_ui():
    cfg = load_config()

    with gr.Blocks(title="WEP · 一键环绕声") as demo:
        fdk_badge = " libfdk_aac ✅" if FDK_AAC else " ffmpeg aac"
        gr.HTML(f'''<div id="header"><h1>🎧 一键环绕声 WEP</h1><p>立体声 → 5.1/7.1 环绕声 · 多格式输出</p><div id="gpu-badge">🖥️ {GPU_LABEL} | ffmpeg {"✅" if FFMPEG_OK else "❌"} |{fdk_badge}</div></div><div class="pipeline-bar"><span class="pipe-step">📁 上传</span><span class="pipe-arrow">→</span><span class="pipe-step">🎚️ AI 分离</span><span class="pipe-arrow">→</span><span class="pipe-step">🔊 混音</span><span class="pipe-arrow">→</span><span class="pipe-step">📀 输出</span></div>''')

        # ── 分轨管理面板 ──────────────────────────
        with gr.Accordion("📂 分轨管理（已有分轨可跳过 AI 分离）", open=False) as stems_panel:
            with gr.Row():
                stems_dropdown = gr.Dropdown(label="📂 选择已有分轨", choices=get_stems_labels(), value=None, interactive=True, allow_custom_value=False, scale=3)
                refresh_btn = gr.Button("🔄 刷新", scale=1)
            with gr.Row():
                load_stems_btn = gr.Button("📥 加载选中分轨", variant="secondary", scale=2)
                delete_stems_btn = gr.Button("🗑️ 删除选中分轨", variant="stop", scale=2)
            stems_status = gr.Markdown("💡 选择已有分轨后点击「加载」，将跳过 AI 分离直接上混")
            # 隐藏状态：记录当前加载的分轨路径
            loaded_stems_path = gr.State(value=None)
            loaded_stems_label = gr.State(value=None)

        audio_input = gr.Audio(label="🎵 拖放音频文件（加载已有分轨时可不填）", type="filepath", sources=["upload"])
        size_estimate = gr.Markdown("")

        # ── 上传后自动预估输出文件大小 ──────────────
        def estimate_size(audio_path, fmt, ch, sr, bd):
            if not audio_path:
                return ""
            try:
                import librosa
                p = Path(audio_path)
                dur = librosa.get_duration(path=str(p))
                channels_map = {"5.1": 6, "7.1": 8, "stereo": 2}
                ch_count = channels_map.get(ch, 6)
                sample_rate = int(sr)
                bit_depth = int(bd)
                bytes_per_sec = sample_rate * (bit_depth // 8) * ch_count
                if fmt == "aac":
                    # AAC 是压缩的，粗略按码率估算（默认 512k）
                    # 512000 bits/sec = 64000 bytes/sec
                    bytes_per_sec = 64000
                elif fmt == "flac":
                    # FLAC 压缩率约 50-60%
                    bytes_per_sec *= 0.55
                total_bytes = int(dur * bytes_per_sec)
                ch_name = {"5.1": "5.1(6ch)", "7.1": "7.1(8ch)", "stereo": "立体声"}.get(ch, ch)
                fmt_name = {"wav": "WAV", "flac": "FLAC", "aac": "AAC"}.get(fmt, fmt)
                if total_bytes >= 1024 * 1024 * 1024:
                    size_str = f"{total_bytes / 1024**3:.2f} GB"
                else:
                    size_str = f"{total_bytes / 1024**2:.1f} MB"
                return f"📊 **预计输出**: `{size_str}` | {fmt_name} {sample_rate}Hz/{bit_depth}bit {ch_name} | 时长: {dur/60:.1f} 分钟"
            except Exception:
                return ""

        with gr.Row():
            model_select = gr.Radio(choices=[("⚡ htdemucs 快速","htdemucs"),("🎯 htdemucs_ft 高质量","htdemucs_ft")], value=cfg.get("model","htdemucs_ft"), label="🤖 AI 模型", info="htdemucs：速度快内存低；htdemucs_ft：音质更高分离精度")
            preset = gr.Radio(choices=[("🎵 音乐","Music"),("🎬 电影","Movie"),("🎌 动漫","Anime"),("🔊 杜比","PLIIx")], value=cfg.get("preset","Music"), label="🎚️ 预设", info="音乐：人声/乐器分离最佳；电影：对白/环绕/低音增强；动漫：OP/ED/配音优化；杜比：模拟 PLIIx 环绕扩展")

        with gr.Row():
            sample_rate = gr.Radio(choices=[("44.1kHz CD","44100"),("48kHz 推荐","48000"),("96kHz 高解析","96000")], value=cfg.get("sample_rate","48000"), label="📊 采样率", info="44.1kHz：CD标准；48kHz：车机/影视标准推荐；96kHz：高解析但文件更大更慢")
            bit_depth = gr.Radio(choices=[("16-bit CD","16"),("24-bit 推荐","24"),("32-bit float","32")], value=cfg.get("bit_depth","24"), label="🎚️ 位深", info="16-bit：CD音质256KB/s/声道；24-bit：专业录音级推荐；32-bit：浮点无损动态范围最大")

        with gr.Row():
            output_format = gr.Radio(choices=[("📀 FLAC 无损","flac"),("💿 WAV/PCM 无损","wav"),("🎵 AAC/m4a","aac")], value=cfg.get("output_format","wav"), label="📁 输出格式", info="FLAC：无损压缩50%体积；WAV：无损PCM车机最佳兼容；AAC：512k高音质仅50MB")
            channel_config = gr.Radio(choices=[("7.1 环绕声 (8 声道)","7.1"),("5.1 环绕声 (6 声道)","5.1"),("立体声","stereo")], value=cfg.get("channel_config","7.1"), label="🔊 声道布局", info="5.1：FL/FR/FC/LFE/Ls/Rs 车载推荐；7.1：5.1+SL/SR 家庭影院；立体声：不环绕")

        with gr.Row(visible=False) as aac_row:
            aac_bitrate = gr.Radio(choices=[("128k 小体积","128k"),("256k 标准","256k"),("320k 高质量","320k"),("512k 推荐","512k"),("768k 超高","768k"),("1024k 极高","1024k")], value=cfg.get("aac_bitrate","512k"), label="🎵 AAC 码率")

        with gr.Accordion("⚙️ 高级选项", open=False):
            with gr.Row():
                precision = gr.Radio(choices=[("FP16 加速（推荐）","fp16"),("FP32 安全","fp32")], value=cfg.get("precision","fp16"), label="⚡ GPU 精度", info="FP16：AMD/NVIDIA实测2-3倍加速，显存减半；FP32：兜底模式兼容所有GPU")
                lfe_freq = gr.Radio(choices=[("80Hz 车载","80"),("120Hz 家庭影院","120")], value=cfg.get("lfe_freq","80"), label="🔊 LFE 分频点", info="80Hz：车载低音炮标准推荐；120Hz：家庭影院THX标准，低音更丰满")
                loudnorm = gr.Radio(choices=[("-14 LUFS 流媒体","-14"),("-18 LUFS 广播","-18")], value=cfg.get("loudnorm","-14"), label="📏 响度目标", info="-14 LUFS：Spotify/YouTube/Apple Music标准；-18 LUFS：广播电台，动态范围更大")

        run_btn = gr.Button("🚀 开始制作", variant="primary", elem_id="run-btn")
        status = gr.Markdown("💡 就绪 — 上传音频或加载已有分轨后点击开始")
        log_output = gr.Textbox(label="📜 处理日志", lines=10, interactive=False, autoscroll=True)
        output_audio = gr.Audio(label="📀 输出", type="filepath")
        output_info = gr.Markdown("")

        # ── 分轨管理交互 ──────────────────────────
        def on_refresh_stems():
            labels = get_stems_labels()
            count = len(labels)
            return gr.update(choices=labels, value=None), None, None, f"✅ 已扫描，共 {count} 个分轨项目"

        def on_load_stems(selected_label):
            if not selected_label:
                return None, None, "⚠️ 请先选择一个分轨"
            info = get_stem_info_by_label(selected_label)
            if not info:
                return None, None, "❌ 无效的分轨选项"
            return info["path"], selected_label, f"✅ 已加载：{info['name']}（模型：{info['model']}）"

        def on_delete_stems(selected_label):
            if not selected_label:
                return None, None, "⚠️ 请先选择一个分轨"
            info = get_stem_info_by_label(selected_label)
            if not info:
                return None, None, "❌ 无效的分轨选项"
            ok, msg = delete_stems(info["model"], info["name"])
            labels = get_stems_labels()
            return gr.update(choices=labels, value=None), None, f"{'✅' if ok else '❌'} {msg}"

        refresh_btn.click(fn=on_refresh_stems,
            inputs=[],
            outputs=[stems_dropdown, loaded_stems_path, loaded_stems_label, stems_status])

        load_stems_btn.click(fn=on_load_stems,
            inputs=[stems_dropdown],
            outputs=[loaded_stems_path, loaded_stems_label, stems_status])

        delete_stems_btn.click(fn=on_delete_stems,
            inputs=[stems_dropdown],
            outputs=[stems_dropdown, loaded_stems_path, stems_status])

        # 上传或参数变化时实时预估输出大小
        def _estimate(audio_path, fmt, ch, sr, bd):
            return estimate_size(audio_path, fmt, ch, sr, bd)
        audio_input.change(fn=_estimate,
            inputs=[audio_input, output_format, channel_config, sample_rate, bit_depth],
            outputs=[size_estimate])
        output_format.change(fn=lambda fmt: gr.update(visible=(fmt=="aac")), inputs=output_format, outputs=aac_row)
        output_format.change(fn=_estimate,
            inputs=[audio_input, output_format, channel_config, sample_rate, bit_depth],
            outputs=[size_estimate])
        channel_config.change(fn=_estimate,
            inputs=[audio_input, output_format, channel_config, sample_rate, bit_depth],
            outputs=[size_estimate])
        sample_rate.change(fn=_estimate,
            inputs=[audio_input, output_format, channel_config, sample_rate, bit_depth],
            outputs=[size_estimate])
        bit_depth.change(fn=_estimate,
            inputs=[audio_input, output_format, channel_config, sample_rate, bit_depth],
            outputs=[size_estimate])

        # ── 主运行逻辑（支持已有分轨 + 实时日志流）──────────────────
        def on_run(audio_path, model, sel_preset, sr, bd, fmt, ch, aac_br, prec, lfe, ln,
                   existing_stems_path, existing_stems_label, prog=gr.Progress()):
            use_stems = bool(existing_stems_path)
            if not audio_path and not use_stems:
                yield gr.update(value="⚠️ 请上传音频或加载已有分轨"), "", None, "", gr.update(value="🚀 开始制作", interactive=True)
                return

            # 清空旧状态，按钮变「处理中」并禁用
            yield (gr.update(value="⏳ 处理中…"),
                   gr.update(value=""),
                   gr.update(value=None),
                   "",
                   gr.update(value="⏳ 处理中…", interactive=False))

            # 自动适配模型
            if use_stems and existing_stems_label:
                si = get_stem_info_by_label(existing_stems_label)
                if si:
                    model = si["model"]

            from threading import Thread
            import time as _time_mod

            latest_logs = [""]
            final_result = [None]
            thread_error = [None]
            pipeline_state_ref = [None]  # 暴露 state 供主线程读取 ETA

            # 记录上传的 Gradio 临时文件路径，完成后清理
            gradio_upload_path = None
            if audio_path and not str(audio_path).startswith(str(SCRIPT_DIR)):
                gradio_upload_path = Path(audio_path)

            def log_callback(text):
                latest_logs[0] = text

            def worker():
                try:
                    path, logs = run_pipeline(
                        audio_path, sel_preset, model, sr, bd, fmt, ch,
                        aac_br, prec, lfe, ln,
                        existing_stems_dir=existing_stems_path,
                        progress=prog,
                        on_log=log_callback,
                        _state_ref=pipeline_state_ref,
                    )
                    final_result[0] = (path, logs)
                except Exception as e:
                    thread_error[0] = e

            t = Thread(target=worker, daemon=True)
            t.start()

            # 轮询日志，实时 yield 到 UI
            last_yielded = ""
            last_eta_update = 0
            while t.is_alive():
                current = latest_logs[0]
                if current != last_yielded:
                    last_yielded = current
                    last_eta_update = _time_mod.time()
                    yield (gr.update(value="⏳ 处理中…"),
                           gr.update(value=current),
                           None,
                           "",
                           gr.update(value="⏳ 处理中…", interactive=False))
                elif pipeline_state_ref[0] and (_time_mod.time() - last_eta_update) > 10:
                    # 每 10 秒刷新一次 ETA 倒计时，让用户看到变化
                    state = pipeline_state_ref[0]
                    eta_line = state.get_eta_line()
                    if eta_line and not current.endswith(eta_line.split("后完成")[0] + "后完成" if "后完成" in eta_line else ""):
                        # 追加倒计时到显示日志
                        display = current + "\n" + eta_line
                        last_yielded = display
                        last_eta_update = _time_mod.time()
                        yield (gr.update(value="⏳ 处理中…"),
                               gr.update(value=display),
                               None,
                               "",
                               gr.update(value="⏳ 处理中…", interactive=False))
                _time_mod.sleep(0.3)

            t.join(timeout=5)

            # 清理上传的 Gradio 临时文件
            if gradio_upload_path and gradio_upload_path.exists():
                try: gradio_upload_path.unlink(missing_ok=True)
                except: pass

            # 最终输出（成功或失败）
            if thread_error[0]:
                err_msg = str(thread_error[0])
                yield (gr.update(value=f"❌ 错误：{err_msg}"),
                       latest_logs[0],
                       None,
                       err_msg,
                       gr.update(value="🚀 开始制作", interactive=True))
                return

            final_path, final_logs = final_result[0]
            save_config({"model":model,"preset":sel_preset,"sample_rate":sr,"bit_depth":bd,
                         "output_format":fmt,"channel_config":ch,"aac_bitrate":aac_br,
                         "precision":prec,"lfe_freq":lfe,"loudnorm":ln})
            yield (gr.update(value="### ✅ 完成！"),
                   final_logs,
                   gr.update(value=final_path),
                   f"**输出:** `{final_path}`",
                   gr.update(value="🚀 开始制作", interactive=True))

        run_btn.click(fn=on_run,
            inputs=[audio_input, model_select, preset, sample_rate, bit_depth,
                    output_format, channel_config, aac_bitrate, precision, lfe_freq, loudnorm,
                    loaded_stems_path, loaded_stems_label],
            outputs=[status, log_output, output_audio, output_info, run_btn],
            show_progress="hidden")

    return demo

def main():
    """WEP WebUI 入口 —— 供 pip 包和命令行调用"""
    demo = build_ui()
    import tempfile as _tempfile_mod
    demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True,
                allowed_paths=[str(OUTPUT_DIR),str(SCRIPT_DIR),_tempfile_mod.gettempdir()],
                css=CSS, theme=gr.themes.Soft())

if __name__ == "__main__":
    main()
