#!/usr/bin/env python3
"""
5.1 环绕声上混脚本 v2
将 Demucs 分离的 4 stems 混合为 5.1 FLAC @ 48kHz
优化音量平衡
"""

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path

def run_ffmpeg(args, description=""):
    """运行 ffmpeg 命令"""
    cmd = ["ffmpeg", "-y", "-v", "error"] + args
    print(f"  [FFmpeg] {description}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Error: {result.stderr}")
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    return True

def upmix_to_51(stems_dir, output_file, preset="Music"):
    """
    将 4 stems 上混为 5.1 环绕声
    
    5.1 通道布局: FL FR FC LFE Ls Rs
    
    优化后的路由:
    - FL/FR: 所有 stems 混合，保持原始能量
    - FC: 人声 + 少量其他
    - LFE: Bass 低频 (<80Hz)
    - Ls/Rs: Drums + Other 环绕效果
    """
    stems_path = Path(stems_dir)
    
    # 检查 stems 文件
    stems = {}
    for name in ["vocals", "drums", "bass", "other"]:
        for ext in [".wav", ".flac"]:
            f = stems_path / f"{name}{ext}"
            if f.exists():
                stems[name] = str(f)
                break
    
    if len(stems) < 4:
        missing = [n for n in ["vocals", "drums", "bass", "other"] if n not in stems]
        raise FileNotFoundError(f"Missing stems: {missing}")
    
    print(f"Found stems:")
    for name, path in stems.items():
        print(f"  {name}: {path}")
    
    # 预设参数
    presets = {
        "Music": {"delay_ms": 15, "center_db": 1},
        "Movie": {"delay_ms": 10, "center_db": 2},
        "Anime": {"delay_ms": 12, "center_db": 3},
        "PLIIx": {"delay_ms": 20, "center_db": 1},
    }
    params = presets.get(preset, presets["Music"])
    
    # 创建临时目录
    temp_dir = stems_path.parent / "_temp_upmix"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(exist_ok=True)
    
    try:
        print("\n[Step 1] Creating individual channels...")
        
        # FL - 前左 (所有 stems 左声道)
        fl_temp = temp_dir / "FL.wav"
        run_ffmpeg([
            "-i", stems["vocals"],
            "-i", stems["drums"],
            "-i", stems["bass"],
            "-i", stems["other"],
            "-filter_complex",
            "[0:a]pan=mono|c0=c0,volume=1.0[v];"
            "[1:a]pan=mono|c0=c0,volume=1.0[d];"
            "[2:a]pan=mono|c0=c0,volume=1.0[b];"
            "[3:a]pan=mono|c0=c0,volume=0.8[o];"
            "[v][d][b][o]amix=inputs=4:duration=longest:normalize=0:weights=0.3 0.25 0.25 0.2",
            "-ar", "48000",
            "-c:a", "pcm_s24le", str(fl_temp)
        ], "Create FL (front left)")
        
        # FR - 前右 (所有 stems 右声道)
        fr_temp = temp_dir / "FR.wav"
        run_ffmpeg([
            "-i", stems["vocals"],
            "-i", stems["drums"],
            "-i", stems["bass"],
            "-i", stems["other"],
            "-filter_complex",
            "[0:a]pan=mono|c0=c1,volume=1.0[v];"
            "[1:a]pan=mono|c0=c1,volume=1.0[d];"
            "[2:a]pan=mono|c0=c1,volume=1.0[b];"
            "[3:a]pan=mono|c0=c1,volume=0.8[o];"
            "[v][d][b][o]amix=inputs=4:duration=longest:normalize=0:weights=0.3 0.25 0.25 0.2",
            "-ar", "48000",
            "-c:a", "pcm_s24le", str(fr_temp)
        ], "Create FR (front right)")
        
        # FC - 中置 (人声为主，提升增益)
        fc_temp = temp_dir / "FC.wav"
        center_gain = 1.2 + (params["center_db"] * 0.1)
        run_ffmpeg([
            "-i", stems["vocals"],
            "-i", stems["other"],
            "-filter_complex",
            f"[0:a]pan=mono|c0=0.5*c0+0.5*c1,volume={center_gain}[v];"
            "[1:a]pan=mono|c0=0.5*c0+0.5*c1,volume=0.3[o];"
            "[v][o]amix=inputs=2:duration=longest:normalize=0:weights=0.8 0.2",
            "-ar", "48000",
            "-c:a", "pcm_s24le", str(fc_temp)
        ], "Create FC (center) - vocals boosted")
        
        # LFE - 低音 (bass + drums 低频)
        lfe_temp = temp_dir / "LFE.wav"
        run_ffmpeg([
            "-i", stems["bass"],
            "-i", stems["drums"],
            "-filter_complex",
            "[0:a]lowpass=f=80,volume=1.5,pan=mono|c0=0.5*c0+0.5*c1[b];"
            "[1:a]lowpass=f=80,volume=0.8,pan=mono|c0=0.5*c0+0.5*c1[d];"
            "[b][d]amix=inputs=2:duration=longest:normalize=0",
            "-ar", "48000",
            "-c:a", "pcm_s24le", str(lfe_temp)
        ], "Create LFE - bass + drums low-pass 80Hz")
        
        # Ls - 环绕左 (drums + other)
        ls_temp = temp_dir / "Ls.wav"
        delay_ms = params["delay_ms"]
        run_ffmpeg([
            "-i", stems["drums"],
            "-i", stems["other"],
            "-filter_complex",
            f"[0:a]pan=mono|c0=c0,volume=0.7,adelay={delay_ms}|{delay_ms}[d];"
            f"[1:a]pan=mono|c0=c0,volume=0.6,adelay={delay_ms}|{delay_ms}[o];"
            "[d][o]amix=inputs=2:duration=longest:normalize=0:weights=0.5 0.5",
            "-ar", "48000",
            "-c:a", "pcm_s24le", str(ls_temp)
        ], f"Create Ls (surround left) - {delay_ms}ms delay")
        
        # Rs - 环绕右 (drums + other)
        rs_temp = temp_dir / "Rs.wav"
        run_ffmpeg([
            "-i", stems["drums"],
            "-i", stems["other"],
            "-filter_complex",
            f"[0:a]pan=mono|c0=c1,volume=0.7,adelay={delay_ms}|{delay_ms}[d];"
            f"[1:a]pan=mono|c0=c1,volume=0.6,adelay={delay_ms}|{delay_ms}[o];"
            "[d][o]amix=inputs=2:duration=longest:normalize=0:weights=0.5 0.5",
            "-ar", "48000",
            "-c:a", "pcm_s24le", str(rs_temp)
        ], f"Create Rs (surround right) - {delay_ms}ms delay")
        
        # Step 2: 合并为 5.1 并应用最终增益归一化
        print("\n[Step 2] Combining to 5.1 with loudness normalization...")
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 合并并应用 loudnorm 滤镜进行响度归一化
        run_ffmpeg([
            "-i", str(fl_temp),
            "-i", str(fr_temp),
            "-i", str(fc_temp),
            "-i", str(lfe_temp),
            "-i", str(ls_temp),
            "-i", str(rs_temp),
            "-filter_complex",
            "[0:a][1:a][2:a][3:a][4:a][5:a]amerge=inputs=6,loudnorm=I=-14:TP=-1:LRA=11[aout]",
            "-map", "[aout]",
            "-c:a", "flac",
            "-compression_level", "8",
            str(output_file)
        ], "Merge to 5.1 FLAC with loudness normalization (EBU R128)")
        
        # 获取文件大小
        output_size = output_path.stat().st_size / (1024 * 1024)
        print(f"\n{'='*50}")
        print(f"  Done!")
        print(f"{'='*50}")
        print(f"  Output: {output_file}")
        print(f"  Size: {output_size:.2f} MB")
        print(f"{'='*50}")
        
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print(f"\n  Temp directory cleaned")

