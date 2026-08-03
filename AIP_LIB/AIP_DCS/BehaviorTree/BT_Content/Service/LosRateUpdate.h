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
	// (v7 A-1) LOSR 산출 서비스 노드.
	// CheckSight가 Los_Degree(=ATA)를 채운 뒤에 돌아야 한다 — 부호 판정에 쓴다.
	class LosRateUpdate : public SyncActionNode
	{
	private:

	public:

		LosRateUpdate(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config)
		{
		}

		~LosRateUpdate()
		{

		}

		static PortsList providedPorts();

		NodeStatus tick() override;
	};
}
