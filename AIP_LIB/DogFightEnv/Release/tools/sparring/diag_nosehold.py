"""기수 확보 vs 유지 — 못 잡는가, 잡았다가 놓치는가.

diag_pullcmd로 병목이 "위치 확보"임이 확정됐다(당김 거동은 두 교전이 동일하고
이기는 쪽이 오히려 G가 낮다. 차이는 기수를 못 맞춘 상태의 체류 33.5% vs 63.4%).

그 안에서 다시 갈라야 처방이 나온다:
  (ㄱ) **못 잡는다**       — ATA<30도 진입 횟수 자체가 적다 -> 머지/진입 기하 문제
  (ㄴ) **잡았다가 놓친다** — 진입은 하는데 유지가 짧다     -> 오버슛/추적 유지 문제

재는 것: ATA<30도 구간의 **진입 횟수 / 구간당 지속시간 / 이탈 시 상황**.

실행: python tools/sparring/diag_nosehold.py [판수]
"""

from __future__ import annotations

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
from tools.sparring.scenarios import make_ic  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
DT = 1.0 / 60.0
ATA_IN = 30.0        # 이 아래면 "기수 확보"
MIN_RUN = 6          # 0.1초 미만 구간은 노이즈로 버린다


def run(opp: str, tag: str):
    per = []
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            rows.clear()
            runner.run_match(i, 50_000 + i, make_ic(50_000 + i))
            if len(rows) < 600:
                continue
            ata = np.array([r["my_ata"] for r in rows])
            dist = np.array([r["dist"] for r in rows])
            inr = ata < ATA_IN

            runs = []
            s = None
            for k, v in enumerate(inr):
                if v and s is None:
                    s = k
                elif not v and s is not None:
                    if k - s >= MIN_RUN:
                        runs.append((s, k))
                    s = None
            if s is not None and len(inr) - s >= MIN_RUN:
                runs.append((s, len(inr)))

            if not runs:
                per.append({"n": 0, "med": 0.0, "mx": 0.0, "tot": 0.0,
                            "exit_dist": np.nan, "exit_close": np.nan})
                continue

            lens = np.array([(b - a) * DT for a, b in runs])
            # 구간을 빠져나갈 때 거리 — 오버슛이면 가까운 거리에서 튕겨나간다
            ex_d, ex_c = [], []
            for a, b in runs:
                if b < len(dist):
                    ex_d.append(dist[b - 1])
                    # 구간 안에서 거리가 줄다가 늘면 오버슛 징후
                    seg = dist[a:b]
                    ex_c.append(1.0 if (len(seg) > 4 and seg[-1] > seg.min() + 50) else 0.0)
            per.append({
                "n": len(runs),
                "med": float(np.median(lens)),
                "mx": float(lens.max()),
                "tot": float(lens.sum()),
                "exit_dist": float(np.mean(ex_d)) if ex_d else np.nan,
                "exit_close": float(np.mean(ex_c)) if ex_c else np.nan,
            })
    finally:
        runner.close()
    return per


def report(tag: str, d):
    print(f"\n{'='*78}\n{tag}   ({len(d)}판)\n{'='*78}")
    if not d:
        print("  표본 없음")
        return

    def m(k):
        v = [x[k] for x in d if np.isfinite(x[k])]
        return float(np.mean(v)) if v else float("nan")

    print(f"  ATA<{ATA_IN:.0f}° 진입 횟수   판당 {m('n'):5.1f}회")
    print(f"  구간 지속시간          중앙 {m('med'):5.2f}s   최장 {m('mx'):5.2f}s")
    print(f"  총 확보시간            {m('tot'):5.1f}s")
    print(f"  이탈 시 거리           {m('exit_dist'):6.0f}m")
    print(f"  구간 내 최근접 후 벌어짐(오버슛 징후) {100*m('exit_close'):5.1f}%")


print(f"기수 확보 vs 유지 — {N}판씩, 시드 50000~ (현재 빌드)")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll, tag))

print("\n판정: 진입 횟수가 비슷한데 지속시간이 짧다 -> **잡았다가 놓친다**(유지 문제)")
print("      진입 횟수 자체가 적다                -> **못 잡는다**(머지/진입 기하 문제)")
