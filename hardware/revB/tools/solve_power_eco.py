"""Route isolated ECO geometry using the existing geometric search engine."""
from pathlib import Path
import json
import subprocess
import sys
import route_remaining

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'eco/power-sequencing-20261025/project/routing/power-eco'


def main():
    data=json.loads((RUN/'geometry.json').read_text())
    solver=route_remaining.Router(data);solver.run_dir=RUN
    order=list(data['net_order']);failed=[];solver.checkpoint()
    for net in order:
        data['net_order']=[net]
        try:solver.run()
        except RuntimeError as exc:
            failed.append(dict(net=net,error=str(exc)));print('Deferred port for native repair:',net,flush=True)
        solver.checkpoint()
    (RUN/'deferred.json').write_text(json.dumps(failed,indent=2))
    solver.checkpoint()
    print('ECO solver finished.',flush=True)


if __name__=='__main__':
    if '--background' in sys.argv:
        with (RUN/'solver.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-B','-u',str(Path(__file__).resolve())],
                                     stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (RUN/'solver-process.json').write_text(json.dumps(dict(pid=process.pid),indent=2))
        print('ECO solver PID',process.pid)
    else:main()
