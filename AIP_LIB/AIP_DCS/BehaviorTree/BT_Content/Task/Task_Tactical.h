#pragma once
#include "../../behaviortree_cpp_v3/action_node.h"
#include "../../behaviortree_cpp_v3/bt_factory.h"
#include "../../../Geometry/Vector3.h"
#include "../Functions.h"
#include "../BlackBoard/CPPBlackBoard.h"

using namespace BT;

namespace Action
{
	// 전술 결정 단일 노드.
	// BehaviorTree.CPP v3(이 vendored 버전)에서 "Sequence 안에 Fallback"이 자식을 틱하지 못하는
	// 버그가 있어, XML의 다분기 Fallback 대신 C++ if/else 상태머신으로 전술을 직접 결정한다.
	// 상태(우선순위순): AltRecover(저고도) → DefensiveBreak(실위협 방어) →
	//   GunAim(WEZ 콘 직조준+속도관리) → HardTurn(코너속도 최대선회) →
	//   Intercept(원거리 풀리드) → LeadPursuit(중거리 리드추적)
	// VP뿐 아니라 BB->Throttle(전술 스로틀)도 이 노드가 결정한다.
	class Task_Tactical : public SyncActionNode
	{
	public:
		Task_Tactical(const std::string& name, const NodeConfiguration& config) : SyncActionNode(name, config) {}
		~Task_Tactical() {}
		static PortsList providedPorts();
		NodeStatus tick() override;
	};
}
