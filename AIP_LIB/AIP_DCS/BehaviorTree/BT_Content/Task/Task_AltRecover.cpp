#include "Task_AltRecover.h"
#include <cmath>

PortsList Action::Task_AltRecover::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
}

NodeStatus Action::Task_AltRecover::tick()
{
	Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

	// 비상 상승: 전방벡터를 수평으로 평탄화(Z=0)해서 인버티드 상태라도
	// 컨트롤러가 wings-level로 롤한 뒤 똑바로 당겨 올라가도록 유도한다.
	// (forward를 그대로 쓰면 기수가 아래를 향한 채 상승 VP를 못 따라감)
	Vector3 fwd = (*BB)->MyForwardVector;
	fwd.Z = 0.0;
	const float len = (float)std::sqrt(fwd.X * fwd.X + fwd.Y * fwd.Y);
	if (len > 1e-3f)
		fwd = fwd * (1.0f / len);

	(*BB)->VP_Cartesian = (*BB)->MyLocation_Cartesian
		+ fwd * 1500.0f
		+ Vector3(0.0f, 0.0f, 2500.0f);

	(*BB)->IsAimmingMode = false;

	return NodeStatus::SUCCESS;
}
