"""Draw the frozen, actual routing and codec escape obstructions for review."""
import html,json
import pcbnew as k
from diagnose_unconnected import ROOT,OUT,point,bbox,sha

COLORS={'RUN_ENABLE':'#1a7a5a','DAC3_N':'#bd5279','DAC6_P':'#007fa5','DAC7_N':'#b07800','DAC7_P':'#7545a0','AIN2':'#b9432e'}
BLOCKERS={'DAC8_P':'#e18a13','DAC8_N':'#1671be','BCLK':'#923b9f','+5VA':'#d44848'}
PAIRS=[('RUN_ENABLE',('U4','13'),('U5','2')),('DAC3_N',('U1','29'),('R170','1')),('DAC6_P',('U1','36'),('R229','1')),
       ('DAC7_N',('U1','38'),('R250','1')),('DAC7_P',('U1','39'),('R249','1')),('AIN2',('U1','45'),('C23','1'))]
def main():
    b=k.LoadBoard(str(OUT/'frozen-project/ILDA8CH.kicad_pcb'))
    pads={(f.GetReference(),p.GetNumber()):p for f in b.GetFootprints() for p in f.Pads() if p.GetNumber()}
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-5 -10 228 122" width="2280" height="1220">',
        '<style>text{font-family:Arial,sans-serif}.label{font-size:1.6px;fill:#20354a}.small{font-size:1.35px;fill:#526575}</style>',
        '<rect x="-5" y="-10" width="228" height="122" fill="#f3f5f7"/>',
        '<text x="0" y="-5.4" font-size="3.2" fill="#20354a">RevB-P3 — six open nets / actual frozen copper geometry</text>',
        '<text x="0" y="-1.5" font-size="1.8" fill="#526575">Diagnostic drawing from KiCad data; not a GUI screenshot. Placement and primary PCB unchanged.</text>',
        '<rect x="0" y="0" width="110" height="100" fill="#fff" stroke="#20354a" stroke-width=".25"/>']
    for f in b.GetFootprints():
        r=f.GetBoundingBox(False,False);x,y,w,h=[k.ToMM(n) for n in (r.GetX(),r.GetY(),r.GetWidth(),r.GetHeight())]
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#e7ebef" stroke="#9faeba" stroke-width=".07"/>')
        if f.GetReference() in ['U1','U4','U5','J1','J2','A1']:
            name='CS42448' if f.GetReference()=='U1' else f.GetReference()
            svg.append(f'<text class="label" x="{x+w/2}" y="{y+h/2}" text-anchor="middle">{name}</text>')
    for t in b.GetTracks():
        if isinstance(t,k.PCB_VIA):continue
        a,c=point(t.GetStart()),point(t.GetEnd());color=COLORS.get(t.GetNetname(),'#b7c1ca')
        opacity=1 if t.GetNetname() in COLORS else .4
        svg.append(f'<path d="M{a[0]} {a[1]} L{c[0]} {c[1]}" fill="none" stroke="{color}" opacity="{opacity}" stroke-width=".10"/>')
    for number,(net,start,end) in enumerate(PAIRS,1):
        a,c=point(pads[start].GetPosition()),point(pads[end].GetPosition());color=COLORS[net]
        svg.append(f'<path d="M{a[0]} {a[1]} L{c[0]} {c[1]}" fill="none" stroke="{color}" stroke-width=".26" stroke-dasharray="1 .65"/>')
        svg.append(f'<circle cx="{c[0]}" cy="{c[1]}" r="1.05" fill="#fff" stroke="{color}" stroke-width=".2"/>')
        svg.append(f'<text x="{c[0]}" y="{c[1]+.55}" font-size="1.5" text-anchor="middle" fill="{color}">{number}</text>')
        svg.append(f'<text x="123" y="{4+3.8*number}" font-size="2.0" fill="{color}">{number}. {net}: {start[0]}.{start[1]} → {end[0]}.{end[1]}</text>')
    svg += ['<rect x="123" y="34" width="95" height="64" fill="#fff" stroke="#6d7f8d" stroke-width=".15"/>',
        '<text x="123" y="32" font-size="2.2" fill="#20354a">U1 bottom edge — 8× geometry view</text>',
        '<defs><clipPath id="roi"><rect x="54.5" y="22.2" width="11.875" height="8"/></clipPath></defs>',
        '<g transform="translate(123 34) scale(8) translate(-54.5 -22.2)" clip-path="url(#roi)">',
        '<rect x="54" y="14.5" width="10" height="10" fill="#e6eaee" stroke="#9aa8b4" stroke-width=".025"/>']
    for t in b.GetTracks():
        name=t.GetNetname();color=BLOCKERS.get(name,'#a6b2bd')
        if isinstance(t,k.PCB_VIA):
            x,y=point(t.GetPosition());diam=k.ToMM(t.Padstack().Size(k.F_Cu).x)
            svg.append(f'<circle cx="{x}" cy="{y}" r="{diam/2}" fill="{color}" opacity=".75"/><circle cx="{x}" cy="{y}" r=".15" fill="#fff"/>')
        else:
            a,c=point(t.GetStart()),point(t.GetEnd());width=k.ToMM(t.GetWidth())
            opacity=1 if name in BLOCKERS else .4
            svg.append(f'<path d="M{a[0]} {a[1]} L{c[0]} {c[1]}" fill="none" stroke="{color}" opacity="{opacity}" stroke-width="{width}" stroke-linecap="round"/>')
    u1=next(f for f in b.GetFootprints() if f.GetReference()=='U1')
    for pad in u1.Pads():
        r=pad.GetBoundingBox();x,y,w,h=[k.ToMM(n) for n in (r.GetX(),r.GetY(),r.GetWidth(),r.GetHeight())]
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx=".075" fill="#d5ba6b" stroke="#947824" stroke-width=".012"/>')
        if pad.GetNumber() in ['36','38','39','45']:
            px,py=point(pad.GetPosition())
            svg.append(f'<circle cx="{px}" cy="{py}" r=".27" fill="none" stroke="#cf263a" stroke-width=".04" stroke-dasharray=".10 .06"/>')
            svg.append(f'<text x="{px}" y="{py-.62}" font-size=".34" fill="#a41528" text-anchor="middle">{pad.GetNumber()}</text>')
    svg += ['</g>',
        '<text x="123" y="102" font-size="1.5" fill="#526575">Main blockers: DAC8_P (F) · DAC8_N (B) · BCLK (B) · +5VA (F)</text>',
        '<text x="123" y="105" font-size="1.65" fill="#526575">Red dashed rings mark open pads, not new vias.</text>',
        '<text x="0" y="105" font-size="1.8" fill="#20354a">Overview dashed lines indicate missing interconnects; they are not proposed routes.</text>',
        '<text x="0" y="109" font-size="1.5" fill="#526575">Source PCB SHA-256: 07bc192509e2… · 6 opens · 36 dangling-via warnings · 2 silk-edge warnings</text>','</svg>']
    (OUT/'diagnostic-map.svg').write_text('\n'.join(svg))
    print('Diagnostic map:',OUT/'diagnostic-map.svg')
if __name__=='__main__':main()
