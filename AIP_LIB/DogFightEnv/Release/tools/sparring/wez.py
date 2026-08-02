"""공식 3-Phase WEZ 룰 — 로컬 sim이 Phase1으로 고정되어 있으므로 하네스가 직접 계산한다.

로컬 env(`single_agent_env.update_damage`)는 `config["wez"]` 한 벌만 쓰고 경과시간에
따라 갱신하지 않는다(기본 angle_deg=2.0 → 반각 1.0°, 152.4~914.4m = Phase1 고정).
따라서 로컬 `ep_wez_steps`는 Phase2/3 구간을 과소집계한다. 여기서 시간 게이트를 직접 건다.

각도 규약 (근거: 노션 「📐 용어·지표 표준」):
  - ATA = `GeoMathUtil._get_antenna_train_angle` — 부호가 있으므로 abs() 필수
  - env가 `proj=False`(3D)로 판정하므로 여기서도 3D로 맞춘다. 콘 판정은 3D가 맞다
  - HCA는 `_get_heading_cross_angle`이 정면머지에서 0을 반환하는 결함이 있어 쓰지 않는다
    (필요하면 `hca_deg()` 사용)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

FT = 0.3048

# 51-state 인덱스 (근거: src/dogfight/sim/state_schema.py)
IDX_SIM_TIME = 41
IDX_ALT = 44
IDX_HEALTH = 45


@dataclass(frozen=True)
class Phase:
    """대회 공식 WEZ 단계. cone_deg는 **반각**(half-angle)이다."""

    index: int
    t_start: float
    t_end: float
    cone_deg: float
    min_range_m: float
    max_range_m: float
    damage_mult: float

    def contains_time(self, t: float) -> bool:
        return self.t_start <= t < self.t_end


# 근거: 대회 공식 사이트(aipilot2026.kau.ac.kr), CLAUDE.md 「공식 WEZ 룰」
# 배율(1.0/0.3/0.1)은 engagement_monitor.py L19-23 기준 — 서버 로그로 대조 필요(리스크 #4)
PHASES: tuple[Phase, ...] = (
    Phase(1, 0.0, 100.0, 1.0, 500 * FT, 3000 * FT, 1.0),
    Phase(2, 100.0, 150.0, 2.0, 500 * FT, 3500 * FT, 0.3),
    Phase(3, 150.0, 200.0, 3.0, 500 * FT, 4000 * FT, 0.1),
)

MATCH_DURATION_S = 200.0
KNOCKOUT_ALT_M = 1000 * FT  # 304.8m — 대회 공식. env 기본값 300.0은 쓰지 않는다


def phase_at(sim_time: float) -> Phase:
    """경과시간에 해당하는 Phase. 200초를 넘으면 마지막 Phase를 유지한다."""
    for ph in PHASES:
        if ph.contains_time(sim_time):
            return ph
    return PHASES[-1]


def ata_deg(geo, shooter_state, target_state) -> float:
    """사수 기수 → 표적 시선각(교범 ATA). 항상 0 이상."""
    return abs(float(geo._get_antenna_train_angle(shooter_state, target_state, False)))


def aspect_from_tail_deg(geo, own_state, target_state) -> float:
    """교범 기준 AA — 표적 **꼬리**에서 잰 각(0°=내가 적 6시).

    `GeoMathUtil._get_aspect_angle`은 부호가 있으므로 abs()를 취한다. 크기는 교범과 일치.
    (BT의 `MyAspectAngle_Degree`는 기수 기준이라 이것과 보완각 관계 — 혼동 주의)
    """
    return abs(float(geo._get_aspect_angle(own_state, target_state, False)))


def hca_deg(own_state, target_state) -> float:
    """기수 교차각. 0°=동일침로, 180°=정면.

    `GeoMathUtil._get_heading_cross_angle`은 수평 정면머지에서 sign=0이 되어 0을
    반환하는 결함이 있다(코드 주석에도 명시). 그래서 직접 계산한다.
    """
    return float(np.degrees(np.arccos(np.clip(
        float(np.dot(_forward(own_state), _forward(target_state))), -1.0, 1.0
    ))))


def _forward(state) -> np.ndarray:
    """NED 기준 기수 단위벡터. state[3:6] = roll, pitch, yaw (deg)."""
    pitch = np.radians(float(state[4]))
    yaw = np.radians(float(state[5]))
    cp = np.cos(pitch)
    return np.array([cp * np.cos(yaw), cp * np.sin(yaw), -np.sin(pitch)], dtype=np.float64)


def in_wez(ata_abs_deg: float, distance_m: float, ph: Phase) -> bool:
    """해당 Phase 기준으로 사격 조건을 만족하는가."""
    return (ata_abs_deg <= ph.cone_deg) and (ph.min_range_m <= distance_m <= ph.max_range_m)


def in_phase_range(distance_m: float, ph: Phase) -> bool:
    """거리 조건만 만족하는가 — '접근 문제'와 '조준 문제'를 분리하기 위한 지표."""
    return ph.min_range_m <= distance_m <= ph.max_range_m


def damage_proxy(ata_abs_deg: float, distance_m: float, ph: Phase, dt: float) -> float:
    """데미지 추정치. env `update_damage`의 선형 감쇠식에 Phase 배율을 곱한 형태.

    ⚠️ 서버 실제 산식은 미확인이다(리스크 #4). 순위 비교용이며, 절대값을 신뢰하지 말 것.
    주 지표는 항상 원시 틱수(`wez_dealt_ticks`)다.
    """
    if not in_wez(ata_abs_deg, distance_m, ph):
        return 0.0
    span = ph.max_range_m - ph.min_range_m
    if span <= 0:
        return 0.0
    return ((ph.max_range_m - distance_m) / span) * dt * ph.damage_mult


class WezCounter:
    """한 판 동안의 WEZ 통계를 누적한다.

    - `dealt_ticks` : 내가 사격 조건을 만족한 틱 수 (**주 지표**)
    - `recv_ticks`  : 적이 사격 조건을 만족한 틱 수
    - `anyphase_*`  : Phase1 고정 기준(로컬 env·engagement_monitor 호환). 시간게이트 해석
                      이 맞는지 서버 로그와 대조하기 위해 병기한다
    """

    def __init__(self, dt: float):
        self.dt = float(dt)
        self.dealt_ticks = 0
        self.recv_ticks = 0
        self.anyphase_dealt_ticks = 0
        self.ticks_in_phase_range = 0
        self.by_phase: dict[int, int] = {ph.index: 0 for ph in PHASES}
        self.dmg_dealt = 0.0
        self.dmg_recv = 0.0
        self.first_wez_t: float | None = None
        self.min_ata_deg = float("inf")
        self.min_distance_m = float("inf")
        self.ticks_ata_lt_5deg = 0
        self._burst = 0
        self.longest_burst_ticks = 0

    def update(self, sim_time: float, my_ata: float, enemy_ata: float, distance_m: float) -> Phase:
        ph = phase_at(sim_time)
        p1 = PHASES[0]

        self.min_ata_deg = min(self.min_ata_deg, my_ata)
        self.min_distance_m = min(self.min_distance_m, distance_m)
        if my_ata < 5.0:
            self.ticks_ata_lt_5deg += 1
        if in_phase_range(distance_m, ph):
            self.ticks_in_phase_range += 1

        hit = in_wez(my_ata, distance_m, ph)
        if hit:
            self.dealt_ticks += 1
            self.by_phase[ph.index] += 1
            self.dmg_dealt += damage_proxy(my_ata, distance_m, ph, self.dt)
            if self.first_wez_t is None:
                self.first_wez_t = sim_time
            self._burst += 1
            self.longest_burst_ticks = max(self.longest_burst_ticks, self._burst)
        else:
            self._burst = 0

        if in_wez(enemy_ata, distance_m, ph):
            self.recv_ticks += 1
            self.dmg_recv += damage_proxy(enemy_ata, distance_m, ph, self.dt)

        if in_wez(my_ata, distance_m, p1):
            self.anyphase_dealt_ticks += 1

        return ph

    def as_dict(self) -> dict:
        return {
            "wez_dealt_ticks": self.dealt_ticks,
            "wez_recv_ticks": self.recv_ticks,
            "wez_dealt_ticks_phase1only": self.anyphase_dealt_ticks,
            "wez_by_phase": dict(self.by_phase),
            "ticks_in_phase_range": self.ticks_in_phase_range,
            "ticks_ata_lt_5deg": self.ticks_ata_lt_5deg,
            "longest_wez_burst": self.longest_burst_ticks,
            "first_wez_t": self.first_wez_t,
            "min_ata_deg": None if self.min_ata_deg == float("inf") else self.min_ata_deg,
            "min_distance_m": None if self.min_distance_m == float("inf") else self.min_distance_m,
            "dmg_dealt": self.dmg_dealt,
            "dmg_recv": self.dmg_recv,
        }


def specific_energy_m(state: Sequence[float], speed_ms: float) -> float:
    """비에너지 = 고도 + v²/2g (미터). 교범 §4.4 에너지 관리의 기본 지표."""
    return float(state[IDX_ALT]) + (speed_ms * speed_ms) / (2.0 * 9.80665)
