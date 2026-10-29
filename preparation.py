"""Artwork preparation only: physical scale, palette, exterior mask, vector paths."""
import base64
import io
import math
import re
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from scipy import ndimage
from shapely import Polygon, make_valid
import vtracer

SVG = 'http://www.w3.org/2000/svg'
INK = 'http://inkstitch.org/namespace'
ET.register_namespace('', SVG)
ET.register_namespace('inkstitch', INK)
Image.MAX_IMAGE_PIXELS = 20_000_000
NAVY_WHITE = ['#ffffff', '#002e5d']


def clean_paths(root, palette, sentinel, expansion=0):
    """Repair traced polygons and remove sub-thread-width edge noise (0.075 mm)."""
    nodes = []
    candidates = [*palette,sentinel]
    colors = np.array([[int(c[j:j+2],16) for j in (1,3,5)] for c in candidates])
    for node in root:
        fill = node.get('fill','')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',fill): continue
        rgb = np.array([int(fill[j:j+2],16) for j in (1,3,5)])
        distances = ((colors-rgb)**2).sum(axis=1)
        index = int(distances.argmin())
        # Large VTracer clusters can round #FFFFFF to #FEFEFE. Match the known
        # palette including the outside sentinel, rather than dropping real white.
        if index == len(palette): continue
        if distances[index]>12: raise ValueError('Tracing changed an artwork color unexpectedly. Try fewer colors.')
        rings = []
        for part in node.get('d','').split('Z'):
            values = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?',part)]
            if len(values)>=6: rings.append(list(zip(values[::2],values[1::2])))
        if not rings: continue
        shape = make_valid(Polygon(rings[0],rings[1:])).simplify(.6,preserve_topology=True)
        if expansion:
            # Apply edge overlap once at artwork resolution, then simplify again.
            # Native fill expansion can create very large routing boundaries.
            shape = shape.buffer(expansion,quad_segs=4).simplify(.6,preserve_topology=True)
        pending = [shape]
        while pending:
            polygon = pending.pop(0)
            if polygon.geom_type != 'Polygon':
                pending.extend(getattr(polygon,'geoms',[])); continue
            if polygon.is_empty: continue
            path = ET.Element(f'{{{SVG}}}path',{'fill':palette[index]})
            if node.get('transform'): path.set('transform',node.get('transform'))
            segments = []
            for ring in [polygon.exterior,*polygon.interiors]:
                points = list(ring.coords)[:-1]
                segments.append('M'+' L'.join(f'{x:.3f},{y:.3f}' for x,y in points)+'Z')
            path.set('d',' '.join(segments)); nodes.append(path)
    return nodes


