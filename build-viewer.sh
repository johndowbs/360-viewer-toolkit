#!/usr/bin/env bash
# ============================================================
# 360° CHARACTER VIEWER BUILD SCRIPT
# ============================================================
# One command. Video in, deployed viewer out.
#
# CORE LOGIC: This script does NOT assume the video is a clean
# 360° rotation. It DETECTS where the full rotation completes
# by comparing frames to frame 1 using perceptual similarity.
# Only the frames within one true 360° orbit are used.
#
# Usage:
#   ./build-viewer.sh <video_file> <character_name> [--deploy] [--frames N]
#
# Examples:
#   ./build-viewer.sh /tmp/julie-v1.mp4 julie --deploy
#   ./build-viewer.sh /tmp/mark-v2.mp4 mark --frames 144
#   ./build-viewer.sh /tmp/doug-v1.mp4 doug --deploy --frames 96
#
# The --frames flag sets the output frame count (default: 192).
# Fewer frames = smaller viewer, faster load. 96 is minimum for
# smooth rotation. 192 is butter-smooth.
#
# Pipeline:
#   1. Probe video metadata
#   2. Extract ALL frames from video
#   3. Detect 360° rotation boundary (SSIM comparison to frame 1)
#   4. Sample N evenly-spaced frames from the 360° range ONLY
#   5. Crop/resize to 1280x720, centered
#   6. Validate every frame
#   7. Generate viewer HTML
#   8. Deploy (if --deploy)
# ============================================================

set -euo pipefail

# ── Config (DO NOT CHANGE) ──────────────────────────────────
TARGET_FRAMES=192       # overridable with --frames
TARGET_W=1280
TARGET_H=720
JPG_QUALITY=92
SENSITIVITY=0.4
DEPLOY_ROOT="/var/www/roarofwinchester/360-viewer"
TOOLKIT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${TOOLKIT_DIR}/viewer/index.html"

# SSIM threshold: when a later frame's similarity to frame 1
# rises back above this value (after the dip), we've completed
# one full rotation. Tuned from real Veo 3 videos.
SSIM_LOOP_THRESHOLD=0.72

# Minimum frames into the video before we start looking for the
# loop-back. Prevents false positives from early similar frames.
# Set to 40% of total frames (camera has to get at least to the
# side view before we believe it's come back around).
MIN_ROTATION_PCT=40

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[360]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }
die()  { err "$@"; exit 1; }

# ── Parse args ──────────────────────────────────────────────
VIDEO=""
CHARACTER=""
DEPLOY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy)  DEPLOY=true; shift ;;
    --frames)  TARGET_FRAMES="$2"; shift 2 ;;
    -*)        die "Unknown flag: $1" ;;
    *)
      if [[ -z "$VIDEO" ]]; then VIDEO="$1"
      elif [[ -z "$CHARACTER" ]]; then CHARACTER="$1"
      else die "Unexpected arg: $1"
      fi
      shift ;;
  esac
done

[[ -z "$VIDEO" ]] && die "Usage: $0 <video_file> <character_name> [--deploy] [--frames N]"
[[ -z "$CHARACTER" ]] && die "Usage: $0 <video_file> <character_name> [--deploy] [--frames N]"
[[ -f "$VIDEO" ]] || die "Video not found: $VIDEO"
[[ -f "$TEMPLATE" ]] || die "Template not found: $TEMPLATE"
[[ "$TARGET_FRAMES" -ge 36 && "$TARGET_FRAMES" -le 600 ]] || die "Frame count must be 36-600"

