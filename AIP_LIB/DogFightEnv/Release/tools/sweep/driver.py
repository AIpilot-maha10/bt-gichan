"""스윕 드라이버 — 변형별 XML 생성 → 하네스 실행 → 랭킹.

## 점수 (위험회피형)

계획대로 **평균이 아니라 최악값 중심**이다. EP7에서 "평균은 3.8배인데 shutout은 악화"인
변형을 하마터면 채택할 뻔했다.

    variant_score = 0.5*평균 + 0.5*p20 − 300*추락율 − 50*shutout율

`0.5*평균 + 0.5*p20` 블렌드가 편차 문제를 직접 최적화한다.
추락 300은 어떤 WEZ 이득도 상쇄하지 못하게 하는 값이다.

실행: python -m tools.sweep.driver [--seeds N] [--opponent jegalmin]
"""

from __future__ import annotations

import argparse
import itertools
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
from tools.sparring.scenarios import make_ic, seed_list  # noqa: E402
from tools.sweep.xml_gen import write  # noqa: E402

OPPONENTS = {
    "jegalmin": SideSpec("AIP_jegalmin.dll", None, "jegalmin"),
    "btjegal": SideSpec("AIP_BTJegal.dll", None, "btjegal"),
}
XML_DIR = r"D:\aipilot-artifacts\sweep\xml"


