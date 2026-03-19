# 360° Character Viewer Toolkit

Build interactive, drag-to-rotate 360° character viewers using AI video generation and a zero-dependency web viewer.

## What This Does

Turn a single reference image into a fully interactive 360° character viewer that runs in the browser with no libraries, no frameworks, and no build tools.

**[Live Demo](https://anenduringspark.com/360-viewer/dariah/)** | **[Full Tutorial](https://anenduringspark.com/360-tutorial/)**

## How It Works

1. Start with a reference image of your character
2. Generate a 360° orbital rotation video using Google Veo 3
3. Extract frames with ffmpeg
4. Drop them into the included web viewer

The viewer preloads all frames and maps mouse drag, touch swipe, scroll wheel, and keyboard input to frame changes. Modulo arithmetic wraps the rotation seamlessly.

## Quick Start

### Prerequisites

- Python 3.8+ with `google-genai` package
- Google Cloud account with Vertex AI API enabled
- ffmpeg
- Any static web server

### 1. Install

```bash
git clone https://github.com/johndowbs/360-viewer-toolkit.git
cd 360-viewer-toolkit
pip install google-genai
```

### 2. Add Your Reference Image

Place your character's reference image in the `references/` directory as a PNG file.

### 3. Write Your Prompt

Copy `prompts/template.txt` and fill in your character's details. See the [Prompt Guide](#prompt-guide) below.

### 4. Generate

```bash
python generate-360.py mycharacter prompts/mycharacter-prompt.txt
```

This generates 2 candidate videos in `videos/`. Watch both, pick the best one.

### 5. Extract Frames

```bash
mkdir -p viewer/frames
ffmpeg -i videos/mycharacter-v1.mp4 -qscale:v 2 viewer/frames/frame_%04d.jpg
```

### 6. Deploy

Copy `viewer/index.html` and your frames to any static web server. Done.

## Prompt Guide

The prompt is the most critical part. It must:

- **Describe the character precisely**: every garment, every facial feature, hair color/length/texture, build, pose
- **Lock the camera movement**: "mathematically precise, perfectly horizontal 360-degree circular orbit"
- **Freeze the subject**: "frozen neutral standing position, completely static"
- **Specify the environment**: minimal dark studio, three-point lighting
- **Set the style**: painterly, photorealistic, etc.

See `prompts/template.txt` for the full reusable template with inline comments.

## File Structure

```
360-viewer-toolkit/
  generate-360.py          # Video generation script (Veo 3 via Vertex AI)
  prompts/
    template.txt           # Reusable prompt template with [BRACKETS] to fill
    dariah-example.txt     # Working example prompt
  viewer/
    index.html             # Zero-dependency interactive viewer
  references/              # Your character reference images (not tracked)
  videos/                  # Generated videos (not tracked)
```

## Configuration

Edit the top of `generate-360.py`:

| Variable | Description |
|----------|-------------|
| `PROJECT` | Your Google Cloud project ID |
| `LOCATION` | Vertex AI region (default: us-central1) |
| `MODEL` | Veo model (default: veo-3.0-generate-001) |
| `NUM_VIDEOS` | Candidates to generate (default: 2) |
| `DURATION` | Video length in seconds (default: 8, max for Veo 3) |

## Viewer Customization

Edit `viewer/index.html`:

| Variable | Default | Effect |
|----------|---------|--------|
| `TOTAL_FRAMES` | 192 | Must match your extracted frame count |
| `sensitivity` | 0.15 | Drag sensitivity (higher = faster rotation) |

## Built With

- [Google Veo 3](https://cloud.google.com/vertex-ai) (video generation)
- [ffmpeg](https://ffmpeg.org/) (frame extraction)
- Vanilla HTML/CSS/JavaScript (viewer)

## Examples

This toolkit was built for [The Roar of Winchester](https://roarofwinchester.com), a fantasy novel series. You can explore the full character gallery with 10+ interactive viewers at [roarofwinchester.com/main.html#characters](https://roarofwinchester.com/main.html#characters).

## Tutorial

For a detailed walkthrough with screenshots and video, see the [full tutorial](https://anenduringspark.com/360-tutorial/).

## License

MIT
