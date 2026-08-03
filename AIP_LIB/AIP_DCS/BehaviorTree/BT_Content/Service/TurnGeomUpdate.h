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
	// (v7 A-1) 양측의 실제 선회율·선회반경을 비행경로에서 잰다.
	class TurnGeomUpdate : public SyncActionNode
	{
	public:

		TurnGeomUpdate(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config)
		{
		}

		~TurnGeomUpdate()
		{
		}

		static PortsList providedPorts();

		NodeStatus tick() override;
	};
}