def main():
    parser = argparse.ArgumentParser(description="5.1 Surround Upmix from Demucs stems (v2 - optimized volume)")
    parser.add_argument("stems_dir", help="Directory containing bass.wav, drums.wav, other.wav, vocals.wav")
    parser.add_argument("-o", "--output", help="Output FLAC file path")
    parser.add_argument("-p", "--preset", choices=["Music", "Movie", "Anime", "PLIIx"], 
                       default="Music", help="Processing preset (default: Music)")
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.stems_dir):
        print(f"Error: Directory not found: {args.stems_dir}")
        sys.exit(1)
    
    if not args.output:
        stems_path = Path(args.stems_dir)
        track_name = stems_path.name
        output_dir = stems_path.parent.parent / "Final_5.1"
        output_dir.mkdir(exist_ok=True)
        args.output = str(output_dir / f"{track_name}.5.1.flac")
    
    print(f"{'='*50}")
    print(f"  5.1 Surround Upmixer v2 (Optimized Volume)")
    print(f"{'='*50}")
    print(f"  Input:  {args.stems_dir}")
    print(f"  Output: {args.output}")
    print(f"  Preset: {args.preset}")
    print(f"{'='*50}\n")
    
    upmix_to_51(args.stems_dir, args.output, args.preset)

if __name__ == "__main__":
    main()
