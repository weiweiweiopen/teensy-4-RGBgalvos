"""Compile the isolated RevB-P4 firmware; never upload or edit installed cores."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
CLI='/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli'
FQBN='teensy:avr:teensy40:usb=serialmidiaudio,speed=600,opt=o2std,keys=en-us,audiorate=44,audioblocksize=normal,USBchannelcount=8'
build=RUN/'build/firmware';build.mkdir(parents=True,exist_ok=True)
command=[CLI,'compile','--fqbn',FQBN,'--build-path',str(build),str(WORK/'firmware/ilda8ch_revB')]
result=subprocess.run(command,capture_output=True,text=True)
(RUN/'analysis/firmware-build.log').write_text(result.stdout+result.stderr)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(RUN/'analysis/firmware-build.json').write_text(json.dumps(dict(command=command,returncode=result.returncode,
    firmware_sha256={p.name:sha(p) for p in (WORK/'firmware/ilda8ch_revB').iterdir() if p.is_file()},
    uploaded=False),indent=2)+'\n')
print(result.stdout+result.stderr)
sys.exit(result.returncode)
