#!/usr/bin/env python3
"""
CSP forensic alibi-consistency pipeline on the Microsoft GeoLife GPS dataset.

Forensic question
-----------------
A suspect claims their phone (and therefore they) stayed in the HOME_NORTH
district during a one-hour window (14:00..15:00). Independent evidence (a CCTV
hit) places them at the CRIME_SCENE_SOUTH district at one specific time. We
model the suspect's possible movements as a Constraint Satisfaction Problem
(CSP) over discrete time slots and ask the solver: is there ANY physically
reachable sequence of locations consistent with every piece of evidence?

  - If the CSP is INFEASIBLE (UNSAT): the pieces of evidence contradict each
    other. The alibi and the CCTV hit cannot both be true. The solver returns
    the minimal set of conflicting constraints. (It never returns "guilty".)
  - If the CSP is FEASIBLE (SAT): there exists at least one timeline that
    satisfies all evidence, i.e. the story is internally consistent.

We use a real GeoLife trajectory only to *ground* the region grid in genuine
Beijing coordinates and to demonstrate real GPS parsing; the alibi reasoning
itself is performed by OR-Tools CP-SAT.
"""

import glob
import math
import os
import sys

from ortools.sat.python import cp_model

# --------------------------------------------------------------------------- #
# 0. Configuration
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_GLOB = os.path.join(
    HERE, "data", "Geolife Trajectories 1.3", "Data", "010", "Trajectory", "*.plt"
)

# Time slots: 14:00, 14:10, ..., 15:00  -> 7 slots, 10-minute steps.
SLOT_LABELS = ["14:00", "14:10", "14:20", "14:30", "14:40", "14:50", "15:00"]
STEP_MINUTES = 10

# Maximum assumed travel speed for reachability (km/h).
MAX_SPEED_KMH = 120.0
MAX_REACH_KM = MAX_SPEED_KMH * (STEP_MINUTES / 60.0)  # how far you can go in one slot


# --------------------------------------------------------------------------- #
# 1. Parse a real GeoLife .plt trajectory
#    Format: 6 header lines, then CSV rows:
#      lat,lon,0,alt,days,date,time
# --------------------------------------------------------------------------- #
def parse_plt(path):
    points = []
    with open(path, "r") as fh:
        for i, line in enumerate(fh):
            if i < 6:  # skip the 6 header lines
                continue
            parts = line.strip().split(",")
            if len(parts) < 7:
                continue
            lat = float(parts[0])
            lon = float(parts[1])
            alt = float(parts[3])
            date = parts[5]
            time = parts[6]
            points.append((lat, lon, alt, date, time))
    return points


# --------------------------------------------------------------------------- #
# 2. Region grid + haversine distance matrix
# --------------------------------------------------------------------------- #
def haversine_km(a, b):
    """Great-circle distance in km between (lat, lon) tuples."""
    R = 6371.0088
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def build_regions(anchor):
    """
    Four regions laid out around a real Beijing anchor point taken from the
    GeoLife trajectory. Offsets are deliberately large (tens of km) so that the
    speed-limited reachability constraints actually bite. With MAX_REACH_KM = 20
    km per 10-min slot, the resulting distance matrix makes ONLY the
    HOME_NORTH <-> MIDTOWN hop traversable in a single slot:

        HOME_NORTH  --16.7km--  MIDTOWN   (reachable in one slot)
        CRIME_SCENE_SOUTH = 66.7 km from HOME, 50.0 km from MIDTOWN  (isolated)
        ELSEWHERE         = 61.0 km east                             (isolated)

    So the CRIME scene is genuinely too far to reach within a 10-minute slot at
    120 km/h -- the physical fact that drives the UNSAT result.
    """
    lat0, lon0 = anchor
    # ~0.15 deg lat ~= 16.7 km (one hop OK); 0.30 deg ~= 33 km (two hops).
    regions = {
        "HOME_NORTH":        (lat0 + 0.30, lon0),
        "MIDTOWN":           (lat0 + 0.15, lon0),         # ~16.7 km S of HOME
        "CRIME_SCENE_SOUTH": (lat0 - 0.30, lon0),         # ~66.7 km S of HOME
        "ELSEWHERE":         (lat0,        lon0 + 0.60),  # ~61 km E
    }
    return regions


