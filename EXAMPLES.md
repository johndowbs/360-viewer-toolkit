# Examples Gallery

Live interactive viewers built with this toolkit. Click any link to try the drag-to-rotate viewer yourself.

---

## Characters from "An Enduring Spark"

These viewers were all created using the workflow in this repository, from a single reference image each.

| Character | Viewer Link | Style |
|-----------|------------|-------|
| Dariah | [Interactive Viewer](https://anenduringspark.com/360-viewer/dariah/) | Painterly oil painting |
| Julie | [Interactive Viewer](https://anenduringspark.com/360-viewer/julie/) | Painterly oil painting |
| Arthur (Young) | [Interactive Viewer](https://anenduringspark.com/360-viewer/arthur-young/) | Painterly oil painting |
| Arthur (Old) | [Interactive Viewer](https://anenduringspark.com/360-viewer/arthur-old/) | Painterly oil painting |
| Emily | [Interactive Viewer](https://anenduringspark.com/360-viewer/emily/) | Painterly oil painting |
| Alessia | [Interactive Viewer](https://anenduringspark.com/360-viewer/alessia/) | Painterly oil painting |
| Doug | [Interactive Viewer](https://anenduringspark.com/360-viewer/doug/) | Painterly oil painting |
| Owen | [Interactive Viewer](https://anenduringspark.com/360-viewer/owen/) | Painterly oil painting |
| Dmitra | [Interactive Viewer](https://anenduringspark.com/360-viewer/dmitra/) | Painterly oil painting |
| Mark | [Interactive Viewer](https://anenduringspark.com/360-viewer/mark/) | Painterly oil painting |

Full gallery with all characters: [roarofwinchester.com](https://roarofwinchester.com/main.html#characters)

---

## How These Were Made

Each character followed the exact same 6-step process documented in this repo:

1. Single painted reference image (generated with Gemini image model)
2. 360° orbital video via Veo 3 with the prompt template from `prompts/template.txt`
3. Frame extraction with ffmpeg
4. Dropped into `viewer/index.html`
5. Deployed to a static web server

Total active time per character: ~30 minutes (plus ~5 minutes generation wait).

---

## Submit Your Own

Built a viewer using this toolkit? Open a pull request adding your example to this page. Include:
- A link to the live viewer
- The style/approach you used
- Any prompt modifications that worked well for your use case
