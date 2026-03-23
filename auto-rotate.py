#!/usr/bin/env python3
"""
auto-rotate.py — Automatic 360° frame reordering

Takes a video of a character rotating (possibly multiple times, with glitches,
in any direction) and produces a clean set of frames in natural rotational order.

Algorithm:
  1. Extract all frames from the video
  2. Compute compact feature vectors (color histograms + thumbnails)
  3. Build pairwise distance matrix
  4. Embed into 2D via MDS — rotation frames form a circle
  5. Sort by angle around the circle center
  6. Deduplicate overlapping rotations (keep best frame per angle bin)
  7. Export clean ordered frames + viewer HTML

Usage:
  python3 auto-rotate.py input.mp4 [--output-dir ./output] [--frames 120] [--preview]
"""
import argparse
import json
import subprocess
import shutil
import sys
from pathlib import Path
import numpy as np
from PIL import Image

# ═══════════════════════════════════════════════════════════════
# FEATURE EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_features(img_path, thumb_size=32, hist_bins=32):
    """Compact feature vector: flattened grayscale thumbnail + color histogram."""
    img = Image.open(img_path)

    # Grayscale thumbnail (captures structure/pose)
    gray = np.array(img.convert("L").resize((thumb_size, thumb_size)), dtype=np.float64)
    gray_flat = gray.flatten() / 255.0

    # Color histogram per channel (captures color distribution)
    rgb = np.array(img.convert("RGB").resize((128, 128)))
    hists = []
    for ch in range(3):
        h = np.histogram(rgb[:, :, ch], bins=hist_bins, range=(0, 256))[0].astype(np.float64)
        h /= h.sum() + 1e-10
        hists.append(h)

    hist_flat = np.concatenate(hists)

    # Combined feature vector
    return np.concatenate([gray_flat * 0.6, hist_flat * 0.4])


# ═══════════════════════════════════════════════════════════════
# DISTANCE MATRIX
# ═══════════════════════════════════════════════════════════════

def build_distance_matrix(features):
    """Euclidean distance between all pairs."""
    n = len(features)
    mat = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = np.linalg.norm(features[i] - features[j])
            mat[i, j] = d
            mat[j, i] = d
    return mat


# ═══════════════════════════════════════════════════════════════
# MDS EMBEDDING (classical / metric)
# ═══════════════════════════════════════════════════════════════

def mds_embed_2d(dist_matrix):
    """Classical MDS: embed distance matrix into 2D coordinates."""
    n = dist_matrix.shape[0]
    D_sq = dist_matrix ** 2

    # Double centering
    H = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * H @ D_sq @ H

    # Eigendecomposition — take top 2
    eigenvalues, eigenvectors = np.linalg.eigh(B)

    # Sort descending
    idx = np.argsort(-eigenvalues)
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Top 2 components
    coords = eigenvectors[:, :2] * np.sqrt(np.maximum(eigenvalues[:2], 0))
    return coords


# ═══════════════════════════════════════════════════════════════
# CIRCULAR ORDERING
# ═══════════════════════════════════════════════════════════════

def circular_order(coords_2d):
    """Sort points by angle around their centroid."""
    center = coords_2d.mean(axis=0)
    angles = np.arctan2(coords_2d[:, 1] - center[1], coords_2d[:, 0] - center[0])
    order = np.argsort(angles)
    return order, angles


# ═══════════════════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════════════════

def deduplicate_by_angle(order, angles, features, target_frames=None):
    """
    If multiple rotations overlap, multiple frames map to similar angles.
    Bin by angle and keep the one with the median feature vector (most typical).
    """
    sorted_indices = order
    sorted_angles = angles[order]

    if target_frames is None:
        # Estimate: count unique angle bins at 3° resolution
        bins = np.round(np.degrees(sorted_angles) / 3) * 3
        unique_bins = len(np.unique(bins))
        target_frames = min(unique_bins, len(order))

    # Create N evenly-spaced angle bins
    bin_edges = np.linspace(-np.pi, np.pi, target_frames + 1)
    selected = []

    for i in range(len(bin_edges) - 1):
        low, high = bin_edges[i], bin_edges[i + 1]
        mask = (sorted_angles >= low) & (sorted_angles < high)
        candidates = sorted_indices[mask]

        if len(candidates) == 0:
            continue
        elif len(candidates) == 1:
            selected.append(candidates[0])
        else:
            # Pick the frame closest to the median feature in this bin
            feats = np.array([features[c] for c in candidates])
            median_feat = np.median(feats, axis=0)
            dists = [np.linalg.norm(features[c] - median_feat) for c in candidates]
            selected.append(candidates[np.argmin(dists)])

    return selected