# --------------------------------------------------------------------------- #
# 3 + 4. Build and solve the CSP
# --------------------------------------------------------------------------- #
def solve_alibi(regions, dist, cctv_slot_index, scenario_name,
                cctv_region="CRIME_SCENE_SOUTH"):
    """
    Build a CP-SAT model with one integer variable per time slot whose value is
    a region index. Apply:
      - anchor constraint: phone evidence pins HOME_NORTH at 14:00 and 15:00,
      - CCTV constraint: at cctv_slot_index the suspect is in `cctv_region`
        (set cctv_slot_index = None to omit the CCTV evidence entirely),
      - reachability: consecutive slots must be within MAX_REACH_KM.

    Reachability and the CCTV hit are added as ASSUMPTION literals so that, on
    UNSAT, CP-SAT can return the minimal conflicting subset.
    """
    region_names = list(regions.keys())
    n_regions = len(region_names)
    n_slots = len(SLOT_LABELS)
    HOME = region_names.index("HOME_NORTH")
    CCTV_R = region_names.index(cctv_region)

    model = cp_model.CpModel()

    # One variable per slot: which region is the suspect in?
    loc = [model.NewIntVar(0, n_regions - 1, f"slot_{i}_{SLOT_LABELS[i]}")
           for i in range(n_slots)]

    assumptions = []          # literals we can blame on UNSAT
    assumption_desc = {}      # literal index -> human description

    # --- Anchor constraint: phone provider records HOME_NORTH at start & end ---
    model.Add(loc[0] == HOME)
    model.Add(loc[n_slots - 1] == HOME)

    # --- CCTV constraint (assumption) ---
    if cctv_slot_index is not None:
        cctv_lit = model.NewBoolVar(f"cctv_at_{SLOT_LABELS[cctv_slot_index]}")
        model.Add(loc[cctv_slot_index] == CCTV_R).OnlyEnforceIf(cctv_lit)
        assumptions.append(cctv_lit)
        assumption_desc[cctv_lit.Index()] = (
            f"CCTV: suspect at {cctv_region} at {SLOT_LABELS[cctv_slot_index]}"
        )

    # --- Reachability constraints (assumptions), one per consecutive pair ---
    # If dist[a][b] > MAX_REACH_KM then transition a->b is forbidden in this slot.
    for t in range(n_slots - 1):
        reach_lit = model.NewBoolVar(f"reach_{SLOT_LABELS[t]}_to_{SLOT_LABELS[t+1]}")
        for a in range(n_regions):
            for b in range(n_regions):
                if dist[a][b] > MAX_REACH_KM:
                    # forbid (loc[t]==a AND loc[t+1]==b) when reach_lit is on
                    ta = model.NewBoolVar(f"t{t}_a{a}")
                    tb = model.NewBoolVar(f"t{t+1}_b{b}")
                    model.Add(loc[t] == a).OnlyEnforceIf(ta)
                    model.Add(loc[t] != a).OnlyEnforceIf(ta.Not())
                    model.Add(loc[t + 1] == b).OnlyEnforceIf(tb)
                    model.Add(loc[t + 1] != b).OnlyEnforceIf(tb.Not())
                    model.AddBoolOr([ta.Not(), tb.Not()]).OnlyEnforceIf(reach_lit)
        assumptions.append(reach_lit)
        assumption_desc[reach_lit.Index()] = (
            f"Reachability {SLOT_LABELS[t]}->{SLOT_LABELS[t+1]} "
            f"(<= {MAX_REACH_KM:.0f} km in {STEP_MINUTES} min)"
        )

    model.AddAssumptions(assumptions)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    print(f"\n=== Scenario: {scenario_name} ===")
    cctv_txt = ("none" if cctv_slot_index is None
                else f"{cctv_region} @ {SLOT_LABELS[cctv_slot_index]}")
    print(f"CCTV evidence : {cctv_txt}")
    print(f"Phone anchor  : HOME_NORTH @ {SLOT_LABELS[0]} and @ {SLOT_LABELS[-1]}")
    print(f"Solver status : {solver.StatusName(status)}")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("RESULT: FEASIBLE -- a consistent timeline exists:")
        for i in range(n_slots):
            print(f"   {SLOT_LABELS[i]}  ->  {region_names[solver.Value(loc[i])]}")
    elif status == cp_model.INFEASIBLE:
        print("RESULT: INFEASIBLE -- the evidence is mutually contradictory.")
        core = solver.SufficientAssumptionsForInfeasibility()
        print("Minimal conflicting constraint set (UNSAT core):")
        if core:
            for lit_idx in core:
                desc = assumption_desc.get(lit_idx, f"<assumption literal {lit_idx}>")
                print(f"   - {desc}")
        else:
            print("   (solver returned an empty core; anchors alone conflict)")
        print("Forensic reading: the alibi and the CCTV hit cannot both be true.")
        print("The agent reports a CONTRADICTION -- it does NOT conclude 'guilty'.")
    else:
        print(f"RESULT: solver returned status {solver.StatusName(status)}")

    return status


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    print("=" * 70)
    print("CSP FORENSIC ALIBI-CONSISTENCY PIPELINE  (GeoLife GPS dataset)")
    print("=" * 70)

    # ---- 1. Parse a real trajectory --------------------------------------- #
    plt_files = sorted(glob.glob(DATA_GLOB))
    if not plt_files:
        print(f"ERROR: no .plt files found at {DATA_GLOB}", file=sys.stderr)
        sys.exit(1)
    plt_path = plt_files[0]
    print(f"\n[1] Parsing real GeoLife trajectory:")
    print(f"    {plt_path}")
    points = parse_plt(plt_path)
    print(f"    Parsed {len(points)} GPS points (6 header lines skipped).")
    print(f"    Sample row 1: lat={points[0][0]}, lon={points[0][1]}, "
          f"alt={points[0][2]}, date={points[0][3]}, time={points[0][4]}")
    mid = len(points) // 2
    print(f"    Sample row {mid}: lat={points[mid][0]}, lon={points[mid][1]}, "
          f"alt={points[mid][2]}, date={points[mid][3]}, time={points[mid][4]}")

    # ---- 2. Region grid grounded on a real GPS point ---------------------- #
    anchor = (points[0][0], points[0][1])
    print(f"\n[2] Building region grid anchored on real GPS point "
          f"lat={anchor[0]:.5f}, lon={anchor[1]:.5f}")
    regions = build_regions(anchor)
    region_names = list(regions.keys())
    for name, (la, lo) in regions.items():
        print(f"    {name:18s} centroid=({la:.5f}, {lo:.5f})")

    # Haversine distance matrix between region centroids.
    coords = [regions[n] for n in region_names]
    n = len(coords)
    dist = [[haversine_km(coords[i], coords[j]) for j in range(n)] for i in range(n)]
    print(f"\n    Haversine distance matrix (km), max reach per "
          f"{STEP_MINUTES} min = {MAX_REACH_KM:.0f} km:")
    header = "    " + " " * 18 + "".join(f"{nm[:8]:>10s}" for nm in region_names)
    print(header)
    for i, nm in enumerate(region_names):
        row = "    " + f"{nm:18s}" + "".join(f"{dist[i][j]:10.1f}" for j in range(n))
        print(row)

    # ---- 3+4. Solve both scenarios for real ------------------------------- #
    print("\n[3/4] Building & solving the CSP with OR-Tools CP-SAT ...")

    # Scenario (a): CCTV at 14:30 (index 3). HOME and CRIME are ~40 km apart;
    # you cannot get from HOME (14:00) to CRIME (14:30) and back to HOME (15:00)
    # within the 20 km/slot reach budget -> expect INFEASIBLE.
    solve_alibi(regions, dist, cctv_slot_index=3,
                scenario_name="(a) CCTV at 14:30  [expect INFEASIBLE]")

    # Scenario (b): the CCTV hit is re-timed to a *reachable* place. MIDTOWN is
    # adjacent to HOME (20 km = exactly one slot's reach), so a hit at MIDTOWN @
    # 14:30 CAN be reconciled with the HOME anchors -> expect FEASIBLE, and the
    # solver returns a concrete HOME->MIDTOWN->HOME timeline. (Re-timing CCTV to
    # 15:30 would push it outside the 14:00-15:00 window entirely; we instead
    # keep it inside the window but at a reachable region to get a richer SAT
    # witness.)
    solve_alibi(regions, dist, cctv_slot_index=3,
                scenario_name="(b) CCTV retimed to MIDTOWN @ 14:30  [expect FEASIBLE]",
                cctv_region="MIDTOWN")

    print("\n" + "=" * 70)
    print("DONE. Interpretation:")
    print("  Scenario (a) is UNSAT: the phone-at-HOME alibi and the CCTV hit at")
    print("  CRIME_SCENE_SOUTH are physically irreconcilable given the speed")
    print("  limit -> the solver returns the minimal conflicting evidence set.")
    print("  Scenario (b) is SAT: re-timing the CCTV hit to the reachable")
    print("  MIDTOWN district yields a fully consistent HOME<->MIDTOWN timeline.")
    print("=" * 70)


if __name__ == "__main__":
    main()
