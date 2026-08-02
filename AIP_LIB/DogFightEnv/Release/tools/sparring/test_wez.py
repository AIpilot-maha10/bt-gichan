"""wez.py 단위 검증 — 경계값과 GeoMathUtil 일치성.

실행: python tools/sparring/test_wez.py   (Release 폴더에서)
"""

from __future__ import annotations

import os
import sys

import numpy as np

# Windows 콘솔 기본 코드페이지(cp949)에서 한글·기호가 깨지거나 예외가 나는 것을 막는다
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

_RELEASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _RELEASE)
sys.path.insert(0, os.path.join(_RELEASE, "src"))

from tools.sparring import wez as W  # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  {'OK ' if ok else 'FAIL'} {name}: got={got} want={want}")
    if not ok:
        FAILS.append(name)


def check_close(name: str, got: float, want: float, tol: float) -> None:
    ok = abs(got - want) <= tol
    print(f"  {'OK ' if ok else 'FAIL'} {name}: got={got:.6g} want={want:.6g} tol={tol:g}")
    if not ok:
        FAILS.append(name)


print("=== 1. Phase 시간 경계 ===")
for t, want_idx in [(0.0, 1), (99.9, 1), (100.0, 2), (149.9, 2), (150.0, 3), (199.9, 3), (250.0, 3)]:
    check(f"phase_at({t})", W.phase_at(t).index, want_idx)

print("\n=== 2. Phase별 콘/사거리 (교범→미터 환산) ===")
check_close("P1 cone(반각)", W.PHASES[0].cone_deg, 1.0, 0)
check_close("P1 max_range", W.PHASES[0].max_range_m, 914.4, 1e-6)
check_close("P2 max_range", W.PHASES[1].max_range_m, 1066.8, 1e-6)
check_close("P3 max_range", W.PHASES[2].max_range_m, 1219.2, 1e-6)
check_close("min_range(공통)", W.PHASES[0].min_range_m, 152.4, 1e-6)
check_close("녹아웃 고도", W.KNOCKOUT_ALT_M, 304.8, 1e-9)

print("\n=== 3. 콘 경계값 (Phase1, 반각 1°) ===")
p1 = W.PHASES[0]
check("ATA 0.5° @500m  → 사격", W.in_wez(0.5, 500.0, p1), True)
check("ATA 1.0° @500m  → 사격(경계 포함)", W.in_wez(1.0, 500.0, p1), True)
check("ATA 1.5° @500m  → 불가", W.in_wez(1.5, 500.0, p1), False)
check("ATA 0.5° @150m  → 불가(너무 가까움)", W.in_wez(0.5, 150.0, p1), False)
check("ATA 0.5° @1000m → 불가(너무 멂)", W.in_wez(0.5, 1000.0, p1), False)

print("\n=== 4. Phase2에서는 같은 기하가 사격 가능해진다 ===")
p2 = W.PHASES[1]
check("ATA 1.5° @1000m: P1", W.in_wez(1.5, 1000.0, p1), False)
check("ATA 1.5° @1000m: P2", W.in_wez(1.5, 1000.0, p2), True)

print("\n=== 5. GeoMathUtil ATA와 우리 ata_deg 일치 (100쌍) ===")
from GeoMathUtil import GeometryInfo  # noqa: E402

geo = GeometryInfo()
rng = np.random.default_rng(20260802)
max_diff = 0.0
for _ in range(100):
    own = np.zeros(51)
    tgt = np.zeros(51)
    own[0:3] = rng.uniform(-5000, 5000, 3)
    tgt[0:3] = rng.uniform(-5000, 5000, 3)
    own[3:6] = rng.uniform(-180, 180, 3)
    tgt[3:6] = rng.uniform(-180, 180, 3)
    ours = W.ata_deg(geo, own, tgt)
    theirs = abs(float(geo._get_antenna_train_angle(own, tgt, False)))
    max_diff = max(max_diff, abs(ours - theirs))
check_close("ATA 최대 오차", max_diff, 0.0, 1e-9)

print("\n=== 6. HCA 자체계산 — GeoMathUtil 결함 회피 확인 ===")


def mk(n, e, d, hdg):
    s = np.zeros(51)
    s[0:3] = [n, e, d]
    s[3:6] = [0, 0, hdg]
    return s


own_n = mk(0, 0, -5000, 0)
check_close("동일침로 → 0°", W.hca_deg(own_n, mk(1000, 0, -5000, 0)), 0.0, 1e-6)
check_close("★정면머지 → 180° (GeoMathUtil은 0을 반환)",
            W.hca_deg(own_n, mk(1000, 0, -5000, 180)), 180.0, 1e-6)
check_close("90° 교차 → 90°", W.hca_deg(own_n, mk(1000, 0, -5000, 90)), 90.0, 1e-6)
buggy = abs(float(geo._get_heading_cross_angle(own_n, mk(1000, 0, -5000, 180), False)))
print(f"  (참고) GeoMathUtil._get_heading_cross_angle 정면머지 = {buggy} ← 결함 재현")
if buggy > 1e-6:
    FAILS.append("GeoMathUtil HCA 결함이 사라짐 — 전제 재확인 필요")

print("\n=== 7. 교범 기준 AA (꼬리 기준) ===")
check_close("내가 적 6시 → 0°", W.aspect_from_tail_deg(geo, own_n, mk(1000, 0, -5000, 0)), 0.0, 1e-6)
check_close("90° 교차 → 90°", W.aspect_from_tail_deg(geo, own_n, mk(1000, 0, -5000, 90)), 90.0, 1e-6)

print("\n=== 8. WezCounter 누적 ===")
c = W.WezCounter(1 / 60)
for _ in range(10):
    c.update(10.0, 0.5, 90.0, 500.0)      # 내가 사격 조건
for _ in range(5):
    c.update(20.0, 90.0, 0.5, 500.0)      # 적이 사격 조건
for _ in range(3):
    c.update(30.0, 0.5, 90.0, 5000.0)     # 조준은 됐지만 거리 밖
check("dealt_ticks", c.dealt_ticks, 10)
check("recv_ticks", c.recv_ticks, 5)
check("longest_burst", c.longest_burst_ticks, 10)
check("first_wez_t", c.first_wez_t, 10.0)
check("P1 집계", c.by_phase[1], 10)
check("거리조건 충족 틱", c.ticks_in_phase_range, 15)
check_close("min_ata", c.min_ata_deg, 0.5, 1e-9)
print(f"  (참고) dmg_dealt={c.dmg_dealt:.5f}")

print("\n" + "=" * 60)
if FAILS:
    print(f"FAILED {len(FAILS)}건: {FAILS}")
    sys.exit(1)
print("전부 통과")
