"""Compare local data/full_output_tb_SIMPLE.json against the Drive version.
Specifically: are the Tessier Carole lessons attributed to Imane Berrai
in BOTH files, or only locally?
"""
import io, json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from googleapiclient.http import MediaIoBaseDownload
from backend.tools.sync_yaml_to_drive import get_drive, find_folder_id, ROOT_FOLDER_NAME

DATA_FILE = "full_output_tb_SIMPLE.json"

drive = get_drive()
root = find_folder_id(drive, ROOT_FOLDER_NAME)
data_folder = find_folder_id(drive, "data", root) or root
print(f"Drive root: {root}")
print(f"Drive data folder: {data_folder}")

q = f"name='{DATA_FILE}' and '{data_folder}' in parents and trashed=false"
files = drive.files().list(q=q, fields="files(id,name,modifiedTime)").execute().get("files", [])
if not files:
    sys.exit(f"❌ {DATA_FILE} not found in Drive 'data' folder")
f = files[0]
print(f"Drive file: {f['id']} modified={f['modifiedTime']}")

buf = io.BytesIO()
dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=f["id"]))
done = False
while not done:
    _, done = dl.next_chunk()
buf.seek(0)
drive_data = json.loads(buf.read().decode("utf-8"))

local = json.load(open("data/full_output_tb_SIMPLE.json", encoding="utf-8"))

print()
print(f"LOCAL:  {len(local)} families")
print(f"DRIVE:  {len(drive_data)} families")

# Look at Tessier Carole specifically
def carole(d):
    for fid, f in d.items():
        if "tessier" in (f.get("parent_name", "") or "").lower():
            return fid, f
    return None, None

l_id, l_f = carole(local)
d_id, d_f = carole(drive_data)
print()
print(f"=== Tessier Carole in LOCAL ({l_id}) ===")
if l_f:
    print(f"  lessons: {len(l_f.get('lessons', []))}")
    teachers = {}
    statuses = {}
    for L in l_f.get("lessons", []):
        t = L.get("teacher", "?")
        s = L.get("attendance_status", "?")
        teachers[t] = teachers.get(t, 0) + 1
        statuses[s] = statuses.get(s, 0) + 1
    print(f"  teachers: {teachers}")
    print(f"  statuses: {statuses}")

print()
print(f"=== Tessier Carole in DRIVE ({d_id}) ===")
if d_f:
    print(f"  lessons: {len(d_f.get('lessons', []))}")
    teachers = {}
    statuses = {}
    for L in d_f.get("lessons", []):
        t = L.get("teacher", "?")
        s = L.get("attendance_status", "?")
        teachers[t] = teachers.get(t, 0) + 1
        statuses[s] = statuses.get(s, 0) + 1
    print(f"  teachers: {teachers}")
    print(f"  statuses: {statuses}")

# All families count
print()
print(f"=== Total payable lessons in each ===")
PAYABLE = {"Present", "Unrecorded", "AbsentNoMakeup"}
def count_payable(d):
    n = 0
    for f in d.values():
        for L in f.get("lessons", []):
            if L.get("attendance_status") in PAYABLE:
                n += 1
    return n
print(f"LOCAL: {count_payable(local)} payable lessons")
print(f"DRIVE: {count_payable(drive_data)} payable lessons")
