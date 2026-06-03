#!/usr/bin/env python3
"""Hardened benchmark for CASE camera-ready (citable planning times).

Per variant: generation time (median of 5), then 5 solve repetitions capturing
both Python wall-clock AND Fast Downward's internal search/total times parsed
from UPF log_messages. Reports median, min, max. Optimality certified via
MinimizeSequentialPlanLength (status should be SOLVED_OPTIMALLY).

Run from AAS2PDDL_Clean/. Writes bench_results_v2.md / .json. Output is line-
buffered with flush so background progress is visible.
"""
import sys, time, json, io, contextlib, statistics, re
from pathlib import Path

sys.path.insert(0, "src")
from unified_planning.shortcuts import get_environment, OneshotPlanner
from unified_planning.model.metrics import MinimizeSequentialPlanLength
from aas_loader import AASLoader
from aas_extractor import AASExtractor
from pddl_builder import UPFProblemBuilder

env = get_environment()
env.credits_stream = None

BASE = Path("examples/mps500")
VARIANTS = [
    ("base",      BASE / "aasx"),
    ("variant_a", BASE / "aasx_variant_a"),
    ("variant_b", BASE / "aasx_variant_b"),
    ("variant_c", BASE / "aasx_variant_c"),
    ("variant_d", BASE / "aasx_variant_d"),
]
GEN_REPEAT = 5
SOLVE_REPEAT = 5

RE_SEARCH = re.compile(r"\bSearch time:\s*([\d.]+)s")
RE_TOTAL = re.compile(r"\bTotal time:\s*([\d.]+)s")


def build(input_dir, name):
    with contextlib.redirect_stdout(io.StringIO()):
        loader = AASLoader(Path(input_dir), domainName=name)
        loader.load()
        ex = AASExtractor(loader)
        b = UPFProblemBuilder(loader.domainName)
        b.buildTypes(ex.extractTypeHierarchy())
        b.buildFluents(ex.extractDataElementTypes())
        b.buildActions(ex.extractProcessOperators())
        b.buildObjects(ex.extractInstances())
        ini, g = ex.extractInitialStatesAndGoals()
        b.buildInit(ini); b.buildGoals(g)
    b.problem.add_quality_metric(MinimizeSequentialPlanLength())
    return b


def parse_fd_times(result):
    txt = "\n".join(m.message for m in (result.log_messages or []))
    s = RE_SEARCH.findall(txt)
    t = RE_TOTAL.findall(txt)
    return (float(s[-1]) if s else None, float(t[-1]) if t else None)


def solve_once(problem):
    t0 = time.perf_counter()
    with OneshotPlanner(name="fast-downward-opt") as pl:
        with contextlib.redirect_stdout(io.StringIO()):
            r = pl.solve(problem)
    wall = time.perf_counter() - t0
    fd_search, fd_total = parse_fd_times(r)
    length = len(r.plan.actions) if r.plan else 0
    return wall, fd_search, fd_total, length, str(r.status).split(".")[-1]


def summ(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"median": round(statistics.median(xs), 2),
            "min": round(min(xs), 2), "max": round(max(xs), 2)}


def main():
    print(f"GEN_REPEAT={GEN_REPEAT} SOLVE_REPEAT={SOLVE_REPEAT}", flush=True)
    rows = []
    for name, d in VARIANTS:
        if not Path(d).exists():
            print(f"[skip] {d} missing", flush=True); continue
        gts = []
        for _ in range(GEN_REPEAT):
            t0 = time.perf_counter(); b = build(d, name); gts.append(time.perf_counter() - t0)
        gen_med = round(statistics.median(gts), 3)

        walls, searches, totals, lengths, statuses = [], [], [], [], []
        for i in range(SOLVE_REPEAT):
            w, fs, ft, ln, st = solve_once(b.problem)
            walls.append(w); searches.append(fs); totals.append(ft)
            lengths.append(ln); statuses.append(st)
            print(f"  {name} run{i+1}: wall={w:.2f}s fd_search={fs}s steps={ln} {st}", flush=True)

        row = {
            "name": name, "gen_time_s": gen_med,
            "plan_length": lengths[0],
            "lengths_consistent": len(set(lengths)) == 1,
            "status": statuses[0],
            "wall_s": summ(walls),
            "fd_search_s": summ(searches),
            "fd_total_s": summ(totals),
        }
        rows.append(row)
        ws, fss = summ(walls), summ(searches)
        print(f"== {name}: gen={gen_med}s  wall median={ws['median']}s [{ws['min']}-{ws['max']}]  "
              f"fd_search median={fss['median'] if fss else 'n/a'}s  steps={lengths[0]}  {statuses[0]}", flush=True)

    Path("bench_results_v2.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    md = ["| Variant | Gen (s) | Steps | Status | FD search median (s) | FD search [min-max] | Wall median (s) |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        fs, w = r["fd_search_s"], r["wall_s"]
        fs_med = fs["median"] if fs else "n/a"
        fs_range = f"{fs['min']}-{fs['max']}" if fs else "n/a"
        md.append(f"| {r['name']} | {r['gen_time_s']} | {r['plan_length']} | {r['status']} | "
                  f"{fs_med} | {fs_range} | {w['median']} |")
    Path("bench_results_v2.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\nWrote bench_results_v2.json / .md", flush=True)


if __name__ == "__main__":
    main()
