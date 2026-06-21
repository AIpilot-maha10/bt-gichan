#pragma once
#include "../../behaviortree_cpp_v3/action_node.h"
#include "../../behaviortree_cpp_v3/bt_factory.h"
#include "../../../Geometry/Vector3.h"
#include "../Functions.h"
#include "../BlackBoard/CPPBlackBoard.h"

using namespace BT;

namespace Action
{
	// SEARCH/획득 기동: 나란히(측면) 출발 또는 적이 사각에 있을 때
	// 적을 직접 조준하면 급격한 pitch/roll로 루프·급강하가 생기므로,
	// "적이 있는 수평 방향"으로만 선회하면서 고도는 약간 상승 유지한다.
	class Task_Search : public SyncActionNode
	{
	public:
		Task_Search(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config) {}
		~Task_Search() {}
		static PortsList providedPorts();
		NodeStatus tick() override;
	};
}
