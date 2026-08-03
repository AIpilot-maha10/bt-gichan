"""헛당김 진단 — 고G인데 LOSR 진전이 없는 시간이 얼마나 되는가.

교범 §4.6.3.1.11:
  *"풀스로틀 + 최대당김인데 LOSR 진전이 없으면 → 멈추고 에너지를 회복하라
    (adequate radial G is not available)"*
교범 §4.6.3.1.5:
  *"선회는 최대 G가 아니라 airspeed sustaining feel로 — 5G로 잡고 속도가 유지되는
    수준까지 낮춘다"*

diag_leadturn에서 **양측 모두 머지 전 25초 내내 고G**로 나왔다(내가 vs jegalmin
12/12판, vs btjegal 5/12판). 언로드를 아무도 안 하니 "리드턴 시점"이 아예 없다.
그런데 **이기는 상대(5/12)와 못 이기는 상대(12/12)에서 내 행동이 갈린다.**

그래서 재는 것: **당기고 있는데 각도를 못 벌고 있는 시간**.
이게 크면 Ease/TCX(계획 A-2b)를 넣을 근거가 된다 — 교리 복사가 아니라 실측 근거로.

지표는 A-1에서 만든 BT 내부값을 쓴다(diag_btmetrics로 독립검증 완료).

실행: python tools/sparring/diag_wastedpull.py [판수]
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
PULL_G = 4.0        # 이 위면 "당기는 중"
LOSR_DEAD = 2.0     # |LOSR|가 이 아래면 "각도 진전 없음" (deg/s)
CORNER_KT = 350.0   # A-4 실측 코너속도


def run(opp: str) -> list[dict]:
    per: list[dict] = []
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, "opp"),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            seed = 50_000 + i
            rows.clear()
            r = runner.run_match(i, seed, make_ic(seed))
            bt = [x["bt"] for x in rows if x.get("bt")]
            if not bt:
                continue
            nz = np.array([b.get("bt_nz_est", np.nan) for b in bt])
            losr = np.array([b.get("bt_losr", np.nan) for b in bt])
            cas = np.array([b.get("bt_cas_kt", np.nan) for b in bt])
            ok = np.isfinite(nz) & np.isfinite(losr) & np.isfinite(cas)
            nz, losr, cas = nz[ok], losr[ok], cas[ok]
            if nz.size == 0:
                continue
            pulling = nz >= PULL_G
            dead = np.abs(losr) < LOSR_DEAD
            per.append({
                "seed": seed,
                "outcome": r.outcome,
                "tgt_health": r.tgt_health_final,
                "pull_pct": 100.0 * pulling.mean(),
                # ★ 핵심: 당기는데 각도를 못 버는 시간
                "wasted_pct": 100.0 * (pulling & dead).mean(),
                # 당기는 시간 중 헛당김 비율
                "wasted_of_pull": 100.0 * (pulling & dead).sum() / max(pulling.sum(), 1),
                "cas_med": float(np.median(cas)),
                "cas_below_corner": 100.0 * (cas < CORNER_KT).mean(),
                "nz_med": float(np.median(nz)),
                "losr_absmed": float(np.median(np.abs(losr))),
            })
    finally:
        runner.close()
    return per


def report(tag: str, d: list[dict]):
    print(f"\n{'='*78}\n{tag}  ({len(d)}판)\n{'='*78}")
    if not d:
        print("  표본 없음")
        return
    print(f"  {'시드':>6}{'결과':>9}{'적체력':>8}{'당김%':>8}{'헛당김%':>9}"
          f"{'당김중헛':>9}{'CAS중앙':>9}{'코너미만%':>10}")
    for a in d:
        print(f"  {a['seed']:>6}{a['outcome']:>9}{a['tgt_health']:8.3f}"
              f"{a['pull_pct']:8.1f}{a['wasted_pct']:9.1f}{a['wasted_of_pull']:9.1f}"
              f"{a['cas_med']:9.1f}{a['cas_below_corner']:10.1f}")

    def m(k):
        return float(np.mean([a[k] for a in d]))
    print(f"\n  평균: 당김 {m('pull_pct'):.1f}%   ★헛당김 {m('wasted_pct'):.1f}%"
          f"   (당김 시간 중 {m('wasted_of_pull'):.1f}%가 헛당김)")
    print(f"        CAS 중앙 {m('cas_med'):.0f}kt   코너({CORNER_KT:.0f}kt) 미만 "
          f"{m('cas_below_corner'):.1f}%   Nz 중앙 {m('nz_med'):.2f}G"
          f"   |LOSR| 중앙 {m('losr_absmed'):.2f}°/s")


print(f"헛당김 진단 — {N}판씩, 시드 50000~")
print(f"당김 = Nz_est >= {PULL_G}G,  각도진전없음 = |LOSR| < {LOSR_DEAD}°/s")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll))

print("\n해석: 헛당김%가 높으면 = 에너지를 쓰면서 각도를 못 벌고 있다.")
print("      두 상대에서 크게 갈리면 Ease/TCX(A-2b)를 넣을 실측 근거가 된다.")
