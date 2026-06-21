#include "Task_Pursuit.h"
#include "VPSafety.h"

PortsList Action::Task_Pursuit::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_Pursuit::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

	Vector3 vp = (*BB)->TargetLocaion_Cartesian;
	MakeVPSafe(*BB, vp);
	(*BB)->VP_Cartesian = vp;
	(*BB)->IsAimmingMode = true;
	(*BB)->SelectedBehavior = "Pursuit";

	return NodeStatus::SUCCESS;
}
