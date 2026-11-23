"""Offline internal-consistency check, not independent verification of API execution."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from lab.contracts import Diagnosis
from lab.evaluator import evaluate
from lab.sandbox import SCENARIOS
root=Path(__file__).resolve().parents[1]
digest=hashlib.sha256()
for path in sorted((root/'backend/lab').glob('*.py')):
    digest.update(path.name.encode());digest.update(path.read_bytes())
seen=[]
for path in (root/'evidence/runs').glob('*.json'):
    capture=json.loads(path.read_text());seen.append(capture['scenario'])
    assert capture['source_digest']==digest.hexdigest(), 'Capture source differs from this V1 release'
    hashes=capture['workload_fingerprints']
    verdict=evaluate(capture['scenario'],Diagnosis.model_validate(capture['diagnosis']),capture['trace'],hashes['before'],hashes['after'])
    assert verdict==capture['verdict'], 'Stored verdict differs from recalculated verdict'
    assert verdict['passed'], 'Included release capture failed'
assert sorted(seen)==sorted(SCENARIOS), 'Expected one development capture per scenario'
print('Four V1 captures are internally consistent. No model calls were made.')
