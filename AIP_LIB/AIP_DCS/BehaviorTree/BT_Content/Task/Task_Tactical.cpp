#include "Task_Tactical.h"
#include "VPSafety.h"
#include <algorithm>
#include <cmath>

PortsList Action::Task_Tactical::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_Tactical::tick()
{
	Optional<CPPBlackBoard*> BBopt = getInput<CPPBlackBoard*>("BB");
	if (!BBopt || BBopt.value() == nullptr)
		return NodeStatus::FAILURE;
	CPPBlackBoard* bb = BBopt.value();

	const Vector3 myPos = bb->MyLocation_Cartesian;
	const Vector3 tgtPos = bb->TargetLocaion_Cartesian;

	// 적이 없으면 직진
	if (bb->Enemy.empty())
	{
		bb->VP_Cartesian = myPos + bb->MyForwardVector * 10000.0f;
		bb->IsAimmingMode = false;
		bb->SelectedBehavior = "Straight";
		return NodeStatus::SUCCESS;
	}

	const float alt = (float)myPos.Z;
	const float dist = bb->Distance;
	const float los = bb->Los_Degree;
	const float ao = bb->MyAngleOff_Degree;

	Vector3 vp;
	const char* behavior = "Pursuit";
	bool aiming = false;
	float maxDive = 15.0f;

	// horizontal forward vector (flattened) for search/recover
	Vector3 fwdFlat = bb->MyForwardVector;
	fwdFlat.Z = 0.0;
	float fwdLen = (float)std::sqrt(fwdFlat.X * fwdFlat.X + fwdFlat.Y * fwdFlat.Y);
	if (fwdLen > 1e-3f) fwdFlat = fwdFlat * (1.0f / fwdLen);

	if (alt < 700.0f)
	{
		// PRIORITY 0: 저고도 비상 상승 (wings-level climb)
		vp = myPos + fwdFlat * 1500.0f + Vector3(0.0f, 0.0f, 2500.0f);
		behavior = "AltRecover";
	}
	else if (los > 95.0f && dist < 2500.0f)
	{
		// 방어: 적이 6시이고 근접 → 하드 브레이크 + 상승
		vp = myPos + bb->MyRightVector * 8000.0f + Vector3(0.0f, 0.0f, 500.0f);
		behavior = "DefensiveBreak";
	}
	else if (los < 1.0f && dist < 914.0f)
	{
		// Phase1 정밀 교전
		vp = tgtPos; aiming = true; behavior = "Pursuit";
	}
	else if (ao < 10.0f && dist < 1067.0f)
	{
		// Phase2
		vp = tgtPos; aiming = true; behavior = "Pursuit";
	}
	else if (ao < 25.0f && dist < 1220.0f)
	{
		// Phase3 리드 (Phase1 진입 시도)
		float lead = std::min(dist / std::max(bb->TargetSpeed_MS, 50.0f), 3.0f);
		vp = tgtPos + bb->TargetForwardVector * bb->TargetSpeed_MS * lead;
		behavior = "LeadPursuit";
	}
	else if (los > 40.0f)
	{
		// 수색/획득: 적이 기수에서 크게 벗어남 → 수평 turn-in + 약간 상승
		Vector3 toT = tgtPos - myPos; toT.Z = 0.0;
		float l = (float)std::sqrt(toT.X * toT.X + toT.Y * toT.Y);
		Vector3 dir = (l > 1.0f) ? toT * (1.0f / l) : fwdFlat;
		vp = myPos + dir * 5000.0f;
		vp.Z = myPos.Z + 400.0f;
		behavior = "Search";
	}
	else if (ao > 30.0f && dist < 1500.0f)
	{
		// 오버슈트 회피
		vp = tgtPos + bb->TargetRightVector * 800.0f + Vector3(0.0f, 0.0f, 300.0f);
		behavior = "OffsetPursuit";
	}
	else if (ao < 25.0f && dist > 1500.0f && dist < 4000.0f)
	{
		// 하이요요: 위로 당겨 오버테이크 속도 조절
		Vector3 toT = tgtPos - myPos;
		float d = std::max((float)toT.length(), 1.0f);
		Vector3 dir = toT * (1.0f / d);
		vp = myPos + dir * d * 0.5f + Vector3(0.0f, 0.0f, 1500.0f);
		behavior = "HighYoYo";
	}
	else if (dist > 4000.0f)
	{
		// 로우요요: 재접근 에너지 확보
		float lead = std::min(dist / std::max(bb->MySpeed_MS, 100.0f), 3.0f);
		vp = tgtPos + bb->TargetForwardVector * lead * bb->TargetSpeed_MS - Vector3(0.0f, 0.0f, 200.0f);
		behavior = "LowYoYo";
		maxDive = 25.0f;
	}
	else if (ao < 60.0f)
	{
		// 일반 리드 추적
		float lead = std::min(dist / std::max(bb->TargetSpeed_MS, 50.0f), 3.0f);
		vp = tgtPos + bb->TargetForwardVector * bb->TargetSpeed_MS * lead;
		behavior = "LeadPursuit";
	}
	else
	{
		// 기본: 직접 추적
		vp = tgtPos; aiming = true; behavior = "Pursuit";
	}

	// 공통 안전 클램프(지상충돌/과도 다이브 방지)
	MakeVPSafe(bb, vp, maxDive);

	bb->VP_Cartesian = vp;
	bb->IsAimmingMode = aiming;
	bb->SelectedBehavior = behavior;
	return NodeStatus::SUCCESS;
}
