#!/usr/bin/env python3
"""
CANONICAL 360° CHARACTER GENERATION SCRIPT
===========================================
This is the ONE script to use for all 360° character viewer generations.
Do NOT write new scripts. Do NOT use REST API. Do NOT use generativelanguage.googleapis.com.

Usage:
  python3 generate-360.py <character> <prompt_file>

Example:
  python3 generate-360.py mark data/files/360-project-alpha/prompts/mark-prompt.txt

Prerequisites:
  pip install google-genai
  gcloud auth application-default login (already done on this server)

Output:
  - Videos saved to data/files/360-project-alpha/videos/{character}-v1.mp4, v2.mp4
  - Status written to data/files/360-project-alpha/videos/{character}-gen-status.json
"""
from google import genai
from google.genai import types
import os, sys, time, json

# ============================================================
# CONFIGURATION — DO NOT CHANGE
# ============================================================
PROJECT = "your-gcp-project-id"
LOCATION = "us-central1"
MODEL = "veo-3.0-generate-001"
ASPECT_RATIO = "16:9"
NUM_VIDEOS = 2          # Nick's rule: always 2, never more
DURATION = 8            # seconds (Veo 3 max is 8)
NEGATIVE_PROMPT = "subject rotation, turntable, body movement, subject turning, walking, shifting, swaying, zooming, character movement"
REF_DIR = "references"
OUTPUT_DIR = "videos"

# ============================================================
# HOW THE API WORKS (so Lars never forgets)
# ============================================================
# 1. We use the google-genai Python SDK with vertexai=True
# 2. Authentication: gcloud application-default credentials (already configured)
# 3. client.models.generate_videos() returns a GenerateVideosOperation
# 4. Poll with: client.operations.get(operation) — NOT REST API, NOT HTTP
# 5. When operation.done == True, videos are in operation.result.generated_videos
# 6. Each video has .video.video_bytes (bytes) or .video.uri (download URL)
# 7. If URI, download with gcloud auth token in Authorization header
# ============================================================

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <character> <prompt_file>")
        sys.exit(1)
    
    character = sys.argv[1]
    prompt_file = sys.argv[2]
    
    ref_image = os.path.join(REF_DIR, f"{character}.png")
    if not os.path.exists(ref_image):
        print(f"ERROR: Reference image not found: {ref_image}")
        sys.exit(1)
    
    with open(prompt_file) as f:
        prompt = f.read().strip()
    
    # Strip any comment lines from prompt file
    prompt_lines = [l for l in prompt.split('\n') if not l.startswith('#') and l.strip()]
    prompt = ' '.join(prompt_lines)
    
    with open(ref_image, "rb") as f:
        img_bytes = f.read()
    
    status_file = os.path.join(OUTPUT_DIR, f"{character}-gen-status.json")
    
    def update_status(status, **kwargs):
        data = {"status": status, "time": time.strftime("%H:%M:%S"), "character": character, **kwargs}
        with open(status_file, "w") as f:
            json.dump(data, f)
        print(f"[{data['time']}] {character}: {status}")
    
    # Step 1: Create client
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    
    # Step 2: Submit
    update_status("submitting")
    operation = client.models.generate_videos(
        model=MODEL,
        prompt=prompt,
        image=types.Image(image_bytes=img_bytes, mime_type="image/png"),
        config=types.GenerateVideosConfig(
            aspect_ratio=ASPECT_RATIO,
            number_of_videos=NUM_VIDEOS,
            duration_seconds=DURATION,
            negative_prompt=NEGATIVE_PROMPT,
            person_generation="allow_all",
        ),
    )
    update_status("generating", operation=operation.name)
    
    # Step 3: Poll using SDK (NOT REST)
    for attempt in range(120):  # up to 20 min
        time.sleep(10)
        operation = client.operations.get(operation)
        if operation.done:
            update_status("completed", attempts=attempt+1)
            break
        if attempt % 6 == 0:
            update_status("polling", attempt=attempt+1)
    
    if not operation.done:
        update_status("timeout")
        sys.exit(1)
    
    # Step 4: Download videos
    result = operation.result
    videos = result.generated_videos if hasattr(result, 'generated_videos') else []
    
    downloaded = []
    for i, sample in enumerate(videos):
        vid_idx = i + 1
        out_path = os.path.join(OUTPUT_DIR, f"{character}-v{vid_idx}.mp4")
        video = sample.video
        
        if video and video.video_bytes:
            with open(out_path, "wb") as f:
                f.write(video.video_bytes)
            size = os.path.getsize(out_path)
            downloaded.append(f"{character}-v{vid_idx}.mp4 ({size//1024}KB)")
            print(f"  Saved {character}-v{vid_idx}.mp4 ({size//1024}KB)")
        elif video and video.uri:
            import urllib.request, subprocess
            token = subprocess.check_output(
                ["gcloud", "auth", "application-default", "print-access-token"], text=True
            ).strip()
            req = urllib.request.Request(video.uri, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(out_path, "wb") as f:
                    f.write(resp.read())
            size = os.path.getsize(out_path)
            downloaded.append(f"{character}-v{vid_idx}.mp4 ({size//1024}KB)")
            print(f"  Downloaded {character}-v{vid_idx}.mp4 ({size//1024}KB)")
    
    update_status("done", videos=downloaded)

if __name__ == "__main__":
    main()
