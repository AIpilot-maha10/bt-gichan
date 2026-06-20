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
	class Task_LeadPursuit : public SyncActionNode
	{
	public:
		Task_LeadPursuit(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config) {}
		~Task_LeadPursuit() {}
		static PortsList providedPorts();
		NodeStatus tick() override;
	};
}
