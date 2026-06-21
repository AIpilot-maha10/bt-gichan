#include "Task_LeadPursuit.h"
#include "VPSafety.h"

PortsList Action::Task_LeadPursuit::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_LeadPursuit::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

	// Lead pursuit: VP = target position + target velocity * lead time
	float lead_sec = std::min((*BB)->Distance / std::max((*BB)->TargetSpeed_MS, 50.0f), 3.0f);

	Vector3 vp = (*BB)->TargetLocaion_Cartesian
		+ (*BB)->TargetForwardVector * (*BB)->TargetSpeed_MS * lead_sec;

	MakeVPSafe(*BB, vp);
	(*BB)->VP_Cartesian = vp;
	(*BB)->IsAimmingMode = false;
	(*BB)->SelectedBehavior = "LeadPursuit";

	return NodeStatus::SUCCESS;
}
