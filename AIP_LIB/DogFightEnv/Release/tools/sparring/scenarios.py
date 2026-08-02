"""초기조건(IC) 생성 — 하네스가 직접 만든다.

## 왜 env의 scenario 모드를 안 쓰는가

1. **`--scenario default`는 완전 결정론적**이다. 같은 판을 N번 돌려도 똑같아서 통계 표본이
   안 된다(3판 돌려 동일 결과가 나온 이유).
2. env의 랜덤 시나리오는 `env.np_random`을 쓰는데, 그 소비 순서가 env 내부 사정에 따라
   달라질 수 있다. **같은 시드 = 같은 초기조건**이 보장돼야 두 빌드를 페어 비교할 수 있다.

그래서 IC는 시드 전용 RNG(`default_rng(seed)`)로 여기서 만들고,
`env.change_init_position()`으로 직접 꽂는다. env는 `initial_scenario.mode="default"`로 두어
위치를 건드리지 않게 한다.

## 좌표 규약
`change_init_position(init_n, init_e, init_d, ...)` — NED. **`init_d`는 음수가 고도**다
(init_d=-7000 → 7000m). heading은 도(deg), 0=북.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

FT = 0.3048


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
                init_n=s.n,
                init_e=s.e,
                init_d=-s.alt_m,  # ★ 음수가 고도
                init_roll=s.roll_deg,
                init_pitch=s.pitch_deg,
                init_heading=s.heading_deg,
                init_speed=s.speed_ms,
            )

    def as_dict(self) -> dict:
        d = {"family": self.family, "note": self.note}
        for tag, s in (("own", self.own), ("tgt", self.tgt)):
            d.update({
                f"{tag}_n": round(s.n, 1), f"{tag}_e": round(s.e, 1),
                f"{tag}_alt": round(s.alt_m, 1), f"{tag}_hdg": round(s.heading_deg, 1),
                f"{tag}_spd": round(s.speed_ms, 1),
            })
        d["init_dist_m"] = round(float(np.hypot(self.own.n - self.tgt.n,
                                                self.own.e - self.tgt.e)), 1)
        d.update(self.meta)
        return d


def _wrap(deg: float) -> float:
    return float((deg + 180.0) % 360.0 - 180.0)


# --------------------------------------------------------------------------- #
# 패밀리별 생성기
# --------------------------------------------------------------------------- #

def make_preliminary(rng: np.random.Generator) -> InitialCondition:
    """대회 예선 포맷 — 측면(East축) 2,000~3,000ft 분리, 헤딩 180° 차이.

    정면 head-on이 아니라 나란히 어긋난 배치라 **적 획득용 turn-in이 먼저 필요**하다.
    근거: `single_agent_env._apply_preliminary_initial_scenario`
    """
    sep = float(rng.uniform(2000.0, 3000.0)) * FT
    alt = float(rng.choice([3000.0, 5000.0, 7000.0]))
    base = float(rng.uniform(-180.0, 180.0))
    spd_o = float(rng.uniform(200.0, 250.0))
    spd_t = float(rng.uniform(200.0, 250.0))
    half = sep / 2.0
    return InitialCondition(
        "preliminary",
        Side(0.0, -half, alt, _wrap(base), spd_o),
        Side(0.0, +half, alt, _wrap(base + 180.0), spd_t),
        note=f"abeam {sep:.0f}m @{alt:.0f}m",
    )


def make_ref_varied(rng: np.random.Generator) -> InitialCondition:
    """폭넓은 기하 — 거리·상대방위·헤딩·고도차를 넓게 흩뿌린다.

    특정 배치에 과적합되지 않게 하는 용도. 결과 편차가 가장 큰 패밀리라
    p20(하위 20% 분위수) 지표가 여기서 주로 결정된다.
    """
    rng_m = float(rng.uniform(1500.0, 6000.0))
    bearing = float(rng.uniform(-180.0, 180.0))
    alt_o = float(rng.uniform(4000.0, 8000.0))
    alt_t = alt_o + float(rng.uniform(-1500.0, 1500.0))
    return InitialCondition(
        "ref_varied",
        Side(0.0, 0.0, alt_o, float(rng.uniform(-180, 180)), float(rng.uniform(200, 300))),
        Side(rng_m * np.cos(np.radians(bearing)), rng_m * np.sin(np.radians(bearing)),
             max(alt_t, 1500.0), float(rng.uniform(-180, 180)), float(rng.uniform(200, 300))),
        note=f"r={rng_m:.0f}m brg={bearing:.0f}°",
    )


def make_two_circle(rng: np.random.Generator) -> InitialCondition:
    """레이트 교착을 **일부러** 유발한다 — 동고도 정면머지 + 고속.

    Day 1 진단에서 gichan은 HardTurn 77.6% / 교착 37.4초로 여기에 가장 취약했다.
    교리(§4.8.4.2.4.2.2)상 350kt 초과 머지는 2서클(레이트 싸움)로 간다.
    A의 TCX/Ease 사이클이 실제로 효과가 있는지 **가장 직접적으로 재는 패밀리**다.
    """
    sep = float(rng.uniform(3000.0, 6000.0)) * FT
    alt = float(rng.uniform(5000.0, 7000.0))
    base = float(rng.uniform(-180.0, 180.0))
    spd = float(rng.uniform(240.0, 290.0))  # >350kt CAS 급 → 2서클 유도
    off = float(rng.uniform(-300.0, 300.0))  # 완전 정면이면 퇴화하므로 살짝 어긋냄
    return InitialCondition(
        "two_circle",
        Side(-sep / 2.0, -off, alt, _wrap(base), spd),
        Side(+sep / 2.0, +off, alt, _wrap(base + 180.0), spd),
        note=f"headon {sep:.0f}m {spd:.0f}m/s",
    )


def make_adversarial(rng: np.random.Generator) -> InitialCondition:
    """불리한 시작 — 크래시·교착을 빨리 찾아내는 용도.

    셋 중 하나를 고른다:
      defensive : 적이 내 6시 600~1,200m (즉시 방어 국면)
      low_alt   : 1,200~1,800m 저고도 (PreventLandCrash·저고도 가드 시험)
      energy_dn : 내 속도가 적보다 80~120 m/s 낮음 (에너지 열세)
    """
    kind = str(rng.choice(["defensive", "low_alt", "energy_dn"]))
    base = float(rng.uniform(-180.0, 180.0))
    if kind == "defensive":
        alt = float(rng.uniform(4000.0, 6000.0))
        d = float(rng.uniform(600.0, 1200.0))
        # 적을 내 꼬리 뒤쪽에 같은 침로로 배치 → 적이 공격 위치
        rad = np.radians(base)
        own = Side(0.0, 0.0, alt, _wrap(base), float(rng.uniform(200, 250)))
        tgt = Side(-d * np.cos(rad), -d * np.sin(rad), alt,
                   _wrap(base), float(rng.uniform(240, 290)))
    elif kind == "low_alt":
        alt = float(rng.uniform(1200.0, 1800.0))
        sep = float(rng.uniform(1500.0, 3000.0))
        own = Side(0.0, 0.0, alt, _wrap(base), float(rng.uniform(200, 260)))
        tgt = Side(sep, float(rng.uniform(-500, 500)), alt,
                   _wrap(base + 180.0), float(rng.uniform(200, 260)))
    else:  # energy_dn
        alt = float(rng.uniform(4000.0, 7000.0))
        sep = float(rng.uniform(1500.0, 3500.0))
        tspd = float(rng.uniform(270.0, 300.0))
        own = Side(0.0, 0.0, alt, _wrap(base), tspd - float(rng.uniform(80.0, 120.0)))
        tgt = Side(sep, float(rng.uniform(-800, 800)), alt + float(rng.uniform(0, 800)),
                   _wrap(base + float(rng.uniform(120, 240))), tspd)
    return InitialCondition("adversarial", own, tgt, note=kind, meta={"adv_kind": kind})


# --------------------------------------------------------------------------- #

FAMILIES: dict[str, Callable[[np.random.Generator], InitialCondition]] = {
    "preliminary": make_preliminary,
    "ref_varied": make_ref_varied,
    "two_circle": make_two_circle,
    "adversarial": make_adversarial,
}

# 비중 — 대회 포맷을 가장 많이, 교착 유발과 불리한 시작으로 약점을 빨리 찾는다
WEIGHTS: dict[str, float] = {
    "preliminary": 0.35,
    "ref_varied": 0.30,
    "two_circle": 0.20,
    "adversarial": 0.15,
}


def make_ic(seed: int, family: str | None = None) -> InitialCondition:
    """시드 하나 → IC 하나. **같은 시드는 항상 같은 IC**(페어 비교의 전제).

    family를 주면 그 패밀리로 강제, 안 주면 시드로 가중 추첨한다.
    """
    rng = np.random.default_rng(seed)
    if family is None:
        names = list(WEIGHTS)
        probs = np.array([WEIGHTS[n] for n in names], dtype=float)
        family = str(rng.choice(names, p=probs / probs.sum()))
    return FAMILIES[family](rng)


def seed_list(count: int, base: int = 10_000) -> list[int]:
    """연속 시드. 확정 검증 때는 base를 바꿔 **겹치지 않는 시드**를 쓴다."""
    return [base + i for i in range(count)]


def balanced_seeds(per_family: int, base: int = 10_000) -> list[tuple[int, str]]:
    """패밀리별로 같은 수만큼 뽑는다 — 패밀리별 성능을 따로 보려면 이쪽."""
    out: list[tuple[int, str]] = []
    for fi, fam in enumerate(FAMILIES):
        for i in range(per_family):
            out.append((base + fi * 1000 + i, fam))
    return out
