//LOSR(시선 회전율) 산출 서비스 노드 — (v7 A-1)
//
//교범 §4.3.9: LOSR은 BFM 판단의 기본축이다.
//  · 턴서클 진입    = 후방 LOSR 증가 + 적 AA 증가가 멈춤
//  · 리드턴 시작    = 급격한 후방 LOSR 증가  (§4.8.3.1)
//  · 리드턴 너무 이름 = LOSR이 얼어붙음 → G를 잠깐 푼다 (§4.8.3.2)
//  · 2서클 승리단서 = 전방 LOSR + AA<90    (§4.8.4.1.5.1)
//  · TCX/Ease 종료  = 후방 LOSR 발생       (§4.6.3.1.8)
//
//⚠️ 양자화 함정: 위경도가 1e-6도(≈0.11m) 단위로 들어온다. 60Hz 인접 틱(이동 4m)으로
//   방향 변화를 재면 노이즈가 ~90°/s 껴서 이론치의 6배가 나온다(A-4에서 확인).
//   그래서 기선을 12틱(0.2초, 이동 ~50m)으로 늘렸다. 교차검증 실측/이론 = 0.92.
//
//이 노드는 지표만 만든다 — 행동을 바꾸지 않는다. 도입 검증은 "같은 시드에서 결과가
//완전히 동일한가"로 한다. 하나라도 다르면 어딘가 부작용이 있다는 뜻이다.

#include "LosRateUpdate.h"

namespace Action
{
	PortsList LosRateUpdate::providedPorts()
	{
		return {
			InputPort<CPPBlackBoard*>("BB")
		};
	}

	NodeStatus LosRateUpdate::tick()
	{
		Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");
		CPPBlackBoard* bb = *BB;

		const int N = CPPBlackBoard::LOSR_BASE + 1;

		//적을 놓친 동안의 이력은 버린다. 안 버리면 재포착 순간에 그동안 누적된
		//각도가 0.2초로 나눠져 터무니없이 큰 LOSR이 튀어나온다.
		if (bb->Enemy.empty())
		{
			bb->LosHistCount = 0;
			bb->LosHistHead = 0;
			bb->LosRate_DegPerSec = 0.0f;
			bb->LosRateMag_DegPerSec = 0.0f;
			return NodeStatus::SUCCESS;
		}

		const Vector3 los = bb->TargetLocaion_Cartesian - bb->MyLocation_Cartesian;

		//겹쳐 있으면 방향이 정의되지 않는다 (angleBetween이 0으로 나눈다)
		if (los.lengthSquared() < 1.0)
		{
			bb->LosRate_DegPerSec = 0.0f;
			bb->LosRateMag_DegPerSec = 0.0f;
			return NodeStatus::SUCCESS;
		}

		//현재값을 링버퍼에 넣는다
		bb->LosHistVec[bb->LosHistHead] = los;
		bb->LosHistAta[bb->LosHistHead] = bb->Los_Degree;
		bb->LosHistTime[bb->LosHistHead] = bb->RunningTime;
		const int head = bb->LosHistHead;
		bb->LosHistHead = (bb->LosHistHead + 1) % N;
		if (bb->LosHistCount < N) bb->LosHistCount++;

		//기선이 아직 안 찼으면 0을 낸다 (짧은 기선으로 계산하면 양자화 노이즈를 먹는다)
		if (bb->LosHistCount < N)
		{
			bb->LosRate_DegPerSec = 0.0f;
			bb->LosRateMag_DegPerSec = 0.0f;
			return NodeStatus::SUCCESS;
		}

		//가장 오래된 표본 = 링버퍼에서 머리 바로 다음 칸
		const int tail = bb->LosHistHead;
		const double dt = bb->LosHistTime[head] - bb->LosHistTime[tail];
		if (dt <= 1e-6)
		{
			bb->LosRate_DegPerSec = 0.0f;
			bb->LosRateMag_DegPerSec = 0.0f;
			return NodeStatus::SUCCESS;
		}

		//관성 LOS 회전각 (내 자세와 무관 — 순수하게 시선이 공간에서 얼마나 돌았나)
		const double angRad = bb->LosHistVec[tail].angleBetween(bb->LosHistVec[head]);
		const float mag = (float)(angRad * 57.2958 / dt);

		//부호: ATA가 늘면 적이 내 기수에서 멀어지는 중 = 후방(+)
		const float dAta = bb->LosHistAta[head] - bb->LosHistAta[tail];
		const float sgn = (dAta > 0.0f) ? 1.0f : ((dAta < 0.0f) ? -1.0f : 0.0f);

		bb->LosRateMag_DegPerSec = mag;
		bb->LosRate_DegPerSec = mag * sgn;

		//닫힘속도도 여기서 낸다 — LOS 벡터 이력이 이미 있으므로 길이 차만 쓰면 된다.
		//부호: +면 가까워지는 중(교범의 closure와 같은 방향).
		//같은 12틱 기선을 쓰므로 LOSR과 시간 정렬이 맞는다.
		const double dNear = bb->LosHistVec[tail].length() - bb->LosHistVec[head].length();
		bb->Closure_MS = (float)(dNear / dt);

		return NodeStatus::SUCCESS;
	}
}
