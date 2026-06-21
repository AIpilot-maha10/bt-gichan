#include "Task_Search.h"
#include "VPSafety.h"
#include <algorithm>
#include <cmath>

PortsList Action::Task_Search::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_Search::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");
	if (!BB || BB.value() == nullptr)
		return NodeStatus::FAILURE;

	CPPBlackBoard* bb = BB.value();

	// 수평 방향(적 쪽)으로만 선회. 고도차는 제거하여 급기동 방지.
	Vector3 toTarget = bb->TargetLocaion_Cartesian - bb->MyLocation_Cartesian;
	toTarget.Z = 0.0;
	const float len = (float)std::sqrt(toTarget.X * toTarget.X + toTarget.Y * toTarget.Y);
	if (len < 1.0f)
		return NodeStatus::FAILURE;

	Vector3 dir = toTarget * (1.0f / len);

	// 먼 거리의 수평 turn-in 점 + 현재 고도보다 살짝 위(에너지 유지)
	const float TURN_IN_DIST = 5000.0f;
	const float CLIMB_OFFSET = 400.0f;

	Vector3 vp = bb->MyLocation_Cartesian + dir * TURN_IN_DIST;
	vp.Z = bb->MyLocation_Cartesian.Z + CLIMB_OFFSET;

	// 안전 클램프(지상충돌/과도한 다이브 방지)는 공통 헬퍼로 일관 적용
	MakeVPSafe(bb, vp);

	bb->VP_Cartesian = vp;
	bb->IsAimmingMode = false;
	bb->SelectedBehavior = "Search";

	return NodeStatus::SUCCESS;
}
