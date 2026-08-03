//비에너지 산출 서비스 노드 — (v7 A-1)
//
//교범 §4.2.3 (BFM 3대 공리 중 하나): "Energy versus Nose Position"
//  "어떤 싸움이든, 매 순간 에너지와 기수위치 중 무엇이 더 중요한지 알고 있어야 한다"
//  "가용 에너지는 ①공격적 이익 ②방어적 필요 ③머지 준비 에만 쓴다.
//   그 외에는 유지하거나 늘린다"
//
//비에너지(specific energy) Es = h + v²/2g — 고도와 속도를 한 축으로 묶은 값이다.
//단위가 미터라 "적보다 몇 m 유리한가"로 바로 읽힌다.
//
//이 노드는 지표만 만든다. 행동은 바꾸지 않는다.
//
//⚠️ 주의: 에너지 계열 *조치*는 EP8/9/17/18/19/20에서 여섯 번 연속 기각됐다.
//   지표가 생겼다고 바로 조치를 붙이지 말 것 — 그 여섯 번이 이미 그렇게 실패했다.
//   이 값은 우선 **진단용**이다.

#include "EnergyUpdate.h"

namespace Action
{
	PortsList EnergyUpdate::providedPorts()
	{
		return {
			InputPort<CPPBlackBoard*>("BB")
		};
	}

	NodeStatus EnergyUpdate::tick()
	{
		Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");
		CPPBlackBoard* bb = *BB;

		const float G = 9.80665f;

		//Cartesian의 Z가 고도. (A-0에서 LLA->Cartesian 변환 누락을 고친 뒤로 유효)
		const float myAlt = (float)bb->MyLocation_Cartesian.Z;
		const float myV = bb->MySpeed_MS;
		bb->MyEnergy_M = myAlt + (myV * myV) / (2.0f * G);

		if (bb->Enemy.empty())
		{
			//적이 없으면 비교가 무의미하다. 직전값을 남겨두면 오판을 부르므로 0으로 둔다.
			bb->TargetEnergy_M = 0.0f;
			bb->EnergyAdvantage_M = 0.0f;
			return NodeStatus::SUCCESS;
		}

		const float tgtAlt = (float)bb->TargetLocaion_Cartesian.Z;
		const float tgtV = bb->TargetSpeed_MS;
		bb->TargetEnergy_M = tgtAlt + (tgtV * tgtV) / (2.0f * G);

		bb->EnergyAdvantage_M = bb->MyEnergy_M - bb->TargetEnergy_M;

		return NodeStatus::SUCCESS;
	}
}
