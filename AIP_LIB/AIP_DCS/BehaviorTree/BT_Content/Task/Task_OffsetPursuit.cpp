#include "Task_OffsetPursuit.h"
#include "VPSafety.h"

PortsList Action::Task_OffsetPursuit::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_OffsetPursuit::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

	// Offset pursuit: aim to the side of target to avoid overshoot
	Vector3 vp = (*BB)->TargetLocaion_Cartesian
		+ (*BB)->TargetRightVector * 800.0f
		+ Vector3(0.0f, 0.0f, 300.0f);

	MakeVPSafe(*BB, vp);
	(*BB)->VP_Cartesian = vp;

	(*BB)->IsAimmingMode = false;
	(*BB)->SelectedBehavior = "OffsetPursuit";

	return NodeStatus::SUCCESS;
}
