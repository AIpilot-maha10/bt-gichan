from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass, fields as dc_fields
from pathlib import Path

import numpy as np

from dogfight.unreal.client import RemoteClientContext
from dogfight.unreal.protocol import CMD, PlaneInfo

D2R = np.pi / 180.0
R2D = 180.0 / np.pi

KNOCKOUT_ALT_M = 304.8  # 1000ft

PHASES = [
    {"name": "Phase1", "los_max": 1.0, "dist_min": 152.4, "dist_max": 914.4, "mult": 1.0},
    {"name": "Phase2", "los_max": 2.0, "dist_min": 152.4, "dist_max": 1066.8, "mult": 0.3},
    {"name": "Phase3", "los_max": 3.0, "dist_min": 152.4, "dist_max": 1219.2, "mult": 0.1},
]


@dataclass
class TickRecord:
    tick: int = 0
    elapsed_sec: float = 0.0
    own_x: float = 0.0
    own_y: float = 0.0
    own_z: float = 0.0
    own_roll: float = 0.0
    own_pitch: float = 0.0
    own_yaw: float = 0.0
    own_vx: float = 0.0
    own_vy: float = 0.0
    own_vz: float = 0.0
    own_speed: float = 0.0
    enemy_x: float = 0.0
    enemy_y: float = 0.0
    enemy_z: float = 0.0
    enemy_roll: float = 0.0
    enemy_pitch: float = 0.0
    enemy_yaw: float = 0.0
    enemy_vx: float = 0.0
    enemy_vy: float = 0.0
    enemy_vz: float = 0.0
    enemy_speed: float = 0.0
    distance: float = 0.0
    ata_deg: float = 0.0
    aa_deg: float = 0.0
    enemy_ata_deg: float = 0.0
    phase_active: str = ""
    dmg_dealt: float = 0.0
    dmg_received: float = 0.0
    cmd_roll: float = 0.0
    cmd_pitch: float = 0.0
    cmd_yaw: float = 0.0
    cmd_throttle: float = 0.0
    # BT 내부/파생 정보
    task: str = ""           # 현재 실행 중인 Task(전략) 이름
    vp_x: float = 0.0        # VP(추적점) 좌표
    vp_y: float = 0.0
    vp_z: float = 0.0
    vp_dist: float = 0.0     # 내 위치 → VP 거리(m)
    vp_dive_deg: float = 0.0 # 내 위치 → VP 하강각(+면 VP가 아래)
    closure_ms: float = 0.0  # 닫힘속도(+면 접근), m/s
    own_energy_m: float = 0.0  # 비에너지 = 고도 + v^2/2g (에너지 우위 판정)
    enemy_energy_m: float = 0.0


def _ata(own_ned: np.ndarray, tgt_ned: np.ndarray) -> float:
    roll, pitch, yaw = own_ned[3] * D2R, own_ned[4] * D2R, own_ned[5] * D2R
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    Tx = np.array([[1, 0, 0], [0, cr, sr], [0, -sr, cr]])
    Ty = np.array([[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]])
    Tz = np.array([[cy, sy, 0], [-sy, cy, 0], [0, 0, 1]])
    p = tgt_ned[:3] - own_ned[:3]
    n = np.linalg.norm(p)
    if n < 1e-6:
        return 0.0
    p_body = Tx @ Ty @ Tz @ (p / n)
    return float(np.arccos(np.clip(p_body[0], -1.0, 1.0)) * R2D)


def _aa(own_ned: np.ndarray, tgt_ned: np.ndarray) -> float:
    roll, pitch, yaw = tgt_ned[3] * D2R, tgt_ned[4] * D2R, tgt_ned[5] * D2R
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    Tx = np.array([[1, 0, 0], [0, cr, sr], [0, -sr, cr]])
    Ty = np.array([[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]])
    Tz = np.array([[cy, sy, 0], [-sy, cy, 0], [0, 0, 1]])
    Tz_pi = np.array([[-1, 0, 0], [0, -1, 0], [0, 0, 1]])
    p = own_ned[:3] - tgt_ned[:3]
    n = np.linalg.norm(p)
    if n < 1e-6:
        return 0.0
    p_body = Tz_pi @ Tx @ Ty @ Tz @ (p / n)
    return float(np.arccos(np.clip(p_body[0], -1.0, 1.0)) * R2D)


