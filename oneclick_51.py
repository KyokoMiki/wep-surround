#!/usr/bin/env python3
"""
一键环绕声制作流水线 - 整合版
MP3/WAV/FLAC -> 5.1 FLAC @ 48kHz
Demucs 分离 + 上混一气呵成，内存中处理，无需中间文件

使用方法:
    python oneclick_51.py "音频文件.mp3"
    python oneclick_51.py "音频文件.mp3" -p Music -o "输出.flac"
"""

import os
import sys
import argparse
import numpy as np
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="5.1 Surround Upmix Pipeline (Integrated)")
    parser.add_argument("input_file", help="Input audio file (MP3/WAV/FLAC)")
    parser.add_argument("-p", "--preset", choices=["Music", "Movie", "Anime", "PLIIx"], 
                       default="Music", help="Processing preset (default: Music)")
    parser.add_argument("-o", "--output", help="Output FLAC file path")
    parser.add_argument("-m", "--model", default="htdemucs", 
                       help="Demucs model name (default: htdemucs, faster than htdemucs_ft)")
    
    args = parser.parse_args()
    
    # 延迟导入重型库
    import torch
    import soundfile as sf
    from scipy.signal import butter, filtfilt, resample_poly
    
    input_file = Path(args.input_file)
    if not input_file.exists():
        print(f"Error: File not found - {input_file}")
        sys.exit(1)
    
    input_file = input_file.resolve()
    filename = input_file.stem
    
    # 默认输出路径
    if args.output:
        output_file = Path(args.output)
    else:
        output_dir = Path.home() / "Music" / "Final_5.1"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{filename}.5.1.flac"
    
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 50)
    print("  5.1 Surround Upmix Pipeline (Integrated)")
    print("=" * 50)
    print(f"  Input:  {input_file}")
    print(f"  Output: {output_file}")
    print(f"  Model:  {args.model}")
    print(f"  Preset: {args.preset}")
    print("=" * 50)
    print()
    
    # 检查 GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print()
    
    # ========================================
    # Step 1: Demucs 分离 (直接在内存中处理)
    # ========================================
    print("[Step 1/2] AI Source Separation (Demucs)...")
    
    from demucs import pretrained
    from demucs.apply import apply_model
    from demucs.audio import AudioFile
    
    print(f"  Loading model: {args.model}")
    model = pretrained.get_model(args.model)
    model.to(device)
    model.eval()
    
    print(f"  Loading audio...")
    audio = AudioFile(str(input_file)).read(streams=0, samplerate=44100, channels=2)
    audio = audio.to(device)
    
    print(f"  Separating... (GPU acceleration)")
    with torch.no_grad():
        ref = audio.mean(0)
        audio_centered = audio - ref.mean()
        sources = apply_model(model, audio_centered[None], progress=True)[0]
        sources = sources + ref.mean()
    
    # 获取 stem 名称和转换到 numpy
    stem_names = model.sources
    stems = {}
    for i, name in enumerate(stem_names):
        stems[name] = sources[i].cpu().numpy()
    
    sample_rate = 44100
    print(f"  Separated {len(stems)} stems: {list(stems.keys())}")
    
    # 释放 GPU 内存
    del model, sources, audio, audio_centered
    if device == "cuda":
        torch.cuda.empty_cache()
    
    # ========================================
    # Step 2: 5.1 上混 (内存中处理)
    # ========================================
    print()
    print("[Step 2/2] 5.1 Surround Upmix...")
    
    # 预设参数
    presets = {
        "Music": {"delay_ms": 15, "center_gain": 1.2},
        "Movie": {"delay_ms": 10, "center_gain": 1.3},
        "Anime": {"delay_ms": 12, "center_gain": 1.4},
        "PLIIx": {"delay_ms": 20, "center_gain": 1.2},
    }
    params = presets.get(args.preset, presets["Music"])
    
    # 获取 stems
    vocals = stems.get("vocals", np.zeros((2, 1000)))
    drums = stems.get("drums", np.zeros_like(vocals))
    bass = stems.get("bass", np.zeros_like(vocals))
    other = stems.get("other", np.zeros_like(vocals))
    
    print(f"  Creating FL/FR (front channels)...")
    # FL, FR - 前方左右
    fl = 0.3 * vocals[0] + 0.25 * drums[0] + 0.25 * bass[0] + 0.2 * other[0]
    fr = 0.3 * vocals[1] + 0.25 * drums[1] + 0.25 * bass[1] + 0.2 * other[1]
    
    print(f"  Creating FC (center channel)...")
    # FC - 中置 (人声为主)
    fc = params["center_gain"] * (vocals[0] + vocals[1]) / 2
    
    print(f"  Creating LFE (low frequency)...")
    # LFE - 低音 (bass + drums 低频)
    nyquist = sample_rate / 2
    cutoff = 80 / nyquist
    b, a = butter(2, cutoff, btype='low')
    bass_low = filtfilt(b, a, (bass[0] + bass[1]) / 2)
    drums_low = filtfilt(b, a, (drums[0] + drums[1]) / 2)
    lfe = 1.5 * bass_low + 0.8 * drums_low
    
    print(f"  Creating Ls/Rs (surround channels) with {params['delay_ms']}ms delay...")
    # Ls, Rs - 环绕左右
    delay_samples = int(params["delay_ms"] * sample_rate / 1000)
    
    ls_base = 0.5 * drums[0] + 0.5 * other[0]
    rs_base = 0.5 * drums[1] + 0.5 * other[1]
    
    if delay_samples > 0:
        ls = np.concatenate([np.zeros(delay_samples), ls_base[:-delay_samples]])
        rs = np.concatenate([np.zeros(delay_samples), rs_base[:-delay_samples]])
    else:
        ls, rs = ls_base, rs_base
    
    # 组合为 5.1 (FL, FR, FC, LFE, Ls, Rs)
    print(f"  Combining to 5.1 multichannel...")
    audio_51 = np.stack([fl, fr, fc, lfe, ls, rs], axis=0)
    
    # 重采样到 48kHz
    target_sr = 48000
    if sample_rate != target_sr:
        print(f"  Resampling to {target_sr} Hz...")
        gcd = np.gcd(target_sr, sample_rate)
        up = target_sr // gcd
        down = sample_rate // gcd
        
        resampled = []
        for i in range(6):
            resampled.append(resample_poly(audio_51[i], up, down))
        audio_51 = np.array(resampled)
        sample_rate = target_sr
    
    # 响度归一化 (EBU R128 简化版)
    print(f"  Normalizing loudness (EBU R128)...")
    rms = np.sqrt(np.mean(audio_51 ** 2))
    target_rms = 10 ** (-14 / 20)  # -14 dBFS
    gain = target_rms / (rms + 1e-10)
    
    # 限制增益避免爆音
    peak = np.max(np.abs(audio_51))
    max_gain = 0.95 / (peak + 1e-10)
    gain = min(gain, max_gain)
    
    audio_51 = audio_51 * gain
    
    # 写入文件
    print()
    print(f"  Writing output: {output_file}")
    audio_51 = audio_51.T.astype(np.float32)  # 转置为 (samples, channels)
    sf.write(str(output_file), audio_51, sample_rate, format="FLAC", subtype="PCM_24")
    
    # 完成
    size_mb = output_file.stat().st_size / (1024 * 1024)
    print()
    print("=" * 50)
    print("  Done!")
    print("=" * 50)
    print(f"  Output: {output_file}")
    print(f"  Size:   {size_mb:.2f} MB")
    print(f"  Format: 5.1 FLAC @ {sample_rate} Hz")
    print("=" * 50)

if __name__ == "__main__":
    main()
