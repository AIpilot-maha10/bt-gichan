"""에너지 고갈 진단 — "얼마나 오래 느린가, 언제 그렇게 되는가".

## 왜

베이스라인 30판(vs jegalmin)에서 최저속도 중앙값이 **54.9 m/s TAS**(107kt)였고
**29/30판**이 100 m/s 아래로 떨어졌다. F-16 실속속도(~130~150kt) 한참 아래다.

다만 "최저속도"는 판 전체의 **한 순간**이라 두 가지가 구분이 안 된다:
  (a) 순간적으로 한 번 훅 떨어졌다 회복  → 큰 문제 아님
  (b) 상당 시간을 실속권에서 허우적댄다 → 이게 WEZ 0틱의 근본 원인

체류시간과 발생 국면(어떤 Task 중인가)을 재서 가른다.

## 기준

A-4 실측: 최대 선회율은 **KCAS 180~190 m/s(350kt)**. 그래서 CAS 기준으로 구간을 나눈다.
  - CAS < 60 m/s (117kt)  : 실속권. 조종면이 거의 안 듣는다
  - CAS < 90 m/s (175kt)  : 심각한 저에너지
  - CAS < 185 m/s (360kt) : 코너 미만 = 최대 선회율을 못 낸다

실행: python tools/sparring/diag_energy.py [판수] [상대DLL]
"""

from __future__ import annotations

import os
import sys
from collections import Counter

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

from tools.sparring import wez as W  # noqa: E402
from tools.sparring.runner import MatchRunner, SideSpec  # noqa: E402
from tools.sparring.scenarios import make_ic  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
TGT = sys.argv[2] if len(sys.argv) > 2 else "AIP_jegalmin.dll"
KT = 0.51444
IDX_KCAS, IDX_KTAS, IDX_NZ = 12, 27, 31

CORNER_CAS = 185.0   # A-4 실측
SLOW_CAS = 90.0
STALL_CAS = 60.0


def longest_run(mask: np.ndarray) -> int:
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


print("=" * 74)
print(f"에너지 고갈 진단 — gichan vs {TGT}, {N}판 × 200초")
print("=" * 74)

per_match = []
tasks_slow: Counter = Counter()
tasks_all: Counter = Counter()
track: list = []


def sink(i: int, d: dict) -> None:
    s = d["own_state"]
    track.append((float(s[IDX_KCAS]), float(s[IDX_KTAS]), float(s[IDX_NZ]),
                  float(s[W.IDX_ALT]), d["task"], float(s[W.IDX_SIM_TIME]),
                  d["own_energy"], d["dist"], d["my_ata"]))


runner = MatchRunner(
    SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
    SideSpec(TGT, None, "opp"),
    max_engage_time=W.MATCH_DURATION_S,
    tick_sink=sink,
)
try:
    for i in range(N):
        seed = 10_000 + i          # 베이스라인과 같은 시드
        track.clear()
        r = runner.run_match(i, seed, make_ic(seed))
        if not track:
            continue
        cas = np.array([t[0] for t in track])
        tsk = [t[4] for t in track]
        n = len(cas)
        below_corner = cas < CORNER_CAS
        slow = cas < SLOW_CAS
        stall = cas < STALL_CAS
        per_match.append((seed, r.family, n,
                          below_corner.mean(), slow.mean(), stall.mean(),
                          longest_run(slow) / 60.0, cas.min(),
                          r.wez_dealt_ticks))
        tasks_all.update(tsk)
        tasks_slow.update([t for t, m in zip(tsk, slow) if m])
        print(f"  [{i}] seed={seed} {r.family:<12} 코너미만 {100*below_corner.mean():5.1f}%"
              f"  저속<90 {100*slow.mean():5.1f}%  실속<60 {100*stall.mean():5.1f}%"
              f"  최장저속 {longest_run(slow)/60.0:5.1f}s  minCAS {cas.min():5.1f}", flush=True)
finally:
    runner.close()

arr = per_match
print("\n" + "=" * 74)
print(f"{N}판 종합")
print("=" * 74)
print(f"  코너속도(CAS 185) 미만 체류 : 평균 {100*np.mean([a[3] for a in arr]):5.1f}% "
      f"= {200*np.mean([a[3] for a in arr]):5.1f}초/판")
print(f"  저속(CAS 90) 미만 체류      : 평균 {100*np.mean([a[4] for a in arr]):5.1f}% "
      f"= {200*np.mean([a[4] for a in arr]):5.1f}초/판")
print(f"  실속권(CAS 60) 미만 체류    : 평균 {100*np.mean([a[5] for a in arr]):5.1f}% "
      f"= {200*np.mean([a[5] for a in arr]):5.1f}초/판")
print(f"  최장 연속 저속 구간         : 평균 {np.mean([a[6] for a in arr]):5.1f}s  "
      f"최대 {np.max([a[6] for a in arr]):5.1f}s")
print(f"  최저 CAS                    : 중앙 {np.median([a[7] for a in arr]):5.1f} m/s "
      f"({np.median([a[7] for a in arr])/KT:.0f} kt)")

print("\n--- 저속(CAS<90) 상태일 때 무슨 Task를 하고 있었나 ---")
tot_slow = sum(tasks_slow.values()) or 1
tot_all = sum(tasks_all.values()) or 1
print(f"  {'Task':<16}{'저속중 비율':>12}{'전체 비율':>11}{'과대표현':>10}")
for t, c in tasks_slow.most_common(8):
    share_slow = c / tot_slow
    share_all = tasks_all[t] / tot_all
    ratio = share_slow / share_all if share_all > 0 else 0
    flag = " ★" if ratio > 1.3 else ""
    print(f"  {t:<16}{100*share_slow:11.1f}%{100*share_all:10.1f}%{ratio:9.2f}x{flag}")

print("\n" + "=" * 74)
print("판정")
print("=" * 74)
slow_pct = 100 * np.mean([a[4] for a in arr])
if slow_pct > 15:
    print(f"→ ★ 저속 체류가 {slow_pct:.0f}%다. 순간적 사고가 아니라 **만성적 에너지 고갈**이다.")
    print("   코너속도 아래에서 계속 당기다 속도가 붕괴하는 죽음의 나선.")
elif slow_pct > 3:
    print(f"→ 저속 체류 {slow_pct:.0f}%. 무시할 수준은 아니다.")
else:
    print(f"→ 저속 체류 {slow_pct:.0f}%. 순간적 현상. 최저속도만 보고 과잉해석할 뻔했다.")
print(f"\n참고: 코너 미만 체류가 {100*np.mean([a[3] for a in arr]):.0f}%라면,")
print("      그 시간 동안은 최대 선회율을 못 내고 있다는 뜻이다.")
