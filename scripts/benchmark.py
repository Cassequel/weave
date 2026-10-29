"""Run a private image through the real engine and save local review artifacts."""
import argparse
import base64
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps')]
from PIL import Image,ImageDraw
from preparation import prepare
from inkstitch_backend import digitize


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--size',type=float,default=120)
    parser.add_argument('--output',type=Path,default=ROOT/'.local/cougar')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    image=Image.open(args.image);width=args.size;height=width*image.height/image.width
    data='data:image/png;base64,'+base64.b64encode(args.image.read_bytes()).decode()
    cfg=dict(width=width,height=height,colors=2,paletteMode='navy-white',removeBackground=True)
    p=prepare(data,cfg)
    (args.output/'artwork.svg').write_text(p['svg'],encoding='utf-8')
    (args.output/'project.weave.json').write_text(json.dumps(dict(version=2,source=dict(data=data,name=args.image.name),settings=p['settings'],locked=True)),encoding='utf-8')
    print(f"Prepared {p['regionCount']} regions; starting Ink/Stitch.",flush=True)
    started=time.monotonic();r,pes=digitize(p)
    (args.output/'design.pes').write_bytes(pes)
    (args.output/'result.json').write_text(json.dumps(r),encoding='utf-8')
    metrics={k:v for k,v in r.items() if k!='paths'}
    metrics.update(regionCount=p['regionCount'],removedRegions=p['removedRegions'],seconds=round(time.monotonic()-started,2))
    (args.output/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    canvas=Image.new('RGB',(1200,1200),'#b8c4be');draw=ImageDraw.Draw(canvas)
    scale=min(1100/r['width'],1100/r['height']);last=None;last_color=None
    for x,y,cmd,color in r['paths']:
        point=(50+x*scale,50+y*scale)
        if last and cmd=='stitch' and last_color==color:draw.line([last,point],fill=r['threads'][color],width=2)
        last=point;last_color=color
    canvas.save(args.output/'stitches.png')
    print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__':main()