CHARACTER=$(echo "$CHARACTER" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')

# ── Work directory ──────────────────────────────────────────
WORKDIR="/tmp/360-build-${CHARACTER}-$$"
FRAMES_ALL="${WORKDIR}/all"
FRAMES_FINAL="${WORKDIR}/final"
mkdir -p "$FRAMES_ALL" "$FRAMES_FINAL"
log "Work dir: $WORKDIR"
log "Target: $TARGET_FRAMES frames at ${TARGET_W}x${TARGET_H}"

# ============================================================
# STEP 1: PROBE VIDEO
# ============================================================
log "Step 1/7: Probing video..."

read V_WIDTH V_HEIGHT V_FPS_RAW V_DURATION < <(
  ffprobe -v quiet -select_streams v:0 \
    -show_entries stream=width,height,r_frame_rate \
    -show_entries format=duration \
    -of csv=p=0:s=' ' "$VIDEO" 2>/dev/null | tr '\n' ' '
)

# Clean up: ffprobe sometimes outputs stream line then format line
V_WIDTH=$(echo "$V_WIDTH" | tr -d '[:space:]')
V_HEIGHT=$(echo "$V_HEIGHT" | cut -d',' -f1 | tr -d '[:space:]')

# Re-probe cleanly
V_WIDTH=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=width -of csv=p=0 "$VIDEO")
V_HEIGHT=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=height -of csv=p=0 "$VIDEO")
V_FPS_RAW=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO")
V_DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO")
V_FPS=$(python3 -c "print(round(eval('$V_FPS_RAW'), 2))")
V_TOTAL=$(python3 -c "print(int(float('$V_DURATION') * eval('$V_FPS_RAW')))")

echo "  Resolution:    ${V_WIDTH}x${V_HEIGHT}"
echo "  FPS:           ${V_FPS} (${V_FPS_RAW})"
echo "  Duration:      ${V_DURATION}s"
echo "  Total frames:  ${V_TOTAL}"
ok "Video probed"

# ============================================================
# STEP 2: EXTRACT ALL FRAMES
# ============================================================
log "Step 2/7: Extracting all frames..."

ffmpeg -hide_banner -loglevel warning -i "$VIDEO" \
  -qmin 1 -q:v 2 \
  "${FRAMES_ALL}/frame_%06d.jpg"

RAW_COUNT=$(ls "$FRAMES_ALL"/frame_*.jpg 2>/dev/null | wc -l)
log "  Extracted $RAW_COUNT frames"
[[ "$RAW_COUNT" -ge "$TARGET_FRAMES" ]] || die "Only $RAW_COUNT frames in video. Need at least $TARGET_FRAMES."
ok "All frames extracted"

# ============================================================
# STEP 3: DETECT 360° ROTATION BOUNDARY
# ============================================================
log "Step 3/7: Detecting 360° rotation boundary..."
log "  Comparing frames to frame 1 using SSIM..."

