#!/usr/bin/env python3
"""
360° CHARACTER VIEWER BUILD SCRIPT
===================================
One command. Video in, deployed viewer out.

CORE LOGIC:
  This script does NOT blindly extract N frames. It analyzes
  the video's rotation using SSIM to understand:
    1. How many degrees of rotation does this video contain?
    2. Where is the 180° point (back of head)?
    3. Does the video complete a full 360° loop?
    4. What frame range represents exactly one rotation?

  It then extracts frames ONLY from the valid 360° range.

Usage:
  python3 build-viewer.py <video> <character> [--deploy] [--frames N]

Examples:
  python3 build-viewer.py /tmp/julie-v1.mp4 julie --deploy
  python3 build-viewer.py /tmp/mark.mp4 mark --frames 144 --deploy
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
# CONSTANTS (the standard — do not change per-character)
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
    """Extract video metadata via ffprobe."""
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
# ROTATION ANALYSIS — the core intelligence
# ════════════════════════════════════════════════════════════
def analyze_rotation(frames_dir: Path, total_frames: int) -> dict:
    """
    Analyze the rotation in the video using SSIM curves.

    Strategy:
      1. Compute SSIM of every Nth frame vs frame 1 (coarse scan)
      2. Find the deepest SSIM valley BEFORE the midpoint — that
         could be partial rotation or visual drift
      3. Find the TRUE 180° point: the deepest trough in the
         first smooth descent. After that, SSIM should either:
         (a) rise back up (camera coming back around) = full 360°
         (b) plateau or keep falling = over-rotation or drift
      4. Look for SSIM rising back above 0.85+ = completed loop
      5. If no clean loop: estimate 360° = 2 × (180° frame index)

    Returns:
      {
        "rotation_degrees": estimated total rotation,
        "full_360_frame": last frame of one complete rotation,
        "loop_detected": True if SSIM clearly loops back,
        "half_rotation_frame": the 180° point,
        "ssim_curve": [(frame_idx, ssim), ...],
        "confidence": "high" | "medium" | "low",
        "notes": str,
      }
    """
    ref = frames_dir / "frame_000001.jpg"
    if not ref.exists():
        raise FileNotFoundError(f"Reference frame not found: {ref}")

    # Coarse scan: every ~5 frames, or less for short videos
    step = max(1, total_frames // 60)
    indices = list(range(1, total_frames + 1, step))
    if indices[-1] != total_frames:
        indices.append(total_frames)

    print(f"  Scanning {len(indices)} sample frames (step={step})...")

    curve = []
    for idx in indices:
        fpath = frames_dir / f"frame_{idx:06d}.jpg"
        if fpath.exists():
            s = compute_ssim(str(ref), str(fpath))
            curve.append((idx, s))

    # ── Find the 180° point ──
    # The 180° point is the first significant minimum after the
    # initial descent. We look for where the SSIM STOPS falling
    # and either flattens or rises.
    #
    # Algorithm: find the first local minimum where SSIM is below
    # 0.5 and the next few points are >= this point.

    ssim_vals = [s for _, s in curve]
    frame_idxs = [i for i, _ in curve]

    # Smooth the curve to avoid noise
    if len(ssim_vals) >= 5:
        kernel = np.ones(3) / 3
        smoothed = np.convolve(ssim_vals, kernel, mode="same")
    else:
        smoothed = np.array(ssim_vals)

    # Find 180° point: first minimum after initial descent
    # Must be at least 25% into the video (to avoid false early dips)
    min_search_start = len(smoothed) // 4
    half_point_idx = None
    half_point_frame = None

    for i in range(min_search_start, len(smoothed) - 2):
        # Local minimum: lower than neighbors and below 0.5
        if smoothed[i] <= smoothed[i - 1] and smoothed[i] <= smoothed[i + 1]:
            if smoothed[i] < 0.5:
                half_point_idx = i
                half_point_frame = frame_idxs[i]
                break

    # If no clean local min, use global minimum in the first 70% of video
    if half_point_idx is None:
        search_end = int(len(smoothed) * 0.7)
        if search_end > min_search_start:
            subset = smoothed[min_search_start:search_end]
            rel_idx = np.argmin(subset)
            half_point_idx = min_search_start + rel_idx
            half_point_frame = frame_idxs[half_point_idx]

    # ── Detect full loop ──
    # After the 180° point, does SSIM rise back above 0.8?
    loop_detected = False
    loop_frame = None

    if half_point_idx is not None:
        for i in range(half_point_idx + 1, len(smoothed)):
            if smoothed[i] > 0.80:
                loop_detected = True
                loop_frame = frame_idxs[i]
                break

    # ── Estimate rotation ──
    if loop_detected and loop_frame:
        # Clean loop: the loop frame is where 360° completes
        full_360_frame = loop_frame
        rotation_degrees = 360
        confidence = "high"
        notes = f"Clean loop detected. Frame 1 matches frame {loop_frame} (SSIM > 0.80)."

    elif half_point_frame:
        # No clean loop. Estimate 360° = 2 × 180° point.
        estimated_360 = half_point_frame * 2
        rotation_degrees = round((total_frames / estimated_360) * 360)

        if estimated_360 <= total_frames:
            # Video contains a full 360° (or more)
            full_360_frame = min(estimated_360, total_frames)
            confidence = "medium"
            notes = (
                f"180° detected at frame {half_point_frame}. "
                f"Estimated 360° at frame {estimated_360}. "
                f"Video has ~{rotation_degrees}° total rotation."
            )
        else:
            # Video is short of 360°
            full_360_frame = total_frames  # use all we have
            confidence = "low"
            notes = (
                f"180° detected at frame {half_point_frame}, "
                f"but 360° would need ~{estimated_360} frames. "
                f"Video only has {total_frames} (~{rotation_degrees}° rotation). "
                f"Using all frames — viewer will have a jump at the loop point."
            )
    else:
        # Can't even find 180°. Use all frames.
        full_360_frame = total_frames
        rotation_degrees = 360  # assume
        confidence = "low"
        notes = "Could not detect rotation pattern. Using all frames as-is."

    # ── Fine-tune the 360° boundary ──
    # If we have a medium/high confidence boundary, do a dense
    # scan around it to find the exact best frame.
    if confidence in ("high", "medium") and full_360_frame < total_frames:
        fine_start = max(1, full_360_frame - step * 3)
        fine_end = min(total_frames, full_360_frame + step * 3)
        best_frame = full_360_frame
        best_ssim = 0

        for idx in range(fine_start, fine_end + 1):
            fpath = frames_dir / f"frame_{idx:06d}.jpg"
            if fpath.exists():
                s = compute_ssim(str(ref), str(fpath))
                if s > best_ssim and idx > half_point_frame:
                    best_ssim = s
                    best_frame = idx

        if best_ssim > 0:
            full_360_frame = best_frame
            notes += f" Fine-tuned to frame {best_frame} (SSIM={best_ssim:.4f})."

    return {
        "rotation_degrees": rotation_degrees,
        "full_360_frame": full_360_frame,
        "loop_detected": loop_detected,
        "half_rotation_frame": half_point_frame,
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
    Sample `target_count` evenly-spaced frames from range
    [start_frame, end_frame) and save as frame_0001.jpg etc.

    The end_frame is EXCLUDED (it's the loop-back frame that
    matches start_frame, so including it causes a stutter).
    """
    usable = end_frame - start_frame
    if usable < target_count:
        print(f"  WARNING: Only {usable} usable frames, target was {target_count}")
        target_count = usable

    # Generate evenly spaced indices
    indices = [
        start_frame + int(round(i * (usable - 1) / (target_count - 1)))
        for i in range(target_count)
    ]

    # Deduplicate (rounding can cause repeats)
    seen = set()
    unique = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            unique.append(idx)
    indices = unique

    # If dedup removed some, fill gaps with nearest unused frames
    all_available = set(range(start_frame, end_frame))
    while len(indices) < target_count:
        used = set(indices)
        available = sorted(all_available - used)
        if not available:
            break
        # Insert frames at the largest gaps
        gaps = [(indices[i+1] - indices[i], i) for i in range(len(indices) - 1)]
        gaps.sort(reverse=True)
        for gap_size, gap_pos in gaps:
            if len(indices) >= target_count:
                break
            mid = (indices[gap_pos] + indices[gap_pos + 1]) // 2
            if mid not in used:
                indices.insert(gap_pos + 1, mid)

    indices = sorted(indices[:target_count])

    # Copy frames
    copied = 0
    for out_num, src_idx in enumerate(indices, 1):
        src = src_dir / f"frame_{src_idx:06d}.jpg"
        dst = dst_dir / f"frame_{out_num:04d}.jpg"
        if src.exists():
            shutil.copy2(src, dst)
            copied += 1
        else:
            # Try nearest neighbor
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

    # Get source dimensions
    with Image.open(frames[0]) as img:
        src_w, src_h = img.size

    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    print(f"  Source: {src_w}x{src_h} (ratio {src_ratio:.3f})")
    print(f"  Target: {target_w}x{target_h} (ratio {target_ratio:.3f})")

    if abs(src_ratio - target_ratio) < 0.02:
        strategy = "resize"
        print(f"  Strategy: resize only (ratios match)")
    elif src_ratio < target_ratio:
        # Source taller (e.g., square -> 16:9): crop vertical center
        new_h = int(src_w / target_ratio)
        y_off = (src_h - new_h) // 2
        crop_box = (0, y_off, src_w, y_off + new_h)
        strategy = "crop_v"
        print(f"  Strategy: crop vertical ({src_h}→{new_h}px, -{src_h-new_h}px) then resize")
    else:
        # Source wider: crop horizontal center
        new_w = int(src_h * target_ratio)
        x_off = (src_w - new_w) // 2
        crop_box = (x_off, 0, x_off + new_w, src_h)
        strategy = "crop_h"
        print(f"  Strategy: crop horizontal ({src_w}→{new_w}px, -{src_w-new_w}px) then resize")

    for i, fpath in enumerate(frames, 1):
        with Image.open(fpath) as img:
            if strategy == "crop_v":
                img = img.crop(crop_box)
            elif strategy == "crop_h":
                img = img.crop(crop_box)
            img = img.resize((target_w, target_h), Image.LANCZOS)
            img.save(fpath, "JPEG", quality=quality)

        if i % 50 == 0 or i == len(frames):
            print(f"  Processed {i}/{len(frames)} frames", end="\r")

    print(f"  Processed {len(frames)} frames" + " " * 20)


