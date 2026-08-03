"""A-1 신규 지표 대조 검증 — BT가 계산한 값 vs Python이 독립 계산한 값.

계획 리스크 #13: *"또 다른 계통 버그가 숨어 있을 수 있다 — 좌표 버그가 몇 달간 안 보였다.
새 지표를 만들 때마다 GetDebugScalars로 BT값 vs 실제를 대조한다."*

실제로 A-0에서 `MyLocation_Cartesian`에 위경도가 그대로 들어가 있는 걸 발견했다.
거리·ATA가 통째로 무의미했는데 몇 달간 아무도 몰랐다. 같은 일을 반복하지 않으려면
지표를 **만든 직후에** 대조해야 한다.

검증 대상 (A-1 지표 노드 3종):
  LosRateUpdate  -> bt_losr, bt_losr_mag
  EnergyUpdate   -> bt_energy, bt_tgt_energy, bt_energy_adv
  TurnGeomUpdate -> bt_turn_rate, bt_tgt_turn_rate, bt_turn_radius, bt_tgt_turn_radius
  (AspectAngleUpdate에 추가한) bt_aspect_from_tail

실행: python tools/sparring/diag_btmetrics.py [판수]
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
BASE = 12            # BT의 LOSR_BASE와 같아야 한다
DT_NOM = 1.0 / 60.0
G = 9.80665


def collect(n: int) -> list[dict]:
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec("AIP_jegalmin.dll", None, "jegalmin"),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(n):
            runner.run_match(i, 50_000 + i, make_ic(50_000 + i))
    finally:
        runner.close()
    return rows


def fwd(state) -> np.ndarray:
    """오일러각(deg)에서 기수벡터. state[3]=roll state[4]=pitch state[5]=yaw."""
    p = np.radians(state[4])
    y = np.radians(state[5])
    return np.array([np.cos(p) * np.cos(y), np.cos(p) * np.sin(y), -np.sin(p)])


def cmp(name: str, bt: np.ndarray, py: np.ndarray, tol_rel=0.05, tol_abs=1.0):
    """상대오차 중앙값과 '허용범위 밖' 비율을 낸다."""
    ok = np.isfinite(bt) & np.isfinite(py)
    if ok.sum() == 0:
        print(f"  {name:22s}  표본 없음")
        return
    b, p = bt[ok], py[ok]
    err = np.abs(b - p)
    denom = np.maximum(np.abs(p), 1e-6)
    rel = err / denom
    bad = (err > tol_abs) & (rel > tol_rel)
    flag = "OK " if bad.mean() < 0.05 else "!! "
    print(f"  {flag}{name:22s} 중앙 BT={np.median(b):9.2f} PY={np.median(p):9.2f}"
          f"  |오차|중앙={np.median(err):7.3f}  불일치 {100*bad.mean():5.1f}%")


print(f"A-1 지표 대조 검증 — {N}판 (vs jegalmin, 시드 50000~)")
rows = collect(N)
rows = [r for r in rows if r.get("bt")]
print(f"BT 내부값이 실린 틱: {len(rows)}")
if not rows:
    print("!! GetDebugScalars가 비어 있다 — DLL이 구버전이거나 export 실패")
    sys.exit(1)

own = np.array([r["own_state"] for r in rows])
tgt = np.array([r["tgt_state"] for r in rows])
myata = np.array([r["my_ata"] for r in rows])
btv = {k: np.array([r["bt"].get(k, np.nan) for r in rows])
       for k in ("bt_losr", "bt_losr_mag", "bt_aspect_from_tail", "bt_energy",
                 "bt_tgt_energy", "bt_energy_adv", "bt_turn_rate",
                 "bt_tgt_turn_rate", "bt_turn_radius", "bt_tgt_turn_radius")}

n = len(rows)
print("\n── 에너지 (Es = alt + v²/2g) ──")
# 고도는 NED D(양수=아래)의 반대. state[44]=Alt(MSL, m)를 쓴다
py_e = own[:, 44] + np.linalg.norm(own[:, 6:9], axis=1) ** 2 / (2 * G)
py_te = tgt[:, 44] + np.linalg.norm(tgt[:, 6:9], axis=1) ** 2 / (2 * G)
cmp("MyEnergy_M", btv["bt_energy"], py_e, tol_abs=50.0)
cmp("TargetEnergy_M", btv["bt_tgt_energy"], py_te, tol_abs=50.0)
cmp("EnergyAdvantage_M", btv["bt_energy_adv"], py_e - py_te, tol_abs=50.0)

print("\n── LOSR (12틱 기선, 부호 +=후방) ──")
los = tgt[:, 0:3] - own[:, 0:3]
py_losr = np.full(n, np.nan)
for i in range(BASE, n):
    a, b = los[i - BASE], los[i]
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        continue
    ang = np.degrees(np.arccos(np.clip(float(a @ b) / (na * nb), -1, 1)))
    s = np.sign(myata[i] - myata[i - BASE])
    py_losr[i] = ang / (BASE * DT_NOM) * (s if s != 0 else 1.0)
cmp("LosRate_DegPerSec", btv["bt_losr"], py_losr, tol_abs=1.0)
cmp("LosRateMag", btv["bt_losr_mag"], np.abs(py_losr), tol_abs=1.0)

print("\n── 선회 기하 ──")
py_tr = np.full(n, np.nan)
py_ttr = np.full(n, np.nan)
fo = np.array([fwd(s) for s in own])
ft = np.array([fwd(s) for s in tgt])
for i in range(BASE, n):
    py_tr[i] = np.degrees(np.arccos(np.clip(float(fo[i - BASE] @ fo[i]), -1, 1))) / (BASE * DT_NOM)
    py_ttr[i] = np.degrees(np.arccos(np.clip(float(ft[i - BASE] @ ft[i]), -1, 1))) / (BASE * DT_NOM)
cmp("MyTurnRate", btv["bt_turn_rate"], py_tr, tol_abs=2.0)
cmp("TargetTurnRate", btv["bt_tgt_turn_rate"], py_ttr, tol_abs=2.0)

print("\n── 교범 기준 AA (꼬리 기준) ──")
# 하네스가 이미 aspect_from_tail을 계산해 틱에 싣고 있다
py_aft = np.array([r["aspect_from_tail"] for r in rows])
cmp("AspectFromTail_Deg", btv["bt_aspect_from_tail"], py_aft, tol_abs=3.0)

print("\n주의: 판 경계에서 이력이 섞이면 앞 12틱은 불일치가 정상이다.")
print("      '불일치 %'가 5%를 크게 넘으면 계통 오류를 의심할 것.")
