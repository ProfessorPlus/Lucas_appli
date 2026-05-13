"""Inspect Notion 'Profs hors TutorBird' entries for Tessier Carole
to understand why Imane Berrai gets 1950€ wrongly."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.config_loader import load_secrets, clear_secrets_cache
from scripts.fetch_notion_profs import fetch_notion_profs, convert_notion_profs_to_families

clear_secrets_cache()
secrets = load_secrets()
res = fetch_notion_profs(secrets)
print(f"success={res['success']}  entries={len(res['entries'])}")
print()
print("=== All Notion entries ===")
for e in res["entries"]:
    print(f"  famille={e['famille']!r:<25} prof={e['professeur']!r:<22} eleve={e['eleve']!r:<22} h={e['heures_faites']!r:<6} taux={e['taux_horaire_client']!r}{e['devise_client']}/h  email={e.get('email_prof')!r}")

print()
print("=== After convert_notion_profs_to_families ===")
fams = convert_notion_profs_to_families(res["entries"])
for fid, f in fams.items():
    parent = f.get("parent_name", "") or ""
    if "tessier" in parent.lower() or "carole" in parent.lower():
        print(f"family_id={fid}  parent_name={parent!r}")
        print(f"  fields: {sorted(f.keys())}")
        print(f"  currency={f.get('currency')!r}  source={f.get('source')!r}")
        lessons = f.get("lessons", [])
        print(f"  lessons: {len(lessons)}")
        for L in lessons[:6]:
            print(f"    {L}")

print()
print("=== teacher attribution in raw data file ===")
data = json.load(open("data/full_output_tb_SIMPLE.json", encoding="utf-8"))
for fid, f in data.items():
    parent = (f.get("parent_name") or "").lower()
    if "tessier" in parent or "carole" in parent:
        print(f"family_id={fid}  parent_name={f.get('parent_name')}")
        print(f"  currency={f.get('currency')!r}  source={f.get('source')!r}")
        teachers_seen = {}
        for L in f.get("lessons", []):
            tn = L.get("teacher") or L.get("teacher_name") or "(?)"
            teachers_seen[tn] = teachers_seen.get(tn, 0) + 1
        print(f"  teachers_in_lessons: {teachers_seen}")
        # show a sample lesson
        if f.get("lessons"):
            print(f"  sample lesson: {f['lessons'][0]}")
