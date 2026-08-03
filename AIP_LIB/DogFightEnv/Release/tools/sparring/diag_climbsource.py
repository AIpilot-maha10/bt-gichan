"""상승의 출처 진단 — VP가 위에 있어서 올라가는가?

diag_energyflow 결과 (vs jegalmin, 8판):
  고도 5,230 -> 8,622m 단조 상승 / CAS 298 -> 189kt / **Es는 6,309 -> 9,779로 증가**
-> 에너지를 잃는 게 아니라 전부 고도로 저장하고 속도로 안 쓴다.

조치를 만들기 전에 **왜 올라가는지**를 확정한다. 후보:
  (ㄱ) VP가 내 위에 있다 -> 추적점을 따라 올라간다   ... VP 클램프로 고칠 수 있다
  (ㄴ) VP는 아래인데 올라간다 -> 자세·제어기 문제     ... VP 클램프는 무효
  (ㄷ) 적을 따라간다 (적이 먼저 올라간다)             ... 따라가지 않는 판단이 필요

세 번째가 특히 중요하다 - 교범 §4.2.3은 에너지를 ①공격이익 ②방어필요 ③머지준비
에만 쓰라고 한다. 쏠 가망 없이(WEZ 0.24s) 기수 맞추려 따라 올라가는 건 그 어디에도 없다.

실행: python tools/sparring/diag_climbsource.py [판수]
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
T_LO, T_HI = 50.0, 200.0     # 상승이 일어나는 구간
I_ALT = 44


def run(opp: str, tag: str):
    out = []
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            seed = 50_000 + i
            rows.clear()
            runner.run_match(i, seed, make_ic(seed))
            sel = [r for r in rows if T_LO <= r["t"] < T_HI and r.get("bt")]
            if len(sel) < 100:
                continue
            own = np.array([r["own_state"] for r in sel])
            tgt = np.array([r["tgt_state"] for r in sel])
            vpz = np.array([r["bt"].get("bt_vp_z", np.nan) for r in sel])
            myz = np.array([r["bt"].get("bt_my_z", np.nan) for r in sel])
            ok = np.isfinite(vpz) & np.isfinite(myz)
            if ok.sum() < 100:
                continue
            dz = vpz[ok] - myz[ok]              # VP가 나보다 얼마나 위인가
            myalt, enalt = own[ok, I_ALT], tgt[ok, I_ALT]
            tasks = [r["task"] for r in sel]

            # 내가 올라가는 구간에서 적도 위에 있는가
            climbing = np.gradient(myalt) > 0
            task_when_climb = {}
            for tk, c in zip(tasks[:len(climbing)], climbing):
                if c:
                    task_when_climb[tk] = task_when_climb.get(tk, 0) + 1
            tot = max(sum(task_when_climb.values()), 1)
            top = sorted(task_when_climb.items(), key=lambda x: -x[1])[:3]

            out.append({
                "seed": seed,
                "vp_above_pct": 100.0 * (dz > 0).mean(),
                "dz_med": float(np.median(dz)),
                "alt_gain": float(myalt[-1] - myalt[0]),
                "en_above_pct": 100.0 * (enalt > myalt).mean(),
                "en_alt_gain": float(enalt[-1] - enalt[0]),
                "top_tasks": ", ".join(f"{k} {100*v/tot:.0f}%" for k, v in top),
            })
    finally:
        runner.close()
    return out


def report(tag: str, d):
    print(f"\n{'='*90}\n{tag}   (t={T_LO:.0f}~{T_HI:.0f}초)\n{'='*90}")
    if not d:
        print("  표본 없음")
        return
    print(f"  {'시드':>6}{'VP가위%':>9}{'VP-나(m)':>10}{'내고도증가':>11}"
          f"{'적이위%':>9}{'적고도증가':>11}   상승중 Task")
    for a in d:
        print(f"  {a['seed']:>6}{a['vp_above_pct']:9.1f}{a['dz_med']:10.0f}"
              f"{a['alt_gain']:11.0f}{a['en_above_pct']:9.1f}{a['en_alt_gain']:11.0f}"
              f"   {a['top_tasks']}")

    def m(k):
        return float(np.mean([x[k] for x in d]))
    print(f"\n  평균: VP가 내 위 {m('vp_above_pct'):.1f}%  (중앙 {m('dz_med'):+.0f}m)"
          f"   내 고도증가 {m('alt_gain'):+.0f}m")
    print(f"        적이 나보다 위 {m('en_above_pct'):.1f}%   적 고도증가 {m('en_alt_gain'):+.0f}m")


print(f"상승 출처 진단 — {N}판씩, 시드 50000~")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대 - 대조군)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll, tag))

print("\n판정:")
print("  VP가 위 비율이 높다        -> VP 클램프가 유효한 지렛대")
print("  VP는 아래인데 올라간다     -> 제어기/자세 문제. VP 클램프 무효")
print("  적이 먼저·더 올라간다      -> '따라가지 않는' 판단이 필요 (교범 §4.2.3)")