def _phase_damage(my_ata: float, enemy_ata: float, distance: float):
    best_dealt = 0.0
    best_recv = 0.0
    active = ""
    for ph in PHASES:
        if abs(my_ata) < ph["los_max"] and ph["dist_min"] <= distance <= ph["dist_max"]:
            if ph["mult"] > best_dealt:
                best_dealt = ph["mult"]
                active = ph["name"]
        if abs(enemy_ata) < ph["los_max"] and ph["dist_min"] <= distance <= ph["dist_max"]:
            best_recv = max(best_recv, ph["mult"])
    return active, best_dealt, best_recv


def _ned_from_plane(p: PlaneInfo) -> np.ndarray:
    return np.array([
        p.position.x, p.position.y, p.position.z,
        p.rotation.roll, p.rotation.pitch, p.rotation.yaw,
    ])


class EngagementMonitor:
    def __init__(self, team_name: str = "unknown", log_dir: str | None = None,
                 print_interval: int = 60):
        self.team_name = team_name
        self.print_interval = print_interval
        self._records: list[TickRecord] = []
        self._tick = 0
        self._t0: float | None = None
        self._cum_dealt = 0.0
        self._cum_recv = 0.0
        self._phase_ticks = {"Phase1": 0, "Phase2": 0, "Phase3": 0, "": 0}
        self._min_own_alt = float("inf")
        self._min_enemy_alt = float("inf")
        self._min_dist = float("inf")
        self._own_ko_ticks = 0
        self._enemy_ko_ticks = 0
        self._prev_dist: float | None = None
        self._prev_elapsed: float | None = None
        self._task_ticks: dict[str, int] = {}

        log_path = Path(log_dir) if log_dir else Path("engagement_logs")
        log_path.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._csv_path = log_path / f"engage_{team_name}_{ts}.csv"
        self._csv_file = None
        self._csv_writer = None

    def start(self):
        self._t0 = time.time()
        self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8")
        names = [f.name for f in dc_fields(TickRecord)]
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=names)
        self._csv_writer.writeheader()
        print(f"[EngageLog] Recording → {self._csv_path}")

    def record(self, ctx: RemoteClientContext, cmd: CMD | None = None,
               action_info: dict | None = None):
        if self._t0 is None:
            self.start()

        own = ctx.own_plane.plane_info
        enemy = ctx.enemy_plane.plane_info
        if own is None or enemy is None:
            return

        self._tick += 1
        elapsed = time.time() - self._t0
        action_info = action_info or {}

        own_ned = _ned_from_plane(own)
        enemy_ned = _ned_from_plane(enemy)

        own_spd = math.sqrt(own.velocity.x ** 2 + own.velocity.y ** 2 + own.velocity.z ** 2)
        enemy_spd = math.sqrt(enemy.velocity.x ** 2 + enemy.velocity.y ** 2 + enemy.velocity.z ** 2)
        dx = enemy.position.x - own.position.x
        dy = enemy.position.y - own.position.y
        dz = enemy.position.z - own.position.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        my_ata = _ata(own_ned, enemy_ned)
        my_aa = _aa(own_ned, enemy_ned)
        e_ata = _ata(enemy_ned, own_ned)

        phase, dealt, recv = _phase_damage(my_ata, e_ata, dist)
        self._cum_dealt += dealt
        self._cum_recv += recv
        self._phase_ticks[phase] += 1
        self._min_own_alt = min(self._min_own_alt, own.position.z)
        self._min_enemy_alt = min(self._min_enemy_alt, enemy.position.z)
        self._min_dist = min(self._min_dist, dist)
        if own.position.z < KNOCKOUT_ALT_M:
            self._own_ko_ticks += 1
        if enemy.position.z < KNOCKOUT_ALT_M:
            self._enemy_ko_ticks += 1

        # --- 파생: 닫힘속도 / 비에너지 / VP / Task ---
        closure = 0.0
        if self._prev_dist is not None and self._prev_elapsed is not None:
            dt = elapsed - self._prev_elapsed
            if dt > 1e-3:
                closure = -(dist - self._prev_dist) / dt  # +면 접근
        self._prev_dist = dist
        self._prev_elapsed = elapsed

        G = 9.81
        own_energy = own.position.z + (own_spd * own_spd) / (2.0 * G)
        enemy_energy = enemy.position.z + (enemy_spd * enemy_spd) / (2.0 * G)

        task = str(action_info.get("task", "") or "")
        if task:
            self._task_ticks[task] = self._task_ticks.get(task, 0) + 1
        vp = action_info.get("vp")
        vp_x = vp_y = vp_z = vp_dist = vp_dive = 0.0
        if vp is not None and len(vp) >= 3:
            vp_x, vp_y, vp_z = float(vp[0]), float(vp[1]), float(vp[2])
            vdx, vdy, vdz = vp_x - own.position.x, vp_y - own.position.y, vp_z - own.position.z
            vp_dist = math.sqrt(vdx * vdx + vdy * vdy + vdz * vdz)
            vhoriz = math.sqrt(vdx * vdx + vdy * vdy)
            vp_dive = -math.degrees(math.atan2(vdz, max(vhoriz, 1e-6)))  # +면 VP가 아래

        rec = TickRecord(
            tick=self._tick,
            elapsed_sec=round(elapsed, 3),
            own_x=round(own.position.x, 1),
            own_y=round(own.position.y, 1),
            own_z=round(own.position.z, 1),
            own_roll=round(own.rotation.roll, 1),
            own_pitch=round(own.rotation.pitch, 1),
            own_yaw=round(own.rotation.yaw, 1),
            own_vx=round(own.velocity.x, 1),
            own_vy=round(own.velocity.y, 1),
            own_vz=round(own.velocity.z, 1),
            own_speed=round(own_spd, 1),
            enemy_x=round(enemy.position.x, 1),
            enemy_y=round(enemy.position.y, 1),
            enemy_z=round(enemy.position.z, 1),
            enemy_roll=round(enemy.rotation.roll, 1),
            enemy_pitch=round(enemy.rotation.pitch, 1),
            enemy_yaw=round(enemy.rotation.yaw, 1),
            enemy_vx=round(enemy.velocity.x, 1),
            enemy_vy=round(enemy.velocity.y, 1),
            enemy_vz=round(enemy.velocity.z, 1),
            enemy_speed=round(enemy_spd, 1),
            distance=round(dist, 1),
            ata_deg=round(my_ata, 2),
            aa_deg=round(my_aa, 2),
            enemy_ata_deg=round(e_ata, 2),
            phase_active=phase,
            dmg_dealt=round(dealt, 4),
            dmg_received=round(recv, 4),
            cmd_roll=round(cmd.roll_cmd, 4) if cmd else 0.0,
            cmd_pitch=round(cmd.pitch_cmd, 4) if cmd else 0.0,
            cmd_yaw=round(cmd.yaw_cmd, 4) if cmd else 0.0,
            cmd_throttle=round(cmd.throttle_cmd, 4) if cmd else 0.0,
            task=task,
            vp_x=round(vp_x, 1),
            vp_y=round(vp_y, 1),
            vp_z=round(vp_z, 1),
            vp_dist=round(vp_dist, 1),
            vp_dive_deg=round(vp_dive, 1),
            closure_ms=round(closure, 1),
            own_energy_m=round(own_energy, 0),
            enemy_energy_m=round(enemy_energy, 0),
        )
        self._records.append(rec)
        if self._csv_writer:
            self._csv_writer.writerow(rec.__dict__)
            self._csv_file.flush()

        if self._tick % self.print_interval == 0:
            self._print_live(rec)

    def _print_live(self, r: TickRecord):
        print(
            f"[Engage] t={r.elapsed_sec:6.1f}s  "
            f"task={(r.task or '-'):16s}  "
            f"dist={r.distance:6.0f}m  clos={r.closure_ms:+5.0f}  "
            f"ATA={r.ata_deg:5.1f}  alt={r.own_z:6.0f}  spd={r.own_speed:5.0f}  "
            f"E={r.own_energy_m:6.0f}vs{r.enemy_energy_m:6.0f}  "
            f"phase={r.phase_active or '-':6s}  "
            f"dmg={self._cum_dealt:6.2f}/{self._cum_recv:6.2f}"
        )

    def stop(self):
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
        self._print_summary()

    def _print_summary(self):
        n = len(self._records)
        if n == 0:
            print("[EngageLog] No data recorded.")
            return

        dur = self._records[-1].elapsed_sec
        ratio = self._cum_dealt / max(self._cum_recv, 0.001)
        if self._cum_dealt > self._cum_recv:
            result = f"WIN  ({self.team_name})"
        elif self._cum_recv > self._cum_dealt:
            result = f"LOSS ({self.team_name})"
        else:
            result = "DRAW"

        avg_d = sum(r.distance for r in self._records) / n
        avg_a = sum(r.own_z for r in self._records) / n
        avg_s = sum(r.own_speed for r in self._records) / n
        avg_ata = sum(r.ata_deg for r in self._records) / n

        p1 = self._phase_ticks.get("Phase1", 0)
        p2 = self._phase_ticks.get("Phase2", 0)
        p3 = self._phase_ticks.get("Phase3", 0)
        pn = self._phase_ticks.get("", 0)

        print(f"""
{'=' * 60}
  ENGAGEMENT SUMMARY  [{self.team_name}]
{'=' * 60}
  Duration:        {dur:.1f}s  ({n} ticks)
  Result:          {result}

  DAMAGE
    Dealt:         {self._cum_dealt:.2f}
    Received:      {self._cum_recv:.2f}
    Ratio:         {ratio:.2f}x

  PHASE WEZ TICKS
    Phase1 (x1.0): {p1:>5}
    Phase2 (x0.3): {p2:>5}
    Phase3 (x0.1): {p3:>5}
    Outside WEZ:   {pn:>5}

  FLIGHT
    Avg distance:  {avg_d:.0f}m    Min: {self._min_dist:.0f}m
    Avg altitude:  {avg_a:.0f}m    Min: {self._min_own_alt:.0f}m  (KO<{KNOCKOUT_ALT_M:.0f}m)
    Avg speed:     {avg_s:.0f}m/s
    Avg ATA(LOS):  {avg_ata:.1f}deg

  SAFETY
    Own alt violations:   {self._own_ko_ticks} ticks
    Enemy alt violations: {self._enemy_ko_ticks} ticks
{self._format_task_breakdown(n)}
  CSV: {self._csv_path}
{'=' * 60}""")

    def _format_task_breakdown(self, n: int) -> str:
        if not self._task_ticks:
            return ""
        lines = ["\n  STRATEGY (Task별 체류시간)"]
        for name, cnt in sorted(self._task_ticks.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {name:18s}: {cnt:>5} ticks ({cnt / n * 100:.1f}%)")
        return "\n".join(lines)


class EngagementPolicy:
    """Wraps any CommandPolicy to add engagement logging."""

    def __init__(self, inner, monitor: EngagementMonitor):
        self.inner = inner
        self.monitor = monitor

    def reset(self, context: RemoteClientContext) -> None:
        self.inner.reset(context)

    def compute_command(self, context: RemoteClientContext) -> CMD:
        cmd = self.inner.compute_command(context)
        # inner(ProviderCommandPolicy)가 직전 BT 결과(vp/task)를 보관해 둠
        action_info = getattr(self.inner, "_last_action_info", None)
        self.monitor.record(context, cmd, action_info)
        return cmd
