"""Electrical ECO computations and real generic ngspice DC/AC runs.

Use /usr/local/bin/python3. Models do not certify real-part transients.
"""
from pathlib import Path
import ast
import itertools
import json
import math
import sys
import types

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
DEST=RUN/'analysis/electrical';DEST.mkdir(exist_ok=True)
parts=json.loads((WORK/'sources/electrical.json').read_text())['parts'];pmap={p['ref']:p for p in parts}
assert pmap['C18']['value']=='22u' and pmap['C18']['pins']['1']=='FILT_ADC'
assert pmap['C20']['value']=='100u' and pmap['C20']['pins']['1']=='FILT_DAC'
assert pmap['R26']['pins']['2']==pmap['A1']['pins']['26']=='MCU_3V3'
assert pmap['A1']['pins']['7']=='RAILS_GOOD'
assert pmap['U5']['pins']['1']=='SHUTTER_DISABLE'
assert pmap['U6']['mpn']=='TLV3202AIDGKR'
assert pmap['U6']['pins']['1']!=pmap['U6']['pins']['7']
assert pmap['U7']['pins']=={'1':'CODEC_RESET_GPIO','2':'GND','3':'RAIL_P_GOOD','4':'RESET_QUALIFIED','5':'+3V3','6':'RAIL_N_GOOD'}
assert pmap['U36']['pins']['5']=='MCU_3V3'
assert pmap['U8']['mpn']=='SN74LVC1G175DBVR'
assert pmap['U8']['pins']=={'1':'ARM','2':'GND','3':'+3V3','4':'ARM_QUALIFIED','5':'+3V3','6':'CODEC_RESET'}
assert pmap['R364']['value']==pmap['R365']['value']=='4.7k'
assert pmap['R18']['value']==pmap['R19']['value']==pmap['R373']['value']=='2.2k'
for ch in range(1,9):
    for leg,offset in [('P',0),('N',1)]:
        assert pmap['R'+str(129+20*(ch-1)+offset)]['pins']['1']=='ISO_DAC%d_%s'%(ch,leg)
        pull=pmap['R'+str(401+2*(ch-1)+offset)]
        assert pull['value']=='10M' and pull['pins']=={'1':'IN%d%s'%(ch,leg),'2':'GND'}

def positive_threshold(usb,out,rs=(1e6,200e3,10e6,150e3,100e3),error=0):
    top,bottom,feedback,ref_top,ref_bottom=rs
    reference=usb*ref_bottom/(ref_top+ref_bottom)
    return (reference+error)*(1+top/bottom+top/feedback)-out*top/feedback

def negative_threshold(usb,out,rs=(1e6,100e3,45.3e3,100e3,10e6),error=0):
    top,bias,ref_top,ref_bottom,feedback=rs
    reference=(usb/ref_top+out/feedback)/(1/ref_top+1/ref_bottom+1/feedback)
    return (reference+error)*(1+top/bias)-usb*top/bias

corners={}
for name,fn,nominal in [('positive',positive_threshold,(1e6,200e3,10e6,150e3,100e3)),
                         ('negative',negative_threshold,(1e6,100e3,45.3e3,100e3,10e6))]:
    for state,outputs in [('fault_to_good',[0,.325]),('good_to_fault',[4.4,5.25])]:
        values=[]
        for signs in itertools.product([.99,1.01],repeat=5):
            resistors=tuple(v*s for v,s in zip(nominal,signs))
            for usb,out,error in itertools.product([4.75,5.25],outputs,[-.012,.012]):
                values.append(fn(usb,out,resistors,error))
        corners[name+'_'+state]=dict(min_V=min(values),max_V=max(values),cases=len(values))
summary=dict(
    nominal_thresholds_V=dict(positive_recovery=positive_threshold(5,0),positive_loss=positive_threshold(5,5),
        negative_recovery=negative_threshold(5,0),negative_loss=negative_threshold(5,5)),
    threshold_corners=corners,
    threshold_corner_assumptions='Separate TLV3202 push-pull raw outputs and feedback. All five relevant resistors +/-1%, USB4.75..5.25V, LOW0..0.325V, HIGH4.4..5.25V; +/-12mV aggregate offset/bias allowance. Conservative static independent corners, not latency simulation.',
    adc_sense=dict(positive_factor=6+100/4.7,negative_factor=11+100/4.7,
        positive_at_15V=15/(6+100/4.7),negative_at_minus15V=(33-15)/(11+100/4.7),
        upstream_capacitors=['C37','C38'],downstream_pull_ohms=4700,
        tabulated_off_test_leakage_A=3e-6,tabulated_off_test_drain_V=3e-6*4700*1.001,
        assumed_conservative_isolation_leakage_A=38e-6,off_drain_bound_V=38e-6*4700*1.001,
        mcu_unpowered_negative_bias_V=-18*333.3/(99000+9900+333.3),
        limitation='38uA is the largest published isolation-mode table envelope, not a separately guaranteed -1.5V/3.3V shutdown test corner. Negative-signal high impedance is specified architecturally; validate actual leakage and ramps on hardware.'),
    input_switch=dict(location='Before existing 100k, codec low-impedance side',mpn='ADG4613BRUZ',
        powered_off_leakage_test_A=3e-6,normal_off_max_A=80e-9,
        on_capacitance_typ_F=50e-12,on_capacitance_max_specified=False,
        input_shunt_ohms=10e6,dc_input_attenuation=10e6/(10e6+100e3+12.5),
        dc_load_at_5_25V_A=5.25/(10e6+100e3+12.5)),
    hardware_truth_table=[dict(rails_good=good,reset_request=reset,arm_request=arm,
        codec_reset=good and reset,fresh_arm_clock_requested=arm,
        dac_inputs_connected=good and reset,shutter_oe_disabled=not(good and reset))
        for good,reset,arm in itertools.product([False,True],repeat=3)],
    limits=['Truth table models valid supply levels, not undefined ramp regions or propagation delays.',
            'The ARM latch blocks the known valid-logic-rail recovery pulse; power-on/brownout analog timing remains a hardware qualification item.',
            'Powered-off analog protection is -5.5..+16V within a maximum16V terminal span, not +/-16V.',
            'Exact comparator, supervisor and switch removal transients require bench waveforms.'])