def score(results) -> tuple[float, dict]:
    ok = [r for r in results if not r.error]
    if not ok:
        return -1e9, {}
    d = np.array([r.wez_dealt_ticks for r in ok], dtype=float) / 60.0
    crash = sum(1 for r in ok if r.crashed) / len(ok)
    shut = sum(1 for r in ok if r.shutout) / len(ok)
    s = 0.5 * d.mean() + 0.5 * np.percentile(d, 20) - 300.0 * crash - 50.0 * shut
    return s, {"mean": d.mean(), "p20": float(np.percentile(d, 20)),
               "max": d.max(), "crash": crash, "shutout": shut,
               "recv": sum(r.wez_recv_ticks for r in ok) / len(ok) / 60.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)   # 20판은 순위가 뒤집힌다(아래 주석)
    ap.add_argument("--opponent", default="jegalmin")
    a = ap.parse_args()

    # ⚠️ 표본 하한: **최소 30판/변형**. 20판은 순위를 뒤집는다.
    #   1차 3x3(20판): Hold45가 1위, Hold30(기준)은 5위로 나왔다
    #   2차 1차원(30판): Hold30이 1위, shutout이 30->45->60->90에서 50->63->70->73%로 단조
    #   즉 20판 랭킹은 노이즈였다. EP7(10판 3.8배 -> 75판 소멸)과 같은 함정.
    #
    # 확인된 최적값(변경 불필요):
    #   SnapShotAtaDeg = 40  (EP13: 25/60 둘 다 악화)
    #   HoldTicks      = 30  (위 2차 스윕)
    # ── 스윕 결과 요약 (전부 30판/변형, vs jegalmin) ──────────────────
    # 지금까지 **네 상수 모두 현재값이 최적**이었다. 기준 조합 score -24.25.
    #   SnapShotAtaDeg    25 / [40] / 60      -> 40 최적 (EP13)
    #   HoldTicks         20 / [30] / 45/60/90 -> 30 최적
    #   SnapShotRangeMul  1.0 / [1.15] / 1.35 -> 1.15 최적 (1.0과 거의 동률)
    #   HardTurnAtaDeg    35 / [45] / 55      -> 45 최적
    #
    # 반복 관찰: 평균이 높은 변형은 대개 shutout이 나쁘다(고편차).
    #   예) Snap1.35/Hard55 평균 5.38s(3.6배)인데 shutout 63% vs 기준 50%
    #   -> 점수식이 p20과 shutout에 가중치를 두는 이유다.
    #
    #   InterceptRangeM   2800 / [3500] / 4200 -> 3500 최적 (봉우리 뚜렷)
    #
    # ⚠️ 예선에서 **효과가 전혀 없는** 포트 2개 (9변형 전부 동일 결과):
    #   AltRecoverM    600/900/1200  - 예선 최저고도가 1,936m라 도달 자체를 안 한다
    #   DefBreakRangeM 1000/1400/1800 - DefensiveBreak가 0% 발동(피격 0.05s = 위협 없음)
    #   -> 예선 기준으로는 죽은 상수다. 다시 스윕하지 말 것.
    #      (저고도/방어 시나리오에서는 의미가 있을 수 있다)
    # 5차(마지막): 남은 두 상수.
    # AltRecoverM은 성격이 다르다 - 안전 여유를 실전 공간으로 바꾸는 시도다.
    # 녹아웃이 305m인데 900m에서 회복을 시작하면 595m를 안 쓰는 셈이다.
    # 낮추면 싸울 고도가 늘지만 추락 위험이 오른다 -> 점수식의 추락 -300이 잡아준다.
    #   GunAimRangeMul    1.3 / [1.5] / 1.8  -> 1.5 최적 (양쪽 shutout 73%/77%)
    #
    # ═══ 파라미터 연구 종결 (9포트 중 8개 탐색) ═══
    # **개선 여지 없음.** 6개 상수 전부 현재값이 최적, 2개는 예선에서 무효,
    # 1개(GunAimAtaDeg)는 SnapShot이 선점해 효과 없음.
    # v6의 손튜닝 상수들이 좌표 수정 후에도 국소 최적이다.
    #
    # ⚠️ 한계: 모든 스윕이 시드 10000번대다. 새 시드 50000번대 확정검증에서
    #    vs jegalmin shutout이 50% -> 80%로 나왔다(10000번대가 운이 좋았다).
    #    다만 6개 상수 전부 양방향 악화라는 일관된 패턴이라 시드 특이적일
    #    가능성은 낮다고 본다. 다시 스윕한다면 50000번대로 할 것.
    grid = {
        "GunAimRangeMul": [1.5],   # 재확인용 단일점. 새 축을 넣으려면 여기 수정
    }
    keys = list(grid)
    combos = list(itertools.product(*(grid[k] for k in keys)))
    seeds = seed_list(a.seeds, 10_000)
    print(f"변형 {len(combos)}개 x {len(seeds)}판 = {len(combos)*len(seeds)}판 "
          f"(약 {len(combos)*len(seeds)*11/60:.0f}분), vs {a.opponent}\n")

    rows = []
    for ci, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        tag = "_".join(f"{k[:4]}{v:g}" for k, v in params.items())
        xml = write(os.path.join(XML_DIR, f"{tag}.xml"), params)
        runner = MatchRunner(SideSpec("AIP_gichan.dll", xml, tag),
                            OPPONENTS[a.opponent])
        try:
            res = [runner.run_match(i, s, make_ic(s)) for i, s in enumerate(seeds)]
        finally:
            runner.close()
        sc, m = score(res)
        rows.append((sc, params, m))
        print(f"[{ci+1}/{len(combos)}] {tag:<22} score={sc:7.2f}  "
              f"평균 {m['mean']:5.2f}s  p20 {m['p20']:5.2f}s  "
              f"shutout {m['shutout']*100:3.0f}%  추락 {m['crash']*100:3.0f}%", flush=True)

    print("\n" + "=" * 72)
    print("랭킹 (score = 0.5*평균 + 0.5*p20 − 300*추락율 − 50*shutout율)")
    print("=" * 72)
    for sc, p, m in sorted(rows, key=lambda x: -x[0]):
        star = " ★기준" if p["SnapShotAtaDeg"] == 40.0 and p["HoldTicks"] == 30.0 else ""
        print(f"  {sc:7.2f}  {p}  평균{m['mean']:5.2f}s p20{m['p20']:5.2f}s "
              f"shutout{m['shutout']*100:3.0f}%{star}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
