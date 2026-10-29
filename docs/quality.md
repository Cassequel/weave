# Quality and comparison log

## October 29, 2026: local cougar benchmark

The private reference is the user's square cougar logo, requested at 120 mm with white and navy thread. The image and generated artifacts are excluded from Git. White areas inside the silhouette are stitched; only the exterior background is removed.

The original scanline engine and the new Ink/Stitch engine were evaluated from the same image at the same artwork size. More stitches are expected when preserving additional detail and adding underlay. Fewer travel moves are useful but do not prove sew quality.

| Measure | Original engine | Final Ink/Stitch preset |
| --- | ---: | ---: |
| Stitches | 8,355 | 20,460 |
| Jump / travel commands | 4,113 | 37 |
| Travel longer than 5 mm | 2,349 | 31 |
| Travel distance | 51,109.3 mm | 1,266.8 mm |
| Trim commands | Not reported | 36 |
| Longest stitch | Not reported | 3.14 mm |
| Reopened thread sequence | White / navy | White `#FFFFFF`, navy `#002E5D` |
| Actual sewn bounds | Within hoop | 120.4 × 117.4 mm |

The 120 mm setting specifies the source artwork's width; the original image has vertical margins, so the stitched silhouette is shorter than the source canvas. Compensation can make the sewn bounds slightly larger than the requested artwork width. The final file is checked against the 127 × 177.8 mm hoop in either orientation.

The final cotton preset adds nominal 0.15 mm uniform edge overlap during vector preparation. Directional pull compensation and interior travel routing produced unacceptable conversion times on this artwork. Boundary travel with underlay completed the uncompensated benchmark in approximately 65 seconds and the final preset in 69.62 seconds on the development computer. The final preset reduced travel commands by 99.1% and travel distance by 97.5% compared with the old engine. This is a routing tradeoff: boundary travel can reinforce or bulk up edges. It needs a physical comparison before being preferred on sew quality grounds.

Tracing uses opaque sentinel pixels and matches slight color rounding back to the selected palette. A regression test covers the case where VTracer rounds a large white region to `#FEFEFE`; it must remain white thread. The prepared shape preview uses the actual vector artwork, not only the cleaned raster image.

## Software checks

- Isolated tests cover background removal, retained white regions and holes, thread overrides, malformed and oversized input, hoop limits, cancelled jobs and exact export bytes.
- Integration tests run the official Ink/Stitch executable, reopen PES 6, and check physical scale, exact RGB colors, bounds and travel counts.
- Local HTTP tests cover cross-site rejection, expired preparation IDs, preparation, job completion and exact file downloads.
- Browser checks cover all three stages, cancellation, clearing stale previews on size changes, and saving/reopening the cougar project with its image and 120 mm white/navy settings intact.
- Synthetic legacy-engine checks include transparency, small features and photo-like gradients. The new pipeline is not yet calibrated for photographs or small lettering.

## Physical validation still required

No NS2750D stitch-out has been performed. Before treating a file as proven, confirm the machine label, check that it opens the PES at the correct size, and sew stabilized woven cotton using the intended thread and needle. Record fabric, stabilizer, tension, color order, machine handling of trims, thread breaks, gaps, edge registration, puckering and photographs. Compare expansion 0 versus 0.15 mm under the same conditions. Inspect the whiskers, small trademark and hat lettering in particular.

Future comparisons should include a manually digitized Ink/Stitch reference and, when available, an independent commercial digitizer. The current comparison is against Weave's old engine; it is not evidence that Weave matches expert digitizing or a commercial product.

## Reproduce locally

```powershell
.\.venv\Scripts\python scripts/benchmark.py --image 'C:\path\to\cougar.jpg' --size 120 --output .local/cougar
```

This saves the editable SVG, original-image project, PES, readback metrics and a path preview. Keep these personal artifacts local. Save physical stitch-out observations alongside them.
