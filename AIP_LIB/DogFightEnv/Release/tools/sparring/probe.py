"""BT 상태를 판 사이에 확실히 초기화하는 ActionProvider.

## 왜 필요한가 (하네스 최우선 수정 대상)

`CPPBlackBoard::RunningTime`은 **생성자에서만 0**이고(`CPPBlackBoard.cpp:5`),
`RunCPPBT()`가 매 틱 `RunningTime += DeltaSecond`로 무한 누적한다
(`CPPBehaviorTree.cpp:297`). `Task_Tactical`은 이 값으로 WEZ Phase를 고른다.

그런데 `BTActionProvider.reset()`은 **no-op**이다(`bt_action_provider.py:38-40`,
"Keep native BT alive across episode resets for multienv"). 따라서 한 프로세스에서
연속으로 판을 돌리면 **2판째부터 BT가 Phase2/3 상태로 시작**한다. 이걸 고치지 않으면
하네스가 뽑는 모든 숫자가 거짓이 된다.

## 어떻게 고치는가

`RemoveBT(fighter_id)`로 **자기 트리만** 파괴한다. `BTList.erase()` →
`shared_ptr` 소멸 → `~UCPPBehaviorTree()` → `delete BB` → 다음
`CreateBehaviorTree()`가 `new CPPBlackBoard()`로 RunningTime=0인 새 블랙보드를 만든다.
(누수 없음 — 소멸자가 BB를 지운다. `CPPBehaviorTree.cpp:55-58`)

⚠️ DLL의 `Reset()`은 쓰지 않는다. 전역 `BTList.clear()`라서 **양측이 같은 DLL 파일을
쓰는 경우**(자기대전 등) 상대 트리까지 지운다. 상대 provider는 자기 캐시(
`_registered_fighter_ids`)가 살아 있어 트리를 다시 만들지 않으므로, 상대가 조용히
빈 BT로 싸우게 된다.
"""

from __future__ import annotations

from typing import Any

from dogfight.ai.action_provider import ActionContext, ActionResult
from dogfight.ai.bt_action_provider import BTActionProvider


class RecordingBTProvider(BTActionProvider):
    """판 사이에 BT를 재생성하고, 마지막 VP/Task를 기록해 두는 provider."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.last_task: str = ""
        self.last_vp = None
        self.last_debug: dict = {}   # (A-0) BT 블랙보드 내부값
        self.reset_count: int = 0

    def reset(self, context: ActionContext | None = None) -> None:
        for fighter_id in list(self._registered_fighter_ids):
            try:
                self.ai_pilot.RemoveBT(fighter_id)
            except Exception:
                pass
        self._registered_fighter_ids.clear()
        self.last_task = ""
        self.last_vp = None
        self.last_debug = {}
        self.reset_count += 1

    def compute_action(self, context: ActionContext) -> ActionResult:
        result = super().compute_action(context)
        info = result.info or {}
        self.last_task = info.get("task", "") or ""
        self.last_vp = info.get("vp")
        fid = info.get("fighter_id")
        if fid is not None:
            # Step 직후에 읽어야 이번 틱의 블랙보드 상태가 잡힌다
            self.last_debug = self.ai_pilot.GetDebugScalars(fid)
        return result
