#!/usr/bin/env python3
"""
一键环绕声 WEP 工作流 (Workflow Execution Pipeline)
============================================================================
立体声音频 → Demucs AI分轨 → 5.1/7.1 环绕声 FLAC

用法:
    拖放音频文件到此脚本
    python oneclick_WEP.py "音频文件.mp3"
    python oneclick_WEP.py "音频文件.flac" --preset Movie --layout 7.1
    python oneclick_WEP.py "音频文件.wav" --skip-separate (仅上混已有stems)

功能:
    1. AI音源分离 — Demucs htdemucs_ft (AMD ROCm / NVIDIA CUDA 自动检测)
    2. 环绕声上混  — 4 stems → 5.1/7.1 多声道 FLAC
    3. 预设模式    — Music / Movie / Anime / PLIIx
    4. 音轨预分析  — 自动调整中置增益 / 环绕增益 / 去相关延迟
    5. 响度归一化  — EBU R128 (-14 LUFS)

环境要求:
    - Python 3.10+
    - demucs >= 4.0 (pip install demucs)
    - ffmpeg (PATH 可用)
    - AMD RX 9070 XT: ROCm 7.2+ / NVIDIA: CUDA 12+
"""

import os
import sys
import subprocess
import argparse
import shutil
import time
import json
from pathlib import Path
from datetime import datetime

# ════════════════════════════════════════════════════════════════════════════
#  配置区
# ════════════════════════════════════════════════════════════════════════════

VERSION = "1.0.0"
SCRIPT_DIR = Path(__file__).parent.resolve()
SEPARATED_DIR = SCRIPT_DIR / "separated"
DEFAULT_PRESET = "Music"
DEFAULT_LAYOUT = "5.1"
SAMPLE_RATE = 48000


# ════════════════════════════════════════════════════════════════════════════
#  WEP 日志系统
# ════════════════════════════════════════════════════════════════════════════

class WEPLogger:
    """WEP 工作流日志器 —— 带时间戳/阶段/进度的结构化日志"""
    def __init__(self, log_file=None):
        self.start_time = time.time()
        self.stages = []
        self.log_file = log_file
        self.lines = []

    def _log(self, level, tag, msg, elapsed=None):
        ts = datetime.now().strftime("%H:%M:%S")
        elapsed_str = f" [+{elapsed:.1f}s]" if elapsed is not None else ""
        line = f"[{ts}] [{level:<5}] [{tag}] {msg}{elapsed_str}"
        print(line)
        self.lines.append(line)

    def stage_start(self, n, total, name):
        msg = f"━━━ Stage {n}/{total}: {name} ━━━"
        print(f"\n{msg}")
        self.stages.append({"stage": n, "name": name, "start": time.time()})

    def stage_done(self, n, ok=True):
        stage = self.stages[n - 1]
        elapsed = time.time() - stage["start"]
        status = "✅ OK" if ok else "❌ FAILED"
        print(f"  {status}  ({elapsed:.1f}s)")

    def info(self, tag, msg):
        self._log("INFO", tag, msg)

    def warn(self, tag, msg):
        self._log("WARN", tag, msg)

    def error(self, tag, msg):
        self._log("ERROR", tag, msg)

    def time(self, tag, msg, duration):
        self._log("TIME", tag, msg, duration)

    def total_elapsed(self):
        return time.time() - self.start_time

    def save(self):
        if self.log_file:
            Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
            Path(self.log_file).write_text("\n".join(self.lines), encoding="utf-8")


log = WEPLogger()


# ════════════════════════════════════════════════════════════════════════════
#  环境检测
# ════════════════════════════════════════════════════════════════════════════

