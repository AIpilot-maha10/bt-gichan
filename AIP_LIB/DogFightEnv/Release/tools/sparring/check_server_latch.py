"""서버 교전로그로 개전 래치(EP33~36)가 의도대로 잡히는지 확인한다.

bt-v7.2의 채택 4건(EP33/34/35/36)은 **개전 0.5초 시점의 대칭/비대칭 판정**에
의존한다. 로컬 IC는 결정론적이라 양측이 정확히 같은 고도(4,702m)에서 시작하지만,
**대회 서버는 접속 타이밍이 달라 개전 시점 상태가 다를 수 있다.**

래치가 잘못 "비대칭"으로 잡히면 에너지 회복 강하가 그 판 내내 꺼져
EP24/26의 이득(신규 시드 btjegal 승 20->32)을 통째로 잃는다.

이 스크립트는 **재빌드 없이** 기존 `--engage-log` CSV만으로 그걸 확인한다.

## 쓰는 법

```
python run_unreal_inference.py --mode bt --bt-dll AIP_gichan.dll \
  --bt-rule-xml Rule_gichan.xml --server-ip <IP> --team-name <팀> \
  --ownship-force-side 1 --target-force-side 2 --engage-log

python tools/sparring/check_server_latch.py engagement_logs/
```

## 판정

- **대칭(2)** 으로 잡히면 정상 — 예선 IC는 양측 대칭이므로 이게 기대값이다
- **비대칭(1)** 으로 잡히면 문제 — 강하가 꺼진다. `LATCH_ALT_M`(현재 300m)
  재조정이나 판정 시점(현재 0.5초) 조정이 필요하다
"""

from __future__ import annotations

import csv
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

# FightClassify.cpp와 같은 값이어야 한다
LATCH_AT_SEC = 0.5
LATCH_ALT_M = 300.0
LATCH_ES_M = 500.0
G = 9.80665


def pick(path: str) -> list[str]:
    if os.path.isdir(path):
        f = [os.path.join(path, x) for x in os.listdir(path) if x.endswith(".csv")]
        if not f:
            print(f"CSV가 없다: {path}")
            sys.exit(1)
        return sorted(f, key=os.path.getmtime)[-5:]   # 최근 5개
    return [path]


def analyse(path: str):
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            try:
                t = float(r.get("elapsed_sec", 0) or 0)
            except ValueError:
                continue
            if t > LATCH_AT_SEC + 2.0:
                break
            rows.append((t, r))
    if not rows:
        return None

    # 래치 시점에 가장 가까운 틱
    tgt = min(rows, key=lambda x: abs(x[0] - LATCH_AT_SEC))
    t, r = tgt

    def f(k):
        try:
            return float(r.get(k, 0) or 0)
        except ValueError:
            return 0.0

    dz = f("own_z") - f("enemy_z")
    own_es = f("own_z") + f("own_speed") ** 2 / (2 * G)
    en_es = f("enemy_z") + f("enemy_speed") ** 2 / (2 * G)
    des = own_es - en_es

    aheadAlt = abs(dz) > LATCH_ALT_M
    aheadEs = abs(des) > LATCH_ES_M
    # 위치 우위는 CSV에 aspect가 없을 수 있어 ATA만 참고로 본다
    ata = f("ata_deg")
    latch = 1 if (aheadAlt or aheadEs) else 2
    return {"t": t, "dz": dz, "des": des, "ata": ata,
            "aheadAlt": aheadAlt, "aheadEs": aheadEs, "latch": latch,
            "own_z": f("own_z"), "enemy_z": f("enemy_z")}


files = pick(sys.argv[1] if len(sys.argv) > 1 else "engagement_logs/")
print("개전 래치 확인 — 서버 교전로그가 로컬 전제와 맞는가\n")
print(f"판정 시점 {LATCH_AT_SEC}s | 고도 임계 ±{LATCH_ALT_M:.0f}m | Es 임계 ±{LATCH_ES_M:.0f}m\n")

bad = 0
for p in files:
    a = analyse(p)
    name = os.path.basename(p)
    if a is None:
        print(f"  {name}: 개전 구간 데이터 없음")
        continue
    mark = "OK  대칭" if a["latch"] == 2 else "!!  비대칭"
    print(f"  {name}")
    print(f"    t={a['t']:.2f}s  내고도 {a['own_z']:.0f}m  적고도 {a['enemy_z']:.0f}m"
          f"  dz={a['dz']:+.0f}m  dEs={a['des']:+.0f}m  ATA={a['ata']:.0f}°")
    print(f"    -> OpeningLatch = {a['latch']}  [{mark}]"
          f"{'  (고도 초과)' if a['aheadAlt'] else ''}"
          f"{'  (에너지 초과)' if a['aheadEs'] else ''}")
    if a["latch"] != 2:
        bad += 1

print()
if bad == 0:
    print("★ 전부 대칭(2)으로 잡힌다 — 로컬 전제가 서버에서도 성립한다.")
    print("  에너지 회복 강하가 정상 발동하므로 EP24/26 이득이 유지된다.")
else:
    print(f"⚠️ {bad}건이 비대칭(1)으로 잡힌다 — **강하가 그 판 내내 꺼진다.**")
    print("  조치 후보:")
    print("   1) LATCH_ALT_M을 실제 개전 dz보다 크게 (FightClassify.cpp)")
    print("   2) 판정 시점을 더 앞으로 (LATCH_AT_SEC 0.5 -> 0.2)")
    print("   3) 서버 접속 타이밍 때문이면 첫 유효 틱 기준으로 변경")
