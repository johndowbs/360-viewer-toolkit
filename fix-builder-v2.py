#!/usr/bin/env python3
with open('/var/www/roarofwinchester/360-viewer/builder/index.html', 'r') as f:
    html = f.read()

# FIX 1: Update pickFrameCount to always target 192 when enough frames exist
old_pick = """function pickFrameCount(analysis, fps) {
  const usable = analysis.full360Frame + 1;
  
  // If usable frames are fewer than 100, use them all (minus loop frame)
  if (usable <= 100) return Math.max(36, usable - 1);
  
  // For high-confidence 360, standard targets based on source density
  if (usable >= 288) return 192;  // Plenty of source frames: smooth output
  if (usable >= 192) return 144;  // Good source: balanced
  if (usable >= 120) return Math.min(usable - 1, 120);
  return Math.max(36, usable - 1);
}"""

new_pick = """function pickFrameCount(analysis, fps) {
  const usable = analysis.full360Frame + 1;
  
  // V2 method: 192 evenly-sampled frames is the proven sweet spot.
  // Provides ~1.9 deg angular resolution with 0.35 sensitivity.
  // Confirmed as the best feel across all deployed viewers.
  if (usable >= 192) return 192;
  if (usable <= 100) return Math.max(36, usable - 1);
  return Math.min(usable - 1, 144);
}"""

html = html.replace(old_pick, new_pick)

# FIX 2: Update sensitivity to use 0.35 for 192 frames
old_sens = """  const sensitivity = frameCount <= 72 ? 0.25 :
                      frameCount <= 144 ? 0.35 :
                      0.4;"""

new_sens = """  const sensitivity = frameCount <= 72 ? 0.25 :
                      frameCount <= 144 ? 0.35 :
                      frameCount <= 192 ? 0.35 :
                      0.4;"""

html = html.replace(old_sens, new_sens)

# FIX 3: Update 192 option label
old_select = '<option value="192">192 (smooth)</option>'
new_select = '<option value="192">192 (smooth, recommended)</option>'
html = html.replace(old_select, new_select)

# FIX 4: Update the setting hint
old_hint = '"Auto" picks the best count based on your video\'s frame rate and rotation quality.'
new_hint = '"Auto" targets 192 frames (proven smoothest). Lower for smaller files, higher for ultra-smooth.'
html = html.replace(old_hint, new_hint)

with open('/var/www/roarofwinchester/360-viewer/builder/index.html', 'w') as f:
    f.write(html)

print("Builder updated with V2 method")
