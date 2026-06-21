from __future__ import annotations

import os

import numpy as np

from dogfight.ai.action_provider import ActionContext, ActionProvider, ActionResult, clip_action
from dogfight.ai.native_bt import AIPilot


REMOTE_BT_FIGHTER_ID = 0
SAFE_VP = np.zeros(3, dtype=np.float32)


class BTActionProvider(ActionProvider):
    def __init__(
        self,
        dll_name: str = "AIP_DCS_base.dll",
        ai_pilot: AIPilot | None = None,
        confidence: float = 0.85,
        rule_xml_path: str | None = None,
    ):
        self.ai_pilot = ai_pilot if ai_pilot is not None else AIPilot(dll_name)
        self.confidence = confidence
        self._registered_fighter_ids: dict[int, int] = {}
        # DLL이 로드할 Rule XML을 직접 지정(폴더 1개에서 클라별 다른 XML).
        # CreateBehaviorTree(지연 호출)보다 먼저 전역에 설정되어야 하므로 여기서 호출.
        # BT 라이브러리 realpath()가 bare 상대명("Rule_gichan.xml")을 거부하므로 절대경로로 변환.
        # XML은 DLL과 같은 Release 폴더에 있으므로 DLL 디렉터리 기준으로 해소.
        if rule_xml_path:
            resolved = rule_xml_path
            if not os.path.isabs(resolved):
                dll_dir = os.path.dirname(getattr(self.ai_pilot, "dll_path", "") or "")
                candidate = os.path.join(dll_dir, resolved) if dll_dir else resolved
                resolved = candidate if os.path.exists(candidate) else os.path.abspath(resolved)
            self.ai_pilot.SetRuleXmlPath(resolved)

    def reset(self, context: ActionContext | None = None) -> None:
        # 2026-05-26: Keep native BT alive across episode resets for multienv.
        return None

    def _remove_behavior_tree(self, fighter_id: int) -> None:
        try:
            self.ai_pilot.RemoveBT(fighter_id)
        except Exception:
            pass
        self._registered_fighter_ids.pop(fighter_id, None)

    def _ensure_behavior_tree(self, context: ActionContext) -> None:
        model = context.sim.get_model()
        fighter_id = model.fighterID
        force_side = int(model._forceSide)
        registered_force = self._registered_fighter_ids.get(fighter_id)
        if registered_force == force_side:
            return
        if registered_force is not None:
            raise RuntimeError(
                "BT fighter id reused with a different force side: "
                f"fighter_id={fighter_id}, previous={registered_force}, current={force_side}"
            )
        # 2026-05-26: Create native BT once and reuse it until provider close().
        self.ai_pilot.CreateBehaviorTree(fighter_id, force_side)
        self._registered_fighter_ids[fighter_id] = force_side

    def _ensure_remote_behavior_tree(self, fighter_id: int, force_side: int) -> None:
        registered_force = self._registered_fighter_ids.get(fighter_id)
        if registered_force == force_side:
            return
        if registered_force is not None:
            raise RuntimeError(
                "Remote BT fighter id reused with a different force side: "
                f"fighter_id={fighter_id}, previous={registered_force}, current={force_side}"
            )
        # 2026-05-26: Remote BT is created once and reused until provider close().
        self.ai_pilot.CreateBehaviorTree(fighter_id, force_side)
        self._registered_fighter_ids[fighter_id] = force_side

    @staticmethod
    def _vp_to_array(vp) -> tuple[np.ndarray, bool]:
        vp_array = np.array([vp.X, vp.Y, vp.Z], dtype=np.float32)
        if np.all(np.isfinite(vp_array)):
            return vp_array, True
        return SAFE_VP.copy(), False

    def compute_action(self, context: ActionContext) -> ActionResult:
        if context.sim is None or context.opponent_sim is None:
            return self._compute_remote_action(context)

        self._ensure_behavior_tree(context)
        model = context.sim.get_model()
        opponent_model = context.opponent_sim.get_model()

        control_action = self.ai_pilot.Step(
            model.fighterID,
            model._forceSide,
            opponent_model.fighterID,
            opponent_model._forceSide,
            model.get_fdm_data(),
            opponent_model.get_fdm_data(),
        )
        vp = self.ai_pilot.GetVP(model.fighterID, model._forceSide, model.get_fdm_data())
        vp_array, vp_valid = self._vp_to_array(vp)

        action = clip_action(
            [
                control_action.RollCMD,
                control_action.PitchCMD,
                control_action.RudderCMD,
                control_action.Throttle,
            ]
        )

        if hasattr(context.sim, "action"):
            context.sim.action[:] = action
        if hasattr(context.sim, "VP"):
            context.sim.VP[:] = vp_array

        return ActionResult(
            action=action,
            source="bt",
            confidence=self.confidence,
            info={
                "vp": vp_array,
                "vp_valid": vp_valid,
                "task": self.ai_pilot.GetCurrentTaskName(model.fighterID),
                "fighter_id": model.fighterID,
                "force_side": model._forceSide,
                "target_fighter_id": opponent_model.fighterID,
                "target_force_side": opponent_model._forceSide,
            },
        )

    def _compute_remote_action(self, context: ActionContext) -> ActionResult:
        my_plane = context.info["my_plane_data"]
        target_plane = context.info["target_plane_data"]
        fighter_id = int(context.info.get("my_plane_id", 1))
        bt_fighter_id = REMOTE_BT_FIGHTER_ID
        force_side = int(context.info.get("my_force_side", 1))

        self._ensure_remote_behavior_tree(bt_fighter_id, force_side)
        control_action = self.ai_pilot.StepWithPlaneData(my_plane, target_plane)
        vp = self.ai_pilot.GetVPWithPlaneData(my_plane)
        vp_array, vp_valid = self._vp_to_array(vp)
        action = clip_action(
            [
                control_action.RollCMD,
                control_action.PitchCMD,
                control_action.RudderCMD,
                control_action.Throttle,
            ]
        )
        return ActionResult(
            action=action,
            source="bt",
            confidence=self.confidence,
            info={
                "vp": vp_array,
                "vp_valid": vp_valid,
                "task": self.ai_pilot.GetCurrentTaskName(bt_fighter_id),
                "fighter_id": fighter_id,
                "bt_fighter_id": bt_fighter_id,
                "force_side": force_side,
            },
        )

    def close(self) -> None:
        for fighter_id in list(self._registered_fighter_ids):
            self._remove_behavior_tree(fighter_id)
