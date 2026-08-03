"""초반 국면 진단 — 예선은 497m에서 시작한다(이미 WEZ 사거리 안).

예선 실측: 거리 497m, 고도 4,572m, 헤딩 ±90°(분리축과 수직), ATA 91°.
WEZ 사거리가 152~914m이므로 **시작하자마자 사거리 안**이다. ATA만 91°에서
1°로 줄이면 즉시 데미지다. 첫 패스가 가장 가까운 기회일 수 있다.

첫 20초를 초 단위로 뜯어 두 상대에서 무엇이 갈리는지 본다.

실행: python tools/sparring/diag_opening.py [판수]
"""

from __future__ import annotations

import os
import sys

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_RELEASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _RELEASE)
sys.path.insert(0, os.path.join(_RELEASE, "src"))
os.chdir(_RELEASE)

from tools.sparring.runner import MatchRunner, SideSpec  # noqa: E402
from tools.sparring.scenarios import make_ic  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
WINDOW = 20.0   # 초


def run(opp: str, tag: str):
    per_match = []
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            seed = 50_000 + i
            rows.clear()
            r = runner.run_match(i, seed, make_ic(seed))
            per_match.append((r, [dict(x) for x in rows if x["t"] <= WINDOW]))
    finally:
        runner.close()
    return per_match


def report(tag: str, data):
    print(f"\n{'='*70}\n{tag}\n{'='*70}")
    print(f"  {'t(초)':>6}{'거리(m)':>10}{'내ATA':>9}{'적ATA':>9}{'내속도':>9}{'주요 Task':>16}")
    # 첫 판을 초 단위로
    _, ticks = data[0]
    for sec in range(0, int(WINDOW) + 1, 2):
        near = [t for t in ticks if abs(t["t"] - sec) < 0.02]
        if not near:
            continue
        t = near[0]
        print(f"  {t['t']:6.1f}{t['dist']:10.0f}{t['my_ata']:9.1f}{t['en_ata']:9.1f}"
              f"{t['own_spd']:9.1f}{t['task']:>16}")

    # 전 판 집계
    allt = [t for _, ticks in data for t in ticks]
    d = np.array([t["dist"] for t in allt])
    a = np.array([t["my_ata"] for t in allt])
    inr = (d >= 152.4) & (d <= 914.4)
    print(f"\n  --- 첫 {WINDOW:.0f}초 집계 ({len(data)}판) ---")
    print(f"  사거리 내 비율 {100*inr.mean():5.1f}%   최소거리 {d.min():5.0f}m")
    if inr.sum():
        print(f"  사거리 내 ATA: 중앙 {np.median(a[inr]):5.1f}°  최소 {a[inr].min():5.2f}°"
              f"  <10° {100*(a[inr]<10).mean():4.1f}%")
    # 이 구간에서 실제로 쏜 틱
    early = sum(1 for t in allt if t["my_ata"] <= 1.0 and 152.4 <= t["dist"] <= 914.4)
    print(f"  ★ 첫 {WINDOW:.0f}초 WEZ(1°콘) 틱: {early}")


print(f"초반 국면 진단 — 첫 {WINDOW:.0f}초, {N}판씩 (시드 50000~)")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal"), ("AIP_jegalmin.dll", "vs jegalmin")):
    report(tag, run(dll, tag))
