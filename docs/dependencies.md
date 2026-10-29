# Third-party tools

Weave runs Ink/Stitch as a separately downloaded program. Its official portable distribution is retained intact, including its GPL-3.0-or-later license and notices. No Ink/Stitch source is copied into Weave and its executable is not committed here.

- Ink/Stitch 3.3.0: https://github.com/inkstitch/inkstitch/releases/tag/v3.3.0
- Windows portable ZIP SHA-256: `992a0aec0cf05ad3af1e68e89acd3a0ec65434f4e1d1a418eb54df106984addb`
- CLI documentation: https://inkstitch.org/docs/command-line/
- Fill settings: https://inkstitch.org/docs/stitches/fill-stitch/
- SVG version metadata and supported settings: https://github.com/inkstitch/inkstitch/blob/v3.3.0/lib/update.py and https://github.com/inkstitch/inkstitch/blob/v3.3.0/lib/elements/fill_stitch.py
- VTracer: https://github.com/visioncortex/vtracer (MIT); image-to-vector cutout tracing.
- pyembroidery: https://github.com/EmbroidePy/pyembroidery (MIT); PES 6 writing and readback.
- Pillow, NumPy, SciPy and Shapely: image processing, connected regions and topology repair; their packages retain their own license notices.

Do not assume another Ink/Stitch version accepts the same parameters. Re-run integration tests when upgrading. The browser preview is a path rendering, not a fabric simulation.
