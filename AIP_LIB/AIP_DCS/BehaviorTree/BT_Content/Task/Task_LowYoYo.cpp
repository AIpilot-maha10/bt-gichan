#include "Task_LowYoYo.h"
#include "VPSafety.h"

PortsList Action::Task_LowYoYo::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_LowYoYo::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

	// Low Yo-Yo: slight dive toward target to gain speed for re-approach
	float lead_sec = std::min((*BB)->Distance / std::max((*BB)->MySpeed_MS, 100.0f), 3.0f);

	Vector3 vp = (*BB)->TargetLocaion_Cartesian
		+ (*BB)->TargetForwardVector * lead_sec * (*BB)->TargetSpeed_MS
		- Vector3(0.0f, 0.0f, 200.0f);

	// LowYoYo는 의도적으로 약간 다이브하지만 그래도 안전범위 내로 제한
	MakeVPSafe(*BB, vp, 25.0f);
	(*BB)->VP_Cartesian = vp;

	(*BB)->IsAimmingMode = false;
	(*BB)->SelectedBehavior = "LowYoYo";

	return NodeStatus::SUCCESS;
}
