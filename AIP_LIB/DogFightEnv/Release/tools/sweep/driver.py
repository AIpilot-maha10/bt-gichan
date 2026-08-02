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
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--opponent", default="jegalmin")
    a = ap.parse_args()

    # 첫 다차원 격자. 단일 상수는 EP13/EP15에서 국소최적임이 확인됐으므로
    # **조합 효과**를 본다 (SnapShot 창 x 히스테리시스).
    grid = {
        "SnapShotAtaDeg": [30.0, 40.0, 50.0],
        "HoldTicks": [20.0, 30.0, 45.0],
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
