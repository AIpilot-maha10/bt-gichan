"""★ RunningTime 회귀 테스트 — 하네스 신뢰성의 전제.

`Task_Tactical.cpp:74`가 `GetWez(bb->RunningTime)`으로 사격 창을 고르는데,
`RunningTime`은 블랙보드 생성자에서만 0이고 그 뒤로는 무한 누적된다.
기본 `BTActionProvider.reset()`이 no-op이라 **2판째부터 BT가 다른 Phase로 싸운다.**

이 테스트는 두 가지를 동시에 보인다:
  A) 기본 provider  → 같은 시드 연속 2판의 결과가 **달라야** 한다 (오염 존재 증명)
  B) Recording      → 같은 시드 연속 2판의 결과가 **같아야** 한다 (수정 확인)

B가 통과하지 않으면 이후 하네스가 내는 모든 숫자를 믿을 수 없다.

실행: python tools/sparring/test_bt_reset.py   (Release 폴더에서)
"""

from __future__ import annotations

import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_RELEASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _RELEASE)
sys.path.insert(0, os.path.join(_RELEASE, "src"))
os.chdir(_RELEASE)

from dogfight.ai.bt_action_provider import BTActionProvider  # noqa: E402
from tools.sparring.probe import RecordingBTProvider  # noqa: E402
from tools.sparring.runner import MatchRunner, SideSpec  # noqa: E402

# 70초 × 2판이면 오염 시 2판째가 t=70→140으로 Phase1→2 경계(100s)를 넘는다.
# 경계를 넘어야 전술이 실제로 갈리므로 이 길이가 필요하다.
MATCH_SECONDS = 70.0
SEED = 20260802

# 상대는 jegalmin. AIP_BASE_target.dll은 `./Rule_forTraining.xml`을 하드코딩으로 읽는데
# 그 파일이 우리 gichan 트리로 덮여 있어 현재 초기화에 실패한다(별도 수정 대상).
# jegalmin은 `./Rule.xml`(=Maha 트리)을 읽으며 그 파일은 정상이다.
OWN = SideSpec(dll="AIP_gichan.dll", xml="Rule_gichan.xml", label="gichan")
TGT = SideSpec(dll="AIP_jegalmin.dll", xml=None, label="jegalmin")


def fingerprint(res) -> tuple:
    """판을 식별하는 지문. 결정론적 실행이면 완전히 같아야 한다.

    task_hist를 포함하는 이유: RunningTime 오염은 `GetWez(RunningTime)`가 고르는
    사거리/콘을 바꾸고, 그것이 `inWezRange` 분기 → SnapShot/GunAim 선택을 바꾼다.
    WEZ 틱이 0인 판에서도 **전술 상태 분포**로는 차이가 드러난다.
    """
    return (
        res.outcome,
        res.wez_dealt_ticks,
        res.wez_recv_ticks,
        res.ticks,
        round(res.min_own_alt_m, 3),
        round(res.min_distance_m or -1.0, 3),
        round(res.min_ata_deg or -1.0, 4),
        tuple(sorted(res.task_hist.items())),
    )


def two_matches(provider_cls, tag: str):
    runner = MatchRunner(OWN, TGT, max_engage_time=MATCH_SECONDS)
    # provider 종류를 바꿔치기 (MatchRunner는 기본이 Recording)
    if provider_cls is BTActionProvider:
        for attr, spec in (("_own_provider", OWN), ("_tgt_provider", TGT)):
            old = getattr(runner, attr)
            try:
                old.close()
            except Exception:
                pass
            new = BTActionProvider(dll_name=spec.dll, rule_xml_path=spec.xml)
            setattr(runner, attr, new)
        runner.env._ownship_action_provider = runner._own_provider
        runner.env._target_action_provider = runner._tgt_provider
    try:
        r1 = runner.run_match(0, SEED, None)
        r2 = runner.run_match(1, SEED, None)
    finally:
        runner.close()
    f1, f2 = fingerprint(r1), fingerprint(r2)
    print(f"\n[{tag}]")
    print(f"  1판: {f1}")
    print(f"  2판: {f2}")
    if r1.error or r2.error:
        print(f"  ERROR: {r1.error} / {r2.error}")
    return f1, f2


print("=" * 70)
print(f"RunningTime 회귀 테스트 — {MATCH_SECONDS}초 × 2판, seed={SEED}")
print(f"ownship={OWN.dll}/{OWN.xml}  target={TGT.dll}")
print("=" * 70)

print("\n--- A) 기본 BTActionProvider (reset이 no-op) ---")
a1, a2 = two_matches(BTActionProvider, "기본 provider")
contaminated = a1 != a2

print("\n--- B) RecordingBTProvider (RemoveBT로 트리 재생성) ---")
b1, b2 = two_matches(RecordingBTProvider, "Recording provider")
fixed = b1 == b2

print("\n" + "=" * 70)
print(f"A) 기본 provider가 판 사이 오염되는가 : {'예 (오염 확인)' if contaminated else '아니오'}")
print(f"B) Recording이 재현성을 회복하는가   : {'예 (동일)' if fixed else '아니오 (여전히 다름)'}")

if not fixed:
    print("\nFAIL — 수정 후에도 연속 2판이 다르다. 이 상태로는 하네스 숫자를 믿을 수 없다.")
    sys.exit(1)

if not contaminated:
    print("\n주의 — 기본 provider에서도 차이가 안 나왔다.")
    print("      Recording은 정상이나, 오염을 이 길이/시나리오로는 드러내지 못했다.")
    print("      (판을 더 길게 하거나 Phase 경계를 확실히 넘기게 조정 필요)")
    sys.exit(2)

print("\nPASS — 오염 확인 + 수정 확인. 하네스 재현성 확보.")
