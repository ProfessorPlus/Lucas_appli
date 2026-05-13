"""Reproduce compute_teacher_recap on the freshly-synced data and print
each prof's breakdown, to find why my Next.js total is 5440 instead of 3491."""
import sys, json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.config_loader import load_secrets, clear_secrets_cache
import yaml

clear_secrets_cache()
secrets = load_secrets()
familles_euros = yaml.safe_load(Path("config/familles_euros.yaml").read_text(encoding="utf-8")).get("euros", [])
tarifs = yaml.safe_load(Path("config/tarifs_speciaux.yaml").read_text(encoding="utf-8")).get("tarifs_speciaux", [])

print(f"teachers in secrets: {len(secrets.get('teachers', {}))}")
print(f"familles_euros: {len(familles_euros)}")
print(f"tarifs_speciaux: {len(tarifs)}")

data = json.load(open("data/full_output_tb_SIMPLE.json", encoding="utf-8"))
print(f"data: {len(data)} families")

# Try both functions
from scripts.recap_profs import compute_teacher_recap

from datetime import date
recap = compute_teacher_recap(
    data, secrets, familles_euros, tarifs,
    extraction_end_date=date(2026, 4, 30),
)
print()
print("=== compute_teacher_recap output ===")
print(f"grand_total: {recap.get('grand_total'):.2f}")
print(f"keys: {list(recap.keys())}")
print()

# Detail per teacher (right field names: eur + chf_as_eur)
print(f"{'Teacher':<28} {'#les':>5} {'hrs':>6} {'EUR':>10} {'CHF→EUR':>10} {'TOTAL':>10}")
print("-" * 75)
total = 0.0
for name, d in sorted(recap["teachers"].items()):
    eur = float(d.get("eur", 0))
    chf = float(d.get("chf_as_eur", 0))
    nb = d.get("nb_lessons", 0)
    hrs = d.get("total_hours", 0)
    teach_total = eur + chf
    total += teach_total
    star = "  ← IMANE !" if name == "Imane Berrai" else ""
    print(f"{name:<28} {nb:>5} {hrs:>6.1f} {eur:>10.2f} {chf:>10.2f} {teach_total:>10.2f}{star}")
print("-" * 75)
print(f"{'GRAND TOTAL':<28} {'':>5} {'':>6} {'':>10} {'':>10} {total:>10.2f}")
print()
# show details of Imane's lessons
imane = recap["teachers"].get("Imane Berrai")
if imane and imane.get("details"):
    print("=== Imane Berrai lesson details ===")
    for L in imane["details"][:20]:
        print(f"  {L}")
    if len(imane["details"]) > 20:
        print(f"  ... +{len(imane['details']) - 20} more")

# Dump full recap structure (first few levels only)
print()
print("=== Raw recap (top-level keys) ===")
for k, v in recap.items():
    if isinstance(v, (int, float, str)):
        print(f"  {k}: {v}")
    elif isinstance(v, list):
        print(f"  {k}: list of {len(v)} items")
        if v and isinstance(v[0], dict):
            print(f"    keys of item[0]: {list(v[0].keys())}")
    elif isinstance(v, dict):
        print(f"  {k}: dict with {len(v)} keys")
        sample = list(v.items())[:2]
        for sk, sv in sample:
            if isinstance(sv, dict):
                print(f"    {sk}: dict keys={list(sv.keys())}")
            else:
                print(f"    {sk}: {sv}")
