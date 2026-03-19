# Troubleshooting

Common issues and solutions when building 360° character viewers.

---

## Video Generation Issues

### "The character rotates instead of the camera"
**Cause:** Missing or weak negative prompt.  
**Fix:** Your negative prompt MUST include: `subject rotation, turntable, body movement, subject turning, walking, shifting, swaying, zooming, character movement`. This tells Veo to move the camera, not the subject.

Also add this sentence at the END of your main prompt:  
> "The subject does not move, rotate, or shift position at any point."

### "The character's appearance changes between frames"
**Cause:** Vague character description or description placed too early in the prompt.  
**Fix:** Place your character description at the END of the prompt, after all camera/lighting/environment instructions. Be extremely specific: don't say "brown hair," say "shoulder-length chestnut-brown hair with natural wave, parted slightly left." Every garment, every feature, every color must be explicit.

### "The video has special effects, glowing, or particles"
**Cause:** Missing the "NO SPECIAL EFFECTS" bookends.  
**Fix:** Include `NO SPECIAL EFFECTS` at both the START and END of your prompt. Veo 3 tends to add cinematic flair unless explicitly told not to.

### "Google blocked my generation (safety filter)"
**Cause:** Google's content safety system flagged the image or prompt.  
**Fix:** This can happen even with AI-generated reference images. Try:
- Ensuring clothing fully covers the character
- Removing any language that could be interpreted as depicting a real person
- Using `person_generation="allow_all"` in the API config
- If using Gemini App, try Vertex AI Media Studio instead (fewer restrictions)

### "The background shifts or warps during rotation"
**Cause:** Complex environment in the prompt.  
**Fix:** Use a dark studio background. Complex scenes introduce parallax that breaks the rotation illusion. Stick with: "minimalist, dark studio stage with a subtle, non-reflective matte-grey concrete floor."

---

## Frame Extraction Issues

### "Frames are blurry"
**Cause:** Low quality setting in ffmpeg.  
**Fix:** Use `-qscale:v 2` (high quality JPEG) or extract as PNG:
```bash
ffmpeg -i video.mp4 -qscale:v 2 frames/frame_%04d.jpg
# Or for lossless:
ffmpeg -i video.mp4 frames/frame_%04d.png
```

### "Too many or too few frames"
**Cause:** Wrong frame count for smooth rotation.  
**Fix:** An 8-second Veo video at ~24fps produces ~192 frames. For a full 360° rotation, every frame matters. Don't skip frames unless file size is critical. If you need fewer:
```bash
# Extract every 3rd frame (~64 frames)
ffmpeg -i video.mp4 -vf "select=not(mod(n\,3))" -vsync vfr -qscale:v 2 frames/frame_%04d.jpg
```

### "The rotation doesn't loop seamlessly"
**Cause:** The first and last frames don't match perfectly.  
**Fix:** This is a known limitation of AI video generation. The viewer uses modulo arithmetic to wrap, so a small seam is normal. To minimize it:
- Trim 2-3 frames from each end before building the viewer
- Use frame interpolation to generate a transition frame

---

## Viewer Issues

### "The viewer is laggy on mobile"
**Cause:** Too many high-resolution frames loading at once.  
**Fix:** 
- Resize frames to 512px or 720px wide: `mogrify -resize 720x frames/*.jpg`
- Use JPEG at quality 80 instead of PNG
- Reduce to 48-72 frames instead of 192

### "Touch/drag doesn't work on iOS"
**Cause:** Missing touch event handling or `touch-action` CSS.  
**Fix:** The included `viewer/index.html` handles this. Make sure your container has:
```css
touch-action: none;
```
And that your JS listens for both `mousedown/mousemove/mouseup` AND `touchstart/touchmove/touchend`.

### "Frames load but viewer shows a black box"
**Cause:** Frame paths don't match what the JS expects.  
**Fix:** Check the frame naming convention in `index.html`. By default it expects `frame_0001.jpg`, `frame_0002.jpg`, etc. If your frames use different naming, update the path pattern in the JavaScript.

---

## Deployment Issues

### "Images don't load when deployed"
**Cause:** Relative paths broken, or server not serving the frames directory.  
**Fix:** Ensure your frame images are in the same directory structure as your local setup. Check browser dev console (F12) for 404 errors on frame URLs.

### "CORS errors in browser console"
**Cause:** Loading frames from a different domain.  
**Fix:** Either serve everything from the same domain, or configure CORS headers on your image server:
```
Access-Control-Allow-Origin: *
```

---

## Still Stuck?

- Check the [full tutorial](https://anenduringspark.com/360-tutorial/) for step-by-step screenshots
- Watch the [video walkthrough](https://www.youtube.com/watch?v=x2OZo0gTfck)
- Open an issue on this repo with your prompt, error message, and what you've tried
