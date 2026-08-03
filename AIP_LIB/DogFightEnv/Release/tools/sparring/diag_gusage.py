"""G 사용 진단 — 돌아야 할 때 실제로 당기고 있는가.

EP26 후 (vs jegalmin, 150-200s):
  나        CAS 355kt(=실측 코너) / TAS 212 / **Nz 4.21G** / 선회율 10.8°/s
  jegalmin  CAS 510kt            / TAS 308 / **Nz 6.86G** / 선회율 12.4°/s

코너속도의 F-16이면 4.2G보다 훨씬 더 당길 수 있다. 에너지는 확보했는데
기수위치로 전환하지 않고 있다 — 교범 §4.2.3 "Energy versus Nose Position".

재는 것: **ATA(기수 오차)가 클 때 Nz가 올라가는가.**
  · ATA가 큰데 Nz가 낮다 -> 당길 수 있는데 안 당긴다 (VP/제어기가 요구를 안 만든다)
  · ATA가 큰데 Nz도 높다 -> 이미 최대다. 남은 건 속도뿐
적과 나란히 비교해 "같은 각오차에서 누가 더 당기는가"를 본다.

⚠️ EP19(VP 언로드로 G를 **낮추는** 조치)는 기각됐다. 이건 반대 방향 가설이고,
   그때는 지표가 없어 확인할 수 없었다. 지금은 잰다.

실행: python tools/sparring/diag_gusage.py [판수]
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
I_KCAS, I_NZ, I_ALT = 12, 31, 44
ATA_BINS = [(0, 10), (10, 30), (30, 60), (60, 90), (90, 180)]


def run(opp: str, tag: str):
    rows: list[dict] = []
    keep: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            rows.clear()
            runner.run_match(i, 50_000 + i, make_ic(50_000 + i))
            keep.extend({"my_ata": r["my_ata"], "en_ata": r["en_ata"],
                         "own": r["own_state"], "tgt": r["tgt_state"],
                         "task": r["task"]} for r in rows)
    finally:
        runner.close()
    return keep


def report(tag: str, d):
    print(f"\n{'='*80}\n{tag}   ({len(d)}틱)\n{'='*80}")
    if not d:
        print("  표본 없음")
        return
    myata = np.array([x["my_ata"] for x in d])
    enata = np.array([x["en_ata"] for x in d])
    own = np.array([x["own"] for x in d])
    tgt = np.array([x["tgt"] for x in d])
    mynz = np.abs(own[:, I_NZ])
    ennz = np.abs(tgt[:, I_NZ])
    mycas = own[:, I_KCAS] * MS_TO_KT

    print(f"  {'내 ATA(도)':>12}{'비중%':>8}{'내Nz중앙':>10}{'내Nz p90':>10}"
          f"{'내CAS':>8}{'>6G 비율%':>11}")
    for lo, hi in ATA_BINS:
        m = (myata >= lo) & (myata < hi)
        if m.sum() < 50:
            continue
        print(f"  {lo:5d}-{hi:<6d}{100*m.mean():8.1f}{np.median(mynz[m]):10.2f}"
              f"{np.percentile(mynz[m], 90):10.2f}{np.median(mycas[m]):8.0f}"
              f"{100*(mynz[m] > 6.0).mean():11.1f}")

    # 같은 "각오차 큼" 상황에서 나 vs 적
    need = myata > 60.0        # 내가 돌아야 하는 상황
    eneed = enata > 60.0       # 적이 돌아야 하는 상황
    print(f"\n  ── 돌아야 하는 상황(ATA>60°)에서의 G ──")
    if need.sum() > 50:
        print(f"  나  체류 {100*need.mean():5.1f}%  Nz 중앙 {np.median(mynz[need]):5.2f}"
              f"  p90 {np.percentile(mynz[need],90):5.2f}  >6G {100*(mynz[need]>6).mean():5.1f}%"
              f"  CAS {np.median(mycas[need]):4.0f}kt")
    if eneed.sum() > 50:
        print(f"  적  체류 {100*eneed.mean():5.1f}%  Nz 중앙 {np.median(ennz[eneed]):5.2f}"
              f"  p90 {np.percentile(ennz[eneed],90):5.2f}  >6G {100*(ennz[eneed]>6).mean():5.1f}%")
    print(f"\n  전체 Nz  나 중앙 {np.median(mynz):.2f} p90 {np.percentile(mynz,90):.2f}"
          f"  |  적 중앙 {np.median(ennz):.2f} p90 {np.percentile(ennz,90):.2f}")


print(f"G 사용 진단 — {N}판씩, 시드 50000~ (EP26 적용본)")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll, tag))

print("\n판정: ATA>60°인데 Nz가 낮고 p90도 낮다 -> 당길 수 있는데 안 당긴다.")
print("      p90이 이미 높다면 순간적으로는 당기고 있다 = 지속성 문제다.")
