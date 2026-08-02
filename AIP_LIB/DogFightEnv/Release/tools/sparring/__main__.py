"""스파링 하네스 CLI.

베이스라인 저장:
  python -m tools.sparring baseline --seeds 30 --out D:/aipilot-artifacts/sparring/base

두 빌드 페어 비교:
  python -m tools.sparring compare --base-dll AIP_gichan_v1.dll --new-dll AIP_gichan.dll --seeds 30

저장된 결과 다시 보기:
  python -m tools.sparring show D:/aipilot-artifacts/sparring/base/jegalmin.csv
"""

from __future__ import annotations

import argparse
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_RELEASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _RELEASE)
sys.path.insert(0, os.path.join(_RELEASE, "src"))
os.chdir(_RELEASE)

from tools.sparring import report as R  # noqa: E402
from tools.sparring import wez as W  # noqa: E402
from tools.sparring.result import MatchResult  # noqa: E402
from tools.sparring.runner import MatchRunner, SideSpec, run_series  # noqa: E402
from tools.sparring.scenarios import make_ic, seed_list  # noqa: E402

DEFAULT_OUT = r"D:\aipilot-artifacts\sparring"

# Day 1 실측: AIP_BASE_target은 Rule_forTraining.xml이 덮여 초기화 실패 + 원본도 Task_Empty뿐.
# 실질 상대는 이 둘이다.
OPPONENTS = {
    "jegalmin": SideSpec("AIP_jegalmin.dll", None, "jegalmin"),
    "btjegal": SideSpec("AIP_BTJegal.dll", None, "btjegal"),
}


def _run(own: SideSpec, opp: SideSpec, seeds: list[int], secs: float) -> list[MatchResult]:
    runner = MatchRunner(own, opp, max_engage_time=secs)
    try:
        return run_series(runner, seeds, make_ic)
    finally:
        runner.close()


def _save(results: list[MatchResult], out_dir: str, name: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    R.to_csv(results, os.path.join(out_dir, f"{name}.csv"))
    with open(os.path.join(out_dir, f"{name}.jsonl"), "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(r.to_json() + "\n")


def _load(path: str) -> list[MatchResult]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                d.pop("ic", None) or None
                out.append(MatchResult(**{**d, "ic": {}}))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="tools.sparring")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("baseline", help="기준점 저장 (불변)")
    b.add_argument("--dll", default="AIP_gichan.dll")
    b.add_argument("--xml", default="Rule_gichan.xml")
    b.add_argument("--seeds", type=int, default=30)
    b.add_argument("--seed-base", type=int, default=10_000)
    b.add_argument("--secs", type=float, default=W.MATCH_DURATION_S)
    b.add_argument("--out", default=os.path.join(DEFAULT_OUT, "baseline"))
    b.add_argument("--opponents", default="jegalmin,btjegal")

    c = sub.add_parser("compare", help="두 빌드 페어 비교")
    c.add_argument("--base-dll", required=True)
    c.add_argument("--base-xml", default="Rule_gichan.xml")
    c.add_argument("--new-dll", required=True)
    c.add_argument("--new-xml", default="Rule_gichan.xml")
    c.add_argument("--seeds", type=int, default=30)
    c.add_argument("--seed-base", type=int, default=10_000)
    c.add_argument("--secs", type=float, default=W.MATCH_DURATION_S)
    c.add_argument("--opponent", default="jegalmin")
    c.add_argument("--out", default=os.path.join(DEFAULT_OUT, "compare"))

    s = sub.add_parser("show", help="저장된 jsonl 다시 집계")
    s.add_argument("path")

    a = ap.parse_args()

    if a.cmd == "show":
        print(R.summarize(_load(a.path), os.path.basename(a.path)))
        return 0

    seeds = seed_list(a.seeds, a.seed_base)

    if a.cmd == "baseline":
        own = SideSpec(a.dll, a.xml, "own")
        for opp_name in a.opponents.split(","):
            opp_name = opp_name.strip()
            if opp_name not in OPPONENTS:
                print(f"모르는 상대: {opp_name} (가능: {list(OPPONENTS)})")
                continue
            print(f"\n########## vs {opp_name} — {len(seeds)}판 ##########", flush=True)
            res = _run(own, OPPONENTS[opp_name], seeds, a.secs)
            _save(res, a.out, opp_name)
            print("\n" + R.summarize(res, f"베이스라인 {a.dll} vs {opp_name}"))
        print(f"\n저장 위치: {a.out}")
        return 0

    if a.cmd == "compare":
        opp = OPPONENTS[a.opponent]
        print(f"\n########## 기준 {a.base_dll} ##########", flush=True)
        base = _run(SideSpec(a.base_dll, a.base_xml, "base"), opp, seeds, a.secs)
        print(f"\n########## 신규 {a.new_dll} ##########", flush=True)
        new = _run(SideSpec(a.new_dll, a.new_xml, "new"), opp, seeds, a.secs)
        _save(base, a.out, f"base_{os.path.splitext(a.base_dll)[0]}")
        _save(new, a.out, f"new_{os.path.splitext(a.new_dll)[0]}")
        print("\n" + R.summarize(base, f"{a.base_dll} vs {a.opponent}"))
        print("\n" + R.summarize(new, f"{a.new_dll} vs {a.opponent}"))
        print("\n" + R.compare(base, new, a.base_dll, a.new_dll))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
