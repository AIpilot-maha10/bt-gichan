#include "Task_DefensiveBreak.h"

PortsList Action::Task_DefensiveBreak::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_DefensiveBreak::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

	// Defensive break: hard turn away + climb to evade tail attacker
	(*BB)->VP_Cartesian = (*BB)->MyLocation_Cartesian
		+ (*BB)->MyRightVector * 8000.0f
		+ Vector3(0.0f, 0.0f, 500.0f);

	(*BB)->IsAimmingMode = false;

	return NodeStatus::SUCCESS;
}
