"""Verify this unpacked public release without installing dependencies."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent
manifest = json.loads((root / "BUNDLE_MANIFEST.json").read_text())
errors=[]
for item in manifest["files"]:
    path=root/item["path"]
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        errors.append(item["path"]+": missing or unsafe");continue
    raw=path.read_bytes()
    if len(raw)!=item["bytes"] or hashlib.sha256(raw).hexdigest()!=item["sha256"]:
        errors.append(item["path"]+": checksum mismatch")
print(json.dumps({"status":"failed" if errors else "passed","files":len(manifest["files"]),"errors":errors},indent=2))
raise SystemExit(bool(errors))