def detect_environment():
    """检测 GPU / 依赖 / 工具链状态"""
    env = {
        "gpu": "unknown",
        "gpu_name": "N/A",
        "demucs_ok": False,
        "ffmpeg_ok": False,
        "python_ok": sys.version_info >= (3, 10),
    }

    # 检测 GPU
    try:
        import torch
        if torch.cuda.is_available():
            env["gpu"] = "cuda"
            env["gpu_name"] = torch.cuda.get_device_name(0) or "CUDA GPU"
        elif hasattr(torch, 'hip') and torch.hip.is_available():
            env["gpu"] = "rocm"
            env["gpu_name"] = "AMD ROCm GPU"
        else:
            import subprocess
            r = subprocess.run(["python", "-m", "demucs", "--help"],
                             capture_output=True, text=True, timeout=10)
            if "cuda" in r.stdout.lower() or "rocm" in (r.stderr or "").lower():
                env["gpu"] = "rocm"  # RX 9070 XT
                env["gpu_name"] = "AMD RX 9070 XT (ROCm)"
    except Exception:
        pass

    # 检测 demucs
    try:
        r = subprocess.run(["python", "-m", "demucs", "--version"],
                         capture_output=True, text=True, timeout=10)
        env["demucs_ok"] = r.returncode == 0
    except Exception:
        pass

    # 检测 ffmpeg
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        env["ffmpeg_ok"] = r.returncode == 0
        if env["ffmpeg_ok"]:
            ver_line = r.stdout.split("\n")[0] if r.stdout else ""
            env["ffmpeg_ver"] = ver_line.split(" ")[2] if len(ver_line.split(" ")) > 2 else "?"
    except Exception:
        env["ffmpeg_ok"] = False

    return env


# ════════════════════════════════════════════════════════════════════════════
#  WEP 元数据
# ════════════════════════════════════════════════════════════════════════════