# We don't need to compare EVERY frame. Sample ~60 evenly spaced
# points to find the rough boundary, then refine.
ROTATION_END=$(python3 << PYEOF
import subprocess, os, re, sys

frames_dir = "${FRAMES_ALL}"
raw_count = ${RAW_COUNT}
threshold = ${SSIM_LOOP_THRESHOLD}
min_pct = ${MIN_ROTATION_PCT}

# Reference frame
ref = os.path.join(frames_dir, "frame_000001.jpg")

# Sample ~60 frames across the video for coarse scan
sample_count = min(60, raw_count)
sample_indices = [int(1 + i * (raw_count - 1) / (sample_count - 1)) for i in range(sample_count)]

# Don't check the first min_pct% of frames (too early for loop-back)
min_frame = int(raw_count * min_pct / 100)

ssim_scores = []
found_boundary = None

for idx in sample_indices:
    fname = os.path.join(frames_dir, f"frame_{idx:06d}.jpg")
    if not os.path.exists(fname):
        continue

    # Get SSIM using ImageMagick compare
    result = subprocess.run(
        ["magick", "compare", "-metric", "SSIM", ref, fname, "/dev/null"],
        capture_output=True, text=True, timeout=10
    )
    # SSIM is output on stderr by ImageMagick
    output = result.stderr.strip()
    try:
        ssim = float(output.split()[0])
    except (ValueError, IndexError):
        # Try to parse different format
        m = re.search(r'[\d.]+', output)
        ssim = float(m.group()) if m else 0.0

    ssim_scores.append((idx, ssim))

    # Only look for loop-back after minimum rotation
    if idx >= min_frame and ssim >= threshold:
        found_boundary = idx
        break

if found_boundary:
    # Refine: do a fine-grained scan around the boundary
    # Check frames from (boundary - step) to (boundary + step) 
    coarse_step = max(1, (raw_count // sample_count))
    fine_start = max(min_frame, found_boundary - coarse_step * 2)
    fine_end = min(raw_count, found_boundary + coarse_step * 2)
    
    best_idx = found_boundary
    best_ssim = 0
    
    for idx in range(fine_start, fine_end + 1):
        fname = os.path.join(frames_dir, f"frame_{idx:06d}.jpg")
        if not os.path.exists(fname):
            continue
        result = subprocess.run(
            ["magick", "compare", "-metric", "SSIM", ref, fname, "/dev/null"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stderr.strip()
        try:
            ssim = float(output.split()[0])
        except (ValueError, IndexError):
            m = re.search(r'[\d.]+', output)
            ssim = float(m.group()) if m else 0.0
        
        if ssim > best_ssim:
            best_ssim = ssim
            best_idx = idx
    
    rotation_degrees = (best_idx / raw_count) * (360 * float("${V_DURATION}") / (best_idx / eval("${V_FPS_RAW}"))) if best_idx > 0 else 360
    
    print(f"BOUNDARY:{best_idx}", flush=True)
    print(f"  Loop detected at frame {best_idx}/{raw_count} (SSIM={best_ssim:.4f})", file=sys.stderr)
    print(f"  This means frames 1-{best_idx} = one full 360° rotation", file=sys.stderr)
    print(f"  Frames {best_idx+1}-{raw_count} are overlap/extra rotation", file=sys.stderr)
else:
    # No loop detected. Possible reasons:
    # - Video is exactly 360° (last frame != first because it's one-short-of-loop)
    # - Video is less than 360°
    # - SSIM threshold too high
    # Fall back to using all frames, but warn
    print(f"BOUNDARY:{raw_count}", flush=True)
    print(f"  No loop-back detected (threshold={threshold})", file=sys.stderr)
    print(f"  Using all {raw_count} frames (assuming video = one rotation)", file=sys.stderr)
    
    # Print the SSIM curve for debugging
    print(f"  SSIM samples:", file=sys.stderr)
    for idx, s in ssim_scores[-10:]:
        print(f"    frame {idx}: {s:.4f}", file=sys.stderr)
PYEOF
)

# Parse the boundary frame number
BOUNDARY_FRAME=$(echo "$ROTATION_END" | grep "^BOUNDARY:" | cut -d: -f2)
[[ -z "$BOUNDARY_FRAME" ]] && die "Failed to detect rotation boundary"

log "  360° rotation = frames 1 through $BOUNDARY_FRAME (of $RAW_COUNT total)"
USABLE_FRAMES=$BOUNDARY_FRAME
ok "Rotation boundary detected: frame $BOUNDARY_FRAME"

# ============================================================
# STEP 4: SAMPLE TARGET FRAMES FROM 360° RANGE
# ============================================================
log "Step 4/7: Sampling $TARGET_FRAMES frames from 360° range (1-$BOUNDARY_FRAME)..."

# Key insight: frame 1 and frame BOUNDARY are nearly identical
# (both front-facing). We want frames that span 360° WITHOUT
# duplicating the start/end. So we sample from 1 to BOUNDARY-1.
python3 << PYEOF
import os, shutil

frames_dir = "${FRAMES_ALL}"
final_dir = "${FRAMES_FINAL}"
target = ${TARGET_FRAMES}
boundary = ${BOUNDARY_FRAME}

# Usable range: frame 1 to frame (boundary - 1)
# Frame at boundary ~= frame 1, so exclude it to avoid stutter
usable = boundary - 1
if usable < target:
    # If we have fewer usable frames than target, use what we have
    usable = boundary
    print(f"  NOTE: Only {usable} usable frames, target was {target}")

# Evenly space target frames across the usable range
indices = [int(1 + i * (usable - 1) / (target - 1)) for i in range(target)]

# Remove any duplicates from rounding and ensure we have exactly target
indices = list(dict.fromkeys(indices))  # dedupe preserving order
while len(indices) < target:
    # Fill gaps by inserting midpoints
    new_indices = []
    for i in range(len(indices) - 1):
        new_indices.append(indices[i])
        if len(new_indices) + (len(indices) - i - 1) < target:
            mid = (indices[i] + indices[i+1]) // 2
            if mid not in indices and mid not in new_indices:
                new_indices.append(mid)
    new_indices.append(indices[-1])
    indices = new_indices[:target]

for out_num, src_idx in enumerate(indices[:target], 1):
    src = os.path.join(frames_dir, f"frame_{src_idx:06d}.jpg")
    dst = os.path.join(final_dir, f"frame_{out_num:04d}.jpg")
    if os.path.exists(src):
        shutil.copy2(src, dst)
    else:
        # Nearest available
        for delta in range(1, 10):
            for try_idx in [src_idx + delta, src_idx - delta]:
                alt = os.path.join(frames_dir, f"frame_{try_idx:06d}.jpg")
                if os.path.exists(alt):
                    shutil.copy2(alt, dst)
                    break
            else:
                continue
            break

copied = len([f for f in os.listdir(final_dir) if f.startswith("frame_") and f.endswith(".jpg")])
print(f"  Sampled {copied} frames from {usable}-frame 360° range (step ~{usable/target:.2f})")
PYEOF

SELECTED=$(ls "$FRAMES_FINAL"/frame_*.jpg 2>/dev/null | wc -l)
[[ "$SELECTED" -eq "$TARGET_FRAMES" ]] || die "Expected $TARGET_FRAMES, got $SELECTED"
ok "$TARGET_FRAMES frames sampled from 360° range"

# ============================================================
# STEP 5: CROP/RESIZE TO TARGET DIMENSIONS
# ============================================================
log "Step 5/7: Processing to ${TARGET_W}x${TARGET_H}..."

python3 << 'PYEOF'
import subprocess, glob, os

final_dir = "${FRAMES_FINAL}"
target_w, target_h = ${TARGET_W}, ${TARGET_H}
quality = ${JPG_QUALITY}

first = sorted(glob.glob(os.path.join(final_dir, "frame_*.jpg")))[0]
result = subprocess.run(["identify", "-format", "%w %h", first], capture_output=True, text=True)
src_w, src_h = map(int, result.stdout.strip().split())
src_ratio = src_w / src_h
target_ratio = target_w / target_h

print(f"  Source: {src_w}x{src_h} (ratio {src_ratio:.3f})")
print(f"  Target: {target_w}x{target_h} (ratio {target_ratio:.3f})")

frames = sorted(glob.glob(os.path.join(final_dir, "frame_*.jpg")))

if abs(src_ratio - target_ratio) < 0.02:
    print(f"  Strategy: resize only (ratios match)")
    cmd = ["mogrify", "-resize", f"{target_w}x{target_h}!", "-quality", str(quality)] + frames
elif src_ratio < target_ratio:
    # Source taller than target (square/portrait -> landscape)
    # Crop vertically, keeping center
    new_h = int(src_w / target_ratio)
    y_off = (src_h - new_h) // 2
    crop = f"{src_w}x{new_h}+0+{y_off}"
    print(f"  Strategy: crop {crop} then resize (removing {src_h - new_h}px vertical)")
    cmd = ["mogrify", "-crop", crop, "+repage", "-resize", f"{target_w}x{target_h}!", "-quality", str(quality)] + frames
else:
    # Source wider than target
    new_w = int(src_h * target_ratio)
    x_off = (src_w - new_w) // 2
    crop = f"{new_w}x{src_h}+{x_off}+0"
    print(f"  Strategy: crop {crop} then resize (removing {src_w - new_w}px horizontal)")
    cmd = ["mogrify", "-crop", crop, "+repage", "-resize", f"{target_w}x{target_h}!", "-quality", str(quality)] + frames

subprocess.run(cmd, check=True)
print(f"  Processed {len(frames)} frames")
PYEOF

ok "Frames processed"

# ============================================================
# STEP 6: VALIDATE
# ============================================================
log "Step 6/7: Validating..."

ERRORS=0

FINAL_COUNT=$(ls "$FRAMES_FINAL"/frame_*.jpg 2>/dev/null | wc -l)
if [[ "$FINAL_COUNT" -ne "$TARGET_FRAMES" ]]; then
  err "Count: $FINAL_COUNT (expected $TARGET_FRAMES)"; ERRORS=$((ERRORS+1))
else
  echo "  Count: $FINAL_COUNT ✓"
fi

# Check dimensions on first, middle, last
for f in "frame_0001.jpg" "frame_$(printf '%04d' $((TARGET_FRAMES/2))).jpg" "frame_$(printf '%04d' $TARGET_FRAMES).jpg"; do
  dims=$(identify -format "%wx%h" "$FRAMES_FINAL/$f" 2>/dev/null || echo "MISSING")
  if [[ "$dims" == "${TARGET_W}x${TARGET_H}" ]]; then
    echo "  $f: $dims ✓"
  else
    err "$f: $dims (expected ${TARGET_W}x${TARGET_H})"; ERRORS=$((ERRORS+1))
  fi
done

# Check for corrupt/tiny frames
SIZES=$(stat -c%s "$FRAMES_FINAL"/frame_*.jpg | sort -n)
MIN_SIZE=$(echo "$SIZES" | head -1)
MAX_SIZE=$(echo "$SIZES" | tail -1)
AVG_SIZE=$(echo "$SIZES" | awk '{sum+=$1} END {print int(sum/NR)}')
echo "  Sizes: min=$((MIN_SIZE/1024))KB avg=$((AVG_SIZE/1024))KB max=$((MAX_SIZE/1024))KB"

SMALL_THRESH=$((AVG_SIZE / 5))
SMALL=$(echo "$SIZES" | awk -v t="$SMALL_THRESH" '$1 < t {c++} END {print c+0}')
[[ "$SMALL" -gt 0 ]] && { warn "$SMALL frames suspiciously small"; ERRORS=$((ERRORS+1)); }

# Verify sequence has no gaps
python3 -c "
import os
missing = [i for i in range(1, ${TARGET_FRAMES}+1) if not os.path.exists(f'${FRAMES_FINAL}/frame_{i:04d}.jpg')]
if missing: print(f'  GAPS: {missing}'); exit(1)
else: print(f'  Sequence: 1-${TARGET_FRAMES} continuous ✓')
" || ERRORS=$((ERRORS+1))

# Rotation continuity check: first and last frame should be
# adjacent in the rotation (since we excluded the duplicate)
python3 << PYEOF
import subprocess, re
first = "${FRAMES_FINAL}/frame_0001.jpg"
last = "${FRAMES_FINAL}/frame_$(printf '%04d' $TARGET_FRAMES).jpg"
result = subprocess.run(
    ["magick", "compare", "-metric", "SSIM", first, last, "/dev/null"],
    capture_output=True, text=True, timeout=10
)
output = result.stderr.strip()
try:
    ssim = float(output.split()[0])
except:
    import re as r
    m = r.search(r'[\d.]+', output)
    ssim = float(m.group()) if m else 0

# First and last should NOT be identical (that would mean we
# included the loop frame). They should be somewhat similar
# (adjacent in rotation) but not a match.
if ssim > 0.95:
    print(f"  ⚠ First/last SSIM={ssim:.3f} (too similar, possible duplicate loop frame)")
elif ssim > 0.3:
    print(f"  Wrap continuity: SSIM={ssim:.3f} ✓ (smooth loop)")
else:
    print(f"  Wrap continuity: SSIM={ssim:.3f} (acceptable)")
PYEOF

[[ "$ERRORS" -gt 0 ]] && die "$ERRORS validation errors. Frames at: $FRAMES_FINAL"
ok "All validations passed"

# ============================================================
# STEP 7: GENERATE VIEWER + DEPLOY
# ============================================================
log "Step 7/7: Building viewer..."

CHAR_DISPLAY=$(echo "$CHARACTER" | sed 's/-/ /g' | sed 's/\b\(.\)/\u\1/g')

sed \
  -e "s|<title>360 Viewer</title>|<title>${CHAR_DISPLAY} — 360° Viewer</title>|" \
  -e "s|const TOTAL_FRAMES = [0-9]*;|const TOTAL_FRAMES = ${TARGET_FRAMES};|" \
  -e "s|const sensitivity = [0-9.]*;|const sensitivity = ${SENSITIVITY};|" \
  "$TEMPLATE" > "${FRAMES_FINAL}/index.html"

ok "Viewer HTML generated"

if [[ "$DEPLOY" == true ]]; then
  DEPLOY_DIR="${DEPLOY_ROOT}/${CHARACTER}"

  if [[ -d "$DEPLOY_DIR" ]] && [[ $(find "$DEPLOY_DIR" -name 'frame_*.jpg' | wc -l) -gt 0 ]]; then
    BACKUP="${DEPLOY_DIR}.bak.$(date +%s)"
    warn "Backing up existing viewer to $(basename $BACKUP)"
    mv "$DEPLOY_DIR" "$BACKUP"
  fi

  mkdir -p "$DEPLOY_DIR"
  cp "${FRAMES_FINAL}"/frame_*.jpg "$DEPLOY_DIR/"
  cp "${FRAMES_FINAL}/index.html" "$DEPLOY_DIR/"

  DEP_COUNT=$(ls "$DEPLOY_DIR"/frame_*.jpg | wc -l)
  [[ "$DEP_COUNT" -eq "$TARGET_FRAMES" ]] || die "Deploy verify failed: $DEP_COUNT frames"
  [[ -f "$DEPLOY_DIR/index.html" ]] || die "Deploy verify failed: no index.html"

  echo ""
  echo -e "${GREEN}════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  DEPLOYED: https://roarofwinchester.com/360-viewer/${CHARACTER}/${NC}"
  echo -e "${GREEN}════════════════════════════════════════════${NC}"

  # Clean up work dir on successful deploy
  rm -rf "$WORKDIR"
else
  echo ""
  echo -e "${CYAN}════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  BUILD COMPLETE: ${FRAMES_FINAL}/${NC}"
  echo -e "${CYAN}  Run again with --deploy to push live${NC}"
  echo -e "${CYAN}════════════════════════════════════════════${NC}"
fi

echo ""
echo "Summary:"
echo "  Character:     $CHAR_DISPLAY"
echo "  Source:        $(basename $VIDEO) (${V_WIDTH}x${V_HEIGHT} @ ${V_FPS}fps, ${V_DURATION}s, ${RAW_COUNT} frames)"
echo "  360° range:    frames 1-${BOUNDARY_FRAME} of ${RAW_COUNT}"
echo "  Output:        ${TARGET_FRAMES} frames @ ${TARGET_W}x${TARGET_H}"
echo "  Avg frame:     $((AVG_SIZE / 1024))KB"
echo "  Total size:    ~$((AVG_SIZE * TARGET_FRAMES / 1024 / 1024))MB"