def decode_image(data):
    try:
        if not isinstance(data, str) or len(data) > 17 * 1024 * 1024:
            raise ValueError('Image must be smaller than 12 MB.')
        raw = base64.b64decode(data.split(',', 1)[1], validate=True)
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError('Image must be smaller than 12 MB.')
        image = Image.open(io.BytesIO(raw))
        if image.width * image.height > 20_000_000:
            raise ValueError('Image exceeds 20 million pixels.')
        return ImageOps.exif_transpose(image).convert('RGBA')
    except (IndexError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Unable to read the image. Use PNG or JPEG, or import SVG through the browser.') from exc


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError('Invalid design settings.')
    try:
        width, height = float(settings['width']), float(settings['height'])
        colors = int(settings.get('colors', 2))
        spacing = float(settings.get('spacing', .45))
        compensation = float(settings.get('compensation', .15))
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise ValueError('Choose valid dimensions and stitch settings.') from exc
    if not all(math.isfinite(n) for n in (width, height, spacing, compensation)):
        raise ValueError('Settings must be finite numbers.')
    if min(width, height) < 5 or not ((width <= 127 and height <= 177.8) or (height <= 127 and width <= 177.8)):
        raise ValueError('The design must fit within the 5 × 7 inch hoop; each dimension must be at least 5 mm.')
    if not 2 <= colors <= 8 or not .35 <= spacing <= .8 or not 0 <= compensation <= .3:
        raise ValueError('Use 2–8 colors, row spacing 0.35–0.8 mm and compensation 0–0.3 mm.')
    mode = settings.get('paletteMode', 'navy-white')
    if mode not in ('navy-white', 'auto'):
        raise ValueError('Unknown palette mode.')
    overrides = settings.get('threadColors', [])
    if not isinstance(overrides, list) or len(overrides) > 8 or any(c is not None and (not isinstance(c,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',c)) for c in overrides):
        raise ValueError('Invalid thread colors.')
    return dict(width=width, height=height, colors=colors, spacing=spacing,
                compensation=compensation, paletteMode=mode,
                removeBackground=bool(settings.get('removeBackground',True)), threadColors=overrides)


def prepare(image_data, settings):
    cfg = validate_settings(settings)
    image = decode_image(image_data)
    w, h = max(40, round(cfg['width']*8)), max(40, round(cfg['height']*8))
    image = image.resize((w,h), Image.Resampling.LANCZOS)
    rgba = np.array(image)
    opaque = rgba[:,:,3] >= 128
    # Tiny median filter removes JPEG speckle without a stitch-row-sized blur.
    rgb_image = image.convert('RGB').filter(ImageFilter.MedianFilter(3))
    rgb = np.array(rgb_image)
    if cfg['paletteMode'] == 'navy-white':
        luminance = rgb @ np.array([.2126,.7152,.0722])
        # The logo preset is an explicit two-tone interpretation, not photo inference.
        labels = (luminance < 150).astype(np.int16)
        palette = NAVY_WHITE.copy()
        background_label = 0
    else:
        if not opaque.any(): raise ValueError('No visible artwork remains.')
        strip = Image.fromarray(rgb[opaque].reshape(1,-1,3))
        quant = strip.quantize(colors=cfg['colors'],method=Image.Quantize.MEDIANCUT)
        labels = np.full((h,w),-1,dtype=np.int16)
        labels[opaque] = np.array(quant).reshape(-1)
        values = quant.getpalette()
        palette = ['#%02x%02x%02x' % tuple(values[i:i+3]) for i in range(0,cfg['colors']*3,3)]
        border = np.concatenate([labels[0],labels[-1],labels[:,0],labels[:,-1]])
        border = border[border >= 0]
        background_label = int(np.bincount(border).argmax()) if len(border) else -2
    if cfg['removeBackground']:
        candidate = (labels == background_label) & opaque
        seed = candidate.copy(); seed[1:-1,1:-1] = False
        exterior = ndimage.binary_propagation(seed,mask=candidate)
        opaque &= ~exterior
    labels[~opaque] = -1
    # Only remove sub-pixel-scale noise; report every deletion. Never use a 2 mm² cutoff.
    removed = 0
    for color in range(len(palette)):
        regions, count = ndimage.label(labels == color)
        sizes = np.bincount(regions.ravel())
        tiny = np.flatnonzero((sizes < 3) & (np.arange(len(sizes)) > 0))
        removed += len(tiny)
        labels[np.isin(regions,tiny)] = -1
    if not (labels >= 0).any():
        raise ValueError('No visible artwork remains. Try keeping the background.')
    for i, color in enumerate(cfg['threadColors']):
        if i < len(palette) and color: palette[i] = color.lower()
    cleaned = np.zeros((h,w,4),dtype=np.uint8)
    for i,color in enumerate(palette):
        cleaned[labels == i] = [int(color[j:j+2],16) for j in (1,3,5)] + [255]
    png = io.BytesIO(); Image.fromarray(cleaned).save(png,'PNG')
    # Trace opaque RGB with a unique sentinel. VTracer's transparent-pixel key can
    # collide with white and remap a real white region to #FEFEFE.
    sentinel = next(c for c in ('#ff00ff','#00ff00','#ff8000','#00ffff','#ffff00','#ff0000','#8000ff','#808000','#123456') if c not in palette)
    tracing = cleaned[:,:,:3].copy()
    tracing[cleaned[:,:,3]==0] = [int(sentinel[j:j+2],16) for j in (1,3,5)]
    trace_png = io.BytesIO(); Image.fromarray(tracing).save(trace_png,'PNG')
    traced = vtracer.convert_raw_image_to_svg(trace_png.getvalue(),img_format='png',
        hierarchical='cutout',mode='polygon',filter_speckle=0,color_precision=8,
        layer_difference=0,corner_threshold=90,length_threshold=5,
        splice_threshold=45,path_precision=3)
    root = ET.fromstring(traced)
    root.set('width',f"{cfg['width']}mm"); root.set('height',f"{cfg['height']}mm")
    root.set('viewBox',f'0 0 {w} {h}')
    nodes = clean_paths(root,palette,sentinel,cfg['compensation']*8)
    # White regions sew first, then navy; preserve tracer order within each color.
    order = {c.lower():i for i,c in enumerate(palette)}
    nodes.sort(key=lambda p:order.get(p.get('fill','').lower(),99))
    for node in list(root): root.remove(node)
    metadata = ET.SubElement(root,f'{{{SVG}}}metadata')
    ET.SubElement(metadata,f'{{{INK}}}inkstitch_svg_version').text = '4'
    for i,node in enumerate(nodes):
        node.set('id',f'region-{i+1}')
        node.set('fill-rule','evenodd')
        attrs = {'fill_method':'tatami_fill', 'angle':'30' if node.get('fill','').lower() == palette[0] else '-30',
                 'row_spacing_mm':str(cfg['spacing']), 'max_stitch_length_mm':'3', 'staggers':'4',
                 'fill_underlay':'true', 'fill_underlay_angle':'90',
                 'fill_underlay_row_spacing_mm':'2', 'fill_underlay_inset_mm':'.4',
                 'fill_underlay_max_stitch_length_mm':'3', 'underpath':'false',
                 'underlay_underpath':'false', 'pull_compensation_mm':'0',
                 'expand_mm':'0',
                 'trim_after':'true', 'force_lock_stitches':'true', 'random_seed':'0'}
        for key,value in attrs.items(): node.set(f'{{{INK}}}{key}',value)
        root.append(node)
    if len(nodes)>500:
        raise ValueError('Artwork has more than 500 regions. Reduce colors or simplify the image.')
    warnings = ['Prototype for stabilized woven cotton. Density and compensation still need a physical stitch-out.',
                'This stage uses routed tatami fills with underlay. Automatic satin classification and fine-line recovery are not implemented.',
                'Inspect thin whiskers, small lettering and the trademark in the prepared artwork before generating.']
    if cfg['compensation']: warnings.append(f"Fill edges expand {cfg['compensation']:g} mm in every direction; inspect small openings and color overlap.")
    if cfg['removeBackground']: warnings.append('Only edge-connected background is removed. Check the silhouette for openings or clipped edges.')
    if removed: warnings.append(f'{removed} tiny noise regions (under 3 processing pixels) were removed.')
    return {'settings':cfg,'width':cfg['width'],'height':cfg['height'],'palette':palette,
            'svg':ET.tostring(root,encoding='unicode'),
            'image':'data:image/png;base64,'+base64.b64encode(png.getvalue()).decode(),
            'regionCount':len(nodes),'removedRegions':removed,'warnings':warnings}
