# -*- coding: utf-8 -*-
"""gichan 커리큘럼 — BT 트랙에서 확보한 상대들을 상단에 배치한다 (계획 D-3).

실행:
  python train_curriculum.py --stages-module student.my_curriculum

## ⚠️ 기본 상대(AIP_BASE_target)를 쓰지 않는 이유

`config.py` 기본값은 `target_behavior_dll = "AIP_BASE_target.dll"` 인데
**이 상대는 무기력하다.** 8/4 재확인: 양쪽 0승, 적체력 1.000.
원본 트리가 `Task_Empty`뿐이고 BT.CPP Fallback 버그로 아무것도 틱하지 않는다.
→ **빈 상대에게 학습하면 아무것도 못 배운다.** 반드시 실전 상대로 바꾼다.

## 쓸 수 있는 상대

`SingleAgentEnv._build_ai()`는 DLL만 받고 **rule XML을 못 넘긴다**
(`src/dogfight/envs/`는 수정 금지 영역이라 우회 불가).
따라서 상대는 **자기 기본 XML로 초기화되는 DLL만** 쓸 수 있다.

| DLL | 기본 XML | RL 상대 가능? |
|---|---|---|
| `AIP_BTJegal.dll` | `TopGunV2.xml` | ✅ |
| `AIP_jegalmin.dll` | `Rule.xml` | ✅ |
| `AIP_gichan.dll` | `Rule_gichan.xml` | ✅ (셀프플레이) |
| `AIP_gichan_v6/v1/coordfix.dll` | `Rule_gichan.xml` | ❌ A-1 노드가 없어 초기화 실패 |
| `AIP_BASE_target.dll` | `Rule_forTraining.xml` | ❌ 무기력 |

## 스테이지 설계 근거 (BT에서 배운 것)

- **btjegal 먼저, jegalmin 나중** — BT 기준 btjegal은 이기고(32/40) jegalmin은 무승부다.
  쉬운 상대에서 사격을 배우고 어려운 상대로 넘어간다.
- **초기조건은 예선 실측값** — 고도 4,572m, 분리 497m. 서버 97판 전수조사 결과이고
  학습·평가를 같은 분포로 맞춘다.
- **셀프플레이를 마지막에** — bt-v7.2를 이겨야 제출 가치가 있다.
- **추락은 전 스테이지 진급 차단 조건** (교범 §4.7: 추락 0 > 피격 최소 > WEZ).
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dogfight.ai.curriculum import CurriculumStage


# 산출물은 D드라이브로 (C 보호 — 캠페인 중 수십 GB까지 늘 수 있다)
_ARTIFACTS = {"artifacts_dir": r"D:\aipilot-artifacts\rl\gichan"}


def _stage(idx, name, desc, dll, steps, iters, adv, rand_r, reward=None):
    env = dict(_ARTIFACTS)
    if dll:
        env["target_behavior_dll"] = dll
    return CurriculumStage(
        index=idx,
        name=name,
        description=desc,
        target_mode="fixed" if dll is None else "behavior_tree",
        episode_step_limit=steps,
        max_iterations=iters,
        checkpoint_interval=25,       # 계획 D-4: native_checkpoint_frequency 25
        reward_overrides=reward or {},
        randomization={
            "enabled": True,
            "radius": rand_r,
            "r_roll": 10.0,
            "r_pitch": 8.0,
            "r_heading": 120.0,
        },
        advance_conditions=adv,
        advance_window=10,
        env_overrides=env,
    )


def get_stages() -> list[CurriculumStage]:
    return [
        # ── 0. 비행 생존 — 추락부터 없앤다 ────────────────────────────────
        # BT에서 가장 비싼 실패가 추락이었다. 여기서 못 잡으면 나머지가 무의미하다.
        _stage(
            0, "flight_survival", "고정 표적. 추락을 없애고 스로틀·고도 제어를 익힌다.",
            None, 3600, 150,
            {"crash_rate_max": 0.05},
            500.0,
            # 이 단계에선 교전 항목을 죽이고 생존에 집중
            {"damage_dealt_scale": 50.0, "stalemate_scale": 0.0},
        ),

        # ── 1. btjegal — 이길 수 있는 상대에서 사격을 배운다 ──────────────
        # BT 기준 32/40승. 사격 해법이 실제로 만들어지는 상대다.
        _stage(
            1, "vs_btjegal", "btjegal 상대. BT가 이기는 상대이므로 사격을 먼저 배운다.",
            "AIP_BTJegal.dll", 12200, 400,
            {"crash_rate_max": 0.05, "ep_wez_steps_min": 60.0},
            1200.0,
        ),

        # ── 2. jegalmin — BT가 못 뚫은 벽 ────────────────────────────────
        # BT는 여기서 무승부다(적체력 0.958). 병목은 **종말 추적 유지**로 규명됐다:
        # 확보는 되는데(진입 4.2회 > btjegal 3.6회) 유지가 3.5배 짧다(5.81s vs 20.13s).
        # 적이 Nz 6.03G 브레이크로 깬다. RL이 이걸 배울 수 있는지가 이 트랙의 핵심 질문이다.
        _stage(
            2, "vs_jegalmin", "jegalmin 상대. BT가 못 뚫은 벽 — 종말 추적 유지가 병목이다.",
            "AIP_jegalmin.dll", 12200, 600,
            {"crash_rate_max": 0.05, "win_rate_min": 0.15},
            1500.0,
            # 추적 유지가 목표이므로 콘 체류 보너스를 키운다
            {"wez_hold_bonus": 0.50},
        ),

        # ── 3. 셀프플레이 — bt-v7.2를 이겨야 제출 가치가 있다 ────────────
        _stage(
            3, "vs_gichan_bt", "현재 BT(bt-v7.2) 상대. 이걸 못 이기면 제출 가치가 없다.",
            "AIP_gichan.dll", 12200, 600,
            {"crash_rate_max": 0.03, "win_rate_min": 0.50},
            1500.0,
        ),
    ]


__all__ = ["get_stages"]
