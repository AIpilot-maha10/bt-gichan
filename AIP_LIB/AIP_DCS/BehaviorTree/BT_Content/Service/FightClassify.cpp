//국면 분류 서비스 노드 — (v7 A-1)
//
//교범 §4.3 첫 문장:
//  "BFM은 정해진 기동의 집합이 아니다. **거리·각도·닫힘의 문제를 만들거나 푸는
//   동적 조합**이다."
//
//그래서 상태를 더 쌓는 대신 ①문제를 측정(A-1 지표 노드들) → ②문제 유형 분류(이 노드)
//→ ③해결책 선택(A-2, 아직 미구현) 구조로 간다.
//
//입력은 교범 크로스체크(§4.5) 그대로 고정한다 — 임의로 늘리지 않는다:
//  적 6개: 거리 · AspectFromTail · AOT(=적 ATA) · HCA · LOSR · closure
//  내 3개: G(추정 Nz) · LV(=VP 방향) · 속도
//
//⚠️ **현재 이 값은 아무도 읽지 않는다.** Task_Tactical은 여전히 기존 if/else로 돈다.
//   순수 지표이므로 도입 검증은 "같은 시드에서 결과 완전 동일"로 한다.
//   행동에 연결하는 건 진단으로 근거를 잡은 뒤(A-2)에 한다 —
//   측정 없이 메커니즘부터 만들어 19번 기각당한 전례가 있다.

#include "FightClassify.h"

namespace Action
{
	PortsList FightClassify::providedPorts()
	{
		return {
			InputPort<CPPBlackBoard*>("BB")
		};
	}

	NodeStatus FightClassify::tick()
	{
		Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");
		CPPBlackBoard* bb = *BB;

		if (bb->Enemy.empty())
		{
			bb->FightType = FT_Neutral;
			bb->FightTypeHold = 0;
			return NodeStatus::SUCCESS;
		}

		// ── (v7 EP33) 개전 시 고도 우위를 래치한다 ──────────────────────────────
		// 개전 직후 한 번만 판정하고 그 판 내내 유지한다. 한 번 정해지면 덮어쓰지 않는다.
		//
		// EP32는 같은 구조를 **8초**에 판정했다가 예선을 깨뜨렸다 — 그때는 이미 기동이
		// 진행돼 btjegal전 상당수 판에서 내가 적보다 위에 있고, 래치가 '우위'로 잡혀
		// 그 판 내내 강하가 꺼졌다(승 30->27, 22->18).
		// 예선 IC는 **양측 고도가 정확히 같다**(4,702m). 개전 직후로 당기면 dz≈0이라
		// 열세(2)로 잡히고 예선 동작은 EP28과 동일해진다.
		{
			const double LATCH_AT_SEC = 0.5;      // 개전 직후 — 초기 기하가 아직 살아있다
			const float  LATCH_ALT_M = 300.0f;    // 이만큼 위면 우위로 본다
			if (bb->OpeningLatch == 0 && bb->RunningTime >= LATCH_AT_SEC)
			{
				const float dz = (float)(bb->MyLocation_Cartesian.Z
					- bb->TargetLocaion_Cartesian.Z);
				bb->OpeningLatch = (dz > LATCH_ALT_M) ? 1 : 2;
			}
		}

		const float dist = bb->Distance;
		const float myAta = bb->Los_Degree;			//내 기수 -> 적 (0=적이 정면)
		const float enAta = bb->Los_Degree_Target;	//적 기수 -> 나 (0=내가 적 정면) = AOT
		const float aft = bb->AspectFromTail_Deg;	//교범 기준 AA (0=내가 적 6시)
		const float closure = bb->Closure_MS;
		const float casKt = bb->MyCas_Kt;

		int next = bb->FightType;

		// ── 우선순위 1: 방어 ────────────────────────────────────────────────
		// 적 기수가 나를 향하고(AOT 작음) 가까우면 실위협이다.
		// 교범 판단 우선순위: 추락 0 > 피격 최소 > WEZ 획득.
		if (enAta < 30.0f && dist < 1800.0f && myAta > 60.0f)
		{
			next = FT_Defensive;
		}
		// ── 우선순위 2: 추격 ────────────────────────────────────────────────
		// 내 기수가 적을 향하고(ATA 작음) 내가 적 꼬리 쪽(AspectFromTail 작음)에 있다.
		else if (myAta < 45.0f && aft < 60.0f && dist < 3000.0f)
		{
			next = FT_Chase;
		}
		// ── 우선순위 3: 머지 접근 ───────────────────────────────────────────
		// 양측 고아스펙트로 빠르게 닫히는 중 = 아직 어느 싸움인지 안 정해졌다.
		else if (dist > 900.0f && closure > 80.0f && myAta > 45.0f && enAta > 45.0f)
		{
			next = FT_Merge;
		}
		// ── 우선순위 4: 선회전 — 1서클이냐 2서클이냐 ────────────────────────
		// §4.8.4.2.4.2.2: "At 350 knots or less, consider forcing a one-circle,
		//  min radius fight. If >350 knots ... consider forcing a two-circle fight."
		// 예선 두 속도(CAS 309kt/183kt) 모두 1서클이 정답이다.
		else if (dist < 3500.0f)
		{
			next = (casKt <= 350.0f) ? FT_OneCircle : FT_TwoCircle;
		}
		else
		{
			next = FT_Neutral;
		}

		// ── 히스테리시스 ───────────────────────────────────────────────────
		// §4.8.4.2.4.2.2 "Do not be indecisive." 우유부단이 최악이다.
		// 단 방어는 즉시 들어간다 — 맞고 있는데 유지 카운터를 기다릴 수는 없다.
		const int HOLD = 120;	// 2초 @60Hz
		if (next == FT_Defensive || bb->FightTypeHold <= 0 || next == bb->FightType)
		{
			if (next != bb->FightType)
				bb->FightTypeHold = HOLD;
			else if (bb->FightTypeHold > 0)
				bb->FightTypeHold--;
			bb->FightType = next;
		}
		else
		{
			bb->FightTypeHold--;	//전환 억제 중 — 기존 분류 유지
		}

		return NodeStatus::SUCCESS;
	}
}