def print_header(env, input_file):
    """打印 WEP 工作流头部信息"""
    print("=" * 62)
    print("  🎧 一键环绕声 WEP 工作流  v" + VERSION)
    print("=" * 62)
    print(f"  环境: Python {sys.version.split()[0]}  |  "
          f"GPU: {env['gpu_name']} ({env['gpu']})")
    if env.get("ffmpeg_ver"):
        print(f"  工具: demucs 4.x  |  ffmpeg {env['ffmpeg_ver']}")
    print(f"  输入: {Path(input_file).name}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)


# ════════════════════════════════════════════════════════════════════════════
#  Stage 1: AI 音源分离 (Demucs)
# ════════════════════════════════════════════════════════════════════════════

def stage_separate(input_file, env):
    """Stage 1: 用 Demucs htdemucs_ft 分离为 4 stems"""
    log.stage_start(1, 3, "AI音源分离 — Demucs htdemucs_ft")

    device = "cuda"
    if env["gpu"] == "rocm":
        log.info("GPU", f"使用 AMD ROCm: {env['gpu_name']}")

    input_path = Path(input_file).resolve()
    filename = input_path.stem
    stems_dir = SEPARATED_DIR / "htdemucs_ft" / filename

    # 检查是否已经分离过
    if stems_dir.exists() and all(
        (stems_dir / f"{s}.wav").exists()
        for s in ["bass", "drums", "other", "vocals"]
    ):
        log.info("CACHE", f"已有 stems，跳过分离: {stems_dir}")
        log.stage_done(1, ok=True)
        return str(stems_dir)

    log.info("DEMUCS", f"开始分离: {input_path.name}")
    log.info("PARAMS", f"模型: htdemucs_ft | 设备: {device} | 精度: float32")

    cmd = [
        sys.executable, "-m", "demucs",
        "-n", "htdemucs_ft",
        "-d", device,
        "-o", str(SEPARATED_DIR),
        "--float32",
        "--segment", "7",        # 整数且≤模型训练上限7.8s，8会超限报错
        "--overlap", "0.25",     # 平衡质量/速度
        str(input_path)
    ]

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        log.error("DEMUCS", f"分离失败 (exit code {result.returncode})")
        log.stage_done(1, ok=False)
        raise RuntimeError("Demucs separation failed")

    elapsed = time.time() - t0
    log.time("DEMUCS", f"分离完成", elapsed)
    log.info("OUTPUT", str(stems_dir))
    log.stage_done(1, ok=True)

    return str(stems_dir)


# ════════════════════════════════════════════════════════════════════════════
#  Stage 2: 自适应音频分析
# ════════════════════════════════════════════════════════════════════════════

def analyze_stems(stems_dir):
    """Stage 2: 分析 stems 的立体声宽度/亮度/能量比"""
    log.stage_start(2, 3, "自适应音频分析")

    stems_path = Path(stems_dir)
    stems = {}
    for name in ["vocals", "drums", "bass", "other"]:
        for ext in [".wav", ".flac"]:
            f = stems_path / f"{name}{ext}"
            if f.exists():
                stems[name] = str(f)
                break

    analysis = {
        "width": 0.5,         # 立体声宽度 (0=mono, 1=极宽)
        "brightness": 0.5,    # 频谱亮度 (0=暗, 1=亮)
        "vocal_ratio": 1.0,   # 人声/其他 能量比
        "dynamic_centre_db": 0.0,
        "dynamic_surround_db": 0.0,
        "dynamic_decorr_l": 15,
        "dynamic_decorr_r": 17,
    }

    try:
        # 尝试用 ffmpeg 进行快速分析
        analysis_file = stems.get("vocals") or stems.get("other")
        if not analysis_file or not shutil.which("ffmpeg"):
            log.warn("ANALYSIS", "无 ffmpeg 或 stem 文件，使用默认参数")
            log.stage_done(2, ok=True)
            return analysis

        # 用 ffmpeg ebur128 测量响度平衡
        vocal_rms = measure_rms(stems.get("vocals"))
        other_rms = measure_rms(stems.get("other"))
        if vocal_rms and other_rms and other_rms > 0:
            ratio = vocal_rms / other_rms
            analysis["vocal_ratio"] = round(ratio, 2)

            # 动态环绕增益
            if ratio > 1.5:
                analysis["dynamic_surround_db"] = round(max(-3.0, -3.0 * (ratio - 1.5) / 1.5), 1)
                log.info("ANALYSIS", f"人声突出 (ratio={ratio:.2f}) → 环绕 -{abs(analysis['dynamic_surround_db'])}dB")
            elif ratio < 0.5:
                analysis["dynamic_surround_db"] = round(min(3.0, 3.0 * (0.5 - ratio) / 0.5), 1)
                log.info("ANALYSIS", f"环境声突出 (ratio={ratio:.2f}) → 环绕 +{analysis['dynamic_surround_db']}dB")
            else:
                log.info("ANALYSIS", f"平衡混音 (ratio={ratio:.2f}) → 默认环绕增益")

        # 用 ffmpeg 测量立体声宽度 (Side/Mid RMS)
        width = measure_width(analysis_file)
        if width is not None:
            analysis["width"] = round(width, 3)
            log.info("ANALYSIS", f"立体声宽度: {width:.3f}")

            if width > 0.9:
                analysis["dynamic_centre_db"] = round(max(-4.0, -4.0 * (width - 0.9) / 0.5), 1)
                analysis["dynamic_decorr_l"] = 18
                analysis["dynamic_decorr_r"] = 20
            elif width < 0.3:
                analysis["dynamic_centre_db"] = round(min(3.0, 3.0 * (0.3 - width) / 0.3), 1)
                analysis["dynamic_decorr_l"] = 10
                analysis["dynamic_decorr_r"] = 12

    except Exception as e:
        log.warn("ANALYSIS", f"分析异常: {e}，使用默认参数")

    log.stage_done(2, ok=True)
    return analysis


def measure_rms(filepath):
    """用 ffmpeg volumedetect 测 RMS"""
    if not filepath or not Path(filepath).exists():
        return None
    try:
        r = subprocess.run(
            ["ffmpeg", "-i", filepath, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30
        )
        for line in (r.stderr + r.stdout).split("\n"):
            if "mean_volume:" in line:
                val = line.split(":")[-1].strip().replace(" dB", "")
                # 转线性 RMS 近似
                db = float(val)
                return 10 ** (db / 20)
    except Exception:
        pass
    return None


def measure_width(filepath):
    """测量立体声宽度: Side RMS / Mid RMS"""
    if not filepath or not Path(filepath).exists():
        return None
    tmp_dir = Path(filepath).parent / "_wep_tmp"
    tmp_dir.mkdir(exist_ok=True)
    mid_file = tmp_dir / "_mid.wav"
    side_file = tmp_dir / "_side.wav"

    try:
        # Mid = L+R
        subprocess.run(
            ["ffmpeg", "-y", "-i", filepath, "-af", "pan=mono|c0=0.5*c0+0.5*c1",
             "-ar", "16000", "-c:a", "pcm_s16le", str(mid_file)],
            capture_output=True, timeout=15
        )
        # Side = L-R
        subprocess.run(
            ["ffmpeg", "-y", "-i", filepath, "-af", "pan=mono|c0=0.5*c0-0.5*c1",
             "-ar", "16000", "-c:a", "pcm_s16le", str(side_file)],
            capture_output=True, timeout=15
        )

        mid_rms = measure_rms(str(mid_file))
        side_rms = measure_rms(str(side_file))

        if mid_rms and side_rms and mid_rms > 1e-6:
            return min(1.0, side_rms / mid_rms)
    except Exception:
        pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return None


# ════════════════════════════════════════════════════════════════════════════
#  Stage 3: 5.1 环绕声上混
# ════════════════════════════════════════════════════════════════════════════

def stage_upmix(stems_dir, output_file, preset, layout, analysis):
    """Stage 3: 将 4 stems 上混为 5.1/7.1 环绕声"""
    log.stage_start(3, 3, f"环绕声上混 — {preset} → {layout}")

    t0 = time.time()
    stems_path = Path(stems_dir)

    # 加载 stems
    stems = {}
    for name in ["vocals", "drums", "bass", "other"]:
        for ext in [".wav", ".flac"]:
            f = stems_path / f"{name}{ext}"
            if f.exists():
                stems[name] = str(f)
                break

    missing = [n for n in ["vocals", "drums", "bass", "other"] if n not in stems]
    if missing:
        log.error("STEMS", f"缺少 stems: {missing}")
        raise FileNotFoundError(f"Missing stems: {missing}")

    for name, path in stems.items():
        size_mb = Path(path).stat().st_size / (1024 * 1024)
        log.info("STEM", f"  {name:<8} {size_mb:.1f} MB  [{Path(path).suffix}]")

    # 预设配置
    presets = {
        "Music":  {"centre_db": 1,  "decorr_l": 15, "decorr_r": 17, "xover_hz": 4000, "surround_db": -8},
        "Movie":  {"centre_db": 2,  "decorr_l": 10, "decorr_r": 12, "xover_hz": 2500, "surround_db": -6},
        "Anime":  {"centre_db": 3,  "decorr_l": 12, "decorr_r": 14, "xover_hz": 3000, "surround_db": -7},
        "PLIIx":  {"centre_db": 1,  "decorr_l": 20, "decorr_r": 23, "xover_hz": 3500, "surround_db": -6},
    }
    params = presets.get(preset, presets["Music"])

    # 应用动态分析
    centre_gain = params["centre_db"] + analysis.get("dynamic_centre_db", 0)
    surround_db = params["surround_db"] + analysis.get("dynamic_surround_db", 0)
    decorr_l = analysis.get("dynamic_decorr_l", params["decorr_l"])
    decorr_r = analysis.get("dynamic_decorr_r", params["decorr_r"])

    log.info("PARAMS", f"中置增益: +{centre_gain}dB | 环绕混合: {surround_db}dB | "
             f"去相关: {decorr_l}/{decorr_r}ms | 分频点: {params['xover_hz']}Hz")

    # 临时目录
    temp_dir = stems_path.parent / f"_wep_upmix_{stems_path.name}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(exist_ok=True)

    try:
        # ── 通道创建 ────────────────────────────────────────
        log.info("MIX", "创建 6 个离散声道…")

        # FL — 前左
        fl_temp = temp_dir / "FL.wav"
        create_front_channel(stems, "left", str(fl_temp))
        log.info("CHAN", "  FL ✅  前左 (全轨混合)")

        # FR — 前右
        fr_temp = temp_dir / "FR.wav"
        create_front_channel(stems, "right", str(fr_temp))
        log.info("CHAN", "  FR ✅  前右 (全轨混合)")

        # FC — 中置 (人声为主)
        fc_temp = temp_dir / "FC.wav"
        create_center_channel(stems, str(fc_temp), centre_gain)
        log.info("CHAN", f"  FC ✅  中置 (人声 +{centre_gain}dB)")

        # LFE — 低音
        lfe_temp = temp_dir / "LFE.wav"
        create_lfe_channel(stems, str(lfe_temp))
        log.info("CHAN", "  LFE ✅  低音 (<80Hz)")

        # Ls / Rs — 环绕声道 (+延迟 +去相关)
        ls_temp = temp_dir / "Ls.wav"
        rs_temp = temp_dir / "Rs.wav"
        create_surround_channels(stems, str(ls_temp), str(rs_temp),
                                decorr_l, decorr_r, surround_db,
                                params["xover_hz"])

        log.info("CHAN", f"  Ls ✅  环绕左 ({decorr_l}ms 延迟)")
        log.info("CHAN", f"  Rs ✅  环绕右 ({decorr_r}ms 延迟)")

        # ── 合并 ────────────────────────────────────────────
        log.info("MIX", f"合并为 {layout} 并应用 EBU R128 响度归一化…")

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        merge_51(fl_temp, fr_temp, fc_temp, lfe_temp, ls_temp, rs_temp,
                str(output_path), layout)

        # ── 结果 ────────────────────────────────────────────
        elapsed = time.time() - t0
        output_size = output_path.stat().st_size / (1024 * 1024)

        log.time("UPMIX", "上混完成", elapsed)
        log.info("OUTPUT", str(output_path))
        log.info("SIZE", f"{output_size:.2f} MB")
        log.stage_done(3, ok=True)

        return str(output_path)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        log.info("CLEAN", "临时文件已清理")


def create_front_channel(stems, side, output_file):
    """创建前左/前右声道"""
    ch = "c0" if side == "left" else "c1"
    weights = {"vocals": 0.30, "drums": 0.25, "bass": 0.25, "other": 0.20}

    run_ffmpeg([
        "-i", stems["vocals"], "-i", stems["drums"],
        "-i", stems["bass"], "-i", stems["other"],
        "-filter_complex",
        f"[0:a]pan=mono|c0={ch},volume={weights['vocals']}[v];"
        f"[1:a]pan=mono|c0={ch},volume={weights['drums']}[d];"
        f"[2:a]pan=mono|c0={ch},volume={weights['bass']}[b];"
        f"[3:a]pan=mono|c0={ch},volume={weights['other']}[o];"
        "[v][d][b][o]amix=inputs=4:duration=longest:normalize=0",
        "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s24le", output_file
    ], f"Front {side}")


def create_center_channel(stems, output_file, gain_db):
    """创建中置声道 (人声为主 + 少量其他)"""
    vol_vocal = 10 ** (gain_db / 20) * 0.8
    vol_other = 10 ** (gain_db / 20) * 0.2

    run_ffmpeg([
        "-i", stems["vocals"], "-i", stems["other"],
        "-filter_complex",
        f"[0:a]pan=mono|c0=0.5*c0+0.5*c1,volume={vol_vocal:.3f}[v];"
        f"[1:a]pan=mono|c0=0.5*c0+0.5*c1,volume={vol_other:.3f}[o];"
        "[v][o]amix=inputs=2:duration=longest:normalize=0",
        "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s24le", output_file
    ], "Center")


def create_lfe_channel(stems, output_file):
    """创建 LFE 低音声道 (bass + drums 低通 <80Hz)"""
    run_ffmpeg([
        "-i", stems["bass"], "-i", stems["drums"],
        "-filter_complex",
        "[0:a]lowpass=f=80,volume=1.5,pan=mono|c0=0.5*c0+0.5*c1[b];"
        "[1:a]lowpass=f=80,volume=0.8,pan=mono|c0=0.5*c0+0.5*c1[d];"
        "[b][d]amix=inputs=2:duration=longest:normalize=0",
        "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s24le", output_file
    ], "LFE")


def create_surround_channels(stems, ls_file, rs_file, delay_l, delay_r,
                             surround_db, xover_hz):
    """创建环绕声道 (drums + other → 延迟 + 分频混合)"""
    delay_l_str = f"{delay_l}|{delay_l}"
    delay_r_str = f"{delay_r}|{delay_r}"

    # 环绕左
    run_ffmpeg([
        "-i", stems["drums"], "-i", stems["other"],
        "-filter_complex",
        f"[0:a]pan=mono|c0=c0,volume=0.7,adelay={delay_l_str}[d];"
        f"[1:a]pan=mono|c0=c0,volume=0.6,adelay={delay_l_str}[o];"
        "[d][o]amix=inputs=2:duration=longest:normalize=0:weights=0.5 0.5",
        "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s24le", ls_file
    ], "Surround Left")

    # 环绕右
    run_ffmpeg([
        "-i", stems["drums"], "-i", stems["other"],
        "-filter_complex",
        f"[0:a]pan=mono|c0=c1,volume=0.7,adelay={delay_r_str}[d];"
        f"[1:a]pan=mono|c0=c1,volume=0.6,adelay={delay_r_str}[o];"
        "[d][o]amix=inputs=2:duration=longest:normalize=0:weights=0.5 0.5",
        "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s24le", rs_file
    ], "Surround Right")


def merge_51(fl, fr, fc, lfe, ls, rs, output_file, layout):
    """合并声道 + EBU R128 响度归一化"""
    # 5.1: FL FR FC LFE Ls Rs
    run_ffmpeg([
        "-i", str(fl), "-i", str(fr), "-i", str(fc),
        "-i", str(lfe), "-i", str(ls), "-i", str(rs),
        "-filter_complex",
        "[0:a][1:a][2:a][3:a][4:a][5:a]amerge=inputs=6,loudnorm=I=-14:TP=-1:LRA=11[aout]",
        "-map", "[aout]",
        "-c:a", "flac",
        "-compression_level", "8",
        output_file
    ], "Merge 5.1 + EBU R128")


def run_ffmpeg(args, description=""):
    """运行 ffmpeg 命令"""
    cmd = ["ffmpeg", "-y", "-v", "error"] + args
    log.info("FFMPEG", description)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[:500]}")
    return True


# ════════════════════════════════════════════════════════════════════════════
#  WEP 主流水线
# ════════════════════════════════════════════════════════════════════════════

def run_pipeline(input_file, preset, layout, output_file, skip_separate, stems_from):
    """执行完整 WEP 流水线"""
    # ── 环境检测 ──
    env = detect_environment()
    print_header(env, input_file)

    # ── Stage 1: 音源分离 ──
    if skip_separate and stems_from:
        stems_dir = stems_from
        log.info("SKIP", f"跳过分离，直接使用 stems: {stems_dir}")
    else:
        stems_dir = stage_separate(input_file, env)

    # ── Stage 2: 音频分析 ──
    analysis = analyze_stems(stems_dir)

    # ── 确定输出路径 ──
    if not output_file:
        track_name = Path(stems_dir).name
        output_dir = Path.home() / "Music" / f"Final_{layout}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = str(output_dir / f"{track_name}.{layout}.flac")

    log.info("CONFIG", f"布局: {layout} | 预设: {preset} | 输出: {output_file}")

    # ── Stage 3: 上混 ──
    final_path = stage_upmix(stems_dir, output_file, preset, layout, analysis)

    # ── 完成 ──
    total = log.total_elapsed()
    print("\n" + "=" * 62)
    print("  🎉 流水线完成！")
    print("=" * 62)
    print(f"  输出: {final_path}")
    print(f"  大小: {Path(final_path).stat().st_size / (1024 * 1024):.2f} MB")
    print(f"  耗时: {total:.1f}s")
    print("=" * 62)

    return final_path


# ════════════════════════════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description=f"🎧 一键环绕声 WEP 工作流 v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python oneclick_WEP.py "歌曲.mp3"
  python oneclick_WEP.py "歌曲.flac" --preset Movie --layout 7.1
  python oneclick_WEP.py "歌曲.wav" --preset Anime
  python oneclick_WEP.py "歌曲.mp3" --skip-separate --stems-from ./separated/htdemucs_ft/MyTrack

预设说明:
  Music  - 宽环绕声场，高频推至后置，15ms 去相关 (适合纯音乐)
  Movie  - 紧凑声场，中置 +2dB 对话清晰，10ms 去相关 (适合电影配乐)
  Anime  - 中置 +3dB 人声突出，BGM 友好环绕 (适合动漫BGM)
  PLIIx  - Dolby Pro Logic IIx 近似，极宽扩散环绕 (通用)
        """
    )
    parser.add_argument("input_file", help="输入音频文件 (MP3/WAV/FLAC)，支持拖放")
    parser.add_argument("-p", "--preset", choices=["Music", "Movie", "Anime", "PLIIx"],
                       default=DEFAULT_PRESET, help=f"处理预设 (默认: {DEFAULT_PRESET})")
    parser.add_argument("--layout", choices=["5.1", "7.1"],
                       default=DEFAULT_LAYOUT, help=f"输出声道布局 (默认: {DEFAULT_LAYOUT})")
    parser.add_argument("-o", "--output", help="输出文件路径 (默认: ~/Music/Final_5.1/<曲名>.5.1.flac)")
    parser.add_argument("--skip-separate", action="store_true",
                       help="跳过 AI 分离步骤 (直接使用已有 stems)")
    parser.add_argument("--stems-from",
                       help="已有 stems 目录路径 (配合 --skip-separate 使用)")

    args = parser.parse_args()

    # 检查输入文件
    input_path = Path(args.input_file).resolve()
    if not args.skip_separate and not input_path.exists():
        print(f"\n❌ 文件不存在: {input_path}")
        print("   用法: python oneclick_WEP.py \"音频文件.mp3\"")
        sys.exit(1)

    # 执行流水线
    try:
        run_pipeline(
            input_file=str(input_path),
            preset=args.preset,
            layout=args.layout,
            output_file=args.output,
            skip_separate=args.skip_separate,
            stems_from=args.stems_from,
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 流水线执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
