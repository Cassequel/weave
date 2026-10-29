const $ = id => document.getElementById(id);
let source = null, raster = null, ratio = 1, result = null, sequence = 0, timer = null, threadColors = [];
const controls = ['width','height','colors','background'];
const settings = () => ({width:Number($('width').value), height:Number($('height').value), colors:Number($('colors').value), removeBackground:$('background').value === 'remove', threadColors});
const status = message => $('status').textContent = message;
function invalidate() { result = null; $('export').disabled = true; sequence++; }
function download(blob, name) { const a = document.createElement('a'); const url = URL.createObjectURL(blob); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function readFile(file) { return new Promise((resolve,reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = () => reject(new Error('Could not read this file.')); r.readAsDataURL(file); }); }
function imageFrom(url) { return new Promise((resolve,reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('Unable to open the image.')); image.src = url; }); }
async function prepare(data, name, resetSize = true) {
  if (data.length > 17 * 1024 * 1024) throw new Error('Image is too large (maximum 12 MB).');
  let input = data;
  if (/^data:image\/svg\+xml/i.test(data) || /\.svg$/i.test(name)) {
    const encoded = data.split(',')[1];
    const text = data.includes(';base64,') ? new TextDecoder().decode(Uint8Array.from(atob(encoded), c => c.charCodeAt(0))) : decodeURIComponent(encoded);
    const doc = new DOMParser().parseFromString(text,'image/svg+xml');
    if (doc.querySelector('parsererror, script, foreignObject, image, use, style') || /<!DOCTYPE|<!ENTITY|\b(?:href|src)\s*=|url\s*\(/i.test(text)) throw new Error('SVG must not contain scripts, external resources, or linked elements.');
    input = URL.createObjectURL(new Blob([text],{type:'image/svg+xml'}));
  }
  let img;
  try { img = await imageFrom(input); } finally { if (input.startsWith('blob:')) URL.revokeObjectURL(input); }
  if (!img.naturalWidth || !img.naturalHeight || img.naturalWidth * img.naturalHeight > 20000000) throw new Error('Image must have dimensions under 20 million pixels.');
  ratio = img.naturalWidth / img.naturalHeight;
  const scale = Math.min(1, 1600 / Math.max(img.naturalWidth,img.naturalHeight));
  const canvas = document.createElement('canvas'); canvas.width = Math.max(1,Math.round(img.naturalWidth*scale)); canvas.height = Math.max(1,Math.round(img.naturalHeight*scale));
  canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);
  raster = canvas.toDataURL('image/png'); source = {data,name};
  if (resetSize) { $('width').value = Math.round(Math.min(100, 100*ratio)); $('height').value = Math.round(Number($('width').value)/ratio); }
  $('filename').textContent = name; $('generate').disabled = false; $('save').disabled = false;
}
async function generate() {
  if (!raster) return;
  clearTimeout(timer); const current = ++sequence; result = null; $('export').disabled = true; status('Generating stitches…');
  try {
    const response = await fetch('/api/convert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:raster,settings:settings()})});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    if (current !== sequence) return;
    result = data; draw(); $('export').disabled = false; status('Preview ready. Review the notes before sewing.');
  } catch (error) { if (current === sequence) status(error.message || 'Conversion failed.'); }
}
function draw() {
  const canvas = $('preview'), ctx = canvas.getContext('2d'), w=canvas.width, h=canvas.height;
  ctx.clearRect(0,0,w,h);
  if (!result) return;
  $('empty').hidden = true;
  const landscape = result.width > 127;
  const hoopW = landscape ? 177.8 : 127, hoopH = landscape ? 127 : 177.8;
  const scale = Math.min((w-110)/hoopW,(h-100)/hoopH);
  const left=(w-hoopW*scale)/2, top=(h-hoopH*scale)/2;
  ctx.strokeStyle='#c9bfb0'; ctx.setLineDash([7,7]); ctx.lineWidth=1.5; ctx.strokeRect(left,top,hoopW*scale,hoopH*scale); ctx.setLineDash([]);
  const ox=left+(hoopW-result.width)*scale/2, oy=top+(hoopH-result.height)*scale/2;
  let previous=null;
  for (const [x,y,cmd,color] of result.paths) {
    const point=[ox+x*scale,oy+y*scale];
    if (previous && cmd==='stitch') { ctx.strokeStyle=result.threads[color]; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(...previous); ctx.lineTo(...point); ctx.stroke(); }
    else if (previous && cmd==='jump') { ctx.strokeStyle='#bcb5aa'; ctx.lineWidth=0.65; ctx.setLineDash([2,4]); ctx.beginPath(); ctx.moveTo(...previous); ctx.lineTo(...point); ctx.stroke(); ctx.setLineDash([]); }
    previous=point;
  }
  $('size-stat').textContent=`${result.width} × ${result.height} mm`; $('stitch-stat').textContent=result.stitchCount.toLocaleString(); $('thread-stat').textContent=result.threads.length;
  $('threads').replaceChildren(...result.threads.map((color,i) => { const el=document.createElement('label'); el.className='thread'; const swatch=document.createElement('input'); swatch.type='color'; swatch.value=color; swatch.setAttribute('aria-label',`Thread ${i+1} color`); swatch.addEventListener('change', () => { threadColors[i]=swatch.value; result.threads[i]=swatch.value; draw(); }); el.append(swatch, document.createTextNode(`${i+1} · ${color.toUpperCase()}`)); return el; }));
  $('warnings').replaceChildren(...result.warnings.map(text => {const p=document.createElement('p'); p.textContent='✳  '+text; return p;}));
}
$('file').addEventListener('change',async event => { const file=event.target.files[0]; if (!file) return; invalidate(); threadColors=[]; try { if (file.size > 12*1024*1024) throw new Error('Image is too large (maximum 12 MB).'); if (!['image/png','image/jpeg','image/svg+xml'].includes(file.type) && !/\.(png|jpe?g|svg)$/i.test(file.name)) throw new Error('Choose a PNG, JPEG or SVG image.'); await prepare(await readFile(file),file.name); generate(); } catch(e) { source=null; raster=null; $('generate').disabled=true; $('save').disabled=true; status(e.message); } event.target.value=''; });
$('lock').onclick=() => { const locked=$('lock').getAttribute('aria-pressed')!=='true'; $('lock').setAttribute('aria-pressed',String(locked)); $('lock').textContent=locked?'🔒':'🔓'; };
for (const id of controls) $(id).addEventListener('input', () => { if (id==='width' && $('lock').getAttribute('aria-pressed')==='true') $('height').value=Math.max(1,Math.round(Number($('width').value)/ratio)); if (id==='height' && $('lock').getAttribute('aria-pressed')==='true') $('width').value=Math.max(1,Math.round(Number($('height').value)*ratio)); if(id==='colors' || id==='background') threadColors=[]; $('color-value').textContent=`${$('colors').value} COLORS`; invalidate(); clearTimeout(timer); if (raster) { status('Settings changed. Updating preview…'); timer=setTimeout(generate,400); } });
$('generate').onclick=generate;
$('save').onclick=() => { if (source) download(new Blob([JSON.stringify({version:1,source,settings:settings(),locked:$('lock').getAttribute('aria-pressed')==='true'})],{type:'application/json'}),'weave-project.weave.json'); };
$('open-project').onchange=async event => { const file=event.target.files[0]; if (!file) return; invalidate(); try { if(file.size>18*1024*1024) throw new Error('Project is too large.'); const p=JSON.parse(await file.text()); if(p.version!==1 || !p.source || typeof p.source.data!=='string' || typeof p.source.name!=='string' || !p.settings) throw new Error('This is not a supported Weave project.'); await prepare(p.source.data,p.source.name,false); threadColors=Array.isArray(p.settings.threadColors)?p.settings.threadColors:[]; $('width').value=p.settings.width; $('height').value=p.settings.height; $('colors').value=p.settings.colors; $('background').value=p.settings.removeBackground?'remove':'keep'; $('color-value').textContent=`${$('colors').value} COLORS`; $('lock').setAttribute('aria-pressed',String(p.locked!==false)); $('lock').textContent=p.locked===false?'🔓':'🔒'; generate(); } catch(e) { source=null; raster=null; $('generate').disabled=true; $('save').disabled=true; status(e.message || 'Could not open project.'); } event.target.value=''; };
$('export').onclick=async () => { if (!result) return; $('export').disabled=true; try { const response=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:raster,settings:settings()})}); if (!response.ok) {const e=await response.json(); throw new Error(e.error);} download(await response.blob(),'weave-design.pes'); status('PES downloaded. Test on scrap fabric before using your final item.'); } catch(e) {status(e.message);} finally { $('export').disabled=!result; } };
