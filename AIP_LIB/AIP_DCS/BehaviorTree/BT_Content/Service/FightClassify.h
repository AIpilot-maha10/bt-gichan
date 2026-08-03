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
	// (v7 A-1) "지금 어떤 종류의 싸움인가"를 정한다. 분류만 하고 행동은 바꾸지 않는다.
	// A-1의 다른 지표 노드들이 모두 돈 뒤에 실행돼야 한다(입력이 그 값들이다).
	class FightClassify : public SyncActionNode
	{
	public:

		FightClassify(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config)
		{
		}

		~FightClassify()
		{
		}

		static PortsList providedPorts();

		NodeStatus tick() override;
	};
}
