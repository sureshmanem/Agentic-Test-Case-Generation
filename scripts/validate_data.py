"""Validate synthetic requirements and golden test sets for consistency.

Checks: valid JSON, every acceptance criterion is covered by a golden test (or
explicitly listed as untestable), no references to unknown criteria, and that
rating arithmetic (mappings, notch changes, regulatory selection) in golden
expectations matches the rating scales.

Run: uv run python scripts/validate_data.py
"""
import collections, glob, json, os

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
M = "Aaa Aa1 Aa2 Aa3 A1 A2 A3 Baa1 Baa2 Baa3 Ba1 Ba2 Ba3 B1 B2 B3 Caa1 Caa2 Caa3 Ca C".split()
F = "AAA AA+ AA AA- A+ A A- BBB+ BBB BBB- BB+ BB BB- B+ B B- CCC+ CCC CCC- CC C RD D".split()
mo = {s:i+1 for i,s in enumerate(M)}; fi = {s:i+1 for i,s in enumerate(F)}
ok = True
def fail(msg):
    global ok; ok = False; print("FAIL:", msg)
assert len(M)==21 and len(F)==23
total = 0
for rf in sorted(glob.glob("data/requirements/R*.json")):
    r = json.load(open(rf)); rid = r["id"]
    acs = {a["id"] for a in r["acceptance_criteria"]}
    g = json.load(open(f"data/golden/{rid}_golden.json"))
    cov = collections.Counter(c for t in g["test_cases"] for c in t["covers"])
    ids = [t["id"] for t in g["test_cases"]]
    if len(ids)!=len(set(ids)): fail(f"{rid} duplicate test ids")
    for c in cov:
        if c not in acs: fail(f"{rid} unknown AC {c}")
    for a in acs:
        if a not in cov and a not in g.get("untestable_acs",{}): fail(f"{rid} AC not covered {a}")
    for t in g["test_cases"]:
        for k in ["id","title","type","priority","preconditions","steps","test_data","expected_result","covers"]:
            if k not in t: fail(f"{t.get('id')} missing {k}")
        if t["type"] not in {"positive","negative","boundary","edge"}: fail(f"{t['id']} bad type")
    total += len(ids)
    print(f"{rid}: {len(acs)} ACs, {len(ids)} golden tests, {len(g['expected_ambiguities'])} ambiguities, coverage per AC {dict(sorted(cov.items()))}")
# arithmetic checks
r2 = json.load(open("data/golden/R2_golden.json"))
for m,f in r2["test_cases"][0]["test_data"]["pairs"]:
    if mo[m]!=fi[f]: fail(f"mapping {m}->{f}")
notch = lambda sc,a,b: sc[a]-sc[b]
checks = [(fi,"BBB","BB+",-2),(mo,"Baa2","Baa2",0),(fi,"CCC","RD",-4),(mo,"Aaa","C",-20),(mo,"Ba1","Baa3",1),(mo,"Baa2","Ba1",-2),(mo,"A3","A2",1)]
for sc,a,b,exp in checks:
    if notch(sc,a,b)!=exp: fail(f"notch {a}->{b} = {notch(sc,a,b)} expected {exp}")
# R6 selection
def sel(rs):
    ranks = sorted((mo[v] if ag=="MOODYS" else fi[v], ag) for ag,v in rs.items() if v not in {"WR","WD","NR"})
    if not ranks: return "UNRATED"
    pick = ranks[0] if len(ranks)==1 else ranks[1]
    return pick[0], F[pick[0]-1]
exp6 = {"R6-TC01":(6,"A"),"R6-TC02":(8,"BBB+"),"R6-TC03":(11,"BB+"),"R6-TC04":(4,"AA-"),"R6-TC05":(8,"BBB+"),"R6-TC06":(9,"BBB"),"R6-TC07":(3,"AA"),"R6-TC08":(9,"BBB"),"R6-TC09":"UNRATED"}
for t in json.load(open("data/golden/R6_golden.json"))["test_cases"]:
    got = sel(t["test_data"])
    if got != exp6[t["id"]]: fail(f"{t['id']} got {got}")
print("TOTAL golden tests:", total)
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
raise SystemExit(0 if ok else 1)
