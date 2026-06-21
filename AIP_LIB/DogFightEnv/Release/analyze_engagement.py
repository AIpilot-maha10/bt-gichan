"""Post-fight engagement CSV analyzer.

Usage:
    python analyze_engagement.py engagement_logs/engage_gichan_20260620_150000.csv
    python analyze_engagement.py engagement_logs/  # analyzes most recent CSV in dir
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


KNOCKOUT_ALT_M = 304.8


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_f(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _format_tasks(counts: dict, seq: list, n: int) -> str:
    if not counts:
        return ""
    lines = ["\n  STRATEGY (Task별 체류시간)"]
    for name, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {name:18s}: {cnt:>5} ({cnt / n * 100:.1f}%)")
    # 전환 시퀀스는 너무 길면 축약
    seq_str = " -> ".join(seq[:25]) + (" ..." if len(seq) > 25 else "")
    lines.append(f"    전환순서: {seq_str}")
    return "\n".join(lines)


def analyze(rows: list[dict], label: str = ""):
    n = len(rows)
    if n == 0:
        print("Empty CSV.")
        return

    cum_dealt = sum(to_f(r["dmg_dealt"]) for r in rows)
    cum_recv = sum(to_f(r["dmg_received"]) for r in rows)
    duration = to_f(rows[-1]["elapsed_sec"])

    dists = [to_f(r["distance"]) for r in rows]
    own_alts = [to_f(r["own_z"]) for r in rows]
    own_spds = [to_f(r["own_speed"]) for r in rows]
    atas = [to_f(r["ata_deg"]) for r in rows]
    aas = [to_f(r["aa_deg"]) for r in rows]
    enemy_alts = [to_f(r["enemy_z"]) for r in rows]

    p1 = sum(1 for r in rows if r.get("phase_active") == "Phase1")
    p2 = sum(1 for r in rows if r.get("phase_active") == "Phase2")
    p3 = sum(1 for r in rows if r.get("phase_active") == "Phase3")

    # Task(전략)별 체류시간 + 전환 시퀀스
    task_counts: dict[str, int] = {}
    task_seq: list[str] = []
    for r in rows:
        t = r.get("task") or ""
        if t:
            task_counts[t] = task_counts.get(t, 0) + 1
            if not task_seq or task_seq[-1] != t:
                task_seq.append(t)
    own_ko = sum(1 for a in own_alts if a < KNOCKOUT_ALT_M)
    enemy_ko = sum(1 for a in enemy_alts if a < KNOCKOUT_ALT_M)

    if cum_dealt > cum_recv:
        result = "WIN"
    elif cum_recv > cum_dealt:
        result = "LOSS"
    else:
        result = "DRAW"

    # Time-segment analysis (split into 4 quarters)
    seg_size = max(n // 4, 1)
    segments = []
    for i in range(4):
        start = i * seg_size
        end = min(start + seg_size, n) if i < 3 else n
        seg = rows[start:end]
        if not seg:
            continue
        seg_dealt = sum(to_f(r["dmg_dealt"]) for r in seg)
        seg_recv = sum(to_f(r["dmg_received"]) for r in seg)
        seg_avg_dist = sum(to_f(r["distance"]) for r in seg) / len(seg)
        seg_avg_ata = sum(to_f(r["ata_deg"]) for r in seg) / len(seg)
        seg_t0 = to_f(seg[0]["elapsed_sec"])
        seg_t1 = to_f(seg[-1]["elapsed_sec"])
        segments.append((seg_t0, seg_t1, seg_dealt, seg_recv, seg_avg_dist, seg_avg_ata))

    ratio = cum_dealt / max(cum_recv, 0.001)

    print(f"""
{'=' * 60}
  ENGAGEMENT ANALYSIS  {label}
{'=' * 60}
  Duration:        {duration:.1f}s  ({n} ticks)
  Result:          {result}

  DAMAGE
    Dealt:         {cum_dealt:.2f}
    Received:      {cum_recv:.2f}
    Ratio:         {ratio:.2f}x

  PHASE WEZ TICKS
    Phase1 (x1.0): {p1:>5}  ({p1/n*100:.1f}%)
    Phase2 (x0.3): {p2:>5}  ({p2/n*100:.1f}%)
    Phase3 (x0.1): {p3:>5}  ({p3/n*100:.1f}%)
    Outside WEZ:   {n-p1-p2-p3:>5}  ({(n-p1-p2-p3)/n*100:.1f}%)

  DISTANCE (m)
    Avg: {sum(dists)/n:.0f}   Min: {min(dists):.0f}   Max: {max(dists):.0f}

  ALTITUDE (m)
    Own   Avg: {sum(own_alts)/n:.0f}   Min: {min(own_alts):.0f}
    Enemy Avg: {sum(enemy_alts)/n:.0f}   Min: {min(enemy_alts):.0f}

  SPEED (m/s)
    Avg: {sum(own_spds)/n:.0f}   Min: {min(own_spds):.0f}   Max: {max(own_spds):.0f}

  ANGLES (deg)
    ATA  Avg: {sum(atas)/n:.1f}   Min: {min(atas):.1f}
    AA   Avg: {sum(aas)/n:.1f}   Min: {min(aas):.1f}

  SAFETY
    Own alt violations (<{KNOCKOUT_ALT_M:.0f}m):   {own_ko} ticks
    Enemy alt violations:  {enemy_ko} ticks
{_format_tasks(task_counts, task_seq, n)}
  TIME SEGMENTS
    {'Period':>12s}  {'Dealt':>7s}  {'Recv':>7s}  {'AvgDist':>8s}  {'AvgATA':>7s}""")

    for seg_t0, seg_t1, d, r, ad, aa in segments:
        print(f"    {seg_t0:5.1f}-{seg_t1:5.1f}s  {d:7.2f}  {r:7.2f}  {ad:8.0f}m  {aa:7.1f}°")

    print(f"""
  TACTICAL NOTES""")
    if p1 == 0:
        print("    ⚠ Never entered Phase1 WEZ (LOS<1°, 152-914m) — work on nose tracking")
    if ratio < 0.5:
        print("    ⚠ Getting significantly more damage than dealing — consider defensive improvements")
    if min(own_alts) < KNOCKOUT_ALT_M:
        print(f"    ⚠ Hit knockout altitude zone ({min(own_alts):.0f}m < {KNOCKOUT_ALT_M:.0f}m)")
    if sum(atas) / n > 45:
        print("    ⚠ Average ATA > 45° — nose is rarely pointing at target")
    if sum(dists) / n > 3000:
        print("    ⚠ Average distance > 3km — too far for effective engagement")
    if ratio > 2.0 and p1 > 10:
        print("    ✓ Strong Phase1 presence with good damage ratio")
    if own_ko == 0 and min(own_alts) > 400:
        print("    ✓ Good altitude discipline")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Analyze engagement CSV log")
    parser.add_argument("path", help="CSV file or directory (uses most recent)")
    args = parser.parse_args()

    p = Path(args.path)
    if p.is_dir():
        csvs = sorted(p.glob("engage_*.csv"), key=lambda f: f.stat().st_mtime)
        if not csvs:
            print(f"No engagement CSVs found in {p}")
            sys.exit(1)
        p = csvs[-1]
        print(f"Analyzing most recent: {p.name}")

    rows = load_csv(p)
    analyze(rows, label=p.stem)


if __name__ == "__main__":
    main()