# ═══════════════════════════════════════════════════════════════
# VIEWER HTML
# ═══════════════════════════════════════════════════════════════

def generate_viewer_html(frame_count, sensitivity=0.3):
    """Self-contained 360° viewer HTML."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>360° Character Viewer</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden;background:#0a0a0f;touch-action:none}}
#viewer{{position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;cursor:grab}}
#viewer.dragging{{cursor:grabbing}}
#frame{{max-width:100%;max-height:100%;object-fit:contain;pointer-events:none;user-select:none;-webkit-user-select:none;transform-origin:center center;transition:transform 0.15s ease-out}}
#loading{{position:absolute;top:0;left:0;width:100%;height:100%;background:#0a0a0f;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:100;transition:opacity 0.5s ease}}
#loading.hidden{{opacity:0;pointer-events:none}}
.load-text{{color:rgba(255,255,255,0.5);font-family:-apple-system,sans-serif;font-size:0.85rem;letter-spacing:0.15em;margin-top:16px}}
.load-bar{{width:200px;height:2px;background:rgba(255,255,255,0.1);border-radius:1px;overflow:hidden;margin-top:12px}}
.load-fill{{height:100%;width:0%;background:#c9a84c;transition:width 0.2s ease}}
#hint{{position:absolute;bottom:20px;left:50%;transform:translateX(-50%);color:rgba(255,255,255,0.2);font-family:-apple-system,sans-serif;font-size:11px;letter-spacing:0.05em;transition:opacity 1s ease}}
#zoom-indicator{{position:absolute;top:16px;right:16px;padding:6px 12px;background:rgba(0,0,0,0.6);backdrop-filter:blur(8px);border:1px solid rgba(201,168,76,0.4);border-radius:8px;color:#c9a84c;font-size:0.75rem;font-weight:600;letter-spacing:0.08em;opacity:0;transition:opacity 0.3s ease;z-index:10}}
#zoom-indicator.visible{{opacity:1}}
#zoom-controls{{position:absolute;bottom:20px;right:20px;display:flex;gap:8px;z-index:10}}
.zoom-btn{{width:36px;height:36px;border-radius:50%;background:rgba(0,0,0,0.6);backdrop-filter:blur(8px);border:1px solid rgba(201,168,76,0.3);color:#c9a84c;font-size:1.1rem;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s ease}}
.zoom-btn:hover{{background:rgba(201,168,76,0.2);border-color:rgba(201,168,76,0.6)}}
</style>
</head>
<body>
<div id="viewer">
  <img id="frame" alt="360">
  <div id="loading"><div class="load-text">LOADING</div><div class="load-bar"><div class="load-fill" id="load-fill"></div></div></div>
  <div id="hint">Drag to rotate</div>
  <div id="zoom-indicator">1.0x</div>
  <div id="zoom-controls">
    <button class="zoom-btn" id="btn-out" title="Zoom out">&#8722;</button>
    <button class="zoom-btn" id="btn-reset" title="Reset">&#9675;</button>
    <button class="zoom-btn" id="btn-in" title="Zoom in">&#43;</button>
  </div>
</div>
<script>
const TOTAL={frame_count};
const sensitivity={sensitivity};
const imgs=[];
let cur=0,dragging=false,lastX=0,momentum=0,raf=null;
let zoom=1,minZoom=1,maxZoom=4,zoomStep=0.25,zoomTimer;
const viewer=document.getElementById('viewer');
const frameEl=document.getElementById('frame');
const loading=document.getElementById('loading');
const fill=document.getElementById('load-fill');
const hint=document.getElementById('hint');
const ind=document.getElementById('zoom-indicator');
function preload(){{let loaded=0;for(let i=1;i<=TOTAL;i++){{const img=new Image();img.onload=img.onerror=()=>{{loaded++;fill.style.width=(loaded/TOTAL*100)+'%';if(loaded===TOTAL){{frameEl.src=imgs[0].src;loading.classList.add('hidden');setTimeout(()=>{{hint.style.opacity='0'}},3000)}}}};img.src='frames/frame_'+String(i).padStart(4,'0')+'.jpg';imgs.push(img)}}}}
function show(idx){{cur=((idx%TOTAL)+TOTAL)%TOTAL;frameEl.src=imgs[cur].src}}
function setZoom(z){{zoom=Math.max(minZoom,Math.min(maxZoom,z));frameEl.style.transform='scale('+zoom.toFixed(2)+')';ind.textContent=zoom.toFixed(1)+'x';ind.classList.add('visible');clearTimeout(zoomTimer);zoomTimer=setTimeout(()=>ind.classList.remove('visible'),1500)}}
function tick(){{if(!dragging&&Math.abs(momentum)>0.1){{show(cur+Math.round(momentum));momentum*=0.92;raf=requestAnimationFrame(tick)}}}}
viewer.addEventListener('mousedown',e=>{{dragging=true;lastX=e.clientX;momentum=0;viewer.classList.add('dragging');if(raf)cancelAnimationFrame(raf)}});
window.addEventListener('mousemove',e=>{{if(!dragging)return;const dx=e.clientX-lastX;const steps=Math.round(dx*sensitivity);if(steps){{show(cur+steps);momentum=steps;lastX=e.clientX}}}});
window.addEventListener('mouseup',()=>{{dragging=false;viewer.classList.remove('dragging');raf=requestAnimationFrame(tick)}});
viewer.addEventListener('wheel',e=>{{e.preventDefault();if(e.ctrlKey||e.metaKey){{setZoom(zoom+(e.deltaY>0?-zoomStep:zoomStep))}}else{{show(cur+(e.deltaY>0?2:-2))}}}},{{passive:false}});
let touchMode=null,touchDist=0,touchX=0;
viewer.addEventListener('touchstart',e=>{{if(e.touches.length===2){{touchMode='pinch';touchDist=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY)}}else{{touchMode='rotate';touchX=e.touches[0].clientX;momentum=0;if(raf)cancelAnimationFrame(raf)}}}});
viewer.addEventListener('touchmove',e=>{{e.preventDefault();if(touchMode==='pinch'&&e.touches.length===2){{const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);setZoom(zoom*(d/touchDist));touchDist=d}}else if(touchMode==='rotate'){{const dx=e.touches[0].clientX-touchX;const steps=Math.round(dx*sensitivity);if(steps){{show(cur+steps);momentum=steps;touchX=e.touches[0].clientX}}}}}},{{passive:false}});
viewer.addEventListener('touchend',()=>{{touchMode=null;raf=requestAnimationFrame(tick)}});
document.getElementById('btn-in').addEventListener('click',()=>setZoom(zoom+zoomStep));
document.getElementById('btn-out').addEventListener('click',()=>setZoom(zoom-zoomStep));
document.getElementById('btn-reset').addEventListener('click',()=>setZoom(1));
document.addEventListener('keydown',e=>{{if(e.key==='+'||e.key==='=')setZoom(zoom+zoomStep);else if(e.key==='-')setZoom(zoom-zoomStep);else if(e.key==='0')setZoom(1)}});
preload();
</script>
</body>
</html>'''


# ═══════════════════════════════════════════════════════════════
# VIDEO PROBING
# ═══════════════════════════════════════════════════════════════

def probe_video(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
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
        "duration": duration,
        "total_frames": int(round(duration * fps)),
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Auto-reorder 360° video frames into natural rotation sequence"
    )
    parser.add_argument("video", help="Input video file (MP4, WebM, MOV)")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory (default: <video_name>-360/)")
    parser.add_argument("--frames", "-n", type=int, default=None,
                        help="Target frame count (default: auto)")
    parser.add_argument("--web-height", type=int, default=1280,
                        help="Resize frames to this height for web (default: 1280)")
    parser.add_argument("--preview", action="store_true",
                        help="Just analyze and show results, don't build")
    parser.add_argument("--keep-all", action="store_true",
                        help="Keep all frames (no deduplication)")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"ERROR: Video not found: {video}")
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else Path(f"{video.stem}-360")
    frames_raw = out_dir / "frames-raw"
    frames_out = out_dir / "frames"

    print(f"\n{'='*60}")
    print(f"  AUTO-ROTATE 360° PIPELINE")
    print(f"  Input: {video}")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}")

    # ── 1. Probe video ──
    print(f"\n[1/6] Probing video...")
    info = probe_video(video)
    print(f"  {info['width']}x{info['height']}, {info['fps']}fps, "
          f"{info['duration']:.1f}s, ~{info['total_frames']} frames")

    # ── 2. Extract frames ──
    print(f"\n[2/6] Extracting frames...")
    frames_raw.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-q:v", "3",
         str(frames_raw / "frame_%04d.jpg")],
        capture_output=True, check=True
    )
    raw_files = sorted(frames_raw.glob("frame_*.jpg"))
    total = len(raw_files)
    print(f"  Extracted {total} frames")

    # ── 3. Compute features ──
    print(f"\n[3/6] Computing features for {total} frames...")
    features = []
    for i, f in enumerate(raw_files):
        features.append(extract_features(str(f)))
        if (i + 1) % 50 == 0 or i + 1 == total:
            print(f"  ...{i+1}/{total}")
    features = np.array(features)

    # ── 4. Build distance matrix + MDS ──
    print(f"\n[4/6] Building distance matrix ({total}x{total} = {total*total:,} pairs)...")
    dist = build_distance_matrix(features)
    print(f"  Embedding into 2D via MDS...")
    coords = mds_embed_2d(dist)

    # ── 5. Circular ordering ──
    print(f"\n[5/6] Computing circular order...")
    order, angles = circular_order(coords)

    if args.keep_all:
        selected = list(order)
        print(f"  Keeping all {len(selected)} frames")
    else:
        target = args.frames or min(total, 120)
        selected = deduplicate_by_angle(order, angles, features, target_frames=target)
        print(f"  Deduplicated to {len(selected)} frames (target: {target})")

    if args.preview:
        print(f"\n{'='*60}")
        print("PREVIEW MODE — not building output")
        print(f"  Total raw frames: {total}")
        print(f"  Selected frames: {len(selected)}")
        print(f"  Frame indices (original): {selected[:20]}{'...' if len(selected) > 20 else ''}")
        print(f"{'='*60}")
        return

    # ── 6. Export ──
    print(f"\n[6/6] Exporting {len(selected)} reordered frames...")
    frames_out.mkdir(parents=True, exist_ok=True)

    # Calculate resize dimensions
    src_w, src_h = info["width"], info["height"]
    target_h = args.web_height
    scale = target_h / src_h
    target_w = int(src_w * scale)
    # Ensure even dimensions
    target_w = target_w if target_w % 2 == 0 else target_w + 1
    target_h = target_h if target_h % 2 == 0 else target_h + 1

    for out_idx, src_idx in enumerate(selected):
        src_file = raw_files[src_idx]
        dst_file = frames_out / f"frame_{out_idx+1:04d}.jpg"

        # Resize for web
        img = Image.open(src_file)
        img = img.resize((target_w, target_h), Image.LANCZOS)
        img.save(str(dst_file), "JPEG", quality=92)

        if (out_idx + 1) % 20 == 0 or out_idx + 1 == len(selected):
            print(f"  ...{out_idx+1}/{len(selected)}")

    # Generate viewer HTML
    sens = 0.25 if len(selected) <= 72 else (0.35 if len(selected) <= 144 else 0.4)
    html = generate_viewer_html(len(selected), sens)
    (out_dir / "index.html").write_text(html)

    # Clean up raw frames
    shutil.rmtree(frames_raw)

    # Summary
    total_size = sum(f.stat().st_size for f in frames_out.glob("*.jpg")) / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"  DONE!")
    print(f"  Output: {out_dir}/")
    print(f"  Frames: {len(selected)} @ {target_w}x{target_h}")
    print(f"  Size: {total_size:.1f}MB")
    print(f"  Viewer: {out_dir}/index.html")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
