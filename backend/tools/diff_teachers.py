"""Diff the `teachers` section of local vs Drive secrets.yaml — rate fields only."""
import sys
from pathlib import Path
import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.tools.sync_yaml_to_drive import (
    get_drive, find_folder_id, find_file, download,
    ROOT_FOLDER_NAME, CONFIG_FOLDER_NAME,
)

local = yaml.safe_load(Path("config/secrets.yaml").read_text(encoding="utf-8"))
drive = get_drive()
root = find_folder_id(drive, ROOT_FOLDER_NAME)
cfg = find_folder_id(drive, CONFIG_FOLDER_NAME, root) or root
fobj = find_file(drive, "secrets.yaml", cfg)
drive_data = yaml.safe_load(download(drive, fobj["id"]).decode("utf-8"))

l_teachers = local.get("teachers", {}) or {}
d_teachers = drive_data.get("teachers", {}) or {}
print(f"LOCAL: {len(l_teachers)} teachers   DRIVE: {len(d_teachers)} teachers")
print()

SAFE = ("pay_rate", "hourly_rate", "currency", "pay_rate_chf", "pay_rate_eur", "pay_rate_aed", "split_percent", "rate")

all_names = sorted(set(l_teachers.keys()) | set(d_teachers.keys()))
diff_count = 0
print(f"{'Teacher':<30} {'key':<22} {'local':<18} {'drive':<18}")
print("-" * 90)
for name in all_names:
    l = l_teachers.get(name) or {}
    d = d_teachers.get(name) or {}
    if name not in l_teachers:
        print(f"{name:<30} (entirely MISSING in local)")
        diff_count += 1
        continue
    if name not in d_teachers:
        print(f"{name:<30} (entirely MISSING on drive)")
        diff_count += 1
        continue
    keys = sorted({k for k in set(l) | set(d) if any(s in k.lower() for s in SAFE)})
    for k in keys:
        lv, dv = l.get(k), d.get(k)
        if lv != dv:
            print(f"{name:<30} {k:<22} {str(lv):<18} {str(dv):<18}")
            diff_count += 1

print()
print(f"Total rate-field diffs: {diff_count}")

# also list any *_database_id / *_token fields that differ (other config)
print()
print("=== Other top-level config diffs (non-secret keys) ===")
SKIP_KEYS = {"teachers"}
for k in sorted(set(local) | set(drive_data)):
    if k in SKIP_KEYS:
        continue
    if local.get(k) != drive_data.get(k):
        if isinstance(local.get(k), dict):
            for sub in sorted(set(local.get(k, {})) | set(drive_data.get(k, {}))):
                lv, dv = (local.get(k) or {}).get(sub), (drive_data.get(k) or {}).get(sub)
                if lv != dv:
                    # mask values for safety
                    def mask(v):
                        if v is None:
                            return "(none)"
                        s = str(v)
                        return s if len(s) < 8 else f"{s[:3]}...{s[-2:]}"
                    print(f"  {k}.{sub}: local={mask(lv)} drive={mask(dv)}")
        else:
            print(f"  {k}: local!=drive (top-level)")
