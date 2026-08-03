"""과적합 확정 검증 — 한 번도 안 쓴 시드에서 v7.1 vs 현재 빌드를 페어 비교.

계획 리스크 #2: "시드 과적합 — 20판 튜닝 결과가 노이즈".
채택 3건이 전부 시드 50000/10000에서 판정됐다. 겹치지 않는 시드로 확정한다.

v7.1 상당 = A-1 지표는 있고 EP24/EP26 에너지 회복만 끈 빌드(AIP_gichan_v71.dll).
  (A-1은 no-op 검증에서 80/80 완전 동일이 확인됐으므로 v7.1과 동등하다)
"""
import sys
import os

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_REL = r"C:\develop\AIpilot\AIP_LIB\DogFightEnv\Release"
sys.path.insert(0, _REL)
sys.path.insert(0, os.path.join(_REL, "src"))
os.chdir(_REL)

from tools.sparring.runner import MatchRunner, SideSpec  # noqa: E402
from tools.sparring.scenarios import make_ic  # noqa: E402

N = 40
BASE = 70_000


def run(own_dll: str, opp: str):
    out = []
    runner = MatchRunner(SideSpec(own_dll, "Rule_gichan.xml", "gichan"),
                         SideSpec(opp, None, "opp"))
    try:
        for i in range(N):
            seed = BASE + i
            r = runner.run_match(i, seed, make_ic(seed))
            out.append(r)
    finally:
        runner.close()
    return out


print(f"확정 검증 — 시드 {BASE}~{BASE+N-1} (한 번도 안 쓴 시드), 페어 비교")
for opp, tag in (("AIP_BTJegal.dll", "btjegal"), ("AIP_jegalmin.dll", "jegalmin")):
    a = run("AIP_gichan_v71.dll", opp)      # v7.1 상당
    b = run("AIP_gichan.dll", opp)          # 현재 (EP24+EP26)
    ah = np.array([x.tgt_health_final for x in a])
    bh = np.array([x.tgt_health_final for x in b])
    ap1 = np.array([x.wez_dealt_ticks_phase1only for x in a]) / 60.0
    bp1 = np.array([x.wez_dealt_ticks_phase1only for x in b]) / 60.0
    aw = sum(1 for x in a if x.outcome == "win")
    bw = sum(1 for x in b if x.outcome == "win")
    ac = sum(1 for x in a if x.crashed)
    bc = sum(1 for x in b if x.crashed)
    better = int((bh < ah - 1e-9).sum())
    worse = int((bh > ah + 1e-9).sum())
    print(f"\n=== {tag} (n={N}) ===")
    print(f"  ★적 체력   {ah.mean():.3f} -> {bh.mean():.3f}   개선 {better} / 악화 {worse}")
    print(f"   승리      {aw} -> {bw}판")
    print(f"   Phase1콘  {ap1.mean():.2f}s -> {bp1.mean():.2f}s"
          f"   (>0인 판 {int((ap1>0).sum())} -> {int((bp1>0).sum())})")
    print(f"   추락      {ac} -> {bc}판")
