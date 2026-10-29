# Weave

Weave is an experimental, local image-to-machine-embroidery prototype. Import artwork, choose a physical size and colors, inspect the actual stitch path, and export a Brother-compatible PES file. Images stay on your computer.

## Run

Install Python 3.10 or newer, then in this folder run:

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Open http://127.0.0.1:8765. On macOS or Linux, use `python3 -m venv .venv`, then `.venv/bin/python` in the remaining commands. Stop the server with Ctrl+C.

## Using Weave

Upload a PNG, JPEG or SVG, select the background and palette settings, and set the size. The 5 × 7 inch hoop is rotatable; the design must fit in either orientation. Preview is the generated stitch path, not a simulation of thread on fabric. Save a `.weave.json` project to retain the original image and settings. Open it later using Open project. Export PES and transfer it to the machine using its supported workflow.

Background removal is a simple corner-color heuristic, not subject segmentation. Complex images are simplified, and small details can disappear. Click a thread-color swatch to change it; changing the color count or background resets the swatches. SVGs are rasterized by the browser; external resources and scripts are not supported. Exports are experimental: start on stabilized woven cotton, inspect the design on the machine, and supervise a test stitch-out. The software has not been verified on the NS2750D. It does not calculate underlay or pull compensation; outlines cover horizontal boundaries only. It does not support split designs, satin digitizing, or multi-position hoops.

## Tests

`python -m unittest discover -s tests` exercises conversion, bounds, project-independent settings, and PES readback. See `docs/quality.md` for the evaluation protocol and current limitations.
