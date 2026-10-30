"""Native pin/placement checks and coordinate-accurate SVG for the P1 hand-off."""
from pathlib import Path
import csv,hashlib,html,json,math,sys,xml.etree.ElementTree as E
import pcbnew as k
from design import ROOT,parts

def point(p):return (k.ToMM(p.x),k.ToMM(p.y))
def bbox(f):
    r=f.GetBoundingBox(False,False)
    return [k.ToMM(x) for x in (r.GetX(),r.GetY(),r.GetWidth(),r.GetHeight())]
def dist(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])
def mst(points):
    if len(points)<2:return 0.0
    used={0};best=[dist(points[0],p) for p in points];total=0
    while len(used)<len(points):
        i=min((i for i in range(len(points)) if i not in used),key=lambda i:best[i])
        total+=best[i];used.add(i)
        for j in range(len(points)):
            if j not in used:best[j]=min(best[j],dist(points[i],points[j]))
    return total
def wiring_bound(b):
    nets={}
    for f in b.GetFootprints():
        for p in f.Pads():
            name=p.GetNetname()
            if not name or name.startswith('unconnected-') or name in ['GND','+3V3','+5VA','USB_5V','+15A','-15A','P15_IN','N15_IN']:continue
            nets.setdefault(name,[]).append(point(p.GetPosition()))
    return sum(mst(ps) for ps in nets.values())

def region_density(fps):
    # Occupied courtyard/body bounding-box proxy on a 0.5mm raster. This is a
    # placement comparison, not copper coverage, DFM or an electrical rule.
    step=.5;width=220;height=200;mask=bytearray(width*height)
    for ref,f in fps.items():
        if ref.startswith(('A','J','H','TP','FID')):continue
        x,y,w,h=bbox(f)
        for iy in range(max(0,int(y/step)),min(height,math.ceil((y+h)/step))):
            for ix in range(max(0,int(x/step)),min(width,math.ceil((x+w)/step))):mask[iy*width+ix]=1
    regions={'analog':[2,29,46,67],'codec_control':[44,2,40,40],
             'central_switch_band':[47,42,15,53],'output_resistors':[67,40,25,55]}
    result={}
    for name,(x,y,w,h) in regions.items():
        cells=[mask[iy*width+ix] for iy in range(int(y/step),int((y+h)/step)) for ix in range(int(x/step),int((x+w)/step))]
        result[name]=round(sum(cells)/len(cells)*100,2)
    return result

