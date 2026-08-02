"""한 판의 결과 레코드.

필드는 "무엇을 알고 싶은가"별로 묶었다. 특히 **왜 못 쐈나**를 두 갈래로 분리한다:
`ticks_in_phase_range`(거리는 맞았는데 조준을 못했다) vs `min_ata_deg`(조준은 됐는데
거리가 안 맞았다). 이걸 나눠 놓지 않으면 로그를 봐도 원인을 못 고른다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MatchResult:
    # --- 재현 정보 ---
    match_index: int = 0
    seed: int = 0
    family: str = ""
    ic: dict[str, Any] = field(default_factory=dict)
    own_dll: str = ""
    own_xml: str = ""
    target_dll: str = ""
    target_xml: str = ""

    # --- 결과 ---
    end_condition: str = ""
    outcome: str = ""  # win/loss/draw/timeout/crash/win_enemy_crash
    env_outcome: str = ""  # env 원본 (재분류 전) — 차이를 추적하려고 병기
    own_health_final: float = 1.0
    tgt_health_final: float = 1.0
    sim_time_s: float = 0.0
    ticks: int = 0

    # --- 목표 (WEZ) ---
    wez_dealt_ticks: int = 0
    wez_recv_ticks: int = 0
    wez_dealt_ticks_phase1only: int = 0
    wez_by_phase: dict[int, int] = field(default_factory=dict)
    longest_wez_burst: int = 0
    first_wez_t: float | None = None
    dmg_dealt: float = 0.0
    dmg_recv: float = 0.0

    # --- 왜 못 쐈나 (접근 문제 vs 조준 문제 분리) ---
    ticks_in_phase_range: int = 0
    ticks_ata_lt_5deg: int = 0
    min_ata_deg: float | None = None
    min_distance_m: float | None = None

    # --- 안전 ---
    crashed: bool = False
    enemy_crashed: bool = False
    min_own_alt_m: float = 0.0
    min_alt_margin_m: float = 0.0  # min_own_alt - 304.8. 음수면 추락
    ticks_below_600m: int = 0

    # --- 교착 ---
    stalemate_ticks: int = 0
    max_task_run: int = 0
    task_hist: dict[str, int] = field(default_factory=dict)

    # --- 에너지 ---
    min_own_speed_ms: float = 0.0
    min_own_energy_m: float = 0.0
    mean_energy_advantage_m: float = 0.0

    # --- 운영 ---
    wall_clock_s: float = 0.0
    error: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @property
    def shutout(self) -> bool:
        """한 틱도 못 쏜 판. 평균보다 이 비율이 중요하다."""
        return self.wez_dealt_ticks == 0
