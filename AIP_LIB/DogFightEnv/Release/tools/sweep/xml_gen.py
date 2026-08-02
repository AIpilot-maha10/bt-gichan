"""Rule XML 생성 — 재빌드 없이 전술 상수를 갈아끼운다.

## 왜

EP13/EP15에서 상수 하나를 바꿀 때마다 재빌드(1.5분)했고, 스윕 스크립트가
마지막 변형 DLL을 Release에 남기는 사고도 있었다(두 번 다 동일 시드 재측정으로 잡음).
XML만 바꾸면 빌드가 없고 DLL은 하나로 고정되므로 그 사고가 원천 차단된다.

## 함정 (vendored BehaviorTree.CPP v3)

  · **XML에 선언되지 않은 속성을 쓰면 `RuntimeError`** → `extern "C"` 경계를 넘어
    **하드 크래시**한다(ctypes). 그래서 `PARAMS`에 없는 키는 여기서 먼저 거부한다.
  · XML에서 생략하면 `InputPort` 3-arg 기본값이 주입된다 → 기존 XML 그대로 동작.
  · 포트 타입은 반드시 double/int. `getInput<float>`는 빈 Optional을 반환한다.
"""

from __future__ import annotations

import os

# 단일 진실원천 — Task_Tactical::providedPorts()와 **수동 동기화**해야 한다.
# 여기 없는 키를 넘기면 XML 생성 자체를 거부한다(하드 크래시 방지).
PARAMS: dict[str, float] = {
    "SnapShotAtaDeg": 40.0,     # EP13: 25/60 둘 다 악화 → 40이 최적
    "SnapShotRangeMul": 1.15,
    "GunAimAtaDeg": 22.0,       # EP15: 35는 도달 불가라 변화 없음
    "GunAimRangeMul": 1.5,
    "HardTurnAtaDeg": 45.0,
    "InterceptRangeM": 3500.0,
    "HoldTicks": 30.0,          # EP15: 12는 악화
    "AltRecoverM": 900.0,
    "DefBreakRangeM": 1400.0,
}

_TEMPLATE = """<root main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <SelectTarget name="SelectTarget" BB="{{BB}}"/>
      <DirectionVectorUpdate name="DirectionVectorUpdate" BB="{{BB}}"/>
      <DistanceUpdate name="DistanceUpdate" BB="{{BB}}"/>
      <CheckSight name="CheckSight" BB="{{BB}}"/>
      <AngleOffUpdate name="AngleOffUpdate" BB="{{BB}}"/>
      <AspectAngleUpdate name="AspectAngleUpdate" BB="{{BB}}"/>
      <Task_Tactical name="Tactical" BB="{{BB}}"{attrs}/>
    </Sequence>
  </BehaviorTree>
</root>
"""


def render(params: dict[str, float] | None = None) -> str:
    """params를 반영한 Rule XML 문자열. 기본값과 같은 키는 생략한다(기본값 주입에 맡김)."""
    params = params or {}
    unknown = set(params) - set(PARAMS)
    if unknown:
        raise ValueError(
            f"PARAMS에 없는 키: {sorted(unknown)} — XML에 미선언 속성을 쓰면 "
            f"BT가 RuntimeError를 내고 ctypes 경계에서 하드 크래시한다"
        )
    parts = []
    for k, v in params.items():
        if abs(float(v) - PARAMS[k]) > 1e-9:
            parts.append(f' {k}="{float(v):g}"')
    return _TEMPLATE.format(attrs="".join(parts))


def write(path: str, params: dict[str, float] | None = None) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(params))
    return os.path.abspath(path)
