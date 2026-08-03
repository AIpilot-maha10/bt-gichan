# -*- coding: utf-8 -*-
"""gichan 보상 함수 — BT 트랙에서 알아낸 것을 이식한다 (계획 D-2).

BT로 39번 시도하며 얻은 지식이 여기 그대로 쓰인다. 각 항목의 근거를 남긴다.

계약 (변경 금지):
  · MY_REWARD_CONFIG 는 dict
  · compute_reward(...) 는 (total: float, components: dict) 반환
  · components 의 각 항목이 ep_reward_<name> 으로 기록된다

## BT에서 이식한 것

1. **추락 = 압도적 벌점** — BT 전 과정에서 가장 비싼 실패였다.
   녹아웃 고도는 **304.8m**(대회 공식)이지 기본 reward.py의 600m 플랫이 아니다.

2. **WEZ는 3-Phase 시간 게이트** — 기본 reward.py는 고정 WEZ만 안다.
   Phase1(0~100s) 1도/152.4~914.4m · Phase2(~150s) 2도/~1066.8m · Phase3(~200s) 3도/~1219.2m
   ⚠️ 로컬 sim의 **데미지 계산은 Phase1 고정**이라 실제 데미지와 어긋난다.
      보상은 **대회 룰(3-Phase)** 을 따른다 — 학습 목표는 대회 점수다.

3. **ATA 그라디언트** — 1도 콘은 희소보상이라 shaping이 없으면 학습이 안 된다.
   BT 실측: 사거리 안에 25초 들어가도 ATA<5도는 2.99초뿐이었다.
   **거리보다 각도가 병목**이므로 ATA에 더 무게를 준다.

4. **코너속도(CAS 350kt) 유지** — A-4 실측(47,900표본)에서 최대 선회율 지점.
   BT는 여기서 만성적으로 벗어나 있었다(코너 미만 체류 97.6%).
   ⚠️ 교범 임계값은 전부 CAS 기준인데 우리가 받는 건 TAS다. idx12가 KCAS라 그대로 쓴다.

5. **교착 억제** — 양측 고ATA로 서로 못 쏘는 상태가 BT의 주 실패 모드였다.

6. **피격 벌점 > 가해 보상** — 교범 판단 우선순위: 추락 0 > 피격 최소 > WEZ 획득.
   *"살아있고 비행기가 멀쩡하면 이기고 있는 것"* (AETCTTP §4.7)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dogfight.sim.state_schema import StateIndex


MY_REWARD_CONFIG = {
    # 종결
    "win_reward": 200.0,
    "loss_reward": -200.0,
    "draw_reward": -20.0,        # 무승부도 실패다 (BT가 jegalmin전에서 계속 여기 머물렀다)
    "crash_penalty": -400.0,     # ★ 추락은 패배보다 비싸다
    "step_penalty": -0.01,

    # 교전
    "damage_dealt_scale": 300.0,
    "damage_recv_scale": -450.0,  # 피격이 가해보다 비싸다 (§4.7)
    # ── training_record.py 호환 키 (없으면 학습기록 저장 실패) ────────────
    #    training_record.py:121~130이 아래 키를 **대괄호로 직접** 읽는다.
    #    .get()이 아니라 []라서 없으면 KeyError -> "Training record save failed".
    #    경고만 뜨고 학습은 진행되지만 기록이 안 남는다. 실측으로 확인한 필수 키:
    #      description / step_penalty / damage_scale / low_altitude_penalty
    #      win_reward / loss_reward / draw_reward
    #    우리는 가해/피격·저고도를 분리해 쓰므로 대표값을 호환용으로 둔다.
    "description": "gichan v7.2 — BT 지식 이식 (3-Phase WEZ, ATA 우선, 코너 350kt, 추락 -400)",
    "damage_scale": 300.0,
    "low_altitude_penalty": -0.15,

    # shaping
    "ata_scale": 0.10,           # 각도가 병목 — 가장 큰 shaping
    "range_scale": 0.03,
    "corner_scale": 0.02,
    "wez_hold_bonus": 0.30,      # 콘 안에 머무는 매 틱

    # 안전
    "low_alt_start_m": 800.0,    # 이 아래부터 벌점 (녹아웃 304.8m 대비 여유)
    "low_alt_scale": -0.15,

    # 교착
    "stalemate_ata_deg": 60.0,
    "stalemate_scale": -0.02,
}

_KNOCKOUT_ALT_M = 304.8          # 대회 공식 녹아웃
_CORNER_KCAS_MS = 180.0          # CAS 350kt ~= 180 m/s (A-4 실측 코너)


def _wez_window(sim_time: float) -> tuple[float, float, float]:
    """대회 공식 3-Phase WEZ — (콘 반각 deg, 최소 m, 최대 m).

    ⚠️ 로컬 sim의 데미지는 Phase1 고정이라 이것과 어긋난다.
       그래도 학습 목표는 **대회 점수**이므로 대회 룰을 따른다.
    """
    if sim_time < 100.0:
        return 1.0, 152.4, 914.4
    if sim_time < 150.0:
        return 2.0, 152.4, 1066.8
    return 3.0, 152.4, 1219.2


def compute_reward(
    ownship_state,
    target_state,
    ownship_damage: float,
    target_damage: float,
    geo_info,
    wez_config: dict,
    reward_config: dict,
    terminated: bool,
    truncated: bool,
    end_condition: str,
) -> tuple[float, dict]:
    cfg = reward_config
    c: dict[str, float] = {"step": float(cfg.get("step_penalty", -0.01))}

    dist = float(geo_info._get_distance(ownship_state, target_state))
    # Los_Degree(BT)와 수학적으로 동일한 ATA. WEZ 판정의 주축이다.
    my_ata = float(geo_info._get_antenna_train_angle(ownship_state, target_state, False))
    en_ata = float(geo_info._get_antenna_train_angle(target_state, ownship_state, False))
    sim_t = float(ownship_state[StateIndex.SIM_TIME])
    own_alt = float(ownship_state[StateIndex.ALT])
    own_kcas = float(ownship_state[StateIndex.KCAS])

    cone, r_min, r_max = _wez_window(sim_t)
    in_range = (r_min <= dist <= r_max)

    # ── 1. 실제 데미지 (가장 큰 신호) ─────────────────────────────────────
    c["dmg_dealt"] = float(target_damage) * float(cfg.get("damage_dealt_scale", 300.0))
    c["dmg_recv"] = float(ownship_damage) * float(cfg.get("damage_recv_scale", -450.0))

    # ── 2. ATA shaping — 각도가 병목이다 ────────────────────────────────
    # BT 실측: 사거리 안 25초인데 ATA<5도는 2.99초. 거리가 아니라 각도가 막는다.
    # 180도에서 0, 0도에서 1. 사거리 안이면 두 배 (멀리서 겨누는 건 의미가 적다).
    ata_term = max(0.0, 1.0 - my_ata / 180.0) ** 2
    c["ata"] = ata_term * float(cfg.get("ata_scale", 0.10)) * (2.0 if in_range else 1.0)

    # ── 3. 사거리 shaping ───────────────────────────────────────────────
    rs = float(cfg.get("range_scale", 0.03))
    if dist < r_min:
        # 최소사거리 미만은 데미지가 안 난다 (교범 최근접 금지 305m와도 일치)
        c["range"] = -rs
    elif in_range:
        c["range"] = rs
    else:
        c["range"] = rs * max(0.0, 1.0 - (dist - r_max) / 3000.0)

    # ── 4. WEZ 유지 보너스 — 콘 안에 있는 매 틱 ─────────────────────────
    c["wez_hold"] = (float(cfg.get("wez_hold_bonus", 0.30))
                     if (in_range and my_ata <= cone) else 0.0)

    # ── 5. 코너속도 — A-4 실측 CAS 350kt ────────────────────────────────
    # BT는 코너 미만 체류 97.6%였다. 벗어난 만큼 벌점.
    c["corner"] = -abs(own_kcas - _CORNER_KCAS_MS) / _CORNER_KCAS_MS \
        * float(cfg.get("corner_scale", 0.02))

    # ── 6. 저고도 — 녹아웃 304.8m 기준 ──────────────────────────────────
    lo = float(cfg.get("low_alt_start_m", 800.0))
    if own_alt < lo:
        margin = max(0.0, own_alt - _KNOCKOUT_ALT_M)
        span = max(1.0, lo - _KNOCKOUT_ALT_M)
        c["low_alt"] = (1.0 - margin / span) * float(cfg.get("low_alt_scale", -0.15))
    else:
        c["low_alt"] = 0.0

    # ── 7. 교착 억제 — 양측 고ATA로 서로 못 쏘는 상태 ───────────────────
    st = float(cfg.get("stalemate_ata_deg", 60.0))
    c["stalemate"] = (float(cfg.get("stalemate_scale", -0.02))
                      if (my_ata > st and en_ata > st) else 0.0)

    # ── 8. 종결 ─────────────────────────────────────────────────────────
    term = 0.0
    if terminated or truncated:
        own_h = float(ownship_state[StateIndex.HEALTH])
        tgt_h = float(target_state[StateIndex.HEALTH])
        ec = (end_condition or "").lower()
        # 추락은 패배보다 비싸다. 체력이 남았는데 끝났으면 고도 이탈이다.
        crashed = (("altitude" in ec or "crash" in ec) and own_h > 0.0) \
            or own_alt < _KNOCKOUT_ALT_M
        if crashed:
            term = float(cfg.get("crash_penalty", -400.0))
        elif tgt_h <= 0.0 < own_h:
            term = float(cfg.get("win_reward", 200.0))
        elif own_h <= 0.0 < tgt_h:
            term = float(cfg.get("loss_reward", -200.0))
        else:
            term = float(cfg.get("draw_reward", -20.0))
    c["terminal"] = term

    return float(sum(c.values())), c


__all__ = ["MY_REWARD_CONFIG", "compute_reward"]
