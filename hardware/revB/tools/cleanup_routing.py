"""Finish short local power escapes without changing the project DRC rules."""
import json,shutil,sys
import pcbnew as k
from route_board import ROOT,LIVE,active,note,sha,MM,xy,segment,via

def export_necks(b,fix):
    removed_zones=list(b.Zones())
    for z in removed_zones:b.Remove(z)
    b.SetCopperLayerCount(2);assert k.ExportSpecctraDSN(b,str(fix/'ILDA8CH.dsn'))
    path=fix/'ILDA8CH.dsn';text=path.read_text();start=text.index('(class Power ')
    assert '(width 500)' in text[start:]
    text=text[:start]+text[start:].replace('(width 500)','(width 200)',1);path.write_text(text)

def prepare():
    d=active();assert sha(LIVE)==d['routed_sha256'],'Live PCB changed; preserve it.'
    run=ROOT/d['run'];fix=run/'cleanup';fix.mkdir();(fix/'logs').mkdir()
    shutil.copy2(LIVE,fix/'before.kicad_pcb');shutil.copy2(ROOT/'QA/routing-drc.json',fix/'before-drc.json')
    b=k.LoadBoard(str(LIVE));old=k.LoadBoard(str(run/'placement.kicad_pcb'));fs={f.GetReference():f for f in b.GetFootprints()}
    # DSN roundtrip quantizes six coordinates by 1 nm. Restore exact placement.
    for f in old.GetFootprints():
        other=fs[f.GetReference()]
        assert abs(f.GetPosition().x-other.GetPosition().x)<=1 and abs(f.GetPosition().y-other.GetPosition().y)<=1
        other.SetPosition(f.GetPosition())
    widened=0
    for t in b.GetTracks():
        if not isinstance(t,k.PCB_VIA) and t.GetWidth()<MM(.15):t.SetWidth(MM(.15));widened+=1
        t.SetLocked(True)
    for z in b.Zones():z.SetIsFilled(False)
    k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    shutil.copy2(LIVE,fix/'prepared.kicad_pcb')
    export_necks(b,fix)
    # Only new necks use 0.2mm. Existing 0.5mm buses and local loops are fixed;
    # the unchanged .kicad_pro still enforces its global 0.15mm minimum.
    d.update(cleanup_prepared_sha256=sha(LIVE),cleanup_widened_segments=widened,stage='cleanup_prepared');note(d)
    print('Prepared local cleanup:',fix,'widened segments:',widened)

def refine():
    d=active();assert sha(LIVE)==d['cleanup_prepared_sha256'],'Live PCB changed.'
    fix=ROOT/d['run']/'cleanup';b=k.LoadBoard(str(LIVE));removed=[]
    # Replace two sub-minimum-width branches with legal 0.15mm local jogs;
    # preserve the separately fixed direct opamp-to-feedback-resistor loops.
    for net,offset in [('SUM2N',0),('SUM6N',36)]:
        for t in list(b.GetTracks()):
            if isinstance(t,k.PCB_VIA) or t.GetNetname()!=net:continue
            a,c=xy(t.GetStart()),xy(t.GetEnd())
            if max(a[1],c[1])<=37.5401+offset and max(a[0],c[0])<=47.4001:continue
            removed.append(t);b.Remove(t)
        points=[(48.175,40.6+offset),(48.175,39.3+offset),(48.3,39.175+offset),(48.3,38.25+offset),(47.4,37.35+offset)]
        for a,c in zip(points,points[1:]):segment(b,a,c,net,.15)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    shutil.copy2(LIVE,fix/'prepared.kicad_pcb');export_necks(b,fix)
    d.update(cleanup_prepared_sha256=sha(LIVE),stage='cleanup_prepared');note(d)
    print('Local SUM2N/SUM6N branches refined to 0.15mm; DRC required.')

def finish():
    d=active();assert sha(LIVE)==d['cleanup_prepared_sha256'],'Live PCB changed; retain SES without overwrite.'
    fix=ROOT/d['run']/'cleanup';b=k.LoadBoard(str(LIVE))
    assert k.ImportSpecctraSES(b,str(fix/'ILDA8CH.ses'))
    b.SetCopperLayerCount(4)
    old=k.LoadBoard(str(ROOT/d['run']/'placement.kicad_pcb'));fs={f.GetReference():f for f in b.GetFootprints()}
    for f in old.GetFootprints():fs[f.GetReference()].SetPosition(f.GetPosition())
    for t in b.GetTracks():
        if isinstance(t,k.PCB_VIA):t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    shutil.copy2(LIVE,fix/'result.kicad_pcb')
    d.update(stage='cleanup_imported_pending_drc',routed_sha256=sha(LIVE));note(d)
    print('Cleanup imported; native checks required.')

def local():
    d=active();assert sha(LIVE)==d['routed_sha256'],'Live PCB changed.'
    fix=ROOT/d['run']/'cleanup';assert not (fix/'before-local.kicad_pcb').exists()
    shutil.copy2(LIVE,fix/'before-local.kicad_pcb')
    b=k.LoadBoard(str(LIVE))
    # Two remaining ground pads escape inward under the LQFP body to the
    # continuous inner GND planes, rather than threading the outer cap array.
    for y in [14.25,17.25]:
        segment(b,(72.675,y),(71.25,y),'GND',.15);via(b,(71.25,y))
    # Bridge the two DVDD pads around (not across) the intervening DGND pad.
    points=[(67.25,11.325),(67.25,12.4),(67.65,12.8),(67.85,12.8),(68.25,12.4),(68.25,11.325)]
    for a,c in zip(points,points[1:]):segment(b,a,c,'+3V3',.2)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    d.update(stage='local_escapes_pending_drc',routed_sha256=sha(LIVE));note(d)
    print('Local codec escapes added; DRC required.')

def undo_local():
    d=active();assert sha(LIVE)==d['routed_sha256'],'Live PCB changed; preserve it.'
    fix=ROOT/d['run']/'cleanup'
    shutil.copy2(LIVE,fix/'rejected-local.kicad_pcb')
    shutil.copy2(ROOT/'QA/routing-drc.json',fix/'rejected-local-drc.json')
    shutil.copy2(fix/'before-local.kicad_pcb',LIVE)
    d.update(stage='cleanup_imported_pending_drc',routed_sha256=sha(LIVE));note(d)
    print('Rejected local attempt archived; restored the clearance-clean routing pass.')

def through_vias():
    d=active();assert sha(LIVE)==d['routed_sha256'],'Live PCB changed.'
    b=k.LoadBoard(str(LIVE));changed=0
    for t in b.GetTracks():
        if isinstance(t,k.PCB_VIA):
            if t.GetViaType()!=k.VIATYPE_THROUGH:changed+=1
            t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    d.update(stage='through_vias_pending_drc',routed_sha256=sha(LIVE),normalized_through_vias=changed);note(d)
    print('Corrected SES via types to standard F.Cu-to-B.Cu through vias:',changed)
if __name__=='__main__':{'prepare':prepare,'refine':refine,'finish':finish,'local':local,'undo-local':undo_local,'through-vias':through_vias}[sys.argv[1]]()
