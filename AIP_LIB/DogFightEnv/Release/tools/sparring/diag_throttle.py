"""스로틀 낭비 진단 — 코너 미만인데 스로틀을 죽이고 있는 시간이 얼마나 되는가.

EP24 이후 vs jegalmin 비에너지 추이:
  내  7,132 -> 5,914  (잃는다)
  적  7,739 -> 8,560  (얻는다)
같은 F-16인데 한쪽만 에너지를 잃는다. 150-200s에 CAS 337 vs 518kt, Nz 4.32 vs 6.85G.

용의자: `CornerHoldThrottle`이 **TAS 기준**이다.
  if (speedMs > 230) return 0.25;  if (speedMs < 185) return 1.0;  return 0.55;
고도 3,735m(밀도비 0.845)에서 CAS 337kt = TAS 205 m/s -> **0.55**를 반환한다.
A-4 실측 코너는 CAS 350kt다. **코너 아래인데 스로틀을 절반으로 죽인다.**

EP21이 이 임계값을 CAS로 옮겼다가 참패했다(btjegal 승 27->8). 실패 원인은
"고도 적응성 때문에 저고도에서 훨씬 자주 감속이 걸린 것"으로 추정했다.
그러니 이번엔 임계값을 옮기지 말고 **실제로 얼마나 낭비하는지부터 잰다.**

재는 것:
  · CAS 구간별 내 스로틀 분포 (양쪽 상대)
  · ★ CAS < 350kt인데 스로틀 < 1.0 인 시간 비율 = 남겨둔 에너지
  · 그때 Nz는 얼마인가 (감속이 선회를 위한 것이었나, 그냥 낭비인가)
  · 적의 스로틀과 비교

실행: python tools/sparring/diag_throttle.py [판수]
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
MS_TO_KT = 1.0 / 0.51444
CORNER_KT = 350.0
I_KCAS, I_THR, I_NZ, I_ALT = 12, 21, 31, 44
CAS_BINS = [(0, 200), (200, 250), (250, 300), (300, 350), (350, 400), (400, 999)]


def run(opp: str, tag: str):
    own_all, tgt_all = [], []
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            seed = 50_000 + i
            rows.clear()
            runner.run_match(i, seed, make_ic(seed))
            if rows:
                own_all.append(np.array([r["own_state"] for r in rows]))
                tgt_all.append(np.array([r["tgt_state"] for r in rows]))
    finally:
        runner.close()
    if not own_all:
        return None, None
    return np.vstack(own_all), np.vstack(tgt_all)


def report(tag: str, own, tgt):
    print(f"\n{'='*76}\n{tag}\n{'='*76}")
    if own is None:
        print("  표본 없음")
        return
    cas = own[:, I_KCAS] * MS_TO_KT
    thr = own[:, I_THR]
    nz = np.abs(own[:, I_NZ])
    tcas = tgt[:, I_KCAS] * MS_TO_KT
    tthr = tgt[:, I_THR]

    print(f"  {'CAS 구간(kt)':>14}{'비중%':>8}{'내스로틀':>10}{'내Nz':>8}"
          f"{'스로틀<0.9 비율%':>18}")
    for lo, hi in CAS_BINS:
        m = (cas >= lo) & (cas < hi)
        if m.sum() < 50:
            continue
        print(f"  {lo:6d}-{hi:<7d}{100*m.mean():8.1f}{np.median(thr[m]):10.2f}"
              f"{np.median(nz[m]):8.2f}{100*(thr[m] < 0.9).mean():18.1f}")

    below = cas < CORNER_KT
    waste = below & (thr < 0.9)
    print(f"\n  ★ 코너({CORNER_KT:.0f}kt) 미만 체류 {100*below.mean():5.1f}%")
    print(f"  ★ 그중 스로틀<0.9 = **남겨둔 에너지** {100*waste.sum()/max(below.sum(),1):5.1f}%"
          f"  (전체 시간의 {100*waste.mean():.1f}%)")
    if waste.sum() > 50:
        print(f"     그때 Nz 중앙 {np.median(nz[waste]):.2f}G   스로틀 중앙 {np.median(thr[waste]):.2f}")
    print(f"\n  내  CAS 중앙 {np.median(cas):5.0f}kt  스로틀 중앙 {np.median(thr):.2f}")
    print(f"  적  CAS 중앙 {np.median(tcas):5.0f}kt  스로틀 중앙 {np.median(tthr):.2f}"
          f"   적 코너미만 {100*(tcas < CORNER_KT).mean():.1f}%")


print(f"스로틀 낭비 진단 — {N}판씩, 시드 50000~  (EP24 적용본)")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    o, t = run(dll, tag)
    report(tag, o, t)

print("\n해석: '남겨둔 에너지'가 크고 그때 Nz가 낮으면 = 선회를 위한 감속이 아니라 순수 낭비다.")
