"""AspectFromTail 불일치 원인 규명 — 투영 때문인가, 버그인가.

diag_btmetrics에서 BT 137.6° vs 하네스 111.7°로 72% 불일치가 나왔다.
교범 임계값을 여기에 걸 예정이라 어느 쪽이 맞는지 확정해야 한다.

가설: BT는 적 **Up 벡터에 수직인 평면으로 투영**한 뒤 각을 재고(AspectAngleUpdate.cpp),
하네스는 **3D 그대로** 잰다(GeoMathUtil._get_aspect_angle에 Tz_pi를 곱해 꼬리 기준).
수직 분리가 크면 둘이 크게 갈린다.

검증법: BT 공식을 Python으로 **그대로 재현**해서 BT 출력과 맞는지 본다.
  · 맞으면 -> 구현은 의도대로. 남은 건 "어느 관례를 쓸 것인가"의 선택 문제
  · 틀리면 -> 진짜 버그

실행: python tools/sparring/diag_aspect.py [판수]
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
D2R = np.pi / 180.0


def body_to_ned(state):
    """NED->body 행렬 T를 만들고 그 전치(=body->NED)를 돌려준다.
    GeoMathUtil과 같은 Tx·Ty·Tz 규약을 쓴다."""
    roll, pitch, yaw = state[3] * D2R, state[4] * D2R, state[5] * D2R
    Tx = np.array([[1, 0, 0], [0, np.cos(roll), np.sin(roll)], [0, -np.sin(roll), np.cos(roll)]])
    Ty = np.array([[np.cos(pitch), 0, -np.sin(pitch)], [0, 1, 0], [np.sin(pitch), 0, np.cos(pitch)]])
    Tz = np.array([[np.cos(yaw), np.sin(yaw), 0], [-np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    return (Tx @ Ty @ Tz).T


def ang(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return np.nan
    return np.degrees(np.arccos(np.clip(float(a @ b) / (na * nb), -1.0, 1.0)))


rows: list[dict] = []
runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                     SideSpec("AIP_jegalmin.dll", None, "jegalmin"),
                     tick_sink=lambda i, d: rows.append(d))
try:
    for i in range(N):
        runner.run_match(i, 50_000 + i, make_ic(50_000 + i))
finally:
    runner.close()

rows = [r for r in rows if r.get("bt")]
print(f"\n표본 {len(rows)}틱\n")

bt_val, repl_proj, truth_3d, elev = [], [], [], []
for r in rows:
    own, tgt = r["own_state"], r["tgt_state"]
    Rt = body_to_ned(tgt)
    fwd_t = Rt @ np.array([1.0, 0.0, 0.0])
    up_t = Rt @ np.array([0.0, 0.0, -1.0])

    # BT는 Cartesian(Z=고도, 위 방향 +)을 쓰고 하네스 state는 NED(D 아래 +)다.
    # 방향각만 보므로 NED 그대로 두고 up 벡터도 NED 기준으로 맞춘다.
    p = own[0:3] - tgt[0:3]                    # 적 -> 나

    # ── BT 공식 재현: 적 Up에 수직인 평면으로 투영 후 적 기수와의 각, 그 보각 ──
    p_proj = p - (p @ up_t) * up_t
    a_nose_proj = ang(p_proj, fwd_t)
    repl_proj.append(180.0 - a_nose_proj)

    # ── 3D 그대로 (하네스/교범) ──
    truth_3d.append(ang(p, -fwd_t))

    bt_val.append(r["bt"].get("bt_aspect_from_tail", np.nan))
    # 수직 분리가 얼마나 되는지 (투영 영향의 크기)
    ph = np.linalg.norm(p[0:2])
    elev.append(np.degrees(np.arctan2(abs(p[2]), ph)) if ph > 1e-6 else 90.0)

bt_val = np.array(bt_val)
repl_proj = np.array(repl_proj)
truth_3d = np.array(truth_3d)
elev = np.array(elev)
ok = np.isfinite(bt_val) & np.isfinite(repl_proj) & np.isfinite(truth_3d)
bt_val, repl_proj, truth_3d, elev = bt_val[ok], repl_proj[ok], truth_3d[ok], elev[ok]


def show(name, a, b):
    d = np.abs(a - b)
    print(f"  {name:34s} |차이| 중앙 {np.median(d):7.3f}°  p90 {np.percentile(d,90):7.3f}°"
          f"   >3° 비율 {100*(d>3).mean():5.1f}%")


print("── BT 출력이 어느 공식과 맞는가 ──")
show("BT  vs  BT공식 재현(투영)", bt_val, repl_proj)
show("BT  vs  3D 그대로(교범/하네스)", bt_val, truth_3d)
print()
print("── 두 관례 자체의 차이 ──")
show("투영 vs 3D", repl_proj, truth_3d)
print(f"\n  LOS 앙각(수직분리) 중앙 {np.median(elev):5.1f}°  p90 {np.percentile(elev,90):5.1f}°")
print(f"  값 중앙:  BT {np.median(bt_val):6.2f}°   재현(투영) {np.median(repl_proj):6.2f}°"
      f"   3D {np.median(truth_3d):6.2f}°")
print("\n판정: 'BT vs BT공식 재현'이 맞으면 구현은 의도대로 -> 관례 선택 문제.")
print("      그것도 안 맞으면 진짜 버그다.")
