# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-051
"""两个独立进程共享 SQLite、隔离 output roots 的最小宿主前置；不冒充真实账号连接。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_two_processes_share_claim_authority_and_keep_business_roots_disjoint(tmp_path: Path) -> None:
    setup = f"""
import json,sys
sys.path.insert(0, {str(SCRIPTS)!r})
from content.coordination import CoordinationStore, ROLE_NAMES
s=CoordinationStore({str(tmp_path / 'coordination.sqlite')!r})
s.register_iteration('i1','approval://i1')
for n in (1,2):
 roles = {{r:[json.dumps(['grok-bot',f'a{{n}}-{{r}}',f'run-a{{n}}-{{r}}'])] for r in ROLE_NAMES}}
 s.register_deployment('i1',f'd{{n}}',roles,instance_id=f'i{{n}}',account_identity_ref=f'account://{{n}}',resource_reservation_ref=f'budget://{{n}}')
 s.register_shard('i1',f's{{n}}',f'片{{n}}',f'scope://{{n}}',n,[f'target://{{n}}'])
"""
    subprocess.run([sys.executable, "-B", "-c", setup], check=True)
    worker = """
import json,os,sys
from pathlib import Path
sys.path.insert(0, os.environ['SCRIPTS'])
from content.coordination import CoordinationStore
from content.coordination.fence import WriteFenceToken
s=CoordinationStore(os.environ['DB'])
c=s.claim('i1',os.environ['TEAM'],os.environ['KEY'],shard_id=os.environ['SHARD'],deployment_id=os.environ['DEPLOYMENT'])
t=WriteFenceToken('i1',os.environ['SHARD'],os.environ['DEPLOYMENT'],os.environ['TEAM'],c['generation'],os.environ['TARGET'])
out=Path(os.environ['OUT']); s.fenced_write(t,lambda:(out.mkdir(parents=True,exist_ok=True),(out/'result').write_text(os.environ['TARGET'])))
print(json.dumps(c))
"""
    processes = []
    for n in (1, 2):
        env = {**os.environ, "SCRIPTS": str(SCRIPTS), "DB": str(tmp_path / "coordination.sqlite"), "TEAM": f"team-{n}", "KEY": f"c{n}", "SHARD": f"s{n}", "DEPLOYMENT": f"d{n}", "TARGET": f"target://{n}", "OUT": str(tmp_path / f"output-{n}")}
        processes.append(subprocess.Popen([sys.executable, "-B", "-c", worker], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    results = [p.communicate(timeout=10) for p in processes]
    assert [p.returncode for p in processes] == [0, 0], results
    assert (tmp_path / "output-1/result").read_text() == "target://1"
    assert (tmp_path / "output-2/result").read_text() == "target://2"
    assert not (tmp_path / "output-1/output-2").exists()
