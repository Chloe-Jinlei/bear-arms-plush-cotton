"""Verify every archived payload against archive-manifest.json without Genesis."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'archive-manifest.json').read_text())
errors=[]
for item in manifest['files']:
    p=ROOT/item['path']
    if not p.is_file():errors.append({'path':item['path'],'error':'missing'});continue
    if p.stat().st_size!=item['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
        errors.append({'path':item['path'],'error':'size or SHA-256 mismatch'})
print(json.dumps({'status':'passed' if not errors else 'failed','files_checked':len(manifest['files']),'errors':errors},indent=2))
sys.exit(bool(errors))
