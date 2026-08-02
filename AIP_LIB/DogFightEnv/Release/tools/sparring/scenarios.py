"""초기조건(IC) — 평가 / 진단 / 회귀 세 스위트로 분리한다.

## 왜 세 개로 나누는가

처음엔 4패밀리를 한 풀에 넣고 가중 추첨했는데, 30시드에서 `adversarial`이 **1판**밖에
안 나왔다(의도 15%, 실제 3%). 가장 위험한 상황이 통계에서 지워진 것이다.
목적이 다른 것을 한 풀에 섞으면 이렇게 된다.

| 스위트 | 목적 | 뽑는 법 | 읽는 법 |
|---|---|---|---|
| `eval`  | 대회 성능 예측 | 예선 실측 재현 + 소폭 지터 | 평균·p20·shutout |
| `diag`  | 약점 탐지 | **격자로 전수** | 어느 칸이 0점인가 |
| `regress` | 사고 재발 방지 | 과거 실패 상황 고정 | 그 지표만 |

## 예선 시나리오는 실측했다

서버 교전로그 97판(`engagement_logs/*.csv`)의 첫 틱을 전수 조사한 결과,
빔 계열은 **4종(2속도 × 2사이드)**뿐이고 사실상 결정론적이다:

    고도 4,572m (15,000ft) 고정
    분리 497m, 헤딩은 서로 반대(±90°)로 분리축과 수직 → 빔 패스
    속도 200.1 m/s (46판) 또는 118.6 m/s (41판), 양측 동일
    roll/pitch = 0

원거리 정면(5,537m, ATA 2°)도 로그에 10판 있으나 **예선 시나리오가 아니어서 제외**한다.

결정론적이라 그대로 N번 돌리면 표본이 안 된다. → `preliminary`는 실측값에 **소폭 지터**를
주어 이웃을 표집한다. 지터 없는 원본은 `preliminary_exact`로 따로 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

FT = 0.3048

# ── 예선 실측 상수 (engagement_logs 97판 전수조사, 2026-08-03) ──────────────
PRELIM_ALT_M = 4572.0          # 15,000 ft 정확히
PRELIM_SEP_M = 497.0           # 두 기체 분리거리
PRELIM_SPEEDS_MS = (200.1, 118.6)   # 두 속도 변형 모두 관측됨


@dataclass
class Side:
    n: float
    e: float
    alt_m: float
    heading_deg: float
    speed_ms: float
    roll_deg: float = 0.0
    pitch_deg: float = 0.0


@dataclass
class InitialCondition:
    family: str
    own: Side
    tgt: Side
    note: str = ""
    meta: dict = field(default_factory=dict)

    def apply(self, env) -> None:
        for flight, s in (("ownship", self.own), ("target", self.tgt)):
            env.change_init_position(
                flight,
                init_n=s.n, init_e=s.e,
                init_d=-s.alt_m,          # ★ 음수가 고도
                init_roll=s.roll_deg, init_pitch=s.pitch_deg,
                init_heading=s.heading_deg, init_speed=s.speed_ms,
            )

    def as_dict(self) -> dict:
        d = {"family": self.family, "note": self.note}
        for tag, s in (("own", self.own), ("tgt", self.tgt)):
            d.update({f"{tag}_n": round(s.n, 1), f"{tag}_e": round(s.e, 1),
                      f"{tag}_alt": round(s.alt_m, 1), f"{tag}_hdg": round(s.heading_deg, 1),
                      f"{tag}_spd": round(s.speed_ms, 1)})
        d["init_dist_m"] = round(float(np.hypot(self.own.n - self.tgt.n,
                                                self.own.e - self.tgt.e)), 1)
        d.update(self.meta)
        return d


def _wrap(deg: float) -> float:
    return float((deg + 180.0) % 360.0 - 180.0)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 평가 스위트 — 예선 미러
# ═══════════════════════════════════════════════════════════════════════════

def make_preliminary_exact(rng: np.random.Generator) -> InitialCondition:
    """서버 실측 그대로. 지터 없음 — 회귀·재현 확인용."""
    speed = float(rng.choice(PRELIM_SPEEDS_MS))
    flip = bool(rng.integers(0, 2))
    a = Side(0.0, 0.0, PRELIM_ALT_M, -90.0, speed)
    b = Side(PRELIM_SEP_M, 0.0, PRELIM_ALT_M, 90.0, speed)
    own, tgt = (b, a) if flip else (a, b)
    return InitialCondition("preliminary_exact", own, tgt,
                            note=f"beam {PRELIM_SEP_M:.0f}m {speed:.0f}m/s",
                            meta={"prelim_speed": speed, "side_flip": int(flip)})


def make_preliminary(rng: np.random.Generator) -> InitialCondition:
    """★ 평가 주력 — 예선 실측 + 소폭 지터.

    실측이 사실상 결정론적이라 그대로 돌리면 N판이 전부 같은 판이 된다.
    "같은 시나리오"의 범위를 벗어나지 않으면서 표본이 되도록 이웃을 흩뿌린다.
    지터 폭은 실측값 대비 ±12%(거리)/±8°(헤딩) 수준으로 잡았다.
    """
    speed = float(rng.choice(PRELIM_SPEEDS_MS)) + float(rng.uniform(-12.0, 12.0))
    sep = PRELIM_SEP_M + float(rng.uniform(-60.0, 60.0))
    alt = PRELIM_ALT_M + float(rng.uniform(-150.0, 150.0))
    base = float(rng.uniform(-180.0, 180.0))       # 절대방위는 무의미하므로 회전
    jitter_a = float(rng.uniform(-8.0, 8.0))
    jitter_b = float(rng.uniform(-8.0, 8.0))
    lat = float(rng.uniform(-25.0, 25.0))          # 분리축 직교 방향 미세 어긋남
    flip = bool(rng.integers(0, 2))

    rad = np.radians(base)
    # 분리축(base 방향)으로 sep만큼, 헤딩은 분리축에 수직(±90°)
    a = Side(0.0, lat, alt, _wrap(base - 90.0 + jitter_a), speed)
    b = Side(sep * np.cos(rad), sep * np.sin(rad) - lat, alt,
             _wrap(base + 90.0 + jitter_b), speed)
    own, tgt = (b, a) if flip else (a, b)
    return InitialCondition("preliminary", own, tgt,
                            note=f"beam {sep:.0f}m {speed:.0f}m/s",
                            meta={"prelim_speed": round(speed, 1)})


# ═══════════════════════════════════════════════════════════════════════════
# 2. 진단 카탈로그 — 격자. 셀은 계속 늘려나간다
# ═══════════════════════════════════════════════════════════════════════════
#
# 규칙: 새 약점을 발견하면 여기에 셀을 추가하고 `why`에 **발견 경위**를 적는다.
#       나중에 "이 셀이 왜 있는지" 모르는 일이 없어야 한다.
#       진단은 평균이 아니라 **어느 셀이 0점인가**로 읽는다.

# 교범 기준 (AETCTTP §4.6.1) — 턴서클 안/밖이 핵심 분기
PERCH_6K_M = 6000 * FT   # 1,829m — 적 턴서클 '밖'
PERCH_3K_M = 3000 * FT   # 914m  — 적 턴서클 '안'


def _perch(rng, dist_m: float, aa_deg: float, offensive: bool,
           alt: float = PRELIM_ALT_M, own_spd: float = 180.0,
           tgt_spd: float = 180.0) -> tuple[Side, Side]:
    """퍼치 배치 — 한쪽이 상대 뒤 `dist_m`, 상대 꼬리 기준 `aa_deg`."""
    base = float(rng.uniform(-180.0, 180.0))
    ang = np.radians(base + 180.0 + aa_deg)       # 적 꼬리 방향에서 aa만큼 벌린 위치
    atk = Side(dist_m * np.cos(ang), dist_m * np.sin(ang), alt,
               _wrap(base + aa_deg * 0.5), own_spd)
    dfn = Side(0.0, 0.0, alt, _wrap(base), tgt_spd)
    return (atk, dfn) if offensive else (dfn, atk)


def cell_off_outside_tc(rng):
    own, tgt = _perch(rng, PERCH_6K_M, float(rng.uniform(30, 40)), True)
    return InitialCondition("off_outside_tc", own, tgt, "6K perch, 내가 공격")


def cell_off_inside_tc(rng):
    own, tgt = _perch(rng, PERCH_3K_M, float(rng.uniform(30, 40)), True)
    return InitialCondition("off_inside_tc", own, tgt, "3K perch, 내가 공격")


def cell_def_outside_tc(rng):
    own, tgt = _perch(rng, PERCH_6K_M, float(rng.uniform(30, 40)), False)
    return InitialCondition("def_outside_tc", own, tgt, "6K perch, 내가 방어")


def cell_def_inside_tc(rng):
    own, tgt = _perch(rng, PERCH_3K_M, float(rng.uniform(30, 40)), False)
    return InitialCondition("def_inside_tc", own, tgt, "3K perch, 내가 방어")


def cell_energy_down(rng):
    own, tgt = _perch(rng, float(rng.uniform(900, 2000)), float(rng.uniform(40, 90)), True,
                      own_spd=float(rng.uniform(110, 140)), tgt_spd=float(rng.uniform(220, 260)))
    return InitialCondition("energy_down", own, tgt, "에너지 열세 (내가 100m/s 느림)")


def cell_energy_up(rng):
    own, tgt = _perch(rng, float(rng.uniform(900, 2000)), float(rng.uniform(40, 90)), True,
                      own_spd=float(rng.uniform(230, 270)), tgt_spd=float(rng.uniform(120, 150)))
    return InitialCondition("energy_up", own, tgt, "에너지 우세")


def cell_floor_fight(rng):
    """바닥 근처. 녹아웃 304.8m 위 900~1,400m에서 시작."""
    alt = float(rng.uniform(900.0, 1400.0))
    own, tgt = _perch(rng, float(rng.uniform(600, 1500)), float(rng.uniform(30, 90)),
                      True, alt=alt, own_spd=180.0, tgt_spd=180.0)
    return InitialCondition("floor_fight", own, tgt, f"바닥 근처 {alt:.0f}m",
                            meta={"start_alt": round(alt)})


def cell_beam_slow(rng):
    """예선 빔인데 저속 변형만 — 교착이 가장 잘 나는 조건."""
    ic = make_preliminary(rng)
    for s in (ic.own, ic.tgt):
        s.speed_ms = float(rng.uniform(105.0, 130.0))
    ic.family = "beam_slow"
    ic.note = "예선 빔 · 저속"
    return ic


def cell_beam_fast(rng):
    ic = make_preliminary(rng)
    for s in (ic.own, ic.tgt):
        s.speed_ms = float(rng.uniform(230.0, 270.0))
    ic.family = "beam_fast"
    ic.note = "예선 빔 · 고속"
    return ic


def cell_head_on(rng):
    """정면 머지 — 예선은 아니지만 재교전 중 자주 나오는 기하."""
    sep = float(rng.uniform(1500.0, 3500.0))
    alt = PRELIM_ALT_M + float(rng.uniform(-400, 400))
    base = float(rng.uniform(-180, 180))
    spd = float(rng.uniform(200, 260))
    rad = np.radians(base)
    return InitialCondition(
        "head_on",
        Side(0.0, 0.0, alt, _wrap(base), spd),
        Side(sep * np.cos(rad), sep * np.sin(rad), alt, _wrap(base + 180.0), spd),
        f"정면 {sep:.0f}m")


def cell_alt_split_high(rng):
    """내가 위 — 수직 기동(로우 요요)이 필요한 상황. v6엔 수직기동이 없다."""
    own, tgt = _perch(rng, float(rng.uniform(800, 2000)), float(rng.uniform(40, 100)), True)
    own.alt_m += float(rng.uniform(600, 1500))
    return InitialCondition("alt_split_high", own, tgt, "내가 위 (수직 필요)")


def cell_alt_split_low(rng):
    own, tgt = _perch(rng, float(rng.uniform(800, 2000)), float(rng.uniform(40, 100)), True)
    own.alt_m -= float(rng.uniform(600, 1200))
    return InitialCondition("alt_split_low", own, tgt, "내가 아래")


@dataclass
class DiagCell:
    key: str
    why: str          # 왜 이 셀이 있는가 — 발견 경위
    watch: str        # 무엇을 봐야 하는가
    build: Callable[[np.random.Generator], InitialCondition]


DIAG_CELLS: list[DiagCell] = [
    DiagCell("off_outside_tc",
             "대회 OBFM_Blue/Red에 해당하는데 지금 풀에 사실상 없다(30시드 중 1판)",
             "공격 위치를 주면 쏘는가 — wez_dealt, CZ 체류",
             cell_off_outside_tc),
    DiagCell("off_inside_tc",
             "§4.6.1 '6K는 턴서클 밖, 3K는 안'이 핵심 분기인데 구분해 재본 적이 없다",
             "가까운 공격에서 오버슛하는가 — min_distance, wez_dealt",
             cell_off_inside_tc),
    DiagCell("def_outside_tc",
             "베이스라인에서 jegalmin에게 18.4틱 맞았다(우리는 0.7틱). 방어를 따로 안 봤다",
             "피격을 줄이고 살아남는가 — wez_recv, crashed",
             cell_def_outside_tc),
    DiagCell("def_inside_tc",
             "위와 같되 근접. §4.7 반전 판단(2,000ft 이내)이 필요한 구간",
             "wez_recv, min_distance, 반전 성공 여부",
             cell_def_inside_tc),
    DiagCell("energy_down",
             "Day 3: 코너 미만 체류 97.6%. 이미 열세로 시작하면 회복하는가",
             "min_own_speed, 코너 미만 체류율",
             cell_energy_down),
    DiagCell("energy_up",
             "우세를 줬을 때 그걸 기수위치로 바꾸는가(§4.2.3 공리)",
             "wez_dealt — 우세를 못 살리면 전술 문제",
             cell_energy_up),
    DiagCell("floor_fight",
             "다음 작업이 하강각 클램프 완화라 추락 위험이 직접 올라간다",
             "★crashed, min_own_alt, 바닥 10° 규칙 준수",
             cell_floor_fight),
    DiagCell("beam_slow",
             "예선 실측 속도 118.6 m/s 변형. 교착이 가장 잘 난다",
             "stalemate_ticks, 코너 미만 체류율",
             cell_beam_slow),
    DiagCell("beam_fast",
             "예선 실측 속도 200.1 m/s 변형. 과속 오버슛 쪽",
             "min_distance, wez_dealt",
             cell_beam_fast),
    DiagCell("head_on",
             "예선은 아니지만 재교전 중 반복 발생. GeoMathUtil HCA 결함이 나온 기하이기도 하다",
             "1서클/2서클 선택이 맞는가, stalemate",
             cell_head_on),
    DiagCell("alt_split_high",
             "v6엔 수직기동이 아예 없다(v1의 요요가 v5 개편 때 사라짐). §4.6.3.1.9.1 low yo-yo",
             "고도를 속도로 바꾸는가 — min_own_speed, wez_dealt",
             cell_alt_split_high),
    DiagCell("alt_split_low",
             "아래에서 올려다보는 기하. 조준이 되는가",
             "min_ata, wez_dealt",
             cell_alt_split_low),
]

DIAG_BY_KEY = {c.key: c for c in DIAG_CELLS}


# ═══════════════════════════════════════════════════════════════════════════
# 3. 회귀 스위트 — 사고 재발 방지
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ 재현성 테스트(test_bt_reset.py)와 다르다.
#    재현성  : 같은 빌드 2회 → 궤적이 비트 단위로 동일한가
#    회귀    : 다른 빌드   → **결과가 나빠지지 않았는가**
#    빌드를 고쳤으니 궤적은 당연히 달라진다. crashed/stalemate 같은 결과만 본다.

@dataclass
class RegressCase:
    key: str
    seed: int
    cell: str
    what_happened: str     # 과거에 무슨 일이 있었나
    guard: str             # 무엇이 다시 깨지면 안 되나


REGRESS_CASES: list[RegressCase] = [
    RegressCase("floor_crash_guard", 90001, "floor_fight",
                "v5에서 뒤집힌 채 풀당김으로 3초에 654m 잃고 추락",
                "crashed == False, min_own_alt > 304.8"),
    RegressCase("floor_crash_guard2", 90002, "floor_fight",
                "저고도 시작에서 PreventLandCrash가 개입해야 함",
                "crashed == False"),
    RegressCase("stalemate_beam", 90003, "beam_slow",
                "베이스라인에서 교착 최장 27초(vs jegalmin)",
                "stalemate_ticks가 베이스라인보다 늘지 않을 것"),
    RegressCase("defensive_hits", 90004, "def_inside_tc",
                "jegalmin에게 18.4틱 피격(우리는 0.7틱)",
                "wez_recv_ticks가 늘지 않을 것"),
]


# ═══════════════════════════════════════════════════════════════════════════
# 시드 → IC
# ═══════════════════════════════════════════════════════════════════════════

FAMILIES: dict[str, Callable[[np.random.Generator], InitialCondition]] = {
    "preliminary": make_preliminary,
    "preliminary_exact": make_preliminary_exact,
    **{c.key: c.build for c in DIAG_CELLS},
}


def make_ic(seed: int, family: str | None = None) -> InitialCondition:
    """시드 하나 → IC 하나. **같은 시드는 항상 같은 IC**(페어 비교의 전제).

    family를 안 주면 평가용 `preliminary`로 만든다.
    예선이 빔 시나리오 하나이므로 평가의 기본값도 그것이다.
    """
    rng = np.random.default_rng(seed)
    return FAMILIES[family or "preliminary"](rng)


def seed_list(count: int, base: int = 10_000) -> list[int]:
    """연속 시드. 확정 검증 때는 base를 바꿔 **겹치지 않는 시드**를 쓴다."""
    return [base + i for i in range(count)]


def diag_grid(per_cell: int = 3, base: int = 50_000) -> list[tuple[int, str]]:
    """진단 격자 — 모든 셀을 같은 수만큼. 빈칸이 안 생긴다."""
    out: list[tuple[int, str]] = []
    for ci, cell in enumerate(DIAG_CELLS):
        for i in range(per_cell):
            out.append((base + ci * 100 + i, cell.key))
    return out


def regress_list() -> list[tuple[int, str]]:
    return [(c.seed, c.cell) for c in REGRESS_CASES]
