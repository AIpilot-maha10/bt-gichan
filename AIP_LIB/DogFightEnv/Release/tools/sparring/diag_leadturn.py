"""리드턴 타이밍 진단 — 우리가 적보다 늦게 당기는가?

교범 §4.8.3.1: *리드턴 단서 = 급격한 후방 LOSR 증가. 가장 흔한 실수는 늦은 리드턴.*

초반 진단(diag_opening)에서 t=20에 적 ATA가 btjegal 48°인데 jegalmin은 14°였다.
jegalmin이 기수를 먼저 돌린다는 뜻인데, 그게 **리드턴을 일찍 시작해서**인지
**속도가 있어서 빨리 도는 것**인지 구분이 안 됐다. 이걸 가른다.

## 측정 설계

임계값을 어디에 두느냐로 결론이 바뀌면 안 되므로, **같은 검출기를 양측에 똑같이
적용해 "누가 먼저 당겼나"** 를 잰다. 임계값 선택이 상쇄된다.

- 머지 = 거리의 국소최소(패스). 첫 머지가 결정적이다 — 교범 "마지막에 도는 쪽이 싸움을 정한다"
- 당김 시작 = Nz(51-state idx31)가 PULL_G 이상으로 올라가 PULL_HOLD 이상 유지되는 첫 틱
- **리드턴 랙 = 내 당김시각 − 적 당김시각.** 양수면 내가 늦다
- LOSR = LOS 단위벡터의 관성 회전율(deg/s). 부호는 ATA 변화로 (+ = 후방)

⚠️ NED 위치는 1e-6도(≈0.11m)로 양자화되어 나온다(A-4에서 데임). 인접 틱으로 각도를
재면 노이즈가 실제의 6배로 낀다 → **12틱(0.2초) 기선**을 쓴다.

실행: python tools/sparring/diag_leadturn.py [판수]
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
SEED_BASE = 50_000

DT = 1.0 / 60.0
BASE = 12            # LOSR 기선(틱) — 양자화 노이즈 회피. A-4에서 확정한 값
IDX_NZ = 31
PULL_G = 4.0         # 당김으로 인정할 G
EASE_G = 2.5         # 이 아래면 "안 당기는 중"
MERGE_MAX_M = 3000.0  # 이보다 멀면 패스로 안 봄
WIN_S = 25.0         # 머지 앞쪽 몇 초를 볼 것인가


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def find_merges(dist: np.ndarray) -> list[int]:
    """거리의 국소최소 = 패스. 가까운 것만."""
    out = []
    for i in range(BASE, len(dist) - BASE):
        if dist[i] >= MERGE_MAX_M:
            continue
        if dist[i] <= dist[i - BASE] and dist[i] < dist[i + BASE]:
            if not out or i - out[-1] > 300:   # 5초 이내 중복 제거
                out.append(i)
    return out


def pull_onset(nz: np.ndarray, lo: int, hi: int) -> int | None:
    """머지 직전의 **마지막** 당김 시작 틱.

    교범 §4.8.4.2.4.2.2 *"the last fighter to turn sets the fight"* — 우리가 알고 싶은 건
    "창 안에서 처음 당긴 때"가 아니라 **머지로 들어가는 마지막 선회를 언제 걸었나**다.

    창 시작 시점에 이미 양쪽이 당기고 있으면 "첫 4G" 방식은 둘 다 창 시작을 돌려줘
    랙이 0으로 뭉개진다. 그래서 뒤에서부터 저G 구간을 찾고 그 뒤 첫 고G를 잡는다.

    None = 창 내내 고G였다 (= 끊지 않고 계속 돌고 있었다). 이것도 정보라 따로 센다.
    """
    lo = max(lo, 0)
    hi = min(hi, len(nz))
    i = hi - 1
    while i >= lo and abs(nz[i]) >= EASE_G:
        i -= 1
    if i < lo:
        return None                      # 창 전체가 고G
    for j in range(i, hi):
        if abs(nz[j]) >= PULL_G:
            return j
    return None


def analyse(rows: list[dict]) -> dict | None:
    """한 판 → 첫 머지의 리드턴 지표."""
    if len(rows) < 600:
        return None
    own = np.array([r["own_state"] for r in rows])
    tgt = np.array([r["tgt_state"] for r in rows])
    dist = np.array([r["dist"] for r in rows])
    my_ata = np.array([r["my_ata"] for r in rows])
    en_ata = np.array([r["en_ata"] for r in rows])
    t = np.array([r["t"] for r in rows])

    merges = find_merges(dist)
    if not merges:
        return None
    m = merges[0]

    lo = max(0, m - int(WIN_S / DT))
    my_pull = pull_onset(own[:, IDX_NZ], lo, m)
    en_pull = pull_onset(tgt[:, IDX_NZ], lo, m)
    # 창 내내 고G면 "끊지 않고 계속 돌았다" — 랙은 못 재지만 그 자체가 관찰이다
    if my_pull is None or en_pull is None:
        return {"seed": -1, "nonstop_me": my_pull is None,
                "nonstop_en": en_pull is None, "lag_s": None}

    # LOSR (12틱 기선). 부호: ATA가 늘면 후방(+)
    los = tgt[:, 0:3] - own[:, 0:3]
    def losr_at(i):
        if i < BASE:
            return 0.0
        a, b = unit(los[i - BASE]), unit(los[i])
        ang = np.degrees(np.arccos(np.clip(float(np.dot(a, b)), -1.0, 1.0)))
        sgn = np.sign(my_ata[i] - my_ata[i - BASE])
        return ang / (BASE * DT) * (sgn if sgn != 0 else 1.0)

    return {
        "nonstop_me": False, "nonstop_en": False,
        "t_merge": float(t[m]),
        "d_merge": float(dist[m]),
        # ★ 핵심: 양수면 내가 늦게 당겼다
        "lag_s": float(t[my_pull] - t[en_pull]),
        "my_pull_t": float(t[my_pull]),
        "en_pull_t": float(t[en_pull]),
        "losr_at_my_pull": losr_at(my_pull),
        "losr_at_en_pull": losr_at(en_pull),
        "my_ata_merge": float(my_ata[m]),
        "en_ata_merge": float(en_ata[m]),
        # 당김 시점의 속도 — "늦어서"인지 "느려서"인지 가른다
        "my_spd_pull": float(np.linalg.norm(own[my_pull, 6:9])),
        "en_spd_pull": float(np.linalg.norm(tgt[en_pull, 6:9])),
    }


def run(opp: str, tag: str) -> list[dict]:
    got: list[dict] = []
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            seed = SEED_BASE + i
            rows.clear()
            runner.run_match(i, seed, make_ic(seed))
            a = analyse(rows)
            if a:
                a["seed"] = seed
                got.append(a)
    finally:
        runner.close()
    return got


def report(tag: str, raw: list[dict]):
    print(f"\n{'='*74}\n{tag}   (머지 검출 {len(raw)}/{N}판)\n{'='*74}")
    if not raw:
        print("  머지를 못 찾았다 — MERGE_MAX_M 또는 패스 자체가 없다")
        return

    nonstop_me = sum(1 for a in raw if a.get("nonstop_me"))
    nonstop_en = sum(1 for a in raw if a.get("nonstop_en"))
    data = [a for a in raw if a.get("lag_s") is not None]
    if nonstop_me or nonstop_en:
        print(f"  ⚠️ 머지 전 25초 내내 고G(끊지 않고 계속 선회): "
              f"나 {nonstop_me}판 / 적 {nonstop_en}판  → 이 판들은 랙 측정 제외")
    if not data:
        print("  랙을 잴 수 있는 판이 없다 — 양쪽 다 계속 돌기만 했다")
        return
    print(f"  {'시드':>6}{'머지t':>8}{'머지d':>8}{'내당김':>8}{'적당김':>8}"
          f"{'랙(s)':>8}{'내ATA':>8}{'적ATA':>8}{'내속도':>8}")
    for a in data:
        print(f"  {a['seed']:>6}{a['t_merge']:8.1f}{a['d_merge']:8.0f}"
              f"{a['my_pull_t']:8.1f}{a['en_pull_t']:8.1f}{a['lag_s']:8.2f}"
              f"{a['my_ata_merge']:8.1f}{a['en_ata_merge']:8.1f}{a['my_spd_pull']:8.1f}")

    lag = np.array([a["lag_s"] for a in data])
    late = int((lag > 0).sum())
    print(f"\n  ── 집계 ──")
    print(f"  ★ 리드턴 랙  중앙 {np.median(lag):+.2f}s  평균 {lag.mean():+.2f}s"
          f"   내가 늦은 판 {late}/{len(lag)}")
    print(f"  당김 시점 속도  나 {np.mean([a['my_spd_pull'] for a in data]):5.1f} m/s"
          f"   적 {np.mean([a['en_spd_pull'] for a in data]):5.1f} m/s")
    print(f"  당김 시점 LOSR  나 {np.mean([a['losr_at_my_pull'] for a in data]):+6.2f}°/s"
          f"   적 {np.mean([a['losr_at_en_pull'] for a in data]):+6.2f}°/s")
    print(f"  머지 시 ATA     나 {np.mean([a['my_ata_merge'] for a in data]):5.1f}°"
          f"   적 {np.mean([a['en_ata_merge'] for a in data]):5.1f}°")
    print("  (LOSR가 내 쪽이 훨씬 크면 = 이미 많이 흘러간 뒤에 당기기 시작 = 늦음)")


print(f"리드턴 타이밍 진단 — 첫 머지 기준, {N}판씩 (시드 {SEED_BASE}~)")
print(f"당김 판정: 머지 직전 마지막으로 |Nz|<{EASE_G}G였다가 {PULL_G}G를 넘는 시점")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll, tag))
