"""추적을 놓치는 순간 — 적이 깨는가, 우리가 발산하는가.

diag_nosehold로 병목이 **추적 유지**임이 확정됐다
(ATA<30도 구간 지속: btjegal 20.13s vs jegalmin 5.81s, 진입 횟수는 오히려 더 많다).

그 안에서 다시 갈라야 처방이 나온다:
  (ㄱ) **적이 깬다**       — 이탈 직전 적 Nz가 치솟는다 -> 전술 설계 문제
                             (적의 브레이크를 예측/대응하는 로직이 필요)
  (ㄴ) **우리가 발산한다** — 적은 얌전한데 우리 ATA가 진동한다 -> 제어 감쇠 문제
                             (추적 루프 게인/지연 보상 문제)

재는 것: ATA<30도 구간을 빠져나가기 직전 2초 동안
  · 적 Nz의 최대/증가량      (적이 깨는가)
  · 내 ATA의 부호 반전 횟수  (내가 진동하는가)
  · 내 롤 명령의 부호 반전   (제어 진동인가)

실행: python tools/sparring/diag_trackbreak.py [판수]
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
ATA_IN = 30.0
MIN_RUN = 6
WIN = 120            # 이탈 직전 2초
I_LAT, I_NZ = 15, 31   # LatCtrlCmd(롤 명령), Nz


def sign_flips(x, dead=0.05):
    """부호 반전 횟수 (불감대 밖에서만 센다)."""
    s = np.sign(np.where(np.abs(x) < dead, 0.0, x))
    s = s[s != 0]
    return int((np.diff(s) != 0).sum()) if s.size > 1 else 0


def run(opp: str, tag: str):
    out = []
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
            own = np.array([r["own_state"] for r in rows])
            tgt = np.array([r["tgt_state"] for r in rows])
            inr = ata < ATA_IN

            s = None
            for k, v in enumerate(inr):
                if v and s is None:
                    s = k
                elif not v and s is not None:
                    if k - s >= MIN_RUN:
                        a = max(s, k - WIN)
                        enz = np.abs(tgt[a:k, I_NZ])
                        out.append({
                            # 적이 깨는가
                            "en_nz_max": float(enz.max()) if enz.size else np.nan,
                            "en_nz_rise": float(enz.max() - np.median(enz)) if enz.size else np.nan,
                            # 내가 진동하는가
                            "ata_flips": sign_flips(np.diff(ata[a:k])),
                            "roll_flips": sign_flips(own[a:k, I_LAT]),
                            "my_nz_med": float(np.median(np.abs(own[a:k, I_NZ]))),
                        })
                    s = None
    finally:
        runner.close()
    return out


def report(tag: str, d):
    print(f"\n{'='*76}\n{tag}   (이탈 {len(d)}회)\n{'='*76}")
    if not d:
        print("  표본 없음")
        return

    def m(k):
        v = [x[k] for x in d if np.isfinite(x[k])]
        return float(np.mean(v)) if v else float("nan")

    print(f"  ── 적이 깨는가 (이탈 직전 2초) ──")
    print(f"  적 Nz 최대      {m('en_nz_max'):5.2f}G")
    print(f"  적 Nz 상승폭    {m('en_nz_rise'):5.2f}G   (중앙 대비 최대)")
    print(f"\n  ── 내가 발산하는가 ──")
    print(f"  내 ATA 부호반전 {m('ata_flips'):5.1f}회/2초")
    print(f"  내 롤 부호반전  {m('roll_flips'):5.1f}회/2초")
    print(f"  내 Nz 중앙      {m('my_nz_med'):5.2f}G")


print(f"추적 파괴 원인 — {N}판씩, 시드 50000~ (bt-v7.2)")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll, tag))

print("\n판정: 적 Nz 상승폭이 크게 갈리면 -> **적이 깬다**(전술 설계 문제)")
print("      내 부호반전이 크게 갈리면   -> **우리가 발산한다**(제어 감쇠 문제)")
