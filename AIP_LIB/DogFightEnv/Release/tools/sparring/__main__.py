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
from tools.sparring.scenarios import (  # noqa: E402
    DIAG_BY_KEY, DIAG_CELLS, REGRESS_CASES, diag_grid, make_ic, regress_list, seed_list,
)

DEFAULT_OUT = r"D:\aipilot-artifacts\sparring"

# ── 스파링 로스터 ────────────────────────────────────────────────────────────
# ⚠️ **2상대 판정이 이 프로젝트 최대의 구조적 약점이었다** (8/4 확인).
#   btjegal/jegalmin 둘로만 판정하다가 bt-v7.2를 채택했는데,
#   우리 이전 버전 v7.1과 머리맞대기를 붙이니 3승 16패로 졌다.
#   5상대로 넓히자 17 vs 19로 우위가 절반으로 줄었다(한 상대 기준 20->32였다).
#   -> **판정은 기본 5상대로 한다.** 한 상대의 큰 숫자로 전체를 대표시키지 말 것.
#
# 구버전 gichan 계열은 기본값으로 ./Rule_gichan.xml을 읽는데 A-1 노드 4종
# (LosRateUpdate/EnergyUpdate/TurnGeomUpdate/FightClassify)이 없어 초기화가 실패한다.
# -> Rule_gichan_legacy.xml(A-1 이전 트리)을 지정해 되살렸다. 제출용이 아니다.
LEGACY_XML = "Rule_gichan_legacy.xml"

OPPONENTS = {
    # 외부 팀 BT — 대회 상대의 대표성이 가장 높다
    "jegalmin": SideSpec("AIP_jegalmin.dll", None, "jegalmin"),
    "btjegal": SideSpec("AIP_BTJegal.dll", None, "btjegal"),
    # 자기 계열 — 성향이 달라 과적합 탐지에 쓴다
    "v6": SideSpec("AIP_gichan_v6.dll", LEGACY_XML, "gichan_v6"),
    "coordfix": SideSpec("AIP_gichan_coordfix.dll", LEGACY_XML, "coordfix"),
    "v1": SideSpec("AIP_gichan_v1.dll", LEGACY_XML, "gichan_v1"),
    "v71": SideSpec("AIP_gichan_v71.dll", None, "gichan_v71"),
    # ⚠️ 상대로 무의미 — 양쪽 0승/적체력 1.000. 하네스 동작 확인용으로만.
    #   AIP_BASE_target은 원본 트리가 Task_Empty뿐이라 2.5초 만에 자멸한다.
    "base": SideSpec("AIP_BASE.dll", None, "base"),
    "base_target": SideSpec("AIP_BASE_target.dll", None, "base_target"),
}

# 판정용 기본 로스터 (baseline/compare가 인자 없이 쓰는 값)
DEFAULT_ROSTER = "jegalmin,btjegal,v6,coordfix,v71"


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
    b.add_argument("--opponents", default=DEFAULT_ROSTER)

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

    d = sub.add_parser("diag", help="진단 격자 — 어느 셀이 0점인가")
    d.add_argument("--dll", default="AIP_gichan.dll")
    d.add_argument("--xml", default="Rule_gichan.xml")
    d.add_argument("--per-cell", type=int, default=3)
    d.add_argument("--cells", default="", help="쉼표로 특정 셀만 (기본 전체)")
    d.add_argument("--secs", type=float, default=W.MATCH_DURATION_S)
    d.add_argument("--opponent", default="jegalmin")
    d.add_argument("--out", default=os.path.join(DEFAULT_OUT, "diag"))

    g = sub.add_parser("regress", help="회귀 — 과거 사고가 재발하는가")
    g.add_argument("--dll", default="AIP_gichan.dll")
    g.add_argument("--xml", default="Rule_gichan.xml")
    g.add_argument("--secs", type=float, default=W.MATCH_DURATION_S)
    g.add_argument("--opponent", default="jegalmin")
    g.add_argument("--out", default=os.path.join(DEFAULT_OUT, "regress"))

    s = sub.add_parser("show", help="저장된 jsonl 다시 집계")
    s.add_argument("path")

    a = ap.parse_args()

    if a.cmd == "show":
        print(R.summarize(_load(a.path), os.path.basename(a.path)))
        return 0

    if a.cmd in ("diag", "regress"):
        pairs = (diag_grid(a.per_cell) if a.cmd == "diag" else regress_list())
        if a.cmd == "diag" and a.cells:
            want = {c.strip() for c in a.cells.split(",")}
            pairs = [(s, c) for s, c in pairs if c in want]
        runner = MatchRunner(SideSpec(a.dll, a.xml, "own"), OPPONENTS[a.opponent],
                             max_engage_time=a.secs)
        results = []
        try:
            for i, (seed, cell) in enumerate(pairs):
                res = runner.run_match(i, seed, make_ic(seed, cell))
                results.append(res)
                print(f"[{i:3d}] {cell:<16} seed={seed} {res.outcome:<16} "
                      f"wez={res.wez_dealt_ticks/60:5.2f}s recv={res.wez_recv_ticks/60:5.2f}s "
                      f"minAlt={res.min_own_alt_m:7.1f}"
                      + (f"  ERR={res.error}" if res.error else ""), flush=True)
        finally:
            runner.close()
        _save(results, a.out, a.cmd)

        if a.cmd == "diag":
            print("\n" + "=" * 74)
            print("셀별 결과 — 평균이 아니라 **어느 셀이 0점인가**를 본다")
            print("=" * 74)
            print(f"  {'셀':<17}{'판':>3}{'WEZ평균':>9}{'피격':>8}{'추락':>6}{'shutout':>9}  감시항목")
            for cell in DIAG_CELLS:
                sub_r = [r for r in results if r.family == cell.key and not r.error]
                if not sub_r:
                    continue
                dealt = sum(r.wez_dealt_ticks for r in sub_r) / len(sub_r) / 60
                recv = sum(r.wez_recv_ticks for r in sub_r) / len(sub_r) / 60
                cr = sum(1 for r in sub_r if r.crashed)
                sh = sum(1 for r in sub_r if r.shutout)
                flag = " 🔴" if (cr or sh == len(sub_r)) else ""
                print(f"  {cell.key:<17}{len(sub_r):3d}{dealt:8.2f}s{recv:7.2f}s"
                      f"{cr:6d}{sh}/{len(sub_r):<7}{cell.watch[:40]}{flag}")
        else:
            print("\n" + "=" * 74)
            print("회귀 — 과거 사고가 재발했는가")
            print("=" * 74)
            for case, res in zip(REGRESS_CASES, results):
                bad = res.crashed or res.error
                print(f"  [{'FAIL' if bad else ' OK '}] {case.key:<20} {res.outcome:<16}"
                      f" 추락={res.crashed} minAlt={res.min_own_alt_m:.0f}m"
                      f" 교착={res.stalemate_ticks/60:.1f}s 피격={res.wez_recv_ticks/60:.2f}s")
                print(f"         과거: {case.what_happened}")
                print(f"         기준: {case.guard}")
        print(f"\n저장: {a.out}")
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
