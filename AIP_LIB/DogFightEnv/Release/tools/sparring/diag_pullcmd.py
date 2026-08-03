"""당김 명령 vs 실제 G — "못 당기는가" 안 당기는가".

jegalmin전 병목은 기수 지향 시간이다: 사거리 안 25초인데 ATA<5도가 2.99초뿐
(btjegal은 35.1초 / 44.40초). 그리고 ATA>60도(교전의 66.5%)에서
  나        Nz 중앙 3.87  p90 6.36  >6G 14.2%
  jegalmin  Nz 중앙 5.64  p90 7.85  >6G 46.1%
**p90이 6.36이니 당길 능력은 있는데 지속을 못 한다.**

이게 둘 중 무엇인지가 처방을 완전히 가른다:
  (ㄱ) **못 당긴다** — 명령은 포화인데 G가 안 나온다 = 속도/공력 한계
       -> 처방은 여전히 에너지 쪽. VP나 전술을 고쳐도 소용없다
  (ㄴ) **안 당긴다** — 명령이 포화가 아니다 = 제어기가 충분히 요구하지 않는다
       -> 처방은 VP 배치/제어 쪽. 에너지는 이미 충분하다

51-state에서 직접 읽는다 (추정 없음):
  idx17 LonCtrlCmd(-1~1, PitchUp +)  idx18 ElevatorPosition(deg)
  idx31 Nz(G)  idx13 AOA(deg)  idx12 KCAS(m/s)

실행: python tools/sparring/diag_pullcmd.py [판수]
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
I_KCAS, I_AOA, I_LON, I_ELEV, I_NZ = 12, 13, 17, 18, 31
SAT = 0.9          # |명령|이 이 위면 포화로 본다
NEED_TURN_ATA = 60.0


def run(opp: str, tag: str):
    keep = []
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    try:
        for i in range(N):
            rows.clear()
            runner.run_match(i, 50_000 + i, make_ic(50_000 + i))
            keep.extend({"my_ata": r["my_ata"], "own": r["own_state"]} for r in rows)
    finally:
        runner.close()
    return keep


def report(tag: str, d):
    print(f"\n{'='*80}\n{tag}   ({len(d)}틱)\n{'='*80}")
    if not d:
        print("  표본 없음")
        return
    ata = np.array([x["my_ata"] for x in d])
    own = np.array([x["own"] for x in d])
    lon = own[:, I_LON]
    nz = np.abs(own[:, I_NZ])
    aoa = own[:, I_AOA]
    cas = own[:, I_KCAS] * MS_TO_KT
    elev = own[:, I_ELEV]

    need = ata > NEED_TURN_ATA          # 돌아야 하는 상황
    if need.sum() < 100:
        print("  '돌아야 하는' 표본이 부족하다")
        return

    # PitchUp이 + 인지 - 인지는 규약에 달렸다. 둘 다 찍어 판단 근거를 남긴다.
    satPos = (lon > SAT)
    satNeg = (lon < -SAT)
    sat = satPos | satNeg

    print(f"  ── 돌아야 하는 상황 (ATA>{NEED_TURN_ATA:.0f}°, 전체의 {100*need.mean():.1f}%) ──")
    print(f"  LonCtrlCmd  중앙 {np.median(lon[need]):+.3f}   "
          f"p5 {np.percentile(lon[need],5):+.3f}   p95 {np.percentile(lon[need],95):+.3f}")
    print(f"  포화 비율   |cmd|>{SAT}: {100*sat[need].mean():5.1f}%   "
          f"(+측 {100*satPos[need].mean():.1f}% / −측 {100*satNeg[need].mean():.1f}%)")
    print(f"  Elevator    중앙 {np.median(elev[need]):+.2f}°  "
          f"|최대| {np.max(np.abs(elev[need])):.1f}°")
    print(f"  Nz          중앙 {np.median(nz[need]):.2f}G  p90 {np.percentile(nz[need],90):.2f}G")
    print(f"  AOA         중앙 {np.median(aoa[need]):.1f}°  p90 {np.percentile(aoa[need],90):.1f}°")
    print(f"  CAS         중앙 {np.median(cas[need]):.0f}kt")

    # ★ 핵심 교차: 명령이 포화인데 G가 낮은 시간
    lowG = nz < 4.0
    print(f"\n  ★ 포화인데 Nz<4G      : {100*(sat & lowG & need).sum()/max(need.sum(),1):5.1f}%"
          f"   -> 이게 크면 **못 당긴다**(공력/속도 한계)")
    print(f"  ★ 포화 아닌데 Nz<4G   : {100*(~sat & lowG & need).sum()/max(need.sum(),1):5.1f}%"
          f"   -> 이게 크면 **안 당긴다**(제어기가 요구 안 함)")
    if (sat & lowG & need).sum() > 50:
        m = sat & lowG & need
        print(f"     (못 당길 때) CAS 중앙 {np.median(cas[m]):.0f}kt  AOA 중앙 {np.median(aoa[m]):.1f}°")
    if (~sat & lowG & need).sum() > 50:
        m = ~sat & lowG & need
        print(f"     (안 당길 때) cmd 중앙 {np.median(lon[m]):+.3f}  CAS 중앙 {np.median(cas[m]):.0f}kt")


print(f"당김 명령 vs 실제 G — {N}판씩, 시드 50000~ (현재 빌드)")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal  (이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    report(tag, run(dll, tag))

print("\n판정: 두 상대에서 '포화인데 저G' 비율이 크게 갈리면 원인이 속도다.")
print("      '포화 아닌데 저G'가 크면 제어기/VP가 원인이고 에너지 처방은 헛다리다.")
