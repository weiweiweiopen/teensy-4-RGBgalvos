"""Generate native KiCad hierarchical schematics with explicit pin labels.

Custom symbols are self-contained. Op-amp pin geometry is conventional;
connector/package drawings expose every physical pad, including unused pins.
"""
import json, math, re
from pathlib import Path
from design import ROOT, parts, uid, validate

def q(s): return json.dumps(str(s),ensure_ascii=False)
def prop(k,v,x=0,y=0,hidden=False):
 return f'(property {q(k)} {q(v)} (at {x} {y} 0) (effects (font (size 1.0 1.0))'+(' (hide yes)' if hidden else '')+'))'
def pin(num,name,x,y,angle=0,typ='passive',length=2.54):
 return f'(pin {typ} line (at {x} {y} {angle}) (length {length}) (name {q(name)} (effects (font (size 0.9 0.9)))) (number {q(num)} (effects (font (size 0.9 0.9)))))'
def symbol(p):
 name=p['ref']; kind=p['kind']; coords={}; units=[]
 if kind=='opquad':
  for u,nums in enumerate([(3,2,1),(5,6,7),(10,9,8),(12,13,14)],1):
   plus,minus,out=map(str,nums)
   shape='(polyline (pts (xy -5.08 5.08) (xy 5.08 0) (xy -5.08 -5.08) (xy -5.08 5.08)) (stroke (width 0.254) (type default)) (fill (type background)))'
   units.append(f'(symbol "{name}_{u}_1" {shape} '+pin(plus,'+',-7.62,2.54,0,'input')+pin(minus,'-',-7.62,-2.54,0,'input')+pin(out,'OUT',7.62,0,180,'output')+')')
   coords[u]={plus:(-7.62,2.54),minus:(-7.62,-2.54),out:(7.62,0)}
  units.append(f'(symbol "{name}_5_1" '+pin('4','V+',0,5.08,270,'power_in')+pin('11','V-',0,-5.08,90,'power_in')+')')
  coords[5]={'4':(0,5.08),'11':(0,-5.08)}
 elif kind in ['R','C','D']:
  if kind=='R': shape='(rectangle (start -2.54 1.016) (end 2.54 -1.016) (stroke (width 0.254) (type default)) (fill (type none)))'
  elif kind=='C':shape=''.join(f'(polyline (pts (xy {x} -2.0) (xy {x} 2.0)) (stroke (width 0.254) (type default)) (fill (type none)))' for x in [-0.508,0.508])
  else:shape='(polyline (pts (xy 2 -2) (xy -2 0) (xy 2 2) (xy 2 -2)) (stroke (width 0.254) (type default)) (fill (type none))) (polyline (pts (xy -2 -2) (xy -2 2)) (stroke (width 0.254) (type default)) (fill (type none)))'
  length=2.54 if kind=='R' else 4.572 if kind=='C' else 3.08
  units=[f'(symbol "{name}_1_1" {shape} '+pin('1','K' if kind=='D' else '~',-5.08,0,0,length=length)+pin('2','A' if kind=='D' else '~',5.08,0,180,length=length)+')']
  coords[1]={'1':(-5.08,0),'2':(5.08,0)}
 else:
  numbers=list(p['pins']); count=len(numbers); half=math.ceil(count/2); h=max(5.08,(half+1)*2.54/2)
  shape=f'(rectangle (start -12.7 {h}) (end 12.7 {-h}) (stroke (width 0.254) (type default)) (fill (type background)))'
  ps=[];coords[1]={}
  for i,num in enumerate(numbers):
   left=i<half; j=i if left else i-half; xx=-15.24 if left else 15.24; yy=h-2.54*(j+1)
   net=p['pins'][num]; label=pin_name(p,num)
   typ='passive'
   if p['ref'].startswith('U'):
    if label in ['V+','V-','VDD','VSS','VCC','GND','VA','VD','VLC','VLS','IN','OUT'] and (num in supply_pins(p)):typ='power_in'
    elif p['ref']=='U1':typ='passive' # duplex clocks, analogue bias pins: retain package-neutral model
   typ=p.get('pin_types',{}).get(num,typ)
   ps.append(pin(num,label,xx,yy,0 if left else 180,typ));coords[1][num]=(xx,yy)
  units=[f'(symbol "{name}_1_1" {shape} '+''.join(ps)+')']
 return f'(symbol {q(name)} (pin_names (offset 0.5)) (in_bom yes) (on_board yes) '+prop('Reference',re.sub(r'\d+$','',name),0,5)+prop('Value',p['value'],0,-5)+prop('Footprint',p['fp'],hidden=True)+''.join(units)+')',coords

def supply_pins(p):
 return {'U2':['1','2','5'],'U3':['3','5'],'U4':['8','16'],'U5':['3','5']}.get(p['ref'],[])
