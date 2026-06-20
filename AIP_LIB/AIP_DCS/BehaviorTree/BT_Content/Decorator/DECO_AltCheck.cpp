#include "DECO_AltCheck.h"

namespace Action
{
	PortsList DECO_AltCheck::providedPorts()
	{
		return {
			InputPort<CPPBlackBoard*>("BB"),
			InputPort<std::string>("UpDown"),
			InputPort<std::string>("Altitude")
		};
	}

	NodeStatus DECO_AltCheck::tick()
	{
		Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");
		Optional<std::string> UpOrDown = getInput<std::string>("UpDown");
		Optional<std::string> Alt = getInput<std::string>("Altitude");

		float CurrentAlt = (float)(*BB)->MyLocation_Cartesian.Z;
		std::string UD = UpOrDown.value();
		float InputAlt = std::stof(Alt.value());

		if (UD == "Greater")
		{
			return (CurrentAlt >= InputAlt) ? NodeStatus::SUCCESS : NodeStatus::FAILURE;
		}
		else if (UD == "Less")
		{
			return (CurrentAlt <= InputAlt) ? NodeStatus::SUCCESS : NodeStatus::FAILURE;
		}
		return NodeStatus::FAILURE;
	}
}
