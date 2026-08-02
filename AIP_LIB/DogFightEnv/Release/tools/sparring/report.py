"""집계와 A/B 페어 비교.

## 왜 평균이 아니라 최악값 중심인가

같은 상대 3판에서 대성공(WEZ 178틱) / 소극적 / 추락사가 모두 나온 게 지금까지의 문제다.
평균 40인데 p20이 0인 빌드보다, 평균 30인데 p20이 18인 빌드가 대회에서 낫다.
**가장 중요한 3개: crash율 · shutout율(한 틱도 못 쏜 판) · WEZ의 p20.**

## 왜 페어 비교인가

우리 노이즈 수준에서 두 빌드의 평균만 비교하는 건 무의미하다.
같은 시드 리스트로 양쪽을 돌려 **시드별 차이(delta)**를 보고, 부호검정 + 부트스트랩 CI로 판단한다.

## 단위
주 표기는 **초**다. 하네스는 60Hz 전수(step_ratio=1)지만 RL은 step_ratio=6이라
틱으로 비교하면 6배 차이나 보인다. 틱은 괄호로 병기한다.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

import numpy as np

from .result import MatchResult

HZ = 60.0


def _sec(ticks: float) -> float:
    return ticks / HZ


def _pct(n: int, d: int) -> float:
    return 100.0 * n / d if d else 0.0


def summarize(results: Sequence[MatchResult], title: str = "") -> str:
    ok = [r for r in results if not r.error]
    n = len(ok)
    if n == 0:
        return f"{title}: 유효한 판이 없다 (전체 {len(results)}판 오류)"

    lines: list[str] = []
    add = lines.append
    add("=" * 74)
    add(f"{title}   ({n}판" + (f", 오류 {len(results)-n}판" if len(results) != n else "") + ")")
    add("=" * 74)

    # --- 결과 분포 ---
    oc = Counter(r.outcome for r in ok)
    add("\n[결과]")
    for k, v in oc.most_common():
        add(f"  {k:<18} {v:3d}판 ({_pct(v, n):5.1f}%)")
    crash = sum(1 for r in ok if r.crashed)
    add(f"  {'★추락':<18} {crash:3d}판 ({_pct(crash, n):5.1f}%)   "
        f"적추락 {sum(1 for r in ok if r.enemy_crashed)}판")

    # --- WEZ ---
    dealt = np.array([r.wez_dealt_ticks for r in ok], dtype=float)
    recv = np.array([r.wez_recv_ticks for r in ok], dtype=float)
    shut = int((dealt == 0).sum())
    add("\n[WEZ] 초 단위 (괄호는 틱)")
    add(f"  가한 것  평균 {_sec(dealt.mean()):6.2f}s ({dealt.mean():7.1f})"
        f"  중앙 {_sec(np.median(dealt)):6.2f}s"
        f"  ★p20 {_sec(np.percentile(dealt, 20)):6.2f}s"
        f"  최대 {_sec(dealt.max()):6.2f}s  sd {_sec(dealt.std()):5.2f}s")
    add(f"  받은 것  평균 {_sec(recv.mean()):6.2f}s ({recv.mean():7.1f})"
        f"  최대 {_sec(recv.max()):6.2f}s")
    add(f"  ★shutout(한 틱도 못 쏨) {shut}판 ({_pct(shut, n):5.1f}%)")

    # --- 왜 못 쐈나 ---
    inr = np.array([r.ticks_in_phase_range for r in ok], dtype=float)
    mata = np.array([r.min_ata_deg for r in ok if r.min_ata_deg is not None], dtype=float)
    add("\n[왜 못 쐈나] 접근 문제 vs 조준 문제 분리")
    add(f"  사거리 내 체류  평균 {_sec(inr.mean()):6.2f}s  중앙 {_sec(np.median(inr)):6.2f}s")
    if mata.size:
        add(f"  최소 ATA        평균 {mata.mean():6.2f}°  최소 {mata.min():6.2f}°")

    # --- 안전 ---
    minalt = np.array([r.min_own_alt_m for r in ok], dtype=float)
    add("\n[안전]")
    add(f"  최저고도  전체최소 {minalt.min():7.1f}m  p10 {np.percentile(minalt, 10):7.1f}m"
        f"  중앙 {np.median(minalt):7.1f}m")
    add(f"  600m 미만으로 내려간 판 {sum(1 for r in ok if r.ticks_below_600m > 0)}판")

    # --- 교착 ---
    stale = np.array([r.stalemate_ticks for r in ok], dtype=float)
    add("\n[교착]")
    add(f"  최장 교착구간  평균 {_sec(stale.mean()):6.2f}s  최대 {_sec(stale.max()):6.2f}s")
    tasks: Counter = Counter()
    for r in ok:
        tasks.update(r.task_hist)
    tot = sum(tasks.values()) or 1
    add("  전술 체류: " + "  ".join(f"{k} {100*v/tot:.1f}%" for k, v in tasks.most_common(6)))

    # --- 최악 5판 ---
    add("\n[최악 5판] (추락 > WEZ 적은 순)")
    worst = sorted(ok, key=lambda r: (not r.crashed, r.wez_dealt_ticks))[:5]
    add(f"  {'seed':<8}{'family':<13}{'outcome':<18}{'WEZ':>8}{'minAlt':>9}")
    for r in worst:
        add(f"  {r.seed:<8}{r.family:<13}{r.outcome:<18}"
            f"{_sec(r.wez_dealt_ticks):7.2f}s{r.min_own_alt_m:9.0f}m")

    # --- 패밀리별 ---
    fams = sorted({r.family for r in ok})
    if len(fams) > 1:
        add("\n[패밀리별]")
        add(f"  {'family':<14}{'판':>4}{'WEZ평균':>10}{'p20':>9}{'추락':>7}{'shutout':>9}")
        for f in fams:
            sub = [r for r in ok if r.family == f]
            d = np.array([r.wez_dealt_ticks for r in sub], dtype=float)
            add(f"  {f:<14}{len(sub):4d}{_sec(d.mean()):9.2f}s{_sec(np.percentile(d,20)):8.2f}s"
                f"{_pct(sum(1 for r in sub if r.crashed), len(sub)):6.0f}%"
                f"{_pct(int((d==0).sum()), len(sub)):8.0f}%")

    wall = sum(r.wall_clock_s for r in ok)
    add(f"\n[운영] 총 {wall/60:.1f}분, 판당 {wall/n:.1f}초")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# A/B 페어 비교
# --------------------------------------------------------------------------- #

def _sign_test_p(wins: int, losses: int) -> float:
    """양측 부호검정 p값. 무승부는 제외하고 계산한다(표준 관행)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def _bootstrap_ci(deltas: np.ndarray, iters: int = 10_000, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(deltas), size=(iters, len(deltas)))
    means = deltas[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def compare(base: Sequence[MatchResult], new: Sequence[MatchResult],
            base_name: str = "A(기준)", new_name: str = "B(신규)") -> str:
    """같은 시드로 돌린 두 결과를 페어 비교한다."""
    bmap = {r.seed: r for r in base if not r.error}
    nmap = {r.seed: r for r in new if not r.error}
    seeds = sorted(set(bmap) & set(nmap))
    lines: list[str] = []
    add = lines.append
    add("=" * 74)
    add(f"페어 비교  {base_name}  →  {new_name}   (공통 시드 {len(seeds)}개)")
    add("=" * 74)
    if not seeds:
        add("공통 시드가 없다 — 같은 시드 리스트로 돌려야 비교가 된다")
        return "\n".join(lines)

    def col(name: str, f, higher_better: bool, unit: str = "s", scale=_sec):
        b = np.array([f(bmap[s]) for s in seeds], dtype=float)
        nn = np.array([f(nmap[s]) for s in seeds], dtype=float)
        d = nn - b
        wins = int((d > 0).sum() if higher_better else (d < 0).sum())
        losses = int((d < 0).sum() if higher_better else (d > 0).sum())
        p = _sign_test_p(wins, losses)
        lo, hi = _bootstrap_ci(d)
        sb, sn = scale(b.mean()), scale(nn.mean())
        slo, shi = scale(lo), scale(hi)
        mark = "★" if p < 0.05 else " "
        add(f"{mark} {name:<22}{sb:8.2f}{unit} → {sn:7.2f}{unit}   "
            f"개선 {wins:3d} / 악화 {losses:3d}  p={p:.3f}  "
            f"CI[{slo:+.2f},{shi:+.2f}]{unit}")

    add("")
    col("WEZ 가한 것", lambda r: r.wez_dealt_ticks, True)
    col("WEZ 받은 것", lambda r: r.wez_recv_ticks, False)
    col("사거리 내 체류", lambda r: r.ticks_in_phase_range, True)
    col("교착 최장구간", lambda r: r.stalemate_ticks, False)
    col("최저고도", lambda r: r.min_own_alt_m, True, unit="m", scale=lambda x: x)
    col("최소 ATA", lambda r: r.min_ata_deg if r.min_ata_deg is not None else 180.0,
        False, unit="°", scale=lambda x: x)

    bc = sum(1 for s in seeds if bmap[s].crashed)
    nc = sum(1 for s in seeds if nmap[s].crashed)
    bs = sum(1 for s in seeds if bmap[s].shutout)
    ns = sum(1 for s in seeds if nmap[s].shutout)
    add("")
    add(f"  {'추락':<22}{bc:8d}판 → {nc:7d}판")
    add(f"  {'shutout':<22}{bs:8d}판 → {ns:7d}판")

    bd = np.array([bmap[s].wez_dealt_ticks for s in seeds], dtype=float)
    nd = np.array([nmap[s].wez_dealt_ticks for s in seeds], dtype=float)
    add(f"  {'WEZ p20':<22}{_sec(np.percentile(bd,20)):8.2f}s → "
        f"{_sec(np.percentile(nd,20)):7.2f}s")

    add("")
    add("판정: ★는 부호검정 p<0.05. 추락이 늘었으면 다른 지표가 좋아도 채택하지 않는다.")
    return "\n".join(lines)


def to_csv(results: Sequence[MatchResult], path: str) -> None:
    import csv
    from dataclasses import asdict
    rows = [asdict(r) for r in results]
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for row in rows:
            w.writerow({k: (v if not isinstance(v, dict) else str(v)) for k, v in row.items()})