def watchdog_sequence(latched):
    # Manufacturer truth-table behavior, ignoring analog propagation delays.
    # In particular HC123 may trigger on clear release with B already HIGH.
    events=[(0,0,0,0),(10,1,0,0),(20,1,1,0),(21,1,1,1),(21.002,1,1,0),
            (30,1,1,1),(31,0,1,1),(100,1,1,1),(101,1,1,1),
            (110,1,0,1),(111,1,0,0),(112,1,1,0),(113,1,1,1),(114,0,0,0)]
    eligible=False;prev_arm=prev_hb=prev_clear=False;expiry=-1;out=[]
    for time,reset,arm,hb in events:
        if not reset:eligible=False
        elif arm and not prev_arm:eligible=True
        clear=eligible if latched else bool(reset and arm)
        if not clear:expiry=-1
        elif (hb and not prev_hb) or (clear and not prev_clear and hb):expiry=time+4.7
        out.append(dict(time_ms=time,reset=bool(reset),arm=bool(arm),heartbeat=bool(hb),
                        clear=clear,run=bool(clear and time<expiry)))
        prev_arm,prev_hb,prev_clear=bool(arm),bool(hb),clear
    return out
legacy=watchdog_sequence(False);latched=watchdog_sequence(True)
assert next(e for e in legacy if e['time_ms']==100)['run']
assert not next(e for e in latched if e['time_ms']==100)['run']
assert next(e for e in latched if e['time_ms']==113)['run']
assert not next(e for e in latched if e['time_ms']==114)['run']
summary['arm_recovery_logic_regression']=dict(legacy_and=legacy,new_latch=latched,
    basis='HC123 datasheet p2 clear-release trigger plus SN74LVC1G175 p10 DFF truth table; state-level model, not analog/macromodel timing.')
summary['startup_pulldowns']=dict(ohms=2200,assumed_weak_pullup_ohms=22000,
    resulting_default_V=3.3*2200/(22000+2200),active_GPIO_load_mA=3.3/2200*1000)

# Load the previously declared generic model and its ngspice interface only.
model=types.ModuleType('design');model.ROOT=WORK;model.parts=parts;sys.modules['design']=model
tree=ast.parse((ROOT.parent/'revA/tools/spice_verify.py').read_text())
body=[]
for node in tree.body:
    body.append(node)
    if isinstance(node,ast.FunctionDef) and node.name=='circuit':break
ns={};exec(compile(ast.Module(body=body,type_ignores=[]),'existing_generic_ngspice_model','exec'),ns)
results=[]
for name,rf in [('XY',39000),('Colour',20000)]:
    for cm in [False,True]:
        deck=ns['circuit'](rf,common=cm,dc=0 if cm else 1)
        deck=deck.replace('RIP dp ip 100k','RSIP dp dsp 12.5\nCSIP dsp 0 50p\nRIP dsp ip 100k\nRPIP ip 0 10Meg')
        deck=deck.replace('RIN dn inn 100k','RSIN dn dsn 12.5\nCSIN dsn 0 50p\nRIN dsn inn 100k\nRPIN inn 0 10Meg')
        path=DEST/(name+('_common' if cm else '_diff')+'.cir');path.write_text(deck)
        C=ns['C'];lines=[s.encode() for s in deck.splitlines()];arr=(C.c_char_p*(len(lines)+1))(*lines,None)
        assert ns['lib'].ngSpice_Circ(arr)==0
        ns['cmd']('op');p=ns['values']('v(outp)')[0];n=ns['values']('v(outn)')[0]
        expected=rf/21000*(1/(1+102.7/(100000/11)))*10e6/(10e6+100e3+12.5)
        assert abs(p-(0 if cm else expected))<.0001
        assert abs(p+n)<.0001
        ns['cmd']('ac dec 100 10 1000000')
        freq=[abs(f) for f in ns['values']('frequency')];outputs=ns['values']('v(outp)')
        low=abs(outputs[0]);pole=next((f for f,z in zip(freq,outputs) if abs(z)<low/math.sqrt(2)),None) if not cm else None
        results.append(dict(class_=name,excitation='common_mode' if cm else 'differential',dc_positive_V=p,
            dc_negative_V=n,expected_gain=0 if cm else expected,sampled_minus3dB_Hz=pole,
            low_frequency_AC_gain=low))
        ns['cmd']('destroy all')
errors=[s for s in ns['log'] if 'Error' in s or 'fatal' in s.lower()];assert not errors,errors
(DEST/'ngspice.log').write_text('\n'.join(ns['log']))
summary.update(spice=dict(simulator=ns['LIB'],model='Generic 10MHz opamp, ADG Ron12.5ohm/C50pF typical, TMUX2.7ohm,10k per-leg receiver; not manufacturer macromodels',
    results=results,errors=errors))
(DEST/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(dict(thresholds=summary['nominal_thresholds_V'],corners=corners,spice=results),indent=2))
