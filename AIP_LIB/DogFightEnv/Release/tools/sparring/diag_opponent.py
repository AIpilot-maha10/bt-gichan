"""상대 비교 진단 — 같은 시나리오에서 왜 한쪽만 못 이기는가.

예선 실측(새 시드 40판):
  vs btjegal  : 승 27, WEZ 11.10s, shutout 0%
  vs jegalmin : 무 40, WEZ 0.24s, shutout 80%

같은 초기조건인데 45배 차이가 난다. **상대가 무엇을 다르게 하는가**를 본다.
우리 쪽 로직은 동일하므로 차이는 전적으로 상대 기동에서 온다.

실행: python tools/sparring/diag_opponent.py [판수]
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

from tools.sparring import wez as W  # noqa: E402
from tools.sparring.runner import MatchRunner, SideSpec  # noqa: E402
from tools.sparring.scenarios import make_ic  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
KT = 0.51444


def collect(opp_dll: str, tag: str, n: int):
    rows: list[dict] = []
    runner = MatchRunner(SideSpec("AIP_gichan.dll", "Rule_gichan.xml", "gichan"),
                         SideSpec(opp_dll, None, tag),
                         tick_sink=lambda i, d: rows.append(d))
    out = []
    try:
        for i in range(n):
            seed = 50_000 + i
            rows.clear()
            r = runner.run_match(i, seed, make_ic(seed))
            out.append((r, [dict(x) for x in rows]))
    finally:
        runner.close()
    return out


def summarize(tag: str, data):
    print(f"\n{'='*66}\n{tag}\n{'='*66}")
    wez = np.array([r.wez_dealt_ticks for r, _ in data], dtype=float) / 60
    print(f"  WEZ {wez.mean():.2f}s  shutout {sum(1 for r,_ in data if r.shutout)}/{len(data)}")

    all_t = [t for _, ticks in data for t in ticks]
    if not all_t:
        return
    dist = np.array([t["dist"] for t in all_t])
    my_ata = np.array([t["my_ata"] for t in all_t])
    en_ata = np.array([t["en_ata"] for t in all_t])
    hca = np.array([t["hca"] for t in all_t])
    spd = np.array([t["own_spd"] for t in all_t])
    tgt_spd = np.array([float(np.linalg.norm(t["tgt_state"][6:9])) for t in all_t])
    alt = np.array([t["own_alt"] for t in all_t])
    tgt_alt = np.array([float(t["tgt_state"][W.IDX_ALT]) for t in all_t])

    print(f"\n  --- 기하 ---")
    print(f"  거리      중앙 {np.median(dist):7.0f}m   <1000m {100*(dist<1000).mean():4.1f}%"
          f"   <500m {100*(dist<500).mean():4.1f}%")
    print(f"  내 ATA    중앙 {np.median(my_ata):6.1f}°   <20° {100*(my_ata<20).mean():4.1f}%"
          f"   <5° {100*(my_ata<5).mean():4.1f}%")
    print(f"  적 ATA    중앙 {np.median(en_ata):6.1f}°   <20° {100*(en_ata<20).mean():4.1f}%")
    print(f"  HCA       중앙 {np.median(hca):6.1f}°   >120°(정면류) {100*(hca>120).mean():4.1f}%")

    print(f"\n  --- 속도/고도 (상대가 어떻게 싸우나) ---")
    print(f"  내 속도   중앙 {np.median(spd):6.1f} m/s")
    print(f"  적 속도   중앙 {np.median(tgt_spd):6.1f} m/s   (차이 {np.median(tgt_spd-spd):+6.1f})")
    print(f"  내 고도   중앙 {np.median(alt):7.0f}m")
    print(f"  적 고도   중앙 {np.median(tgt_alt):7.0f}m   (차이 {np.median(tgt_alt-alt):+7.0f})")

    # 적 선회 강도: 기수벡터 변화율
    turn = []
    for _, ticks in data:
        for a, b in zip(ticks[:-1], ticks[1:]):
            fa, fb = b["tgt_state"], a["tgt_state"]
            d = abs(float(fa[5]) - float(fb[5]))
            if d > 180: d = 360 - d
            turn.append(d * 60.0)
    turn = np.array(turn)
    print(f"\n  적 선회율  중앙 {np.median(turn):5.2f}°/s   p90 {np.percentile(turn,90):5.2f}°/s"
          f"   >10°/s {100*(turn>10).mean():4.1f}%")

    inr = (dist >= 152.4) & (dist <= 914.4)
    print(f"\n  --- 사거리(152~914m) 안일 때 ---")
    print(f"  체류 {100*inr.mean():4.1f}%", end="")
    if inr.sum():
        print(f"   그때 내 ATA 중앙 {np.median(my_ata[inr]):5.1f}°"
              f"   최소 {my_ata[inr].min():5.2f}°")
    else:
        print()


print(f"상대 비교 진단 — 같은 시드({50_000}~) {N}판씩")
for dll, tag in (("AIP_BTJegal.dll", "vs btjegal (우리가 이기는 상대)"),
                 ("AIP_jegalmin.dll", "vs jegalmin (못 이기는 상대)")):
    summarize(tag, collect(dll, tag, N))
