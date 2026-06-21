#include "Task_Tactical.h"
#include "VPSafety.h"
#include <algorithm>
#include <cmath>
#include <string>

PortsList Action::Task_Tactical::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

static float clampf(float v, float lo, float hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

NodeStatus Action::Task_Tactical::tick()
{
	Optional<CPPBlackBoard*> BBopt = getInput<CPPBlackBoard*>("BB");
	if (!BBopt || BBopt.value() == nullptr)
		return NodeStatus::FAILURE;
	CPPBlackBoard* bb = BBopt.value();

	const Vector3 myPos = bb->MyLocation_Cartesian;
	const Vector3 tgtPos = bb->TargetLocaion_Cartesian;

	// no enemy -> fly straight
	if (bb->Enemy.empty())
	{
		bb->VP_Cartesian = myPos + bb->MyForwardVector * 10000.0f;
		bb->IsAimmingMode = false;
		bb->SelectedBehavior = "Straight";
		bb->BehaviorHoldTicks = 0;
		return NodeStatus::SUCCESS;
	}

	const float alt = (float)myPos.Z;
	const float dist = bb->Distance;
	const float los = bb->Los_Degree;
	const float ao = bb->MyAngleOff_Degree;

	// horizontal forward vector (flattened) for search/recover
	Vector3 fwdFlat = bb->MyForwardVector;
	fwdFlat.Z = 0.0;
	float fwdLen = (float)std::sqrt(fwdFlat.X * fwdFlat.X + fwdFlat.Y * fwdFlat.Y);
	if (fwdLen > 1e-3f) fwdFlat = fwdFlat * (1.0f / fwdLen);

	// A-step: predict enemy intercept point (constant velocity).
	// enemy velocity = heading * speed; lead by time-to-reach so we aim where the
	// enemy WILL be, not where it is -> better nose-on at the merge.
	const Vector3 enemyVel = bb->TargetForwardVector * bb->TargetSpeed_MS;
	const float t_lead = clampf(dist / std::max(bb->MySpeed_MS, 100.0f), 0.5f, 2.5f);
	const Vector3 predEnemy = tgtPos + enemyVel * t_lead;

	// 1) raw tactical decision by priority
	std::string raw = "Pursuit";
	if (alt < 700.0f)
		raw = "AltRecover";
	else if (los > 95.0f && dist < 2500.0f)
		raw = "DefensiveBreak";
	else if (los < 1.0f && dist < 914.0f)
		raw = "Pursuit";
	else if (ao < 10.0f && dist < 1067.0f)
		raw = "Pursuit";
	else if (ao < 25.0f && dist < 1220.0f)
		raw = "LeadPursuit";
	else if (los > 40.0f && dist > 2500.0f)
		raw = "Search";       // long-range: gentle horizontal turn-in (safe acquisition)
	else if (los > 40.0f)
		raw = "HardTurn";     // close-range off-nose: tight max-rate turn toward intercept
	else if (ao > 30.0f && dist < 1500.0f)
		raw = "OffsetPursuit";
	else if (ao < 25.0f && dist > 1500.0f && dist < 4000.0f)
		raw = "HighYoYo";
	else if (dist > 4000.0f)
		raw = "LowYoYo";
	else if (ao < 60.0f)
		raw = "LeadPursuit";
	else
		raw = "Pursuit";

	// 2) hysteresis: safety/defense states switch instantly; other maneuver states
	// are held for a minimum number of ticks to stop per-tick Search<->Pursuit thrash.
	const std::string last = bb->SelectedBehavior;
	const bool rawHard = (raw == "AltRecover" || raw == "DefensiveBreak");
	const bool lastSoft = !(last == "AltRecover" || last == "DefensiveBreak"
		|| last == "PreventLandCrash" || last == "None" || last == "Straight" || last == "");
	std::string behavior;
	if (rawHard)
	{
		behavior = raw;
		bb->BehaviorHoldTicks = 0;
	}
	else if (bb->BehaviorHoldTicks > 0 && lastSoft && last != raw)
	{
		behavior = last;
		bb->BehaviorHoldTicks -= 1;
	}
	else
	{
		behavior = raw;
		bb->BehaviorHoldTicks = 30;
	}

	// 3) final behavior -> VP
	Vector3 vp;
	bool aiming = false;
	float maxDive = 15.0f;

	if (behavior == "AltRecover")
	{
		vp = myPos + fwdFlat * 1500.0f + Vector3(0.0f, 0.0f, 2500.0f);
	}
	else if (behavior == "DefensiveBreak")
	{
		vp = myPos + bb->MyRightVector * 8000.0f + Vector3(0.0f, 0.0f, 500.0f);
	}
	else if (behavior == "Pursuit")
	{
		vp = predEnemy; aiming = true;
	}
	else if (behavior == "LeadPursuit")
	{
		vp = predEnemy;
	}
	else if (behavior == "Search")
	{
		// long-range acquisition: gentle horizontal turn-in toward the enemy + slight climb
		Vector3 toT = predEnemy - myPos; toT.Z = 0.0;
		float l = (float)std::sqrt(toT.X * toT.X + toT.Y * toT.Y);
		Vector3 dir = (l > 1.0f) ? toT * (1.0f / l) : fwdFlat;
		vp = myPos + dir * 5000.0f;
		vp.Z = myPos.Z + 400.0f;
	}
	else if (behavior == "HardTurn")
	{
		// close-range max-rate turn: aim straight at the intercept point so the
		// controller commands full bank + pull -> fastest nose-on. No climb offset
		// (keep energy in the turn instead of leaking it to altitude).
		vp = predEnemy;
		aiming = true;
	}
	else if (behavior == "OffsetPursuit")
	{
		vp = predEnemy + bb->TargetRightVector * 800.0f + Vector3(0.0f, 0.0f, 300.0f);
	}
	else if (behavior == "HighYoYo")
	{
		Vector3 toT = predEnemy - myPos;
		float d = std::max((float)toT.length(), 1.0f);
		Vector3 dir = toT * (1.0f / d);
		vp = myPos + dir * d * 0.5f + Vector3(0.0f, 0.0f, 1500.0f);
	}
	else if (behavior == "LowYoYo")
	{
		vp = predEnemy - Vector3(0.0f, 0.0f, 200.0f);
		maxDive = 25.0f;
	}
	else
	{
		vp = predEnemy; aiming = true;
	}

	MakeVPSafe(bb, vp, maxDive);

	bb->VP_Cartesian = vp;
	bb->IsAimmingMode = aiming;
	bb->SelectedBehavior = behavior;
	return NodeStatus::SUCCESS;
}