def main():
    path=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'KiCad/ILDA8CH.kicad_pcb'
    b=k.LoadBoard(str(path));fs={f.GetReference():f for f in b.GetFootprints()}
    xml=E.parse(ROOT/'QA/native.net.xml').getroot()
    native={(n.get('ref'),n.get('pin')):net.get('name') for net in xml.findall('nets/net') for n in net.findall('node')}
    mismatches=[];count=0;padmap={}
    for f in fs.values():
        for p in f.Pads():
            if not p.GetNumber():continue
            key=(f.GetReference(),p.GetNumber());padmap[key]=p;count+=1
            if p.GetNetname()!=native.get(key,''):mismatches.append(dict(ref=key[0],pad=key[1],pcb=p.GetNetname(),schematic=native.get(key)))
    assert not mismatches,mismatches
    assert len(fs)==273 and not list(b.GetTracks()) and not list(b.Zones())
    close=[]
    for ch in range(1,9):
        bas=100+ch*20;u='U'+str(10+ch)
        for label,a,c in [
            ('positive feedback OUT',('R'+str(bas+6),'1'),(u,'8')),
            ('positive feedback IN-',('R'+str(bas+6),'2'),(u,'9')),
            ('inverter feedback OUT',('R'+str(bas+8),'1'),(u,'14')),
            ('inverter feedback IN-',('R'+str(bas+8),'2'),(u,'13')),
            ('V+ bypass',('C'+str(bas+3),'1'),(u,'4')),
            ('V- bypass',('C'+str(bas+4),'2'),(u,'11'))]:
            d=dist(point(padmap[a].GetPosition()),point(padmap[c].GetPosition()))
            close.append(dict(channel=ch,check=label,pads=[a,c],distance_mm=round(d,4)))
            # Report geometry; a straight-line pad distance is not a routed-loop check.
            assert padmap[a].GetNetname()==padmap[c].GetNetname(),(label,a,c)
    old=k.LoadBoard(str(ROOT/'sources/revA-base.kicad_pcb'))
    before=wiring_bound(old);after=wiring_bound(b)
    pmap={p['ref']:p for p in parts};rows=[]
    for ref,f in sorted(fs.items()):
        x,y=point(f.GetPosition());rows.append(dict(Reference=ref,Value=f.GetValue(),X_mm=round(x,4),Y_mm=round(y,4),
            Rotation_deg=f.GetOrientationDegrees(),Group=pmap[ref]['page'],Locked=f.IsLocked()))
    with (ROOT/'preview/placement-coordinates.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    drc=json.loads((ROOT/'QA/placement-drc.json').read_text())
    assert not [v for v in drc['violations'] if v['severity']=='error']
    assert not drc['schematic_parity']
    # Native geometric bounding boxes include package courtyards, not full cable bodies.
    j=bbox(fs['J1']);a=bbox(fs['A1'])
    res_right=max(bbox(fs[p['ref']])[0]+bbox(fs[p['ref']])[2] for p in parts if p['page']=='Outputs' and p['ref'].startswith('R') and p['value']=='100')
    audit=dict(stage='PLACEMENT REVIEW / UNROUTED',board_mm=[110,100],area_reduction_pct=round((1-11000/26350)*100,2),
        components=273,pad_comparisons=count,pad_mismatches=mismatches,
        tracks=0,vias=0,unconnected_items=len(drc['unconnected_items']),schematic_parity=0,
        placement_errors=0,warnings=drc['violations'],groups=[g.GetName() for g in b.Groups()],
        connector_bbox_mm=j,teensy_bbox_mm=a,
        teensy_to_connector_projected_gap_mm=round(j[1]-a[1]-a[3],4),
        power_resistor_to_connector_projected_gap_mm=round(j[0]-res_right,4),
        signal_airwire_MST_mm=dict(revA=round(before,2),revB=round(after,2),reduction_pct=round((1-after/before)*100,2),
            meaning='Euclidean spanning-tree lower-bound; excludes power and NC; NOT routed length or SI verification'),
        local_pin_distances=close,pcb_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pcb_source=str(path.relative_to(ROOT)),
        connector_procurement='MPN pending; candidate footprint only',
        user_edit='All footprints unlocked. Native PCB_GROUPs support whole-channel move or entering a group for local edits.')
    (ROOT/'QA/placement-audit.json').write_text(json.dumps(audit,indent=2))
    history=ROOT/'history/placement-v9/KiCad/ILDA8CH.kicad_pcb'
    if history.exists():
        ob=k.LoadBoard(str(history));ofs={f.GetReference():f for f in ob.GetFootprints()}
        def adc_distances(fps):
            pins={p.GetNetname():point(p.GetPosition()) for p in fps['U1'].Pads()}
            return {ref:round(dist(point(p.GetPosition()),pins[p.GetNetname()]),3)
                    for ref in ['C'+str(i) for i in range(22,34)] for p in fps[ref].Pads() if p.GetNetname().startswith('AIN')}
        old_d=adc_distances(ofs);new_d=adc_distances(fs)
        spacing=dict(placement_version=10,comparison='P2 placement v9 to whole-board P3 v10',adc_caps_before_mm=old_d,adc_caps_after_mm=new_d,
            mean_pad_distance_before_mm=round(sum(old_d.values())/12,3),mean_pad_distance_after_mm=round(sum(new_d.values())/12,3),
            dac_escape_rectangle_mm=[48.5,33,11.5,4],
            codec_to_teensy_gap_before_mm=round(bbox(ofs['A1'])[0]-sum(bbox(ofs['U1'])[::2]),3),
            codec_to_teensy_gap_after_mm=round(bbox(fs['A1'])[0]-sum(bbox(fs['U1'])[::2]),3),
            opamp_center_x_before_mm=[point(ofs['U11'].GetPosition())[0],point(ofs['U12'].GetPosition())[0]],
            opamp_center_x_after_mm=[point(fs['U11'].GetPosition())[0],point(fs['U12'].GetPosition())[0]],
            switch_centers_before_mm=[point(ofs['U'+str(i)].GetPosition()) for i in range(21,25)],
            switch_centers_after_mm=[point(fs['U'+str(i)].GetPosition()) for i in range(21,25)],
            smd_region_density_proxy_before_pct=region_density(ofs),smd_region_density_proxy_after_pct=region_density(fs),
            density_basis='Union of SMD footprint body/courtyard bounding boxes, 0.5mm raster; excludes mechanical anchors; heuristic comparison only.',
            meaning='Pad-to-pad straight-line distances; not routed lengths. Green box is an unoccupied placement corridor, not a keepout.')
        for label,fps in [('before',ofs),('after',fs)]:
            occupied=[]
            for i in range(22,34):
                x,y,w,h=bbox(fps['C'+str(i)])
                if x<60 and x+w>48.5 and y<37 and y+h>33:occupied.append('C'+str(i))
            spacing['adc_caps_in_escape_'+label]=occupied
        assert not spacing['adc_caps_in_escape_after']
        (ROOT/'QA/codec-spacing.json').write_text(json.dumps(spacing,indent=2))
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-8 -11 141 124" width="1692" height="1488">',
        '<style>text{font-family:Arial,sans-serif}.p{stroke:#52616d;stroke-width:.08}.ic{fill:#253241}.ref{font-size:.62px;fill:#fff;text-anchor:middle;dominant-baseline:middle}.zone{fill:none;stroke:#7993aa;stroke-width:.15;stroke-dasharray:1 1}</style>',
        '<rect x="-8" y="-11" width="141" height="124" fill="#f3f5f7"/>',
        '<text x="0" y="-6.2" font-size="2.8" fill="#182f44">ILDA8CH RevB-P3 — balanced whole-board floorplan</text>',
        '<text x="0" y="-2.5" font-size="1.65" fill="#52616d">110 × 100 mm PCB · 4 layers · 273 parts · PRE-ROUTE SNAPSHOT v10</text>',
        '<rect x="0" y="0" width="110" height="100" fill="#e3ebe7" stroke="#213b31" stroke-width=".35"/>']
    zones=[('POWER / WD',.5,.5,43,27,'#e7dbca'),('CODEC / USB',44,.5,64,41.5,'#d7e5ed'),
           ('8 ANALOG CHANNELS',2,29,46,67,'#eee6c9'),('OUTPUT SWITCHES',47,42,15,53,'#d3e8f0'),
           ('100R 1W OUTPUTS',67,40,25,55,'#d9e1ed')]
    for name,x,y,w,h,col in zones:
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{col}" opacity=".5"/>')
    svg.append('<rect x="48.5" y="33" width="11.5" height="4" fill="#8bd6b2" fill-opacity=".45" stroke="#248553" stroke-width=".18" stroke-dasharray=".7 .5"/>')
    svg.append('<text x="54.25" y="35.6" font-size="1.15" fill="#155c38" text-anchor="middle">DAC fanout</text>')
    for ref,f in sorted(fs.items()):
        x,y,w,h=bbox(f);p=pmap[ref]
        color='#253241' if ref.startswith(('U','A')) else '#a2b4c1' if ref.startswith(('R','C','FB','D')) else '#607d72'
        if ref=='J1':color='#d7dbe0'
        if ref.startswith('H'):
            cx,cy=point(f.GetPosition());svg.append(f'<circle cx="{cx}" cy="{cy}" r="1.6" fill="#f3f5f7" stroke="#516170" stroke-width=".15"/>');continue
        svg.append(f'<g><title>{html.escape(ref+" / "+p["value"]+" / "+str(tuple(p["xy"])))}</title><rect class="p" x="{x}" y="{y}" width="{w}" height="{h}" rx=".15" fill="{color}"/>')
        if ref.startswith(('U','A','J')):
            if ref=='J1':label='DB25';tc='#253241'
            elif p['kind']=='opquad':label=['X','Y','R','G','B','I','AUX1','AUX2'][int(ref[1:])-11]+' / '+ref;tc='#fff'
            elif ref=='J2':label='MOLEX 3P';tc='#fff'
            elif ref=='A1':label='TEENSY 4.0';tc='#fff'
            elif ref=='U1':label='CS42448';tc='#fff'
            else:label=ref;tc='#fff'
            svg.append(f'<text x="{x+w/2}" y="{y+h/2}" font-size="1.15" fill="{tc}" text-anchor="middle" dominant-baseline="middle">{label}</text>')
        else:svg.append(f'<text class="ref" x="{x+w/2}" y="{y+h/2}">{ref}</text>')
        svg.append('</g>')
    for i,label in enumerate(['X / Y','I / R','G / B','AUX1 / AUX2']):
        x,y=point(fs['U'+str(21+i)].GetPosition())
        svg.append(f'<text x="{x}" y="{y-4}" font-size="1.2" fill="#1b4661" text-anchor="middle">{label}</text>')
    svg += ['<path d="M 115 64 h 12 m -3 -2 l 3 2 -3 2" fill="none" stroke="#1d5e85" stroke-width=".4"/>',
        '<text x="112" y="60" font-size="1.6" fill="#1d5e85">ILDA cable</text>',
        '<text x="88" y="-0.6" font-size="1.4" fill="#1d5e85">USB ↑</text>',
        '<text x="0" y="104" font-size="1.65" fill="#213b31">Flow: codec → buffers / differential amps → switches → 1W resistors → DB25</text>',
        '<text x="0" y="107" font-size="1.45" fill="#52616d">DB25 projects beyond PCB. Footprint MPN / cable clearance still to be finalized. Hover for refs.</text>',
        '<text x="0" y="110" font-size="1.45" fill="#52616d">Top view, origin = PCB upper-left. KiCad groups are editable; no manufacturing files released.</text>','</svg>']
    (ROOT/'preview/floorplan.svg').write_text('\n'.join(svg))
    print(json.dumps({key:audit[key] for key in ['components','pad_comparisons','placement_errors','unconnected_items','teensy_to_connector_projected_gap_mm','power_resistor_to_connector_projected_gap_mm','signal_airwire_MST_mm']},indent=2))
if __name__=='__main__':main()
