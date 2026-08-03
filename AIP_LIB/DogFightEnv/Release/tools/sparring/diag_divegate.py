"""에너지 회복 강하 게이트의 셀별 발동 빈도 — 재빌드 없이 잰다.

diag 10판 격자에서 EP28이 v7.1보다 6셀 전부 나빴다:
  alt_split_high 18.76 -> 3.81 | energy_up 13.21 -> 7.46 | off_outside_tc 9.70 -> 2.20
  floor_fight     7.23 -> 4.00 | alt_split_low 6.41 -> 1.27 | off_inside_tc 5.02 -> 4.83

그런데 alt_split_high는 **내가 명백히 에너지 우위로 시작**하므로 EP28 게이트
(EnergyAdvantage_M < 0)가 억제했어야 한다. 억제가 안 됐다는 뜻이고, 가설이 어긋난다.

게이트 조건을 BT 디버그 스칼라로 **그대로 재구성**해서 셀별 발동 비율을 센다.
(A-1 대조검증에서 bt_cas_kt / bt_my_z / bt_energy_adv 모두 독립계산과 일치 확인됨)

  energyDive = (1 < CAS < 350) && (내고도 - 304.8 > 3000) && (EnergyAdvantage < 0)

메모리 규칙: "검증 전에 이 조건이 각 국면에서 몇 % 발동하는가를 먼저 재라."

실행: python tools/sparring/diag_divegate.py [셀당판수]
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
from tools.sparring import scenarios as SC  # noqa: E402

PER = int(sys.argv[1]) if len(sys.argv) > 1 else 6
CAS_T = 350.0
MARGIN = 3000.0
KNOCK = 304.8

CELLS = ["off_outside_tc", "off_inside_tc", "energy_up", "floor_fight",
         "alt_split_high", "alt_split_low", "beam_slow", "beam_fast", "head_on"]


def cell_ic(name, rng):
    fn = getattr(SC, "cell_" + name)
    return fn(rng)


print(f"강하 게이트 발동 빈도 — 셀당 {PER}판 (EP28 적용본)")
print(f"게이트: 1 < CAS < {CAS_T:.0f}kt  AND  고도-{KNOCK:.0f} > {MARGIN:.0f}m  AND  EnergyAdv < 0\n")
print(f"  {'셀':<18}{'발동%':>8}{'CAS<350%':>10}{'고도여유%':>11}{'Es열세%':>10}"
      f"{'CAS중앙':>9}{'Es차중앙':>10}")

runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                     SideSpec("AIP_jegalmin.dll", None, "jegalmin"))
rows: list[dict] = []
runner.tick_sink = lambda i, d: rows.append(d)
try:
    for cname in CELLS:
        acc = []
        for i in range(PER):
            seed = 60_000 + hash(cname) % 1000 * 10 + i
            rng = np.random.default_rng(seed)
            try:
                ic = cell_ic(cname, rng)
            except Exception as e:
                print(f"  {cname:<18} 시나리오 생성 실패: {e}")
                acc = None
                break
            rows.clear()
            runner.run_match(i, seed, ic)
            bt = [r["bt"] for r in rows if r.get("bt")]
            if not bt:
                continue
            cas = np.array([b.get("bt_cas_kt", np.nan) for b in bt])
            myz = np.array([b.get("bt_my_z", np.nan) for b in bt])
            adv = np.array([b.get("bt_energy_adv", np.nan) for b in bt])
            ok = np.isfinite(cas) & np.isfinite(myz) & np.isfinite(adv)
            cas, myz, adv = cas[ok], myz[ok], adv[ok]
            if cas.size == 0:
                continue
            c1 = (cas > 1.0) & (cas < CAS_T)
            c2 = (myz - KNOCK) > MARGIN
            c3 = adv < 0.0
            acc.append((100 * (c1 & c2 & c3).mean(), 100 * c1.mean(),
                        100 * c2.mean(), 100 * c3.mean(),
                        float(np.median(cas)), float(np.median(adv))))
        if not acc:
            continue
        a = np.array(acc)
        print(f"  {cname:<18}{a[:,0].mean():8.1f}{a[:,1].mean():10.1f}"
              f"{a[:,2].mean():11.1f}{a[:,3].mean():10.1f}"
              f"{a[:,4].mean():9.0f}{a[:,5].mean():10.0f}")
finally:
    runner.close()

print("\n해석: 우위 셀(energy_up / alt_split_high)에서 발동%가 높으면 게이트가 못 막고 있다.")
print("      어느 조건이 안 걸러내는지는 오른쪽 세 열(각 조건의 개별 충족률)로 알 수 있다.")
