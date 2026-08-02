"""MatchRunner — 같은 시드로 N판을 in-process로 돌려 통계를 뽑는다.

CLI(`run_local_dogfight.py`)를 쓰지 않고 직접 env를 다루는 이유:
  1. **시드 제어** — `env.reset(seed=N)`은 존재하지만 CLI에 노출돼 있지 않다.
     같은 시드 = 같은 초기조건이라야 두 빌드를 페어 비교할 수 있다
  2. **info 회수** — `env.step()`의 info에 outcome/ep_wez_steps/final_ata_deg 등이
     들어 있는데 CLI가 전부 버린다
  3. **BT 리셋** — 판 사이 `RunningTime` 오염을 고치려면 provider를 우리가 쥐어야 한다
     (probe.RecordingBTProvider 참조)
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np

_RELEASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RELEASE_DIR not in sys.path:
    sys.path.insert(0, _RELEASE_DIR)
_SRC_DIR = os.path.join(_RELEASE_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from dogfight.envs.single_agent_env import DogFightEnv  # noqa: E402

from . import wez as W  # noqa: E402
from .probe import RecordingBTProvider  # noqa: E402
from .result import MatchResult  # noqa: E402

# 교착 판정: 서로 못 물고 원만 그리는 상태
STALEMATE_MIN_DIST_M = 800.0
STALEMATE_MAX_DIST_M = 3000.0
STALEMATE_ATA_DEG = 60.0
LOW_ALT_WATCH_M = 600.0


@dataclass
class SideSpec:
    """한쪽 기체의 빌드 지정."""

    dll: str
    xml: str | None = None
    label: str = ""

    def make_provider(self) -> RecordingBTProvider:
        return RecordingBTProvider(dll_name=self.dll, rule_xml_path=self.xml)


class MatchRunner:
    """env 하나를 만들어 여러 판을 돌린다.

    env/DLL 생성 비용이 크므로 판마다 새로 만들지 않는다. 대신 provider가 판 사이에
    BT를 재생성해 상태 이월을 끊는다.
    """

    def __init__(
        self,
        ownship: SideSpec,
        target: SideSpec,
        *,
        max_engage_time: float = W.MATCH_DURATION_S,
        artifacts_dir: str | None = None,
        tick_sink: Callable[[int, dict], None] | None = None,
    ):
        self.ownship = ownship
        self.target = target
        self.tick_sink = tick_sink

        self._own_provider = ownship.make_provider()
        self._tgt_provider = target.make_provider()

        env_config = {
            "max_engage_time": float(max_engage_time),
            # 60Hz × 200s = 12000 틱. 여유를 둬서 시간초과가 step limit보다 먼저 걸리게 한다
            "episode_step_limit": 12200,
            # ★ 대회 공식 녹아웃 고도. env 기본값 300.0을 쓰면 302m로 살아남은 판을
            #   생존으로 집계해 추락을 과소평가한다
            "min_altitude": W.KNOCKOUT_ALT_M,
            "step_ratio": 1,  # 1 env step = 1 sim tick(60Hz). 서버와 같은 해상도
            "initial_scenario": {"mode": "default"},  # IC는 하네스가 직접 만든다
            "ownship_control_mode": "behavior_tree",
            "target_mode": "behavior_tree",
            "artifacts_dir": artifacts_dir or os.path.join(_RELEASE_DIR, "artifacts", "logs"),
        }
        self.env = DogFightEnv(
            env_config=env_config,
            ownship_action_provider=self._own_provider,
            target_action_provider=self._tgt_provider,
        )
        self._dt = 1.0 / float(self.env._sim_hz)
        self._noop_action = np.zeros(4, dtype=np.float32)

    # ------------------------------------------------------------------ #

    def run_match(self, match_index: int, seed: int, ic) -> MatchResult:
        """한 판 실행. `ic`는 scenarios.InitialCondition (None이면 env 기본 배치)."""
        res = MatchResult(
            match_index=match_index,
            seed=seed,
            family=getattr(ic, "family", "default"),
            ic=ic.as_dict() if ic is not None else {},
            own_dll=self.ownship.dll,
            own_xml=self.ownship.xml or "",
            target_dll=self.target.dll,
            target_xml=self.target.xml or "",
        )
        t0 = time.perf_counter()
        try:
            self._run_match_inner(res, seed, ic)
        except Exception as exc:  # 한 판 실패가 전체 런을 죽이지 않게
            res.error = f"{type(exc).__name__}: {exc}"
            res.outcome = "error"
        res.wall_clock_s = time.perf_counter() - t0
        return res

    def _run_match_inner(self, res: MatchResult, seed: int, ic) -> None:
        env = self.env
        if ic is not None:
            ic.apply(env)

        env.reset(seed=seed)
        geo = env._geo_info

        counter = W.WezCounter(self._dt)
        min_alt = float("inf")
        min_speed = float("inf")
        min_energy = float("inf")
        energy_adv_sum = 0.0
        ticks_below = 0
        stalemate_run = 0
        stalemate_best = 0
        task_hist: dict[str, int] = {}
        task_run = 0
        task_best = 0
        prev_task = None
        info: dict = {}
        ticks = 0

        while True:
            _obs, _r, terminated, truncated, info = env.step(self._noop_action)
            ticks += 1

            own = env.get_ownship_state()
            tgt = env.get_target_state()
            sim_t = float(own[W.IDX_SIM_TIME])

            dist = float(geo._get_distance(own, tgt))
            my_ata = W.ata_deg(geo, own, tgt)
            en_ata = W.ata_deg(geo, tgt, own)
            counter.update(sim_t, my_ata, en_ata, dist)

            alt = float(own[W.IDX_ALT])
            own_spd = float(np.linalg.norm(own[6:9]))
            tgt_spd = float(np.linalg.norm(tgt[6:9]))
            own_e = W.specific_energy_m(own, own_spd)
            energy_adv_sum += own_e - W.specific_energy_m(tgt, tgt_spd)

            min_alt = min(min_alt, alt)
            min_speed = min(min_speed, own_spd)
            min_energy = min(min_energy, own_e)
            if alt < LOW_ALT_WATCH_M:
                ticks_below += 1

            if (STALEMATE_MIN_DIST_M < dist < STALEMATE_MAX_DIST_M
                    and my_ata > STALEMATE_ATA_DEG and en_ata > STALEMATE_ATA_DEG):
                stalemate_run += 1
                stalemate_best = max(stalemate_best, stalemate_run)
            else:
                stalemate_run = 0

            # 기본 BTActionProvider에는 last_task가 없다(비교 테스트에서 바꿔 끼울 수 있음)
            task = getattr(self._own_provider, "last_task", "") or "(none)"
            task_hist[task] = task_hist.get(task, 0) + 1
            if task == prev_task:
                task_run += 1
            else:
                task_run = 1
                prev_task = task
            task_best = max(task_best, task_run)

            if self.tick_sink is not None:
                # 원시 51-state도 같이 넘긴다 — KCAS/KTAS/Nz 등 진단 스크립트가
                # 필요로 하는 항목이 매번 달라서, 여기서 미리 고르지 않는다
                self.tick_sink(ticks, {
                    "t": sim_t, "dist": dist, "my_ata": my_ata, "en_ata": en_ata,
                    "own_alt": alt, "own_spd": own_spd, "own_energy": own_e,
                    "task": task, "hca": W.hca_deg(own, tgt),
                    "aspect_from_tail": W.aspect_from_tail_deg(geo, own, tgt),
                    "own_state": np.array(own, copy=True),
                    "tgt_state": np.array(tgt, copy=True),
                })

            if terminated or truncated:
                break

        end_condition = str(info.get("end_condition", ""))
        res.end_condition = end_condition
        res.env_outcome = str(info.get("outcome", ""))
        res.outcome = self._reclassify(end_condition, res.env_outcome, info)
        res.own_health_final = float(info.get("ownship_health", 1.0))
        res.tgt_health_final = float(info.get("target_health", 1.0))
        res.sim_time_s = float(env.get_ownship_state()[W.IDX_SIM_TIME])
        res.ticks = ticks

        for key, value in counter.as_dict().items():
            setattr(res, key, value)

        res.crashed = end_condition == "ownship altitude below min"
        res.enemy_crashed = end_condition == "target altitude below min"
        res.min_own_alt_m = 0.0 if min_alt == float("inf") else min_alt
        res.min_alt_margin_m = res.min_own_alt_m - W.KNOCKOUT_ALT_M
        res.ticks_below_600m = ticks_below
        res.stalemate_ticks = stalemate_best
        res.max_task_run = task_best
        res.task_hist = task_hist
        res.min_own_speed_ms = 0.0 if min_speed == float("inf") else min_speed
        res.min_own_energy_m = 0.0 if min_energy == float("inf") else min_energy
        res.mean_energy_advantage_m = energy_adv_sum / max(ticks, 1)

    @staticmethod
    def _reclassify(end_condition: str, env_outcome: str, info: dict) -> str:
        """env의 `_classify_outcome`은 **적 추락을 draw로 분류**한다.

        `single_agent_env.py:406-415`를 보면 crash 판정이 ownship 조건만 보고,
        적이 지면에 박은 경우 healths가 둘 다 양수라 draw로 떨어진다.
        우리 기준으로는 명백한 승리이므로 되살린다.
        """
        if end_condition == "target altitude below min":
            return "win_enemy_crash"
        if end_condition == "ownship altitude below min":
            return "crash"
        return env_outcome or "unknown"

    def close(self) -> None:
        try:
            self.env.close()
        except Exception:
            pass
        for provider in (self._own_provider, self._tgt_provider):
            try:
                provider.close()
            except Exception:
                pass


def run_series(
    runner: MatchRunner,
    seeds: Iterable[int],
    ic_factory: Callable[[int], object] | None = None,
    *,
    progress: bool = True,
) -> list[MatchResult]:
    results: list[MatchResult] = []
    for i, seed in enumerate(seeds):
        ic = ic_factory(seed) if ic_factory is not None else None
        res = runner.run_match(i, seed, ic)
        results.append(res)
        if progress:
            print(
                f"[{i:3d}] seed={seed:<7} {res.family:<12} {res.outcome:<16} "
                f"wez={res.wez_dealt_ticks:<5} recv={res.wez_recv_ticks:<5} "
                f"minAlt={res.min_own_alt_m:7.1f} {res.wall_clock_s:5.1f}s"
                + (f"  ERR={res.error}" if res.error else ""),
                flush=True,
            )
    return results
