"""Capture native-operation diagnostics while printing relevant check results."""
from pathlib import Path
from datetime import datetime
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025'
PYTHON='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3'
operation=sys.argv[1]
script='finish_power_eco.py' if operation in ['cleanup','clean-open-routes','annotate','audit','publish'] else 'route_power_eco.py'
result=subprocess.run([PYTHON,'-B',str(ROOT/'tools'/script),operation],capture_output=True,text=True)
log=RUN/'analysis'/(datetime.now().strftime('%H%M%S')+'-'+operation+'.log')
log.write_text(result.stdout+result.stderr)
for line in result.stdout.splitlines():
    if not line.startswith('swig/python') and 'Debug: Adding duplicate image handler' not in line:
        print(line)
if result.returncode:
    print(result.stderr)
print('Native operation',operation,'exit',result.returncode,'full log:',log)
sys.exit(result.returncode)