def pin_name(p,n):
 if p.get('pin_names'):return p['pin_names'][n]
 if p['ref']=='U1':
  a={1:'AD0',2:'AD1',3:'~{RST}',4:'VLC',5:'ADC_LRCK',6:'VD',7:'DGND',8:'VLS',9:'ADC_SCLK',10:'MCLK',11:'ADC_SDOUT3',12:'ADC_SDOUT2',13:'ADC_SDOUT1',14:'DAC_SDIN4',15:'DAC_SDIN3',16:'DAC_SDIN2',17:'DAC_SDIN1',18:'DAC_SCLK',19:'DAC_LRCK',20:'AUX_LRCK',21:'AUX_SCLK',22:'AUX_SDIN',23:'DGND',24:'VD',35:'MUTEC',42:'AGND',43:'VQ',44:'VA',53:'VA',54:'FILT_DAC',55:'FILT_ADC',56:'AGND',61:'INT',62:'DGND',63:'SCL',64:'SDA'}
  return a.get(int(n),p['pins'][n] or 'NC')
 if p['ref']=='U4':return {1:'1A',2:'1B',3:'~{1RD}',4:'~{1Q}',5:'2Q',6:'2CEXT',7:'2REXT',8:'GND',9:'2A',10:'2B',11:'~{2RD}',12:'~{2Q}',13:'1Q',14:'1CEXT',15:'1REXT',16:'VCC'}[int(n)]
 return p['pins'][n] or 'NC'

def text(t,x,y,size=1.3):
 return f'(text {q(t)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid {q(uid(t+str((x,y))))}))'

def header(page,rootid,lib,paper='A2'):
  return f'(kicad_sch (version 20250114) (generator "eeschema") (uuid {q(rootid)}) (paper {q(paper)}) (title_block (title {q("ILDA8CH RevB-P4 / "+page)}) (date "2026-10-25") (rev "B-P4")) (lib_symbols {lib})'

