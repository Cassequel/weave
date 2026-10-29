"""Experimental raster-to-stitch conversion. Coordinates are millimetres."""
import base64
import io
import math
from collections import deque

import numpy as np
from PIL import Image, ImageOps
from pyembroidery import EmbPattern, EmbThread, STITCH, JUMP, COLOR_CHANGE, END, write_pes

Image.MAX_IMAGE_PIXELS = 20_000_000
MAX_BYTES = 12 * 1024 * 1024


def decode_image(data):
    try:
        raw = base64.b64decode(data.split(',', 1)[1], validate=True)
        if len(raw) > MAX_BYTES:
            raise ValueError('Image is too large (maximum 12 MB).')
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im).convert('RGBA')
        if im.width * im.height > 20_000_000:
            raise ValueError('Image exceeds 20 million pixels.')
        return im
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Unable to read this image. Try a PNG or JPEG.') from exc


def convert(data, settings):
    im = decode_image(data)
    try:
        width, height = float(settings['width']), float(settings['height'])
        colors = int(settings['colors'])
        remove = bool(settings.get('removeBackground', False))
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError('Choose valid dimensions and a color count.') from exc
    if not all(math.isfinite(v) and v >= 5 for v in (width, height)):
        raise ValueError('Each dimension must be at least 5 mm.')
    if not ((width <= 127 and height <= 177.8) or (height <= 127 and width <= 177.8)):
        raise ValueError('The design must fit within the 5 × 7 inch hoop.')
    if not 2 <= colors <= 8:
        raise ValueError('Choose between 2 and 8 colors.')

    # Two pixels per millimetre provides a 0.5 mm fill-row spacing.
    w, h = max(1, round(width * 2)), max(1, round(height * 2))
    im = im.resize((w, h), Image.Resampling.LANCZOS)
    rgba = np.array(im)
    opaque = rgba[:, :, 3] >= 128
    if remove:
        # Flood only from image edges, preserving similarly colored enclosed details.
        rgb = rgba[:, :, :3].astype(np.int16)
        corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
        bg = np.median(corners, axis=0)
        candidate = np.max(np.abs(rgb - bg), axis=2) <= 25
        seen = np.zeros((h, w), dtype=bool)
        queue = deque()
        for x in range(w):
            if candidate[0, x]: queue.append((0, x))
            if candidate[h-1, x]: queue.append((h-1, x))
        for y in range(h):
            if candidate[y, 0]: queue.append((y, 0))
            if candidate[y, w-1]: queue.append((y, w-1))
        while queue:
            y, x = queue.popleft()
            if seen[y, x] or not candidate[y, x]: continue
            seen[y, x] = True
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = y+dy, x+dx
                if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx] and candidate[ny, nx]: queue.append((ny, nx))
        opaque &= ~seen
    if not opaque.any():
        raise ValueError('No visible artwork remains. Try keeping the background.')
    # Quantize only visible pixels so transparency cannot consume palette entries.
    pixels = rgba[:, :, :3][opaque]
    strip = Image.fromarray(pixels.reshape(1, -1, 3), 'RGB')
    quant = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    labels = np.full((h, w), -1, dtype=np.int16)
    labels[opaque] = np.array(quant).reshape(-1)
    palette = quant.getpalette()
    # Discard isolated regions smaller than 2 mm².
    cleaned = np.full((h,w), -1, dtype=np.int16)
    visited = np.zeros((h,w), dtype=bool)
    removed = 0
    for y in range(h):
        for x in range(w):
            color = labels[y,x]
            if color < 0 or visited[y,x]: continue
            visited[y,x] = True
            q = [(y,x)]
            for yy,xx in q:
                for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
                    ny,nx = yy+dy,xx+dx
                    if 0 <= ny < h and 0 <= nx < w and not visited[ny,nx] and labels[ny,nx] == color:
                        visited[ny,nx] = True
                        q.append((ny,nx))
            if len(q) < 8:
                removed += 1
            else:
                for yy,xx in q: cleaned[yy,xx] = color
    if not (cleaned >= 0).any():
        raise ValueError('All visible details are too small. Enlarge or simplify the image.')
    paths, threads = [], []
    # Split long runs into stitches no longer than 3 mm. Each separate row is a jump.
    def line(x1,y1,x2,y2,thread):
        paths.append([round(x1,2),round(y1,2),'jump',thread])
        steps = max(1, math.ceil(math.hypot(x2-x1,y2-y1)/3))
        for i in range(1,steps+1):
            paths.append([round(x1+(x2-x1)*i/steps,2),round(y1+(y2-y1)*i/steps,2),'stitch',thread])
    for c in sorted(int(v) for v in np.unique(cleaned) if v >= 0):
        thread = len(threads)
        threads.append('#%02x%02x%02x' % tuple(palette[c*3:c*3+3]))
        mask = cleaned == c
        for y in range(h):
            row = np.pad(mask[y].astype(np.int8), (1,1))
            diff = np.diff(row)
            starts, ends = np.where(diff == 1)[0], np.where(diff == -1)[0]
            runs = list(zip(starts, ends))
            if y % 2: runs.reverse()
            for a,b in runs:
                if b-a < 2: continue
                x1, x2 = (a+0.5)*width/w, (b-0.5)*width/w
                if y % 2: x1,x2 = x2,x1
                line(x1,(y+0.5)*height/h,x2,(y+0.5)*height/h,thread)
        # Outline horizontal exposed edges as short running-stitch segments.
        for y in range(h):
            above = mask[y-1] if y else np.zeros(w, dtype=bool)
            below = mask[y+1] if y+1 < h else np.zeros(w, dtype=bool)
            edge = mask[y] & (~above | ~below)
            d = np.diff(np.pad(edge.astype(np.int8),(1,1)))
            for a,b in zip(np.where(d == 1)[0],np.where(d == -1)[0]):
                if b-a >= 2: line((a+0.5)*width/w,(y+0.5)*height/h,(b-0.5)*width/w,(y+0.5)*height/h,thread)
    if not any(p[2] == 'stitch' for p in paths):
        raise ValueError('The design contains no usable stitches. Enlarge or simplify it.')
    if len(paths) > 250000:
        raise ValueError('The design is too complex. Reduce colors or simplify the image.')
    overrides = settings.get('threadColors', [])
    if not isinstance(overrides, list) or len(overrides) > 8:
        raise ValueError('Invalid thread colors.')
    import re
    for i, color in enumerate(overrides[:len(threads)]):
        if color is not None:
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('Invalid thread color.')
            threads[i] = color.lower()
    warnings = ['Experimental design: test on stabilized scrap fabric. No underlay or pull compensation is generated.', 'Fine details and photographs are simplified. Preview does not predict fabric movement or thread appearance.', 'Separate rows create jump stitches that may require trimming.']
    if remove: warnings.append('Background removal uses edge colors and may remove parts of the artwork.')
    if removed: warnings.append(f'{removed} small color regions were removed.')
    return {'width':width,'height':height,'threads':threads,'paths':paths,'stitchCount':sum(p[2]=='stitch' for p in paths),'warnings':warnings}


def pes_bytes(result):
    pattern = EmbPattern()
    for color in result['threads']:
        thread = EmbThread()
        thread.set_color(int(color[1:3],16), int(color[3:5],16), int(color[5:7],16))
        pattern.add_thread(thread)
    current = 0
    last_x, last_y = 0, 0
    for x,y,command,color in result['paths']:
        while current < color:
            pattern.add_stitch_absolute(COLOR_CHANGE, last_x*10, last_y*10)
            current += 1
        pattern.add_stitch_absolute(STITCH if command == 'stitch' else JUMP, x*10, y*10)
        last_x, last_y = x, y
    pattern.add_stitch_absolute(END, last_x*10, last_y*10)
    out = io.BytesIO()
    write_pes(pattern, out, {'version': 6})
    return out.getvalue()
