# 360° Character Viewer: LARS Build Guide

## Proven Pipeline (V2 Method)

The gold standard for smooth 360° viewers. Every new viewer should follow this.

### Step 1: Extract all frames from source video
```bash
mkdir -p /tmp/viewer-build/frames-raw
ffmpeg -y -i INPUT.mp4 -q:v 3 /tmp/viewer-build/frames-raw/frame_%04d.jpg
```

### Step 2: Find the 360° trim point
Use the multi-metric analysis (SSIM + color histogram + bilateral symmetry):
- Compute combined score for every frame vs frame 1
- Weights: SSIM 35%, histogram correlation 40%, bilateral symmetry 25%
- Find the last peak in the final 25% (smoothed derivative zero-crossing)
- That frame = the 360° completion point

Key insight: **bilateral symmetry** is the strongest signal for detecting front-facing
poses in AI-generated video, where pixel-level SSIM breaks down due to visual drift.

### Step 3: Sample 192 frames evenly from the usable range
This is what makes the viewer feel smooth. DO NOT use all raw frames.

```python
usable = trim_point  # e.g. 290
target = 192
indices = [round(i * (usable - 1) / (target - 1)) + 1 for i in range(target)]
```

Why 192: provides ~1.9° per frame angular resolution. Enough density for fluid
drag interaction without excessive file size. The novel character viewers all
used 192 and Nick confirmed they felt the best.

### Step 4: Resize for web
```bash
convert frame.jpg -resize x1280 output.jpg  # height 1280, preserve aspect
```

### Step 5: Generate viewer HTML
- Frame count: 192
- Sensitivity: 0.35 (calibrated for 192 frames)
- Include zoom controls (pinch + scroll + buttons)
- Include momentum physics on drag release

### Step 6: Deploy
```
output-dir/
  index.html
  frames-web/
    frame_0001.jpg
    frame_0002.jpg
    ... (192 files)
```

## Sensitivity Settings
| Frame Count | Sensitivity |
|-------------|-------------|
| <=72        | 0.25        |
| 73-144      | 0.35        |
| >=145       | 0.40        |

Exception: 192 frames uses 0.35 (confirmed best feel by Nick).

## Frame Count Guidelines
| Source Frames | Output Target |
|---------------|---------------|
| <100          | Use all (min 36) |
| 100-191       | Use all minus loop frame |
| 192+          | Sample to 192 |

## What Doesn't Work
- **MDS reordering**: Mathematically elegant but produces visual jumps.
  Frames from different moments in the generation look similar by metrics
  but don't flow together. Contiguous frames always beat reordered ones.
- **Raw frame dump**: Using all 290+ frames creates uneven angular spacing
  because AI models don't rotate at constant speed. Always sample evenly.
- **SSIM-only trim detection**: SSIM vs frame 1 fails for AI video because
  of visual drift. The character at 360° looks different enough from frame 1
  that SSIM stays low (~0.3). Must combine with symmetry and histogram metrics.

## Deployed Viewers (Reference)
All novel character viewers: 192 frames, 0.35 sensitivity, x1280 height.
Confirmed by Nick as the best feel.

## Tools
- `build-viewer.py`: Full automated pipeline (original, uses SSIM-only)
- `auto-rotate.py`: MDS-based reordering (experimental, not recommended)
- `360-builder.html`: Browser-based builder with frame strip editor
