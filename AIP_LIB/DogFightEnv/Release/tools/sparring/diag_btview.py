"""A-0. BT가 보는 값 vs 실제 기하 — 불일치 원인 확정.

## 왜

Day 1에서 SnapShot이 **실제 3,762m·ATA 98.8°**에서 발동하는 게 관측됐다.
BT 임계는 1,052m·40°다. 배율이 거리 3.4~3.6× / 각도 2.5~3.8×로 **일정하지 않아**
단순 단위 버그가 아니고, `GetWez()`도 미터로 정상임을 코드로 확인했다.

가설이 셋 남았다:
  (ㄱ) `bb->Distance` 산출 경로가 다르다
  (ㄴ) `bb->Los_Degree` 산출 경로가 다르다
  (ㄷ) 좌표 변환(LLA↔Cartesian, Z 부호)에서 위치 자체가 틀어진다

이제 `GetDebugScalars`로 내부값을 직접 읽으므로 **어느 것인지 바로 갈린다.**
위치가 맞는데 거리가 틀리면 (ㄱ), 위치부터 틀리면 (ㄷ).

실행: python tools/sparring/diag_btview.py [판수]
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

from tools.sparring import wez as W  # noqa: E402
from tools.sparring.runner import MatchRunner, SideSpec  # noqa: E402
from tools.sparring.scenarios import make_ic  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
rows: list[dict] = []


def sink(i: int, d: dict) -> None:
    bt = d.get("bt") or {}
    if not bt:
        return
    own, tgt = d["own_state"], d["tgt_state"]
    rows.append({
        "t": d["t"], "task": d["task"],
        "true_dist": d["dist"], "bt_dist": bt["bt_distance"],
        "true_ata": d["my_ata"], "bt_ata": bt["bt_ata"],
        "true_hca": d["hca"], "bt_hca": bt["bt_hca"],
        "true_spd": d["own_spd"], "bt_spd": bt["bt_speed_ms"],
        "bt_rt": bt["bt_running_time"], "sim_t": d["t"],
        "true_n": float(own[0]), "true_e": float(own[1]), "true_d": float(own[2]),
        "bt_x": bt["bt_my_x"], "bt_y": bt["bt_my_y"], "bt_z": bt["bt_my_z"],
        "true_tn": float(tgt[0]), "true_te": float(tgt[1]), "true_td": float(tgt[2]),
        "bt_tx": bt["bt_tgt_x"], "bt_ty": bt["bt_tgt_y"], "bt_tz": bt["bt_tgt_z"],
        "true_alt": float(own[W.IDX_ALT]),
    })


print("=" * 76)
print(f"A-0 — BT 내부값 vs 실제 기하 ({N}판)")
print("=" * 76)

runner = MatchRunner(
    SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
    SideSpec("AIP_jegalmin.dll", None, "jegalmin"),
    max_engage_time=W.MATCH_DURATION_S,
    tick_sink=sink,
)
try:
    for i in range(N):
        seed = 10_000 + i
        r = runner.run_match(i, seed, make_ic(seed))
        print(f"  [{i}] seed={seed} {r.family:<12} {r.outcome:<12} 표본 {len(rows)}")
finally:
    runner.close()

if not rows:
    print("\nBT 내부값을 못 읽었다 — GetDebugScalars export 또는 바인딩 확인 필요")
    sys.exit(1)


def col(k):
    return np.array([r[k] for r in rows], dtype=float)


print(f"\n표본 {len(rows):,}틱\n")

print("--- 1. 시간 (RunningTime이 SimTime을 따라가는가) ---")
print(f"  BT RunningTime  {col('bt_rt')[0]:8.2f} → {col('bt_rt')[-1]:8.2f}")
print(f"  실제 SimTime    {col('sim_t')[0]:8.2f} → {col('sim_t')[-1]:8.2f}")
print(f"  차이 중앙값     {np.median(col('bt_rt') - col('sim_t')):+8.3f} 초")

print("\n--- 2. 속도 ---")
print(f"  BT {np.median(col('bt_spd')):7.1f}  실제 {np.median(col('true_spd')):7.1f}"
      f"  비율 {np.median(col('bt_spd')/np.maximum(col('true_spd'),1e-6)):.4f}")

print("\n--- 3. ★ 위치 (여기가 틀리면 거리·각도가 전부 틀어진다) ---")
for tag, bt_k, tr_k in (("X vs N", "bt_x", "true_n"), ("Y vs E", "bt_y", "true_e"),
                        ("Z vs D", "bt_z", "true_d")):
    b, t = col(bt_k), col(tr_k)
    print(f"  {tag:<8} BT 중앙 {np.median(b):11.1f}   실제 중앙 {np.median(t):11.1f}"
          f"   차이 중앙 {np.median(b - t):+11.1f}")
print(f"  {'Z vs 고도':<8} BT 중앙 {np.median(col('bt_z')):11.1f}"
      f"   실제 고도 {np.median(col('true_alt')):11.1f}"
      f"   차이 중앙 {np.median(col('bt_z') - col('true_alt')):+11.1f}")

print("\n--- 4. ★ 거리 ---")
bd, td = col("bt_dist"), col("true_dist")
print(f"  BT 중앙 {np.median(bd):8.1f}   실제 중앙 {np.median(td):8.1f}"
      f"   비율 중앙 {np.median(bd/np.maximum(td,1e-6)):.4f}")
print(f"  절대오차 중앙 {np.median(np.abs(bd-td)):8.1f} m   최대 {np.max(np.abs(bd-td)):8.1f} m")

print("\n--- 5. ★ 각도 ---")
for tag, bk, tk in (("ATA", "bt_ata", "true_ata"), ("HCA", "bt_hca", "true_hca")):
    b, t = col(bk), col(tk)
    print(f"  {tag}  BT 중앙 {np.median(b):7.2f}°  실제 중앙 {np.median(t):7.2f}°"
          f"  절대오차 중앙 {np.median(np.abs(b-t)):6.2f}°  최대 {np.max(np.abs(b-t)):7.2f}°")

print("\n--- 6. SnapShot/GunAim 진입 시점 ---")
tasks = [r["task"] for r in rows]
for name in ("SnapShot", "GunAim"):
    idx = [i for i in range(1, len(tasks)) if tasks[i] == name and tasks[i-1] != name]
    if not idx:
        print(f"  {name}: 전환 없음")
        continue
    print(f"  {name} 진입 {len(idx)}회 — BT가 본 값 vs 실제")
    print(f"    거리  BT {np.median([rows[i]['bt_dist'] for i in idx]):8.1f}"
          f"   실제 {np.median([rows[i]['true_dist'] for i in idx]):8.1f}")
    print(f"    ATA   BT {np.median([rows[i]['bt_ata'] for i in idx]):8.2f}°"
          f"  실제 {np.median([rows[i]['true_ata'] for i in idx]):8.2f}°")

print("\n" + "=" * 76)
print("판정")
print("=" * 76)
pos_err = max(abs(np.median(col("bt_x") - col("true_n"))),
              abs(np.median(col("bt_y") - col("true_e"))))
dist_ratio = np.median(bd / np.maximum(td, 1e-6))
ata_err = np.median(np.abs(col("bt_ata") - col("true_ata")))

if pos_err > 50:
    print(f"→ ★ (ㄷ) 좌표 변환 문제. 수평 위치부터 {pos_err:.0f}m 어긋난다.")
elif abs(dist_ratio - 1.0) > 0.05:
    print(f"→ ★ (ㄱ) 거리 산출 문제. 위치는 맞는데 거리 비율이 {dist_ratio:.3f}다.")
elif ata_err > 5.0:
    print(f"→ ★ (ㄴ) 각도 산출 문제. 위치·거리는 맞는데 ATA가 {ata_err:.1f}° 어긋난다.")
else:
    print("→ BT 내부값이 실제와 일치한다. 불일치는 Task 귀속(GetCurrentTaskName 타이밍)")
    print("   문제였을 가능성이 크다 — 상태 전환 통계를 다시 봐야 한다.")
