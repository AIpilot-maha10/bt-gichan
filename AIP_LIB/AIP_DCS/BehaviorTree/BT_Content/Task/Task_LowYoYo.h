#pragma once
#include "../../behaviortree_cpp_v3/action_node.h"
#include "../../behaviortree_cpp_v3/bt_factory.h"
#include "../../../Geometry/Vector3.h"
#include "../Functions.h"
#include "../BlackBoard/CPPBlackBoard.h"
#include <algorithm>

using namespace BT;

namespace Action
{
	class Task_LowYoYo : public SyncActionNode
	{
	public:
		Task_LowYoYo(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config) {}
		~Task_LowYoYo() {}
		static PortsList providedPorts();
		NodeStatus tick() override;
	};
}