# ════════════════════════════════════════════════════════════
# VALIDATION
# ════════════════════════════════════════════════════════════
def validate_frames(frames_dir: Path, expected_count: int, target_w: int, target_h: int) -> list:
    """Validate all frames. Returns list of errors (empty = pass)."""
    errors = []

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    count = len(frames)

    if count != expected_count:
        errors.append(f"Frame count: {count} (expected {expected_count})")

    # Check for gaps in sequence
    for i in range(1, expected_count + 1):
        if not (frames_dir / f"frame_{i:04d}.jpg").exists():
            errors.append(f"Missing: frame_{i:04d}.jpg")
            if len(errors) > 10:
                errors.append("... (truncated)")
                break

    # Check dimensions on sample frames
    sample_indices = [1, expected_count // 4, expected_count // 2, expected_count]
    for idx in sample_indices:
        fpath = frames_dir / f"frame_{idx:04d}.jpg"
        if fpath.exists():
            with Image.open(fpath) as img:
                if img.size != (target_w, target_h):
                    errors.append(f"frame_{idx:04d}.jpg: {img.size} (expected {target_w}x{target_h})")

    # Check for corrupt/tiny files
    sizes = [f.stat().st_size for f in frames]
    if sizes:
        avg = sum(sizes) / len(sizes)
        tiny = [f for f, s in zip(frames, sizes) if s < avg * 0.2]
        if tiny:
            errors.append(f"{len(tiny)} frames suspiciously small (< {int(avg*0.2/1024)}KB)")

    # Wrap continuity: first vs last should be different
    # (they're adjacent in the rotation, not the same)
    first = frames_dir / "frame_0001.jpg"
    last = frames_dir / f"frame_{expected_count:04d}.jpg"
    if first.exists() and last.exists():
        ssim = compute_ssim(str(first), str(last))
        if ssim > 0.95:
            errors.append(f"First/last frames too similar (SSIM={ssim:.3f}). Loop frame may be included.")

    return errors


# ════════════════════════════════════════════════════════════
# VIEWER HTML GENERATION
# ════════════════════════════════════════════════════════════
def generate_viewer_html(
    output_dir: Path,
    character: str,
    frame_count: int,
    sensitivity: float,
    template: Path,
):
    """Generate viewer HTML from template."""
    display_name = character.replace("-", " ").title()

    html = template.read_text()
    html = html.replace("<title>360 Viewer</title>", f"<title>{display_name} \u2014 360\u00b0 Viewer</title>")

    # Replace TOTAL_FRAMES
    import re
    html = re.sub(r"const TOTAL_FRAMES = \d+;", f"const TOTAL_FRAMES = {frame_count};", html)
    html = re.sub(r"const sensitivity = [\d.]+;", f"const sensitivity = {sensitivity};", html)

    (output_dir / "index.html").write_text(html)


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Build 360\u00b0 character viewer from video")
    parser.add_argument("video", help="Path to source video")
    parser.add_argument("character", help="Character name (lowercase, hyphens for spaces)")
    parser.add_argument("--deploy", action="store_true", help="Deploy to web server")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES, help=f"Output frame count (default: {DEFAULT_FRAMES})")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't extract/process")
    args = parser.parse_args()

    video = Path(args.video)
    character = args.character.lower().replace(" ", "-")
    target_frames = args.frames

    if not video.exists():
        print(f"ERROR: Video not found: {video}", file=sys.stderr)
        sys.exit(1)
    if not TEMPLATE.exists():
        print(f"ERROR: Template not found: {TEMPLATE}", file=sys.stderr)
        sys.exit(1)
    if not 36 <= target_frames <= 600:
        print(f"ERROR: Frame count must be 36-600", file=sys.stderr)
        sys.exit(1)

    print(f"{'='*60}")
    print(f"  360° VIEWER BUILD: {character}")
    print(f"  Target: {target_frames} frames @ {TARGET_W}x{TARGET_H}")
    print(f"{'='*60}")

    # ── Step 1: Probe ──
    print(f"\n[1/7] Probing video...")
    info = probe_video(str(video))
    print(f"  Resolution:   {info['width']}x{info['height']}")
    print(f"  FPS:          {info['fps']} ({info['fps_raw']})")
    print(f"  Duration:     {info['duration']:.2f}s")
    print(f"  Total frames: {info['total_frames']}")
    print(f"  Codec:        {info['codec']}")

    # ── Step 2: Extract ALL frames ──
    print(f"\n[2/7] Extracting all frames...")
    workdir = Path(tempfile.mkdtemp(prefix=f"360-{character}-"))
    raw_dir = workdir / "all"
    final_dir = workdir / "final"
    raw_dir.mkdir()
    final_dir.mkdir()

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "warning",
         "-i", str(video), "-qmin", "1", "-q:v", "2",
         str(raw_dir / "frame_%06d.jpg")],
        check=True
    )
    raw_count = len(list(raw_dir.glob("frame_*.jpg")))
    print(f"  Extracted {raw_count} frames to {raw_dir}")

    if raw_count < target_frames:
        print(f"  ERROR: Only {raw_count} frames, need {target_frames}", file=sys.stderr)
        sys.exit(1)

    # ── Step 3: Analyze rotation ──
    print(f"\n[3/7] Analyzing rotation...")
    rotation = analyze_rotation(raw_dir, raw_count)

    print(f"  180° point:     frame {rotation['half_rotation_frame']}")
    print(f"  360° boundary:  frame {rotation['full_360_frame']}")
    print(f"  Loop detected:  {rotation['loop_detected']}")
    print(f"  Est. rotation:  ~{rotation['rotation_degrees']}°")
    print(f"  Confidence:     {rotation['confidence']}")
    print(f"  Notes:          {rotation['notes']}")

    # Print mini SSIM chart
    print(f"\n  SSIM curve (frame 1 vs samples):")
    for idx, ssim in rotation["ssim_curve"][::max(1, len(rotation["ssim_curve"])//20)]:
        bar = "\u2588" * int(ssim * 40)
        marker = ""
        if rotation["half_rotation_frame"] and abs(idx - rotation["half_rotation_frame"]) < 10:
            marker = " <-- 180°"
        if abs(idx - rotation["full_360_frame"]) < 10:
            marker = " <-- 360°"
        print(f"    {idx:4d}: {ssim:.3f} {bar}{marker}")

    if args.dry_run:
        print(f"\n  DRY RUN: Analysis complete. No frames extracted.")
        shutil.rmtree(workdir)
        return

    # ── Step 4: Sample frames from 360° range ──
    print(f"\n[4/7] Sampling {target_frames} frames from 360° range [1, {rotation['full_360_frame']})...")
    copied = sample_frames(
        raw_dir, final_dir,
        start_frame=1,
        end_frame=rotation["full_360_frame"],
        target_count=target_frames,
    )
    print(f"  Sampled {copied} frames")

    if copied != target_frames:
        print(f"  WARNING: Expected {target_frames}, got {copied}")
        target_frames = copied

    # ── Step 5: Crop/resize ──
    print(f"\n[5/7] Processing to {TARGET_W}x{TARGET_H}...")
    process_frames(final_dir, TARGET_W, TARGET_H, JPG_QUALITY)

    # ── Step 6: Validate ──
    print(f"\n[6/7] Validating...")
    errors = validate_frames(final_dir, target_frames, TARGET_W, TARGET_H)

    sizes = [f.stat().st_size for f in sorted(final_dir.glob("frame_*.jpg"))]
    avg_size = sum(sizes) // len(sizes) if sizes else 0
    print(f"  Count:    {len(sizes)} frames")
    print(f"  Sizes:    min={min(sizes)//1024}KB avg={avg_size//1024}KB max={max(sizes)//1024}KB")
    print(f"  Total:    ~{sum(sizes)//1024//1024}MB")

    if errors:
        print(f"\n  ERRORS:")
        for e in errors:
            print(f"    ✗ {e}")
        print(f"\n  Build directory preserved: {final_dir}")
        sys.exit(1)
    else:
        print(f"  All checks passed ✓")

    # ── Step 7: Build viewer + deploy ──
    print(f"\n[7/7] Building viewer...")
    generate_viewer_html(final_dir, character, target_frames, SENSITIVITY, TEMPLATE)
    print(f"  Viewer HTML generated")

    if args.deploy:
        deploy_dir = DEPLOY_ROOT / character
        if deploy_dir.exists() and list(deploy_dir.glob("frame_*.jpg")):
            backup = deploy_dir.with_suffix(f".bak.{os.getpid()}")
            print(f"  Backing up existing to {backup.name}")
            deploy_dir.rename(backup)

        deploy_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(final_dir.glob("frame_*.jpg")):
            shutil.copy2(f, deploy_dir / f.name)
        shutil.copy2(final_dir / "index.html", deploy_dir / "index.html")

        dep_count = len(list(deploy_dir.glob("frame_*.jpg")))
        assert dep_count == target_frames, f"Deploy verify: {dep_count} != {target_frames}"
        assert (deploy_dir / "index.html").exists(), "Deploy verify: no index.html"

        print(f"\n{'='*60}")
        print(f"  DEPLOYED: https://roarofwinchester.com/360-viewer/{character}/")
        print(f"{'='*60}")

        # Clean up
        shutil.rmtree(workdir)
    else:
        print(f"\n{'='*60}")
        print(f"  BUILD COMPLETE: {final_dir}")
        print(f"  Re-run with --deploy to push live")
        print(f"{'='*60}")

    # ── Summary ──
    print(f"\nSummary:")
    display = character.replace("-", " ").title()
    print(f"  Character:     {display}")
    print(f"  Source:        {video.name} ({info['width']}x{info['height']} @ {info['fps']}fps, {info['duration']:.1f}s)")
    print(f"  Rotation:      ~{rotation['rotation_degrees']}° detected ({rotation['confidence']} confidence)")
    print(f"  360° range:    frames 1-{rotation['full_360_frame']} of {raw_count}")
    print(f"  Output:        {target_frames} frames @ {TARGET_W}x{TARGET_H}")
    print(f"  Avg frame:     {avg_size // 1024}KB")
    print(f"  Total:         ~{sum(sizes) // 1024 // 1024}MB")


if __name__ == "__main__":
    main()
