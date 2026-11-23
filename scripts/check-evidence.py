"""Offline internal-consistency check, not independent verification of API execution."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from lab.contracts import Diagnosis
from lab.evaluator import evaluate
from lab.sandbox import SCENARIOS
root=Path(__file__).resolve().parents[1]
# Source digest generated from backend/lab at the published V1.0.0 tag.
v1_source_digest = '2f2390c985e42782a05a48268678d4d6039d3033adfb5122bd82978f806202e7'
seen=[]
for path in (root/'evidence/runs').glob('*.json'):
    capture=json.loads(path.read_text());seen.append(capture['scenario'])
    assert capture['source_digest']==v1_source_digest, 'Capture source differs from this V1 release'
    hashes=capture['workload_fingerprints']
    verdict=evaluate(capture['scenario'],Diagnosis.model_validate(capture['diagnosis']),capture['trace'],hashes['before'],hashes['after'])
    assert verdict==capture['verdict'], 'Stored verdict differs from recalculated verdict'
    assert verdict['passed'], 'Included release capture failed'
assert sorted(seen)==sorted(SCENARIOS), 'Expected one development capture per scenario'
print('Four V1 captures are internally consistent. No model calls were made.')
