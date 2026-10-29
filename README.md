# Weave

A local image-to-embroidery studio for experimental Brother PES designs. Artwork stays on your computer. The current target is the NS2750D's 5 × 7 inch single-position area; machine compatibility and sew quality still require a physical test.

## Start on Windows

Install Python 3.12, then run `powershell -ExecutionPolicy Bypass -File setup.ps1` in this folder. Setup creates a local Python environment and downloads the official Ink/Stitch 3.3.0 portable release, verifying its SHA-256 checksum. No account or paid API is needed. After setup, open **start.bat**, keep its window open, and visit **http://127.0.0.1:8765**.

To open a particular PNG or JPEG at startup:

```powershell
.\run.ps1 -Image 'C:\path\to\artwork.jpg'
```

You can supply an existing compatible Ink/Stitch executable with the `WEAVE_INKSTITCH` environment variable. The bundled setup is Windows-specific. Other platforms need their own compatible executable and Python dependencies.

## Workflow

1. Upload PNG, JPEG or standalone SVG. Set the artwork size in millimeters; proportions are locked by default. The logo preset starts at 120 mm, with white and navy (`#002e5d`) thread.
2. **Prepare artwork.** Exterior-connected white is removed for the logo preset. Enclosed white stays white thread. Other artwork can use a 2–8 color palette. SVG uploads are currently rasterized in the browser before tracing.
3. Review **Prepared shapes**, zoom into small details, and change colors if needed. Changing any conversion setting invalidates the old stitch result. Use the editable SVG download for further work in Inkscape with Ink/Stitch.
4. **Generate reviewed artwork.** Ink/Stitch plans tatami fill, underlay, travel and tie stitches. Generation is a cancellable background job; complicated shapes can take several minutes.
5. Inspect **PES stitches** and the actual sewn dimensions. The preview is reconstructed from the final exported PES, with the same colors, order and coordinates. **Download PES** returns those exact bytes.
6. Save a `.weave.json` project to retain the original image, dimensions, palette, settings and proportion lock. Reopening restores these and asks you to prepare again. Version 1 projects are supported with the general artwork palette.

## Pipeline

`preparation.py` performs physical-scale sampling, JPEG noise cleanup, palette assignment, exterior background masking, VTracer cutout tracing, polygon repair, nominal edge overlap and 0.075 mm edge simplification. It writes separate regions, with holes preserved, into versioned Ink/Stitch SVG.

`inkstitch_backend.py` invokes the official engine as a separate program. The cotton starting preset uses 0.45 mm fill-row spacing, 3 mm maximum fill stitch length, 2 mm underlay spacing, 0.4 mm underlay inset and 0.15 mm expansion around fill edges. These are starting values, not a calibrated fabric recipe. White sews before navy, using different fill angles. Travel follows region boundaries. The slower directional pull-compensation and interior-routing modes are disabled for this prototype; uniform edge expansion still needs fabric calibration.

Ink/Stitch exports PES and its original RGB thread list (EDR). Weave restores those colors and writes PES version 6 using pyembroidery, then reopens the final bytes and checks stitch bounds, thread sequence and counts. It rejects stitches exceeding the hoop. The job service caches the verified file; downloading does not regenerate it. An identical prepared SVG can also reuse its verified PES from the local cache, so repeated conversions avoid the engine startup and routing cost. There is no silent fallback to the old scanline engine. `engine.py` remains solely for comparison with the original prototype.

## Current limits

This is assisted automatic digitizing, not proven production output. Automatic satin columns, dedicated running-stitch recovery for whiskers, manual region editing, lettering digitizing and multi-position hoops are not implemented. Ink/Stitch can treat very small fills as outline runs; Weave does not yet classify these for the user. Small text, the cougar's trademark, skinny lines and photographs need careful inspection. A software preview cannot predict fabric distortion, registration, tension or thread breaks. Trim commands are present, but the NS2750D's handling must be checked physically.

The server binds only to loopback and rejects cross-site conversion requests. Projects are downloaded to the browser's local download location. `.local`, `.tools`, `.deps`, `.venv`, PES files and saved projects are ignored by Git. Do not add personal artwork to the public repository.

## Verification

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
$env:WEAVE_INTEGRATION = '1'
.\.venv\Scripts\python -m unittest discover -s tests -v
```

The second command runs the installed Ink/Stitch engine in addition to isolated tests. For the development-only `.deps` layout, set `$env:PYTHONPATH = Join-Path (Get-Location) '.deps'` first.

See [quality protocol](docs/quality.md) and [third-party tools](docs/dependencies.md).
