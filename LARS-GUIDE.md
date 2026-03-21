# 360° Viewer Build Guide — Lars Self-Reference

**Read this EVERY TIME before doing 360° viewer work. No exceptions.**

---

## The Pipeline

```
Video file or frames → build-viewer.py → deployed viewer
```

One command. No manual steps. No ad-hoc ffmpeg. No guessing frame counts.

```bash
cd /root/larsengine/workspace/360-viewer-toolkit
python3 build-viewer.py /path/to/video.mp4 character-name --deploy
```

---

## What the Script Does

1. **Probes** video (fps, resolution, duration, total frames)
2. **Extracts** ALL frames from the video
3. **Analyzes rotation** using SSIM:
   - Scans ~80 sample frames vs frame 1
   - Finds the global SSIM minimum (opposite side of rotation)
   - Finds the SSIM peak in the final 30% of the video (loop point)
   - If peak > 0.90: high confidence (clean 360° loop)
   - If peak > 0.75: medium confidence
   - If peak < 0.75: low confidence / bad source
4. **Samples** the target frame count from ONLY the 360° range
5. **Crops/resizes** to 1280x720 (or preserves portrait for portrait sources)
6. **Validates** dimensions, sequence continuity, file integrity, wrap smoothness
7. **Generates** viewer HTML from template
8. **Deploys** to /var/www/roarofwinchester/360-viewer/{character}/

---

## Finding the Front-Facing Center Frame

**CRITICAL: Frame 1 of a video is NOT always the front-facing frame.**

Videos may have been trimmed, or the rotation may not start at dead center.
The pipeline must find the true front-facing frame using these methods:

### Method 1: Face Detection (coarse)
- Use OpenCV frontal face cascade on all frames
- Find frames with largest face bounding box + smallest center offset
- Two clusters will appear: zone 1 (first pass) and zone 2 (return pass)

### Method 2: Bilateral Symmetry (medium)
- Mirror each frame left-to-right and compare to original
- Most symmetric frame = most frontal
- Works for full-body shots, not just faces

### Method 3: SSIM Match to Known Reference (precise)
- If you have a reference image of the correct center, compare all frames
- Highest SSIM = the matching frame

### Method 4: Manual START_FRAME Adjustment (final tuning)
- Set `START_FRAME` in the viewer JS to offset the load frame
- 0-indexed: START_FRAME = 0 means frame_0001.jpg loads first
- Small adjustments (2-5 frames) to fine-tune after automated detection

### The Wrap-Around Rule
If the front-facing frame is detected in zone 2 (the return pass),
the sampling range wraps: start at zone 2 center, continue through
end of video, wrap to beginning, stop before zone 2 center repeats.

---

## Standards (Never Deviate)

| Parameter     | Value                    |
|---------------|--------------------------|
| Output frames | 192 (default, adjustable)|
| Dimensions    | 1280x720 JPG (16:9) or preserve portrait |
| JPG quality   | 92                       |
| Sensitivity   | 0.4                      |
| Frame naming  | frame_0001.jpg - NNNN    |
| Frame location| Flat in character dir    |

---

## Critical Logic: Frame Count ≠ Rotation

**THIS IS THE MISTAKE TO NEVER REPEAT.**

- 192 frames from an 8s/24fps video with exactly 360° = perfect
- 521 frames from a longer video with 380° rotation = WRONG if you blindly sample 192

The SSIM analysis detects actual rotation extent. Respect its output.
If confidence is "low," the video is not usable. Tell Nick.

---

## Video Quality Checklist (Before Running Build)

Before processing ANY video:

1. [ ] Subject stays consistent throughout (no face morphing)
2. [ ] Camera orbits smoothly (no jerks or speed changes)
3. [ ] Background stays consistent (no scene changes)
4. [ ] Subject is centered in source video
5. [ ] Run --dry-run first. Confidence must be "medium" or "high"
6. [ ] If confidence is "low" — DO NOT deploy. Flag the source.

---

## When Source is Pre-Extracted Frames (No Video File)

If you have frames already extracted (like the LTX Emily case):

1. Run SSIM analysis directly on the frames (see emily-ltx rebuild code)
2. Use face detection to find the front-facing center frame
3. Find the 360° counterpart using SSIM from center frame to all frames
4. Sample from [center, center+360°), handling wrap-around if needed
5. Set START_FRAME in viewer if the sampled frame 1 isn't perfectly centered

---

## SSIM Curve Patterns for Human 360° Orbits

Human figures produce a **W-shaped** SSIM curve (vs frame 1):
- Dip 1 at ~90° (first profile view)
- Slight rise at ~180° (back of head, symmetric lighting)
- Dip 2 at ~270° (second profile view)
- Return to ~1.0 at ~360° (loop)

Do NOT assume a single V-shaped dip at 180°. The bilateral symmetry
of human bodies means profile views (90°/270°) can have LOWER SSIM
than back-of-head (180°).

The **tail peak method** is the most reliable: find the highest SSIM
in the final 30% of the video. That's the loop point.

---

## File Locations

| What | Where |
|------|-------|
| Build script | `/root/larsengine/workspace/360-viewer-toolkit/build-viewer.py` |
| Bash wrapper | `/root/larsengine/workspace/360-viewer-toolkit/build-viewer.sh` |
| Viewer template | `/root/larsengine/workspace/360-viewer-toolkit/viewer/index.html` |
| This guide | `/root/larsengine/workspace/360-viewer-toolkit/LARS-GUIDE.md` |
| Deploy root | `/var/www/roarofwinchester/360-viewer/` |
| Master videos | `/root/larsengine/data/files/360-project-alpha/videos/` |
| Master archive | `/masters/360/archive/` |
| Live URL pattern | `https://roarofwinchester.com/360-viewer/{character}/` |

---

## Working Viewer Reference Data (verified 2026-03-20)

| Character    | Frames | Dimensions | Source | Size  |
|-------------|--------|------------|--------|-------|
| julie       | 192    | 1280x720   | Veo 3, 8s@24fps | 23MB  |
| dariah      | 192    | 1280x720   | Veo 3, 8s@24fps | 14MB  |
| emily       | 192    | 1280x720   | Veo 3, 8s@24fps | 20MB  |
| emily-ltx   | 192    | 1280x2304  | LTX, 521 frames | 21MB  |
| arthur-young| 192    | 1280x720   | Veo 3, 8s@24fps | 27MB  |
| alessia     | 192    | 1280x720   | Veo 3, 8s@24fps | 17MB  |
| doug        | 192    | 1280x720   | Veo 3, 8s@24fps | 30MB  |
| owen        | 192    | 1280x720   | Veo 3, 8s@24fps | 29MB  |
| mark        | 192    | 1280x720   | Veo 3, 8s@24fps | 4.8MB |
| dmitra      | 156    | 1280x720   | Veo 3, 8s@24fps | 17MB  |

---

## 3D Gaussian Splatting (Future Upgrade Path)

Setup guide saved at: `/root/larsengine/data/files/3d-splatting-setup-guide.md`

Two options:
- **Postshot** (app, easiest): download from jawset.com, drag in frames, train
- **Open source** (free): gaussian-splatting repo + COLMAP + CUDA

Requires Nick's RTX 3090 for the training step. VPS has no GPU.
Key risk: AI-generated frames may not have enough consistency for COLMAP.
Test with one character first before committing.
