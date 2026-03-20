# 360° Viewer Build Guide — Lars Self-Reference

**Read this EVERY TIME before doing 360° viewer work. No exceptions.**

## The Pipeline

```
Video file → build-viewer.py → deployed viewer
```

One command. No manual steps. No ad-hoc ffmpeg. No guessing frame counts.

```bash
cd /root/larsengine/workspace/360-viewer-toolkit
python3 build-viewer.py /path/to/video.mp4 character-name --deploy
```

## What the Script Does (So You Never Forget)

1. **Probes** video (fps, resolution, duration, total frames)
2. **Extracts** ALL frames from the video
3. **Analyzes rotation** using SSIM comparison to frame 1:
   - Finds the 180° point (deepest similarity valley in first half)
   - Checks if SSIM rises back above 0.80 (= clean 360° loop)
   - If no loop: estimates 360° = 2 × (180° frame index)
   - Reports confidence: high/medium/low
4. **Samples** the target number of frames from ONLY the 360° range
5. **Crops/resizes** to 1280×720 (centered)
6. **Validates** dimensions, sequence continuity, file integrity, wrap continuity
7. **Generates** viewer HTML from template
8. **Deploys** to /var/www/roarofwinchester/360-viewer/{character}/

## The Standards (Never Deviate)

| Parameter     | Value                    |
|---------------|--------------------------|
| Output frames | 192 (default, adjustable)|
| Dimensions    | 1280×720 JPG             |
| JPG quality   | 92                       |
| Sensitivity   | 0.4                      |
| Frame naming  | frame_0001.jpg - NNNN    |
| Frame location| Flat in character dir    |

## Critical Logic: Frame Count ≠ Rotation

**THIS IS THE MISTAKE YOU KEEP MAKING. DON'T MAKE IT AGAIN.**

- 192 frames from an 8s/24fps video with exactly 360° = perfect
- 601 frames from a 20s video with 420° rotation = WRONG if you blindly sample 192

The SSIM analysis detects the actual rotation. Respect its output.
If confidence is "low," the video may not be usable. Tell Nick.

## When to Use --dry-run

Run `--dry-run` first when testing a new video to see the rotation analysis
without extracting/processing anything:

```bash
python3 build-viewer.py /path/to/video.mp4 test-name --dry-run
```

## Centering

The crop strategy centers on the geometric center of the frame.
For 360° orbit videos where the subject is centered in the source,
this works correctly. If the subject drifts off-center in the source
video, that's a bad source video — regenerate, don't try to fix in post.

## Video Quality Checklist (Before Running the Build)

Before processing ANY video through the pipeline, verify:

1. [ ] Subject stays consistent throughout (no face morphing)
2. [ ] Camera orbits smoothly (no jerks or speed changes)
3. [ ] Background stays consistent (no scene changes)
4. [ ] Subject is centered in source video
5. [ ] SSIM analysis shows confidence "medium" or "high"
6. [ ] If confidence is "low" — DO NOT deploy. Tell Nick.

## File Locations

- Script: `/root/larsengine/workspace/360-viewer-toolkit/build-viewer.py`
- Template: `/root/larsengine/workspace/360-viewer-toolkit/viewer/index.html`
- Deploy root: `/var/www/roarofwinchester/360-viewer/`
- Live URL: `https://roarofwinchester.com/360-viewer/{character}/`

## Working Viewer Reference Data

All approved viewers share these specs (verified 2026-03-20):

| Character    | Frames | Dimensions | Sensitivity | Size  |
|-------------|--------|------------|-------------|-------|
| julie       | 192    | 1280×720   | 0.4         | 23MB  |
| dariah      | 192    | 1280×720   | 0.4         | 14MB  |
| emily       | 192    | 1280×720   | 0.4         | 20MB  |
| arthur-young| 192    | 1280×720   | 0.4         | 27MB  |
| alessia     | 192    | 1280×720   | 0.4         | 17MB  |
| doug        | 192    | 1280×720   | 0.4         | 30MB  |
| owen        | 192    | 1280×720   | 0.4         | 29MB  |
| mark        | 192    | 1280×720   | 0.4         | 4.8MB |
| dmitra      | 156    | 1280×720   | 0.4         | 17MB  |
