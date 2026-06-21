#include "Task_HighYoYo.h"
#include "VPSafety.h"

PortsList Action::Task_HighYoYo::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_HighYoYo::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

	// High Yo-Yo: pull up above target to bleed overtake speed, then dive back
	// VP = target direction + 1500m upward offset
	Vector3 toTarget = (*BB)->TargetLocaion_Cartesian - (*BB)->MyLocation_Cartesian;
	float dist = std::max((float)toTarget.length(), 1.0f);
	Vector3 dirToTarget = toTarget * (1.0f / dist);

	Vector3 vp = (*BB)->MyLocation_Cartesian
		+ dirToTarget * dist * 0.5f
		+ Vector3(0.0f, 0.0f, 1500.0f);

	MakeVPSafe(*BB, vp);
	(*BB)->VP_Cartesian = vp;

	(*BB)->IsAimmingMode = false;
	(*BB)->SelectedBehavior = "HighYoYo";

	return NodeStatus::SUCCESS;
}
