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
	class Task_HighYoYo : public SyncActionNode
	{
	public:
		Task_HighYoYo(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config) {}
		~Task_HighYoYo() {}
		static PortsList providedPorts();
		NodeStatus tick() override;
	};
}
