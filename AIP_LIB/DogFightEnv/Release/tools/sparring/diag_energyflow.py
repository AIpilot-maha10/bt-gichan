"""에너지 행방 진단 — 풀스로틀에 저G인데 왜 CAS 212kt인가.

diag_wastedpull 결과 (vs jegalmin, 10판):
  당김 15.3% / **헛당김 0.0%** / CAS 중앙 212kt / 코너 미만 98.8% / Nz 중앙 2.54G
-> "과도한 당김이 에너지를 태운다"는 설명이 죽었다. 태울 G가 애초에 없다.

풀스로틀(CornerHoldThrottle은 TAS 185 미만이면 1.0을 낸다)에 저G인데도 느리면
남는 설명은 **상승으로 빠져나간다**뿐이다. 추측하지 말고 잰다.

동시에 확인할 것: **적도 같이 느린가.** 둘 다 212kt면 상호 저에너지 교착이고
(양측 무득점 = shutout 80%와 정합), 나만 느리면 내 문제다. 처방이 완전히 달라진다.

51-state에서 양측 실측값을 그대로 쓴다 (추정 안 함):
  idx12 KCAS(m/s)  idx27 KTAS(m/s)  idx44 Alt(m)  idx31 Nz(G)  idx21 스로틀명령

실행: python tools/sparring/diag_energyflow.py [판수]
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
MS_TO_KT = 1.0 / 0.51444
G = 9.80665
BINS = [(0, 25), (25, 50), (50, 100), (100, 150), (150, 200)]

I_KCAS, I_THR, I_NZ, I_ALT = 12, 21, 31, 44


def run(opp: str, tag: str):
    acc = {b: [] for b in BINS}
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag))
    rows: list[dict] = []
    runner.tick_sink = lambda i, d: rows.append(d)
    try:
        for i in range(N):
            seed = 50_000 + i
            rows.clear()
            runner.run_match(i, seed, make_ic(seed))
            if not rows:
                continue
            own = np.array([r["own_state"] for r in rows])
            tgt = np.array([r["tgt_state"] for r in rows])
            t = np.array([r["t"] for r in rows])
            for b in BINS:
                m = (t >= b[0]) & (t < b[1])
                if m.sum() < 10:
                    continue
                acc[b].append({
                    "my_cas": np.median(own[m, I_KCAS]) * MS_TO_KT,
                    "en_cas": np.median(tgt[m, I_KCAS]) * MS_TO_KT,
                    "my_alt": np.median(own[m, I_ALT]),
                    "en_alt": np.median(tgt[m, I_ALT]),
                    "my_thr": np.median(own[m, I_THR]),
                    "my_nz": np.median(np.abs(own[m, I_NZ])),
                    "en_nz": np.median(np.abs(tgt[m, I_NZ])),
                    # 비에너지 Es = h + v^2/2g  (TAS 기준이라 체축속도 크기를 쓴다)
                    "my_es": np.median(own[m, I_ALT] + np.linalg.norm(own[m, 6:9], axis=1) ** 2 / (2 * G)),
                    "en_es": np.median(tgt[m, I_ALT] + np.linalg.norm(tgt[m, 6:9], axis=1) ** 2 / (2 * G)),
                })
    finally:
        runner.close()
    return acc


def report(tag: str, acc):
    print(f"\n{'='*84}\n{tag}\n{'='*84}")
    print(f"  {'구간(초)':>10}{'내CAS':>8}{'적CAS':>8}{'내고도':>9}{'적고도':>9}"
          f"{'내스로틀':>10}{'내Nz':>7}{'적Nz':>7}{'내Es':>9}{'적Es':>9}")
    for b in BINS:
        d = acc[b]
        if not d:
            continue
        def m(k):
            return float(np.mean([x[k] for x in d]))
        print(f"  {b[0]:4d}-{b[1]:<5d}{m('my_cas'):8.0f}{m('en_cas'):8.0f}"
              f"{m('my_alt'):9.0f}{m('en_alt'):9.0f}{m('my_thr'):10.2f}"
              f"{m('my_nz'):7.2f}{m('en_nz'):7.2f}{m('my_es'):9.0f}{m('en_es'):9.0f}")


print(f"에너지 행방 진단 — {N}판씩, 시드 50000~  (51-state 실측, 추정 없음)")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll, tag))

print("\n읽는 법:")
print("  · 적 CAS도 같이 낮으면 -> 상호 저에너지 교착 (내 문제가 아니다)")
print("  · 내 고도만 올라가면   -> 에너지가 상승으로 빠진다")
print("  · 스로틀이 1.0인데 CAS가 안 오르면 -> 항력(유도항력 or 자세)이 범인")
