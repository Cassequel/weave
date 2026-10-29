"""Run an independently installed Ink/Stitch executable and inspect its exact PES."""
import io
import hashlib
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile
from uuid import uuid4

from pyembroidery import read_pes, write_pes, EmbPattern, EdrReader, COMMAND_MASK, STITCH, JUMP, TRIM, COLOR_CHANGE, END, STOP

ROOT = Path(__file__).resolve().parent


class DigitizingError(RuntimeError):
    pass


def executable():
    configured = os.environ.get('WEAVE_INKSTITCH')
    path = Path(configured) if configured else ROOT / '.tools/inkstitch-3.3.0/inkstitch/bin/inkstitch.exe'
    if not path.is_file():
        raise DigitizingError('Ink/Stitch is not installed. Run setup.ps1 or set WEAVE_INKSTITCH to its executable.')
    return path.resolve()


def export_pes(svg, cancel=None, timeout=600):
    program = executable()
    scratch = ROOT / '.local' / 'tmp'
    scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='weave-',dir=scratch) as directory:
        source = Path(directory)/'artwork.svg'
        source.write_text(svg,encoding='utf-8')
        command = [str(program),'--extension=zip','--format-pes=True','--format-edr=True',str(source)]
        process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        started = time.monotonic()
        try:
            while True:
                if cancel and cancel.is_set(): raise DigitizingError('Conversion cancelled.')
                if time.monotonic()-started > timeout: raise DigitizingError('Ink/Stitch timed out. Try simpler artwork or fewer regions.')
                try:
                    output, errors = process.communicate(timeout=.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        if process.returncode or not output.startswith(b'PK'):
            details = errors.decode('utf-8',errors='replace').strip()[-1500:]
            raise DigitizingError('Ink/Stitch could not generate this design. ' + details)
        # No ZIP extraction: read just the machine file, never paths from an archive.
        with zipfile.ZipFile(io.BytesIO(output)) as archive:
            entries = [i for i in archive.infolist() if i.filename.lower().endswith('.pes')]
            if len(entries)!=1 or entries[0].file_size>20*1024*1024:
                raise DigitizingError('Ink/Stitch returned an unexpected export.')
            pes = archive.read(entries[0])
            color_entries = [i for i in archive.infolist() if i.filename.lower().endswith('.edr')]
            if len(color_entries)!=1 or color_entries[0].file_size>100000:
                raise DigitizingError('Ink/Stitch did not include the original thread colors.')
            colors = archive.read(color_entries[0])
        if not pes.startswith(b'#PES'): raise DigitizingError('Ink/Stitch returned an invalid PES header.')
        # Ink/Stitch's default PES version maps RGB to the small PEC palette.
        # Restore its actual color-block list from its companion EDR, then write PES 6.
        pattern = read_pes(io.BytesIO(pes))
        original = EmbPattern()
        EdrReader.read(io.BytesIO(colors),original)
        if len(original.threadlist)!=len(pattern.threadlist):
            raise DigitizingError('Ink/Stitch thread sequences do not agree across export formats.')
        pattern.threadlist = original.threadlist
        out = io.BytesIO()
        write_pes(pattern,out,{'version':6,'trims':True,'full_jump':True})
        return out.getvalue()


def inspect_pes(pes, prepared):
    pattern = read_pes(io.BytesIO(pes))
    if not pattern or not pattern.stitches: raise DigitizingError('The PES contains no stitches.')
    if len(pattern.stitches)>250000: raise DigitizingError('The exported design exceeds 250,000 commands.')
    sewn = [(x/10,y/10) for x,y,c in pattern.stitches if c & COMMAND_MASK == STITCH]
    if not sewn or not all(math.isfinite(v) for p in sewn for v in p):
        raise DigitizingError('The exported PES has invalid stitch coordinates.')
    min_x,min_y = map(min,zip(*sewn)); max_x,max_y = map(max,zip(*sewn))
    width,height=max_x-min_x,max_y-min_y
    movement = [(x/10,y/10) for x,y,c in pattern.stitches if c & COMMAND_MASK in (STITCH,JUMP)]
    move_width = max(x for x,y in movement)-min(x for x,y in movement)
    move_height = max(y for x,y in movement)-min(y for x,y in movement)
    if not ((move_width<=127 and move_height<=177.8) or (move_height<=127 and move_width<=177.8)):
        raise DigitizingError('The actual stitches exceed the hoop after compensation. Reduce the artwork size.')
    threads=[]
    paths=[]; color=0; jumps=0; trims=0; distance=0.; long_jumps=0; max_length=0.; last=None
    for x,y,raw in pattern.stitches:
        cmd=raw & COMMAND_MASK
        if cmd==COLOR_CHANGE:
            color+=1
            continue
        if cmd==END: break
        if cmd not in (STITCH,JUMP,TRIM,STOP): continue
        while len(threads)<=color:
            t=pattern.threadlist[len(threads)] if len(threads)<len(pattern.threadlist) else None
            if t is None: raise DigitizingError('The PES thread sequence is incomplete.')
            threads.append('#%06x' % (t.color & 0xffffff))
        point=(x/10,y/10)
        length=math.dist(last,point) if last else 0
        if cmd==JUMP:
            jumps+=1; distance+=length; long_jumps+=int(length>5)
        if cmd==TRIM: trims+=1
        if cmd==STITCH: max_length=max(max_length,length)
        name={STITCH:'stitch',JUMP:'jump',TRIM:'trim',STOP:'stop'}[cmd]
        paths.append([round(point[0]-min_x,2),round(point[1]-min_y,2),name,color])
        last=point
    warnings=prepared['warnings'].copy()
    warnings.append('Trim commands are included; whether the machine trims each one must be checked on the NS2750D.')
    if max_length>8: warnings.append(f'The file contains a {max_length:.1f} mm stitch. Inspect it before sewing.')
    return {'width':round(width,2),'height':round(height,2),'artworkWidth':prepared['width'],
            'artworkHeight':prepared['height'],'threads':threads,'paths':paths,'stitchCount':len(sewn),
            'jumpCount':jumps,'trimCount':trims,'longJumpCount':long_jumps,
            'jumpDistanceMm':round(distance,1),'maxStitchMm':round(max_length,2),
            'engine':'Ink/Stitch 3.3.0','warnings':warnings}


def cache_path(prepared):
    key = hashlib.sha256(('inkstitch-3.3.0-pes6-v1\n'+prepared['svg']).encode()).hexdigest()
    return ROOT / '.local' / 'pes-cache' / (key+'.pes')


def cache_result(prepared,pes):
    result = inspect_pes(pes,prepared)
    path = cache_path(prepared)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix('.'+uuid4().hex+'.tmp')
    temporary.write_bytes(pes)
    temporary.replace(path)
    return result


def digitize(prepared,cancel=None):
    if cancel and cancel.is_set(): raise DigitizingError('Conversion cancelled.')
    path = cache_path(prepared)
    if path.is_file():
        pes = path.read_bytes()
        return inspect_pes(pes,prepared),pes
    pes = export_pes(prepared['svg'],cancel)
    return cache_result(prepared,pes),pes