def make_page(page,pp,path,rootid,parentid=None,sheetid=None):
 defs=[];geo={}
 for p in pp:
  s,co=symbol(p);s=s.replace(f'(symbol {q(p["ref"])}',f'(symbol {q("ILDA8CH:"+p["ref"])}',1);defs.append(s);geo[p['ref']]=co
 out=[header(page,rootid,' '.join(defs))]
 if page=='Power':
  # Flags explicitly document the externally supplied / rectified power paths.
  flag='(symbol "ILDA8CH:PowerFlag" (power) (in_bom no) (on_board no) '+prop('Reference','#FLG',hidden=True)+prop('Value','PWR_FLAG',hidden=True)+'(symbol "PowerFlag_1_1" '+pin('1','pwr',0,0,90,'power_out',0)+'))'
  out[0]=header(page,rootid,' '.join(defs)+flag)
  for i,net in enumerate(['GND','+3V3','+15A','-15A','USB_5V','+5VA']):
   x=round((40+i*25)/1.27)*1.27;y=370.84
   sid=uid('flag:'+net)
   out.append(f'(symbol (lib_id "ILDA8CH:PowerFlag") (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (uuid {q(sid)}) '+prop('Reference','#FLG'+str(i+1),x,y,True)+prop('Value','PWR_FLAG',x,y,True)+f'(instances (project "ILDA8CH" (path {q("/"+parentid+"/"+sheetid)} (reference "#FLG{i+1}") (unit 1)))))')
   out.append(f'(global_label {q(net)} (shape passive) (at {x} {y} 0) (effects (font (size 0.9 0.9))) (uuid {q(uid(sid+"label"))}))')
 out.append(text('DC coupled. Physical pin numbers; net names are global and channel-unique.',20,15))
 pathid='/'+rootid if not parentid else '/'+parentid+'/'+sheetid
 grid=0
 for p in pp:
  if p['kind']=='opquad': placements={1:(60,55),2:(60,100),3:(220,55),4:(220,100),5:(330,55)}
  else:
   # Tall codec and connectors get a dedicated column; other parts use sparse grid.
   if p['ref']=='U1':placements={1:(65,90)}
   elif len(p['pins'])>20:placements={1:(65,95)}
   else:
    cols=5 if page in ['Codec','Control','Outputs'] else 7
    offset=155 if page in ['Codec','Control','Outputs'] else 40
    sy=35 if page=='Codec' else 150 if page.startswith('CH') else 45
    placements={1:(offset+(grid%cols)*72,sy+(grid//cols)*43)};grid+=1
  for unit,(x,y) in placements.items():
   x=round(round(x/1.27)*1.27,4);y=round(round(y/1.27)*1.27,4)
   sid=uid(p['ref']+':unit'+str(unit));libid='ILDA8CH:'+p['ref'];suffix=chr(64+unit) if p['kind']=='opquad' and unit<=4 else ''
   fields=prop('Reference',p['ref'],x,y-9)+prop('Value',p['value'],x,y-6)+prop('Footprint',p['fp'],x,y,True)+prop('Datasheet',p['ds'],x,y,True)+prop('MPN',p['mpn'],x,y,True)+prop('LCSC',p['code'],x,y,True)+prop('Assembly','JLC SMT' if p['smt'] else 'POST',x,y,True)
   inbom='no' if p['ref'].startswith(('TP','H','FID')) else 'yes'
   out.append(f'(symbol (lib_id {q(libid)}) (at {x} {y} 0) (unit {unit}) (in_bom {inbom}) (on_board yes) (dnp no) (uuid {q(sid)}) {fields} (instances (project "ILDA8CH" (path {q(pathid)} (reference {q(p["ref"])}) (unit {unit})))))')
   for num,(dx,dy) in geo[p['ref']][unit].items():
    px=round(x+dx,4);py=round(y-dy,4);net=p['pins'][num]
    if net is None:
     out.append(f'(no_connect (at {px} {py}) (uuid {q(uid(sid+num+"NC"))}))');continue
    # Extend every pin to a labelled wire; labels never touch a different symbol.
    if dx==0:ex=px;ey=round(py+(-5.08 if dy>0 else 5.08),4)
    else:ex=round(px+(-5.08 if dx<0 else 5.08),4);ey=py
    out.append(f'(wire (pts (xy {px} {py}) (xy {ex} {ey})) (stroke (width 0) (type default)) (uuid {q(uid(sid+num+"wire"))}))')
    angle=0 if dx<=0 else 180
    out.append(f'(global_label {q(net)} (shape passive) (at {ex} {ey} {angle}) (effects (font (size 0.9 0.9))) (uuid {q(uid(sid+num+"label"))}))')
 if page.startswith('CH'):
  out.append(text('A/B: unity-gain input buffers. C: matched subtractor. D: complementary driver.',20,125))
  out.append(text('X/Y DC gain = 39k/(20k+1k); colour gain = 20k/(20k+1k). Calibrate in firmware.',20,132))
 out.append(')');path.write_text('\n'.join(out))

def main():
 validate();dest=ROOT/'KiCad';dest.mkdir(exist_ok=True)
 rootid=uid('schematic-root');pages=['Control','Power','Codec']+sorted({p['page'] for p in parts if p['page'].startswith('CH')})+['Outputs']
 # Root has hierarchy and no electrical symbols; child pages carry every component.
 root=[header('Index',rootid,'')]
 for i,page in enumerate(pages):
  sid=uid('sheet:'+page);child=uid('root:'+page);x=30+i%4*100;y=45+i//4*65
  root.append(f'(sheet (at {x} {y}) (size 80 40) (fields_autoplaced yes) (stroke (width 0) (type default)) (fill (color 0 0 0 0)) (uuid {q(sid)}) '+prop('Sheetname',page,x,y-2)+prop('Sheetfile',page+'.kicad_sch',x,y+42)+f'(instances (project "ILDA8CH" (path {q("/"+rootid)} (page {q(i+2)})))))')
  make_page(page,[p for p in parts if p['page']==page],dest/(page+'.kicad_sch'),child,rootid,sid)
 root.append(text('Teensy 4.0 / CS42448 / eight independent DC-coupled complementary outputs',30,20,1.7))
 root.append(text('Channels: X, Y, R, G, B, Intensity, AUX1, AUX2. USB PCM colours use 0..positive full scale.',30,27))
 root.append(text('Power: Teensy USB supplies codec 5V/3V3. J2 supplies external +/-15V only.',30,34))
 root.append(')');(dest/'ILDA8CH.kicad_sch').write_text('\n'.join(root))
 # A matching local library makes lib-symbol integrity checks meaningful.
 defs=[symbol(p)[0] for p in parts]
 defs.append('(symbol "PowerFlag" (power) (in_bom no) (on_board no) '+prop('Reference','#FLG',hidden=True)+prop('Value','PWR_FLAG',hidden=True)+'(symbol "PowerFlag_1_1" '+pin('1','pwr',0,0,90,'power_out',0)+'))')
 (dest/'ILDA8CH.kicad_sym').write_text('(kicad_symbol_lib (version 20250114) (generator "kicad_symbol_editor")\n'+'\n'.join(defs)+'\n)')
 (dest/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "ILDA8CH") (type "KiCad") (uri "${KIPRJMOD}/ILDA8CH.kicad_sym") (options "") (descr "RevB-P1 explicit package pin symbols")))')
 print('Generated',len(pages)+1,'native sheets')
if __name__=='__main__':main()
