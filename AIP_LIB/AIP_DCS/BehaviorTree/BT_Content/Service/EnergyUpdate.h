#pragma once
#include "../../behaviortree_cpp_v3/action_node.h"
#include "../../behaviortree_cpp_v3/bt_factory.h"
#include "../../../Geometry/Vector3.h"
#include "../../../Geometry/Quaternion.h"
#include "../Functions.h"
#include "..//BlackBoard/CPPBlackBoard.h"

using namespace BT;

namespace Action
{
	// (v7 A-1) 비에너지 Es = alt + v²/2g 와 적과의 차이를 산출한다.
	class EnergyUpdate : public SyncActionNode
	{
	public:

		EnergyUpdate(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config)
		{
		}

		~EnergyUpdate()
		{
		}

		static PortsList providedPorts();

		NodeStatus tick() override;
	};
}
