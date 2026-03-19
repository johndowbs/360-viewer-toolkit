# 360° Character Viewer Toolkit

Build interactive, drag-to-rotate 360° character viewers using AI video generation and a zero-dependency web viewer.

**[Live Demo](https://anenduringspark.com/360-viewer/dariah/)** | **[Full Tutorial](https://anenduringspark.com/360-tutorial/)** | **[Video Walkthrough](https://www.youtube.com/watch?v=x2OZo0gTfck)**

![Character Gallery](https://roarofwinchester.com/gallery-preview.jpg)

## What This Does

Turn a single reference image into a fully interactive 360° character viewer that runs in the browser with no libraries, no frameworks, and no build tools.

The pipeline:
1. Start with one reference image of your character
2. Generate a 360° orbital rotation video using Google Veo 3
3. Extract frames with ffmpeg
4. Drop them into the included web viewer (60 lines of vanilla JS)

## Documentation

| Document | Description |
|----------|-------------|
| **[Full Tutorial](https://anenduringspark.com/360-tutorial/)** | Step-by-step web guide with screenshots |
| **[Video Walkthrough](https://www.youtube.com/watch?v=x2OZo0gTfck)** | 3-minute narrated tutorial |
| **[Prompt Guide](PROMPT-GUIDE.md)** | Deep dive into prompt engineering for consistent 360° rotations |
| **[Troubleshooting](TROUBLESHOOTING.md)** | Common issues and solutions |
| **[Examples](EXAMPLES.md)** | Gallery of live viewers built with this toolkit |
| **[Contributing](CONTRIBUTING.md)** | How to contribute |

## Quick Start

### Prerequisites

- Python 3.8+ with `google-genai` package
- Google Cloud account with Vertex AI API enabled
- ffmpeg
- Any static web server (GitHub Pages, Netlify, Cloudflare Pages, Nginx, etc.)

### 1. Clone and Install

```bash
git clone https://github.com/johndowbs/360-viewer-toolkit.git
cd 360-viewer-toolkit
pip install google-genai
```

### 2. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

You need a Google Cloud project with the Vertex AI API enabled. See the [full tutorial](https://anenduringspark.com/360-tutorial/#step-3) for details on using the browser-based Gemini App or Vertex AI Media Studio as alternatives to the Python script.

### 3. Add Your Reference Image

Place your character's reference image in `references/` as a PNG file. Tips:
- Full body, centered, neutral pose
- Clean background
- 1024x1024 minimum resolution
- Painterly or illustrated styles produce the most consistent results

### 4. Write Your Prompt

Copy the template and fill in your character's details:

```bash
cp prompts/template.txt prompts/mycharacter.txt
# Edit prompts/mycharacter.txt with your character description
```

See the **[Prompt Guide](PROMPT-GUIDE.md)** for detailed instructions on what makes a good prompt. The prompt is the most critical part of the process.

### 5. Generate the Video

**Option A: Python script (automated)**
```bash
python generate-360.py mycharacter prompts/mycharacter.txt
```

**Option B: Gemini App (browser-based)**
1. Go to [gemini.google.com](https://gemini.google.com)
2. Upload your reference image
3. Paste your prompt
4. Select Veo 3, 16:9 aspect ratio, 8 seconds

**Option C: Vertex AI Media Studio (browser-based)**
1. Go to [console.cloud.google.com/vertex-ai/generative/media-studio](https://console.cloud.google.com/vertex-ai/generative/media-studio)
2. Select "Video generation" and model "veo-3.0-generate-001"
3. Upload reference image, paste prompt
4. Set: 16:9, 8 seconds, person generation allowed

### 6. Extract Frames

```bash
mkdir -p viewer/frames
ffmpeg -i videos/mycharacter-v1.mp4 -qscale:v 2 viewer/frames/frame_%04d.jpg
```

This extracts ~192 frames from the 8-second video. Each frame is one angle of the rotation.

### 7. Configure the Viewer

Open `viewer/index.html` and update the configuration at the top:

```javascript
const CONFIG = {
    frameCount: 192,        // Number of frames extracted
    frameDir: 'frames',     // Directory containing frames
    framePrefix: 'frame_',  // Filename prefix
    frameExt: '.jpg',       // File extension
    framePad: 4,            // Zero-padding digits (frame_0001)
};
```

### 8. Deploy

Copy `viewer/index.html` and the `viewer/frames/` directory to any static web host.

```bash
# Example: deploy to a directory on your server
scp -r viewer/ user@yourserver:/var/www/mycharacter-viewer/
```

Works with GitHub Pages, Netlify, Cloudflare Pages, Vercel, or any web server.

## Project Structure

```
360-viewer-toolkit/
├── README.md                   # This file
├── PROMPT-GUIDE.md             # Detailed prompt engineering guide
├── TROUBLESHOOTING.md          # Common issues and fixes
├── EXAMPLES.md                 # Gallery of live examples
├── CONTRIBUTING.md             # How to contribute
├── LICENSE                     # MIT License
├── generate-360.py             # Python script for Veo 3 API
├── prompts/
│   └── template.txt            # Prompt template with placeholders
├── references/                 # Place reference images here
├── videos/                     # Generated videos land here
└── viewer/
    └── index.html              # Zero-dependency web viewer
```

## How the Viewer Works

The viewer is intentionally simple: ~60 lines of JavaScript with zero dependencies.

- Preloads all frames as `Image` objects
- Maps mouse drag, touch swipe, scroll wheel, and arrow keys to a frame index
- Uses modulo arithmetic to wrap seamlessly at 360°
- Shows a loading progress bar while frames load
- Responsive: works on desktop and mobile

No Three.js, no WebGL, no canvas, no build step. Just DOM image swapping.

## Cost

Using the Veo 3 API via Google Cloud:

| Model | Rate | Cost per 8s Video |
|-------|------|-------------------|
| Veo 3 Fast | $0.10/sec | $0.80 |
| Veo 3 Standard | $0.20/sec | $1.60 |
| Veo 3 4K Audio | $0.60/sec | $4.80 |

Use Veo 3 Fast for iteration and Standard for your final generation. The Gemini App may include some free generations depending on your plan.

## Credits

This toolkit was developed while building the interactive character gallery for [An Enduring Spark](https://anenduringspark.com), an upcoming novel by Nicholas Dowbiggin. The companion site [The Roar of Winchester](https://roarofwinchester.com) showcases the full gallery of characters built with this workflow.

## License

MIT License. See [LICENSE](LICENSE) for details.
