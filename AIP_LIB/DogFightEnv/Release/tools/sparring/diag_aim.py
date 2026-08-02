"""조준 정밀도 진단 — "사거리 안에 있을 때 ATA가 실제로 얼마나 나오는가".

## 왜 이걸 먼저 재는가

회귀 테스트에서 gichan은 SnapShot 572틱 + GunAim 145틱을 쓰면서 공식 WEZ는 0틱이었다.
"쏘고 있다고 믿지만 콘 밖"이라는 뜻인데, 원인이 둘 중 무엇인지에 따라 처방이 완전히 다르다:

  (a) 전술 문제 — 사거리 안에 들어가는 시간 자체가 적다        → TCX/기동 재설계
  (b) 조준 문제 — 사거리 안엔 자주 있는데 ATA가 1°로 안 좁혀진다 → 제어루프/VP 문제

(b)라면 아무리 기동을 고쳐도 점수가 안 난다. 재설계 착수 전에 갈라야 한다.

부수적으로 **판당 wall-clock**도 측정한다(C 스윕 1150판 예산 판단용).

실행: python tools/sparring/diag_aim.py [상대DLL]
"""

from __future__ import annotations

import os
import sys
import time

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

TARGET_DLL = sys.argv[1] if len(sys.argv) > 1 else "AIP_jegalmin.dll"
SEED = 20260802

ticks: list[dict] = []
runner = MatchRunner(
    SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
    SideSpec(TARGET_DLL, None, TARGET_DLL),
    max_engage_time=W.MATCH_DURATION_S,
    tick_sink=lambda i, d: ticks.append(d),
)
t0 = time.perf_counter()
try:
    res = runner.run_match(0, SEED, None)
finally:
    runner.close()
elapsed = time.perf_counter() - t0

print("=" * 68)
print(f"조준 정밀도 진단 — gichan vs {TARGET_DLL}, {W.MATCH_DURATION_S:.0f}초, seed={SEED}")
print("=" * 68)
if res.error:
    print("ERROR:", res.error)
    sys.exit(1)

print(f"결과={res.outcome}  틱={res.ticks}  공식WEZ={res.wez_dealt_ticks}  피격={res.wez_recv_ticks}")
print(f"판당 wall-clock = {elapsed:.1f}초  →  1150판 직렬 추정 {elapsed*1150/3600:.1f}시간")

arr_ata = np.array([t["my_ata"] for t in ticks])
arr_dist = np.array([t["dist"] for t in ticks])
arr_t = np.array([t["t"] for t in ticks])
tasks = np.array([t["task"] for t in ticks])

# Phase별 사거리 마스크 (시간에 따라 사거리 상한이 달라진다)
rmax = np.array([W.phase_at(t).max_range_m for t in arr_t])
cone = np.array([W.phase_at(t).cone_deg for t in arr_t])
in_range = (arr_dist >= 152.4) & (arr_dist <= rmax)

print(f"\n--- (a) 접근: 사거리 안에 있던 시간 ---")
n_in = int(in_range.sum())
print(f"  사거리 내 틱 {n_in} / {len(ticks)}  ({100*n_in/max(len(ticks),1):.1f}%)"
      f"  = {n_in/60:.1f}초")

print(f"\n--- (b) 조준: 사거리 안에 있을 때의 ATA 분포 ---")
if n_in == 0:
    print("  사거리에 한 번도 못 들어갔다 → 문제는 (a) 접근이다")
else:
    a = arr_ata[in_range]
    for q in (0, 1, 5, 10, 25, 50):
        print(f"  p{q:<3}= {np.percentile(a, q):7.2f}°")
    print(f"  최소 = {a.min():.3f}°   평균 = {a.mean():.2f}°")
    for thr in (1.0, 2.0, 3.0, 5.0, 10.0, 20.0):
        n = int((a <= thr).sum())
        print(f"  ATA<={thr:4.1f}° 인 틱: {n:5d}  ({100*n/n_in:5.1f}% of 사거리내, {n/60:.2f}초)")
    hit = int((arr_ata[in_range] <= cone[in_range]).sum())
    print(f"  ★ 해당 Phase 콘 안: {hit}틱")

print(f"\n--- 사격 상태(SnapShot/GunAim)일 때 실제 기하 ---")
gun = np.isin(tasks, ["SnapShot", "GunAim"])
print(f"  사격상태 틱 {int(gun.sum())} ({100*gun.mean():.1f}%)")
if gun.any():
    print(f"  그 중 사거리 내      : {int((gun & in_range).sum())}틱")
    print(f"  그 때 ATA 중앙값     : {np.median(arr_ata[gun]):.2f}°")
    print(f"  그 때 거리 중앙값    : {np.median(arr_dist[gun]):.0f}m")

print(f"\n--- ★ 상태 전환 시점의 실제 기하 (BT가 보는 값 vs 실제) ---")
# SnapShot/GunAim은 히스테리시스가 없어 조건이 참이 된 그 틱에 바로 들어간다.
# 따라서 전환 틱의 실제 기하 = BT 조건이 만족됐다고 판단한 순간의 진짜 값이다.
#   SnapShot 조건: bb->Distance < rMax*1.15 (Phase1=1051m)  AND  bb->Los_Degree < 40
#   GunAim  조건: bb->Distance < rMax*1.50 (Phase1=1372m)  AND  bb->Los_Degree < 22
for name, d_thr, a_thr in (("SnapShot", 1.15, 40.0), ("GunAim", 1.50, 22.0)):
    entries = [i for i in range(1, len(tasks)) if tasks[i] == name and tasks[i - 1] != name]
    if not entries:
        print(f"  {name}: 전환 없음")
        continue
    ed = arr_dist[entries]
    ea = arr_ata[entries]
    thr_d = np.array([W.phase_at(arr_t[i]).max_range_m * d_thr for i in entries])
    print(f"  {name} 진입 {len(entries)}회")
    print(f"    BT 임계 거리 {thr_d.mean():7.0f}m  ← 실제 거리 중앙값 {np.median(ed):7.0f}m"
          f"  (배율 {np.median(ed)/thr_d.mean():.2f}x)")
    print(f"    BT 임계 ATA  {a_thr:7.1f}°  ← 실제 ATA  중앙값 {np.median(ea):7.1f}°"
          f"  (배율 {np.median(ea)/a_thr:.2f}x)")

print(f"\n--- 전술 체류 ---")
for name, cnt in sorted(res.task_hist.items(), key=lambda x: -x[1]):
    print(f"  {name:<14} {cnt:5d}틱 ({100*cnt/max(res.ticks,1):5.1f}%)")

print(f"\n--- 안전/교착 ---")
print(f"  최저고도 {res.min_own_alt_m:.0f}m (여유 {res.min_alt_margin_m:+.0f}m)"
      f"  600m미만 {res.ticks_below_600m}틱")
print(f"  교착 최장구간 {res.stalemate_ticks}틱 ({res.stalemate_ticks/60:.1f}초)")
print(f"  최소거리 {res.min_distance_m:.0f}m")

print("\n" + "=" * 68)
print("판정 기준: 사거리 내 비율이 낮으면 (a)접근 문제 / 사거리엔 있는데")
print("           ATA가 1° 근처로 안 내려가면 (b)조준(제어) 문제")
