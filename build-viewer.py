#!/usr/bin/env python3
"""
360° CHARACTER VIEWER BUILD SCRIPT
===================================
One command. Video in, deployed viewer out.

ROTATION DETECTION LOGIC:
  Human figures are bilaterally symmetric. A 360° orbit produces
  a W-shaped SSIM curve vs frame 1: dips at the two profile views
  (~90° and ~270°), slight rise at back-of-head (~180°), and a
  strong return to ~1.0 at the loop point (~360°).

  The algorithm finds the 360° boundary by looking for where the
  SSIM returns closest to 1.0 in the final portion of the video.

Usage:
  python3 build-viewer.py <video> <character> [--deploy] [--frames N]
  python3 build-viewer.py <video> <character> --dry-run

Examples:
  python3 build-viewer.py /path/to/julie-v34.mp4 julie --deploy
  python3 build-viewer.py /path/to/mark.mp4 mark --frames 144 --deploy
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

# ════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════
DEFAULT_FRAMES = 192
TARGET_W = 1280
TARGET_H = 720
JPG_QUALITY = 92
SENSITIVITY = 0.4
DEPLOY_ROOT = Path("/var/www/roarofwinchester/360-viewer")
SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE = SCRIPT_DIR / "viewer" / "index.html"


# ════════════════════════════════════════════════════════════
# IMAGE SIMILARITY
# ════════════════════════════════════════════════════════════
def compute_ssim(path_a: str, path_b: str, size: int = 256) -> float:
    """Fast SSIM between two images, resized to `size` for speed."""
    i1 = np.array(Image.open(path_a).convert("L").resize((size, size)), dtype=np.float64)
    i2 = np.array(Image.open(path_b).convert("L").resize((size, size)), dtype=np.float64)
    mu1, mu2 = i1.mean(), i2.mean()
    s1_sq, s2_sq = i1.var(), i2.var()
    cov = ((i1 - mu1) * (i2 - mu2)).mean()
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    num = (2 * mu1 * mu2 + C1) * (2 * cov + C2)
    den = (mu1 ** 2 + mu2 ** 2 + C1) * (s1_sq + s2_sq + C2)
    return num / den


# ════════════════════════════════════════════════════════════
# VIDEO PROBING
# ════════════════════════════════════════════════════════════
def probe_video(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    fps_parts = stream["r_frame_rate"].split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
    duration = float(data["format"]["duration"])
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": fps,
        "fps_raw": stream["r_frame_rate"],
        "duration": duration,
        "total_frames": int(round(duration * fps)),
        "codec": stream.get("codec_name", "unknown"),
    }


# ════════════════════════════════════════════════════════════
# ROTATION ANALYSIS
# ════════════════════════════════════════════════════════════
def analyze_rotation(frames_dir: Path, total_frames: int) -> dict:
    """
    Detect rotation extent using SSIM curve analysis.

    For human 360° orbits, the SSIM vs frame 1 shows a W-pattern:
      - Dip 1 at ~90° (profile view)
      - Slight rise at ~180° (back of head, symmetric lighting)
      - Dip 2 at ~270° (other profile)
      - Return to ~1.0 at ~360° (loop complete)

    Algorithm:
      1. Scan SSIM across all frames
      2. Find the global minimum (deepest dip)
      3. Find the peak SSIM in the final 30% of the video
      4. If that peak > 0.90: clean loop, high confidence
      5. If peak > 0.75: probable loop, medium confidence
      6. If peak < 0.75: no loop, low confidence

    The 360° boundary = the frame in the final portion with
    the highest SSIM (closest visual match to frame 1).
    """
    ref = frames_dir / "frame_000001.jpg"
    if not ref.exists():
        raise FileNotFoundError(f"Reference frame not found: {ref}")

    # Sample ~80 frames evenly across the video
    n_samples = min(80, total_frames)
    step = max(1, total_frames // n_samples)
    indices = list(range(1, total_frames + 1, step))
    if total_frames not in indices:
        indices.append(total_frames)

    print(f"  Scanning {len(indices)} frames (step={step})...")

    curve = []
    for idx in indices:
        fpath = frames_dir / f"frame_{idx:06d}.jpg"
        if fpath.exists():
            s = compute_ssim(str(ref), str(fpath))
            curve.append((idx, s))

    ssim_vals = np.array([s for _, s in curve])
    frame_idxs = [i for i, _ in curve]

    # ── Find global minimum ──
    global_min_pos = int(np.argmin(ssim_vals))
    global_min_frame = frame_idxs[global_min_pos]
    global_min_ssim = ssim_vals[global_min_pos]

    # ── Find peak SSIM in final 30% of video ──
    tail_start = int(len(curve) * 0.70)
    tail_scores = ssim_vals[tail_start:]
    tail_indices = frame_idxs[tail_start:]

    if len(tail_scores) == 0:
        # Very short video, use last frame
        tail_peak_ssim = ssim_vals[-1]
        tail_peak_frame = frame_idxs[-1]
    else:
        tail_peak_pos = int(np.argmax(tail_scores))
        tail_peak_ssim = tail_scores[tail_peak_pos]
        tail_peak_frame = tail_indices[tail_peak_pos]

    # ── Fine-tune: dense scan around the tail peak ──
    fine_start = max(1, tail_peak_frame - step * 2)
    fine_end = min(total_frames, tail_peak_frame + step * 2)
    best_frame = tail_peak_frame
    best_ssim = tail_peak_ssim

    for idx in range(fine_start, fine_end + 1):
        fpath = frames_dir / f"frame_{idx:06d}.jpg"
        if fpath.exists():
            s = compute_ssim(str(ref), str(fpath))
            if s > best_ssim:
                best_ssim = s
                best_frame = idx

    # ── Determine confidence and rotation ──
    if best_ssim >= 0.90:
        confidence = "high"
        loop_detected = True
        full_360 = best_frame
        est_degrees = 360
        notes = (
            f"Clean loop: frame {best_frame} matches frame 1 "
            f"(SSIM={best_ssim:.3f}). Full 360\u00b0 in {best_frame} frames."
        )
    elif best_ssim >= 0.75:
        confidence = "medium"
        loop_detected = True
        full_360 = best_frame
        est_degrees = 360
        notes = (
            f"Probable loop: frame {best_frame} has SSIM={best_ssim:.3f} vs frame 1. "
            f"Moderate visual drift but rotation appears complete."
        )
    elif best_ssim >= 0.50:
        confidence = "low"
        loop_detected = False
        full_360 = total_frames
        # Estimate based on how far SSIM recovered
        # If it recovered to 0.50 from a min of 0.20, that's maybe ~270°
        recovery_pct = (best_ssim - global_min_ssim) / (1.0 - global_min_ssim) if global_min_ssim < 1.0 else 0
        est_degrees = int(180 + recovery_pct * 180)
        notes = (
            f"Partial loop: best tail SSIM={best_ssim:.3f} at frame {best_frame}. "
            f"~{est_degrees}\u00b0 rotation estimated. May have a visible jump at loop point."
        )
    else:
        confidence = "low"
        loop_detected = False
        full_360 = total_frames
        # Very poor recovery. Estimate how far the rotation got.
        # Use the global minimum position as a rough 180° estimate
        # (if it's roughly in the middle, the video tried a full rotation
        #  but the AI drifted too much for SSIM to recover)
        mid_pct = global_min_frame / total_frames
        if 0.3 < mid_pct < 0.7:
            # Minimum near the middle suggests attempted 360° with visual drift
            est_degrees = 360
            notes = (
                f"Visual drift: SSIM never recovers above {best_ssim:.3f}. "
                f"The global minimum at frame {global_min_frame} (SSIM={global_min_ssim:.3f}) "
                f"is near the midpoint, suggesting a full rotation with heavy AI drift. "
                f"Video may still be usable but quality is uncertain."
            )
        else:
            # Minimum not centered: probably incomplete rotation
            est_degrees = int(360 * global_min_frame / (total_frames * 0.5))
            est_degrees = min(est_degrees, 360)
            notes = (
                f"Poor rotation: SSIM drops to {global_min_ssim:.3f} at frame {global_min_frame} "
                f"and only recovers to {best_ssim:.3f}. Estimated ~{est_degrees}\u00b0. "
                f"This video is likely not a good 360\u00b0 source."
            )

    return {
        "rotation_degrees": est_degrees,
        "full_360_frame": full_360,
        "loop_detected": loop_detected,
        "global_min_frame": global_min_frame,
        "global_min_ssim": global_min_ssim,
        "tail_peak_frame": best_frame,
        "tail_peak_ssim": best_ssim,
        "ssim_curve": curve,
        "confidence": confidence,
        "notes": notes,
    }


# ════════════════════════════════════════════════════════════
# FRAME SAMPLING
# ════════════════════════════════════════════════════════════
def sample_frames(
    src_dir: Path,
    dst_dir: Path,
    start_frame: int,
    end_frame: int,
    target_count: int,
) -> int:
    """
    Sample `target_count` evenly-spaced frames from [start, end).
    End frame excluded to avoid stutter at the loop point.
    """
    usable = end_frame - start_frame
    if usable < target_count:
        print(f"  INFO: {usable} usable frames < target {target_count}. Using all.")
        target_count = usable

    indices = [
        start_frame + int(round(i * (usable - 1) / (target_count - 1)))
        for i in range(target_count)
    ]

    # Deduplicate
    seen = set()
    unique = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            unique.append(idx)
    indices = unique

    # Fill gaps if dedup removed entries
    all_available = set(range(start_frame, end_frame))
    while len(indices) < target_count:
        used = set(indices)
        available = sorted(all_available - used)
        if not available:
            break
        gaps = [(indices[i+1] - indices[i], i) for i in range(len(indices) - 1)]
        gaps.sort(reverse=True)
        for gap_size, gap_pos in gaps:
            if len(indices) >= target_count:
                break
            mid = (indices[gap_pos] + indices[gap_pos + 1]) // 2
            if mid not in set(indices):
                indices.insert(gap_pos + 1, mid)
    indices = sorted(indices[:target_count])

    copied = 0
    for out_num, src_idx in enumerate(indices, 1):
        src = src_dir / f"frame_{src_idx:06d}.jpg"
        dst = dst_dir / f"frame_{out_num:04d}.jpg"
        if src.exists():
            shutil.copy2(src, dst)
            copied += 1
        else:
            for delta in range(1, 5):
                for try_idx in [src_idx + delta, src_idx - delta]:
                    alt = src_dir / f"frame_{try_idx:06d}.jpg"
                    if alt.exists():
                        shutil.copy2(alt, dst)
                        copied += 1
                        break
                else:
                    continue
                break
    return copied


# ════════════════════════════════════════════════════════════
# IMAGE PROCESSING
# ════════════════════════════════════════════════════════════
def process_frames(frames_dir: Path, target_w: int, target_h: int, quality: int):
    """Crop and resize all frames to target dimensions."""
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if not frames:
        raise FileNotFoundError("No frames to process")

    with Image.open(frames[0]) as img:
        src_w, src_h = img.size

    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    print(f"  Source: {src_w}x{src_h} (ratio {src_ratio:.3f})")
    print(f"  Target: {target_w}x{target_h} (ratio {target_ratio:.3f})")

    if abs(src_ratio - target_ratio) < 0.02:
        crop_box = None
        print(f"  Strategy: resize only")
    elif src_ratio < target_ratio:
        new_h = int(src_w / target_ratio)
        y_off = (src_h - new_h) // 2
        crop_box = (0, y_off, src_w, y_off + new_h)
        print(f"  Strategy: crop vertical center ({src_h}->{new_h}px), then resize")
    else:
        new_w = int(src_h * target_ratio)
        x_off = (src_w - new_w) // 2
        crop_box = (x_off, 0, x_off + new_w, src_h)
        print(f"  Strategy: crop horizontal center ({src_w}->{new_w}px), then resize")

    for i, fpath in enumerate(frames, 1):
        with Image.open(fpath) as img:
            if crop_box:
                img = img.crop(crop_box)
            img = img.resize((target_w, target_h), Image.LANCZOS)
            img.save(fpath, "JPEG", quality=quality)
        if i % 50 == 0 or i == len(frames):
            print(f"  Processed {i}/{len(frames)}", end="\r")
    print(f"  Processed {len(frames)} frames" + " " * 20)


# ════════════════════════════════════════════════════════════
# VALIDATION
# ════════════════════════════════════════════════════════════
def validate_frames(frames_dir: Path, expected: int, tw: int, th: int) -> list:
    errors = []
    frames = sorted(frames_dir.glob("frame_*.jpg"))

    if len(frames) != expected:
        errors.append(f"Count: {len(frames)} (expected {expected})")

    for i in range(1, expected + 1):
        if not (frames_dir / f"frame_{i:04d}.jpg").exists():
            errors.append(f"Missing: frame_{i:04d}.jpg")
            if len(errors) > 10:
                errors.append("...(truncated)")
                break

    for idx in [1, expected // 4, expected // 2, expected]:
        fp = frames_dir / f"frame_{idx:04d}.jpg"
        if fp.exists():
            with Image.open(fp) as img:
                if img.size != (tw, th):
                    errors.append(f"frame_{idx:04d}: {img.size} != ({tw},{th})")

    sizes = [f.stat().st_size for f in frames]
    if sizes:
        avg = sum(sizes) / len(sizes)
        tiny = sum(1 for s in sizes if s < avg * 0.2)
        if tiny:
            errors.append(f"{tiny} frames < 20% of avg size ({int(avg*0.2/1024)}KB)")

    # Wrap check: first and last should NOT be identical
    first = frames_dir / "frame_0001.jpg"
    last = frames_dir / f"frame_{expected:04d}.jpg"
    if first.exists() and last.exists():
        ssim = compute_ssim(str(first), str(last))
        if ssim > 0.98:
            errors.append(f"First/last SSIM={ssim:.3f} (too similar, loop frame included?)")

    return errors


# ════════════════════════════════════════════════════════════
# VIEWER HTML
# ════════════════════════════════════════════════════════════
def generate_viewer(out_dir: Path, character: str, frames: int, sens: float, tmpl: Path):
    import re
    name = character.replace("-", " ").title()
    html = tmpl.read_text()
    html = html.replace("<title>360 Viewer</title>", f"<title>{name} \u2014 360\u00b0 Viewer</title>")
    html = re.sub(r"const TOTAL_FRAMES = \d+;", f"const TOTAL_FRAMES = {frames};", html)
    html = re.sub(r"const sensitivity = [\d.]+;", f"const sensitivity = {sens};", html)
    (out_dir / "index.html").write_text(html)


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def main():
    p = argparse.ArgumentParser(description="Build 360\u00b0 viewer from video")
    p.add_argument("video", help="Source video path")
    p.add_argument("character", help="Character name")
    p.add_argument("--deploy", action="store_true")
    p.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    p.add_argument("--dry-run", action="store_true", help="Analyze only")
    args = p.parse_args()

    video = Path(args.video)
    char = args.character.lower().replace(" ", "-")
    n_frames = args.frames

    assert video.exists(), f"Video not found: {video}"
    assert TEMPLATE.exists(), f"Template not found: {TEMPLATE}"
    assert 36 <= n_frames <= 600, "Frame count must be 36-600"

    print(f"\n{'='*60}")
    print(f"  360\u00b0 BUILD: {char} | target {n_frames} frames @ {TARGET_W}x{TARGET_H}")
    print(f"{'='*60}")

    # ── 1. Probe ──
    print(f"\n[1/7] Probing video...")
    info = probe_video(str(video))
    for k in ["width", "height", "fps", "fps_raw", "duration", "total_frames", "codec"]:
        print(f"  {k}: {info[k]}")

    # ── 2. Extract ──
    print(f"\n[2/7] Extracting all frames...")
    workdir = Path(tempfile.mkdtemp(prefix=f"360-{char}-"))
    raw = workdir / "all"
    final = workdir / "final"
    raw.mkdir(); final.mkdir()

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "warning",
         "-i", str(video), "-qmin", "1", "-q:v", "2",
         str(raw / "frame_%06d.jpg")],
        check=True
    )
    raw_count = len(list(raw.glob("frame_*.jpg")))
    print(f"  Extracted {raw_count} frames")
    assert raw_count >= n_frames, f"Only {raw_count} frames, need {n_frames}"

    # ── 3. Analyze rotation ──
    print(f"\n[3/7] Analyzing rotation...")
    rot = analyze_rotation(raw, raw_count)

    print(f"  Global min:    frame {rot['global_min_frame']} (SSIM={rot['global_min_ssim']:.3f})")
    print(f"  Tail peak:     frame {rot['tail_peak_frame']} (SSIM={rot['tail_peak_ssim']:.3f})")
    print(f"  Loop detected: {rot['loop_detected']}")
    print(f"  Est. rotation: ~{rot['rotation_degrees']}\u00b0")
    print(f"  Confidence:    {rot['confidence']}")
    print(f"  360\u00b0 boundary: frame {rot['full_360_frame']}")
    print(f"  Notes:         {rot['notes']}")

    # Print SSIM curve
    print(f"\n  SSIM curve:")
    display_every = max(1, len(rot["ssim_curve"]) // 20)
    for i, (idx, ssim) in enumerate(rot["ssim_curve"]):
        if i % display_every == 0 or idx == rot["full_360_frame"] or idx == rot["global_min_frame"]:
            bar = "\u2588" * int(ssim * 40)
            markers = []
            if abs(idx - rot["global_min_frame"]) <= 3:
                markers.append("MIN")
            if abs(idx - rot["tail_peak_frame"]) <= 3:
                markers.append("LOOP")
            mark = f" <-- {','.join(markers)}" if markers else ""
            print(f"    {idx:4d}: {ssim:.3f} {bar}{mark}")

    if args.dry_run:
        print(f"\n  DRY RUN complete. Work dir cleaned up.")
        shutil.rmtree(workdir)
        return

    # ── 4. Sample ──
    boundary = rot["full_360_frame"]
    print(f"\n[4/7] Sampling {n_frames} frames from range [1, {boundary})...")
    copied = sample_frames(raw, final, 1, boundary, n_frames)
    print(f"  Sampled {copied} frames")
    if copied != n_frames:
        print(f"  Adjusted target: {copied} frames")
        n_frames = copied

    # ── 5. Process ──
    print(f"\n[5/7] Processing to {TARGET_W}x{TARGET_H}...")
    process_frames(final, TARGET_W, TARGET_H, JPG_QUALITY)

    # ── 6. Validate ──
    print(f"\n[6/7] Validating...")
    errs = validate_frames(final, n_frames, TARGET_W, TARGET_H)
    sizes = [f.stat().st_size for f in sorted(final.glob("frame_*.jpg"))]
    avg = sum(sizes) // len(sizes) if sizes else 0
    print(f"  Count:  {len(sizes)}")
    print(f"  Sizes:  min={min(sizes)//1024}KB avg={avg//1024}KB max={max(sizes)//1024}KB")
    print(f"  Total:  ~{sum(sizes)//1024//1024}MB")

    if errs:
        for e in errs:
            print(f"  \u2717 {e}")
        print(f"\n  Build at: {final}")
        sys.exit(1)
    print(f"  All checks passed \u2713")

    # ── 7. Build + deploy ──
    print(f"\n[7/7] Building viewer...")
    generate_viewer(final, char, n_frames, SENSITIVITY, TEMPLATE)

    if args.deploy:
        dest = DEPLOY_ROOT / char
        if dest.exists() and list(dest.glob("frame_*.jpg")):
            bak = dest.with_suffix(f".bak.{os.getpid()}")
            print(f"  Backing up existing -> {bak.name}")
            dest.rename(bak)

        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(final.glob("frame_*.jpg")):
            shutil.copy2(f, dest / f.name)
        shutil.copy2(final / "index.html", dest / "index.html")

        dc = len(list(dest.glob("frame_*.jpg")))
        assert dc == n_frames, f"Deploy check: {dc} != {n_frames}"

        print(f"\n{'='*60}")
        print(f"  LIVE: https://roarofwinchester.com/360-viewer/{char}/")
        print(f"{'='*60}")
        shutil.rmtree(workdir)
    else:
        print(f"\n{'='*60}")
        print(f"  BUILD: {final}")
        print(f"  Add --deploy to push live")
        print(f"{'='*60}")

    # Summary
    disp = char.replace("-", " ").title()
    print(f"\n  {disp}: {info['width']}x{info['height']} @ {info['fps']}fps, {info['duration']:.1f}s")
    print(f"  Rotation: ~{rot['rotation_degrees']}\u00b0 ({rot['confidence']})")
    print(f"  Range: frames 1-{boundary} of {raw_count}")
    print(f"  Output: {n_frames} frames @ {TARGET_W}x{TARGET_H}, ~{sum(sizes)//1024//1024}MB")


if __name__ == "__main__":
    main()
