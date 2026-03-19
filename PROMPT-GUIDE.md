# Prompt Engineering Guide for 360° Character Viewers

This guide covers everything learned from generating 100+ character rotation videos with Google Veo 3. These principles apply whether you're using the Gemini App, Vertex AI Media Studio, or the Python API.

---

## The Golden Rule

**Camera instructions first. Character description last.**

AI video models have a strong recency bias. Whatever appears last in the prompt gets the most "attention." If you put your character description first, the model will focus on creative interpretation of the character at the expense of following your camera directions. Put the technical requirements first so they're treated as hard constraints, then describe the character as the final detail.

---

## Prompt Anatomy

Every successful 360° prompt has these sections in this exact order:

### 1. Opening Declaration
```
A high-fidelity, production-grade 360-degree orbital camera rotation shot 
for a professional 3D character viewer. NO SPECIAL EFFECTS.
```
This sets the tone. "Production-grade" and "professional" push the model toward consistency. "NO SPECIAL EFFECTS" at the top primes the model to avoid adding particles, glow, etc.

### 2. Camera Movement
```
Camera Movement: The camera performs a mathematically precise, perfectly 
horizontal 360-degree circular orbit at a constant eye-level height and 
a fixed 3-meter radius. Zero vertical tilt, zero zoom fluctuation.
```
Be obsessively specific. "Mathematically precise" and "perfectly horizontal" matter. Without these, you'll get wobbly, drifting orbits.

### 3. Environment
```
Environment: Standing at the exact center of a minimalist, dark studio stage 
with a subtle, non-reflective matte-grey concrete floor.
```
Dark, simple backgrounds produce the best results. Detailed environments introduce inconsistencies between frames.

### 4. Lighting
```
Lighting: Professional three-point studio lighting; Key light, Fill light, 
and Backlight remain stationary relative to the subject to ensure 
consistent shadows.
```
The key phrase is "remain stationary relative to the subject." Without this, shadows shift frame-to-frame and break the illusion.

### 5. Temporal Consistency
```
Temporal Consistency: 100% frame-to-frame coherence. No morphing, no 
flickering, no background shifting.
```
This is your insurance policy against the model getting creative between frames.

### 6. Style
```
Maintain heavy cinematic oil painting painterly style with rich warm palette, 
dramatic chiaroscuro lighting, and visible confident brushstrokes throughout.
```
Adapt this to your art style. The key is being specific and consistent. If you want photorealistic, say "photorealistic, shot on Canon EOS R5, 85mm f/1.4" etc.

### 7. Character Description (LAST)
```
Subject: A full-body view of this same exact woman, same exact face: 
A 22-year-old woman with warm olive-toned skin and a flawless complexion...
[full description continues]
```
Start with "this same exact [man/woman], same exact face" to anchor identity. Then describe EVERYTHING: age, skin tone, hair (color, length, style, texture), eyes (color, shape), facial features (lips, nose, eyebrows, jawline), build, and every single clothing item with color, fit, and fabric.

### 8. Closing Lock
```
NO SPECIAL EFFECTS, no particles, no glowing, no aura, no magical elements.
The subject does not move, rotate, or shift position at any point.
```
Repeat the no-effects instruction and add the subject-lock. Belt and suspenders.

---

## Negative Prompt

Set this in the API configuration (not in the main prompt text):

```
subject rotation, turntable, body movement, subject turning, walking, 
shifting, swaying, zooming, character movement
```

This is critical. Without it, Veo will rotate the CHARACTER instead of orbiting the CAMERA around a static character.

---

## Reference Image Tips

- **Painterly style works best** for consistency. Photorealistic references can trigger the "celebrity look-alike" safety filter.
- **Full body, centered, neutral pose.** Arms at sides or slightly away from body.
- **Clean background.** The reference doesn't need to match the studio background; it's just for character identity.
- **High resolution.** 1024x1024 minimum. The more detail the model can see, the more it preserves.

---

## API Settings That Matter

```python
config = types.GenerateVideosConfig(
    aspect_ratio="16:9",        # Landscape for character viewers
    number_of_videos=1,         # Start with 1 to save cost, bump to 2 for finals
    duration_seconds=8,         # Veo 3 maximum; gives ~192 frames at 24fps
    negative_prompt="...",      # See above
    person_generation="allow_all",  # Required for human characters
)
```

---

## Cost Optimization

- **Iterate with Veo 3 Fast** ($0.10/sec = $0.80 per 8s video) until you nail the prompt
- **Switch to Veo 3 Standard** ($0.20/sec = $1.60 per video) for the final generation
- **Use 1 candidate** during iteration, 2 for the final to pick the best
- Each API call with 2 candidates costs double (2 videos generated)

---

## Common Mistakes

| Mistake | Result | Fix |
|---------|--------|-----|
| Character description at start of prompt | Model "interprets" appearance creatively | Move description to end |
| No negative prompt | Character spins in place | Add subject movement negative prompt |
| Vague clothing description | Outfit changes between frames | Name every garment with color and fit |
| Complex background | Background warps during rotation | Use dark studio |
| Missing "same exact face" | Face drifts across frames | Add identity anchor phrase |
| No "NO SPECIAL EFFECTS" | Magical particles appear | Add at start AND end of prompt |

---

## Example Prompts

See `prompts/template.txt` for the full template. For complete examples that produced the live demos at [roarofwinchester.com](https://roarofwinchester.com), check the [full tutorial](https://anenduringspark.com/360-tutorial/).

---

## Further Reading

- [Full Tutorial](https://anenduringspark.com/360-tutorial/) — step-by-step with screenshots
- [Video Walkthrough](https://www.youtube.com/watch?v=x2OZo0gTfck) — 3-minute narrated guide
- [Google Veo Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/video/overview)
