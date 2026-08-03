//선회 기하(선회율·선회반경) 산출 서비스 노드 — (v7 A-1)
//
//교범이 요구하는데 우리에게 없던 값이다:
//  §4.8.1.3  TR(턴서클 반경) 목표 = 선회직경 1개. "적이 TR을 뺏기 시작하면 더 벌지 말고
//            가진 걸 써라"
//  §4.8.2    머지 목표는 적 CZ 통과. **적 선회반경 안으로 들어가면 반전 기회를 준다**
//  §4.3.12   Exclusive TR — 지면으로부터 선회직경 이내면 수직기동 금지
//            (지금의 임의값 1800m 저고도 가드를 원칙 있는 값으로 바꿀 수 있다)
//
//가정한 G로 계산하지 않고 **실제 비행경로에서 잰다**:
//  ω = 기수벡터가 회전한 각 / Δt      R = V / ω
//
//⚠️ 위경도 양자화(1e-6도 ≈ 0.11m) 때문에 인접 틱으로 각을 재면 노이즈가 실제의 6배로
//   낀다(A-4에서 확인). LOSR과 같은 12틱(0.2초) 기선을 쓴다.
//   단 여기서 쓰는 건 위치가 아니라 **기수벡터(자세)** 라 원래 양자화가 덜하지만,
//   같은 기선을 쓰면 두 지표의 시간 정렬이 맞아 비교가 쉬워진다.
//
//이 노드는 지표만 만든다. 행동은 바꾸지 않는다.

#include "TurnGeomUpdate.h"
#include <cmath>

namespace Action
{
	PortsList TurnGeomUpdate::providedPorts()
	{
		return {
			InputPort<CPPBlackBoard*>("BB")
		};
	}

	NodeStatus TurnGeomUpdate::tick()
	{
		Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");
		CPPBlackBoard* bb = *BB;

		const int N = CPPBlackBoard::LOSR_BASE + 1;

		//적이 없으면 적 쪽 이력이 의미를 잃는다. 통째로 끊는다.
		if (bb->Enemy.empty())
		{
			bb->TurnHistCount = 0;
			bb->TurnHistHead = 0;
			bb->TargetTurnRate_DegPerSec = 0.0f;
			bb->TargetTurnRadius_M = 0.0f;
			return NodeStatus::SUCCESS;
		}

		bb->MyFwdHist[bb->TurnHistHead] = bb->MyForwardVector;
		bb->TgtFwdHist[bb->TurnHistHead] = bb->TargetForwardVector;
		bb->TurnHistTime[bb->TurnHistHead] = bb->RunningTime;
		const int head = bb->TurnHistHead;
		bb->TurnHistHead = (bb->TurnHistHead + 1) % N;
		if (bb->TurnHistCount < N) bb->TurnHistCount++;

		if (bb->TurnHistCount < N)
			return NodeStatus::SUCCESS;   //기선이 찰 때까지는 직전값을 유지한다

		const int tail = bb->TurnHistHead;
		const double dt = bb->TurnHistTime[head] - bb->TurnHistTime[tail];
		if (dt <= 1e-6)
			return NodeStatus::SUCCESS;

		//벡터가 0이면 angleBetween이 0으로 나눈다
		if (bb->MyFwdHist[tail].lengthSquared() < 1e-9 || bb->MyFwdHist[head].lengthSquared() < 1e-9 ||
			bb->TgtFwdHist[tail].lengthSquared() < 1e-9 || bb->TgtFwdHist[head].lengthSquared() < 1e-9)
			return NodeStatus::SUCCESS;

		const double myAng = bb->MyFwdHist[tail].angleBetween(bb->MyFwdHist[head]);
		const double tgAng = bb->TgtFwdHist[tail].angleBetween(bb->TgtFwdHist[head]);

		bb->MyTurnRate_DegPerSec = (float)(myAng * 57.2958 / dt);
		bb->TargetTurnRate_DegPerSec = (float)(tgAng * 57.2958 / dt);

		//R = V / ω. ω가 0에 가까우면(거의 직선) 반경이 발산하므로 상한을 둔다.
		//99999는 "사실상 직선"의 표식이다 — 비교식에서 자연히 탈락한다.
		const float myOmegaRad = (float)(myAng / dt);
		const float tgOmegaRad = (float)(tgAng / dt);
		bb->MyTurnRadius_M = (myOmegaRad > 1e-4f)
			? bb->MySpeed_MS / myOmegaRad : 99999.0f;
		bb->TargetTurnRadius_M = (tgOmegaRad > 1e-4f)
			? bb->TargetSpeed_MS / tgOmegaRad : 99999.0f;

		//추정 하중배수. 대회 서버는 Nz를 안 주므로(9개 값뿐) 선회율로 역산한다.
		//  구심가속도 a = V·ω  ->  n = √(1 + (Vω/g)²)
		//교범 §4.6.3.1.5의 "airspeed sustaining feel"(최대 G가 아니라 속도가 유지되는 G)을
		//판정하려면 지금 몇 G인지 알아야 하는데, 그 창구가 이것뿐이다.
		//⚠️ 수평선회 가정이라 급강하/급상승 중에는 과소평가된다. 절대값보다 추세로 볼 것.
		{
			const float aLat = bb->MySpeed_MS * myOmegaRad;
			const float r = aLat / 9.80665f;
			bb->MyNz_Est = std::sqrt(1.0f + r * r);
		}

		return NodeStatus::SUCCESS;
	}
}
