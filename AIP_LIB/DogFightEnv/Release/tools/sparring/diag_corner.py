"""A-4. 코너속도 실측 — 스로틀 로직의 기준을 정한다.

## 의심

`CornerHoldThrottle`은 **185~230 m/s**를 코너 구간으로 보고 그 위면 감속(0.25), 아래면 가속(1.0)한다.
그런데 `bb->MySpeed_MS`는 **TAS 계열**이고, 문헌의 F-16 코너속도(330~440kt)는 관습상 **CAS 기준**이다.
고도 7,000m에서 TAS 230 m/s ≈ CAS 344kt 수준이라, **우리가 "코너 구간"이라 믿는 곳이
실제로는 최대 선회율 아래**일 수 있다. 그렇다면 계속 너무 느리게 날면서 레이트 싸움을 져 온 것이다.

단, 교범 §4.3.8은 "선회 성능은 **TAS**와 가용 G의 함수"라고 한다. 둘 다 맞다 —
**가용 G는 CAS가, 그 G에서의 반경/율은 TAS가** 결정한다. 그래서 단정하지 않고 잰다.

## 방법

실제 선회율 = 속도벡터 방향의 변화각 / 시간. NED 위치 차분으로 구해 좌표 프레임 문제를 피한다.

⚠️ **기선(baseline)을 반드시 늘려야 한다.** NED 위치는 위경도 1e-6도(**≈0.11m**) 양자화를
거쳐 나오는데, 60Hz 인접 틱의 이동은 4m 남짓이라 각도 노이즈가 최대 1.5°/틱(≈90°/s)까지 낀다.
실제로 인접틱 차분으로 재면 이론치의 **약 6배**가 나온다(검증함). `STRIDE`틱(≈0.2초) 간격으로
재면 이동이 50m가 되어 노이즈가 1°/s 아래로 떨어진다.

교차검증으로 이론치 `ω = g·√(Nz²−1)/V`와 비교해 비율이 1 근처인지 확인한다.

실행: python tools/sparring/diag_corner.py [판수]
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

N_MATCHES = int(sys.argv[1]) if len(sys.argv) > 1 else 3
KT = 0.51444  # m/s per knot

IDX_KCAS, IDX_KTAS, IDX_NZ = 12, 27, 31

STRIDE = 12  # 0.2초 기선. 위치 양자화(0.11m) 노이즈를 1°/s 아래로 누른다

samples: list[np.ndarray] = []  # 판별 (n,6): N,E,D,KCAS,KTAS,Nz,Alt


def make_sink(store: list):
    """판 하나의 원시 궤적을 모은다. 선회율은 판이 끝난 뒤 한꺼번에 계산한다
    (판 경계를 넘어 차분하면 위치가 순간이동해 말도 안 되는 값이 나온다)."""
    def sink(i: int, d: dict) -> None:
        s = d["own_state"]
        store.append(np.array([s[0], s[1], s[2], s[IDX_KCAS], s[IDX_KTAS],
                               s[IDX_NZ], s[W.IDX_ALT]], dtype=float))
    return sink


def turn_rates(track: np.ndarray, stride: int = STRIDE) -> np.ndarray:
    """(kcas, ktas, nz, alt, turn_deg_s) 배열로 변환."""
    pos = track[:, 0:3]
    v = pos[stride:] - pos[:-stride]                      # stride틱 동안의 변위
    n = np.linalg.norm(v, axis=1, keepdims=True)
    ok = n[:, 0] > 1e-6
    vn = np.zeros_like(v)
    vn[ok] = v[ok] / n[ok]
    cos = np.sum(vn[stride:] * vn[:-stride], axis=1)
    ang = np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))
    rate = ang / (stride / 60.0)                          # deg per stride → deg/s
    base = track[stride:len(rate) + stride]               # 해당 구간 중앙쯤의 상태
    return np.column_stack([base[:, 3], base[:, 4], base[:, 5], base[:, 6], rate])


print("=" * 76)
print(f"A-4 코너속도 실측 — gichan vs jegalmin, {N_MATCHES}판 × 200초")
print("=" * 76)

track: list[np.ndarray] = []
runner = MatchRunner(
    SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
    SideSpec("AIP_jegalmin.dll", None, "jegalmin"),
    max_engage_time=W.MATCH_DURATION_S,
    tick_sink=make_sink(track),
)
blocks: list[np.ndarray] = []
try:
    for i in range(N_MATCHES):
        seed = 30000 + i
        track.clear()
        r = runner.run_match(i, seed, make_ic(seed))
        print(f"  [{i}] seed={seed} {r.family:<12} {r.outcome:<16} {r.wall_clock_s:.1f}s")
        if len(track) > STRIDE * 2:
            blocks.append(turn_rates(np.array(track)))
finally:
    runner.close()

arr = np.vstack(blocks)
kcas_ms, ktas_ms, nz, alt, turn = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4]
kcas_kt, ktas_kt = kcas_ms / KT, ktas_ms / KT

print(f"\n표본 {len(arr):,}틱")
print(f"  KCAS  {kcas_ms.min():6.1f}~{kcas_ms.max():6.1f} m/s "
      f"({kcas_kt.min():5.0f}~{kcas_kt.max():5.0f} kt)")
print(f"  KTAS  {ktas_ms.min():6.1f}~{ktas_ms.max():6.1f} m/s "
      f"({ktas_kt.min():5.0f}~{ktas_kt.max():5.0f} kt)")
print(f"  Nz    {nz.min():6.2f}~{nz.max():6.2f} G   고도 {alt.min():.0f}~{alt.max():.0f} m")
print(f"  선회율 최대 {turn.max():.1f}°/s")

# 실제로 선회 중인 표본만 (수평비행은 모든 속도에서 0이라 최대치를 왜곡)
turning = nz > 2.0
print(f"  선회 중(Nz>2G) 표본 {int(turning.sum()):,} ({100*turning.mean():.1f}%)")

# ★ 교차검증 — 측정이 물리와 맞는지. 비율이 1 근처가 아니면 측정을 믿으면 안 된다
theory = np.degrees(9.80665 * np.sqrt(np.maximum(nz ** 2 - 1.0, 0.0))
                    / np.maximum(ktas_ms, 1.0))
ratio = np.median(turn[turning] / np.maximum(theory[turning], 1e-6))
print(f"  [교차검증] 실측/이론(g√(Nz²−1)/V) 중앙값 = {ratio:.2f}"
      f"   {'OK' if 0.6 < ratio < 1.6 else '★측정 의심 — 결론 내지 말 것'}")


def table(speed_ms: np.ndarray, label: str, width: float = 10.0) -> float:
    print(f"\n--- {label} 구간별 달성 선회율 (Nz>2G 표본, p95 = 그 속도에서 낸 최대치) ---")
    print(f"  {label+'(m/s)':<14}{'(kt)':>10}{'표본':>8}{'p95 선회율':>13}{'평균Nz':>9}")
    lo = np.floor(speed_ms[turning].min() / width) * width
    hi = np.ceil(speed_ms[turning].max() / width) * width
    best_rate, best_bin = -1.0, 0.0
    rows = []
    for b in np.arange(lo, hi, width):
        m = turning & (speed_ms >= b) & (speed_ms < b + width)
        cnt = int(m.sum())
        if cnt < 40:
            continue
        p95 = float(np.percentile(turn[m], 95))
        rows.append((b, cnt, p95, float(nz[m].mean())))
        if p95 > best_rate:
            best_rate, best_bin = p95, b
    for b, cnt, p95, mnz in rows:
        star = " ★" if b == best_bin else ""
        bar = "#" * int(p95 / max(best_rate, 1e-6) * 30)
        print(f"  {b:6.0f}~{b+width:<7.0f}{b/KT:9.0f}{cnt:8d}{p95:12.2f}°/s{mnz:8.2f}  {bar}{star}")
    print(f"  → 최대 선회율 구간: {best_bin:.0f}~{best_bin+width:.0f} m/s "
          f"({best_bin/KT:.0f}~{(best_bin+width)/KT:.0f} kt), {best_rate:.2f}°/s")
    return best_bin


best_tas = table(ktas_ms, "KTAS")
best_cas = table(kcas_ms, "KCAS")


def envelope(speed_ms: np.ndarray, label: str, width: float = 10.0) -> tuple[float, float]:
    """★ 속도별 **달성 가능한 최대 Nz**와 그때의 이론 선회율.

    위 표(p95 선회율)는 함정이 있다 — 고속 구간은 BT가 평균 6G로 당겼고 저속 구간은 2G라,
    "그 속도의 성능"이 아니라 "BT가 그 속도에서 한 짓"을 보고 있다.
    코너속도는 **양력한계와 구조한계가 만나는 지점**이므로, 속도별로 실제 뽑아낸
    최대 G(p99)를 보고 거기서 이론 선회율 ω=g√(Nz²−1)/V 를 계산해야 한다.
    """
    print(f"\n--- ★ {label} 구간별 달성 최대 G와 그때의 선회율 (코너속도 판별) ---")
    print(f"  {label+'(m/s)':<14}{'(kt)':>9}{'표본':>7}{'최대Nz(p99)':>13}{'그때 ω':>11}")
    lo = np.floor(speed_ms[turning].min() / width) * width
    hi = np.ceil(speed_ms[turning].max() / width) * width
    best_w, best_b, best_nz = -1.0, 0.0, 0.0
    rows = []
    for b in np.arange(lo, hi, width):
        m = turning & (speed_ms >= b) & (speed_ms < b + width)
        if int(m.sum()) < 40:
            continue
        nz99 = float(np.percentile(nz[m], 99))
        v = b + width / 2.0
        w = float(np.degrees(9.80665 * np.sqrt(max(nz99 ** 2 - 1.0, 0.0)) / max(v, 1.0)))
        rows.append((b, int(m.sum()), nz99, w))
        if w > best_w:
            best_w, best_b, best_nz = w, b, nz99
    for b, cnt, nz99, w in rows:
        star = " ★" if b == best_b else ""
        bar = "#" * int(w / max(best_w, 1e-6) * 28)
        print(f"  {b:6.0f}~{b+width:<7.0f}{b/KT:8.0f}{cnt:7d}{nz99:12.2f}G{w:10.2f}°/s  {bar}{star}")
    print(f"  → 최대: {best_b:.0f}~{best_b+width:.0f} m/s ({best_b/KT:.0f} kt), "
          f"{best_nz:.1f}G에서 {best_w:.2f}°/s")
    return best_b, best_nz


env_tas, nz_tas = envelope(ktas_ms, "KTAS")
env_cas, nz_cas = envelope(kcas_ms, "KCAS")

print("\n" + "=" * 76)
print("판정")
print("=" * 76)
print(f"현재 CornerHoldThrottle 가정: TAS 185~230 m/s ({185/KT:.0f}~{230/KT:.0f} kt)를 코너로 봄")
print(f"  · 230 m/s 초과 → 스로틀 0.25 (감속)")
print(f"  · 185 m/s 미만 → 스로틀 1.00 (가속)")
print(f"\n[관측] 달성 선회율 최대   : KTAS {best_tas:.0f}~{best_tas+10:.0f} m/s "
      f"/ KCAS {best_cas:.0f}~{best_cas+10:.0f} m/s")
print(f"[성능] 달성 G 기준 최적  : KTAS {env_tas:.0f}~{env_tas+10:.0f} m/s "
      f"({env_tas/KT:.0f} kt, {nz_tas:.1f}G)")
if env_tas > 230.0:
    print("→ ★ 최적이 현재 상한(230 m/s)보다 위다. 230 초과에서 스로틀을 0.25로 죽이는 건")
    print("   최대 선회율 구간을 스스로 벗어나는 동작이다. 상한을 올려야 한다.")
elif env_tas < 185.0:
    print("→ ★ 최적이 현재 하한(185 m/s)보다 아래다. 불필요하게 가속해 왔다.")
else:
    print("→ 현재 TAS 구간 안. 가정 유지.")
print("\n⚠️ 한계: BT가 속도 전 구간에서 최대 G를 시도하지 않으므로 이 값은 하한 추정이다.")
print("   확정하려면 전 속도에서 풀당김을 강제하는 전용 스윕이 필요하다(필요시 A-4b).")
print(f"\n고도 {alt.min():.0f}~{alt.max():.0f}m 구간의 CAS/TAS 비 = "
      f"{np.mean(kcas_ms[turning]/np.maximum(ktas_ms[turning],1e-6)):.3f}")
print("(서버는 9개 값만 주므로, CAS 기준이 필요하면 고도로 보정해야 한다)")
