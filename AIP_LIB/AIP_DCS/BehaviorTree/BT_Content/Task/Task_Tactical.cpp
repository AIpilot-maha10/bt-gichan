#include "Task_Tactical.h"
#include "VPSafety.h"
#include <algorithm>
#include <cmath>
#include <string>

// ── (C 트랙) XML 입력 포트 ────────────────────────────────────────────────
// 전술 상수를 XML에서 바꿀 수 있게 노출한다. **재빌드 없이 스윕**하기 위한 것.
//
// 왜 필요한가: EP13/EP15에서 단일 상수를 하나씩 재빌드하며 스윕했는데,
// 변형 하나당 빌드 1.5분이 들고 스크립트가 마지막 변형 DLL을 남기는 사고도 있었다.
// 다차원 조합을 보려면 XML만 갈아끼우는 방식이 필요하다.
//
// 주의 (vendored BehaviorTree.CPP v3의 함정):
//  · `getInput<float>`는 **빈 Optional을 반환**한다(convertFromString에 float 특수화 없음).
//    반드시 double/int를 쓸 것.
//  · XML에 선언 안 된 속성을 쓰면 RuntimeError -> extern "C" 경계를 넘어 하드 크래시.
//  · XML에서 생략하면 3-arg InputPort의 기본값이 주입되므로 **기존 XML 그대로 동작**한다.
static double dport(const BT::TreeNode& n, const char* key, double defv)
{
	auto v = n.getInput<double>(key);
	return (v && std::isfinite(v.value())) ? v.value() : defv;
}

PortsList Action::Task_Tactical::providedPorts()
{
	return {
		InputPort<CPPBlackBoard*>("BB"),
		// 기본값 = 현재 코드값. 바꾸지 않으면 동작이 완전히 동일해야 한다(검증 조건).
		InputPort<double>("SnapShotAtaDeg",   40.0,   "SnapShot 진입 ATA (EP13에서 40이 최적 확인)"),
		InputPort<double>("SnapShotRangeMul",  1.15,  "SnapShot 사거리 배수 (x WEZ rMax)"),
		InputPort<double>("GunAimAtaDeg",     22.0,   "GunAim 진입 ATA"),
		InputPort<double>("GunAimRangeMul",    1.5,   "GunAim 사거리 배수"),
		InputPort<double>("HardTurnAtaDeg",   45.0,   "HardTurn 진입 ATA 하한"),
		InputPort<double>("InterceptRangeM", 3500.0,  "이 거리 이상이면 Intercept"),
		InputPort<double>("HoldTicks",        30.0,   "soft 상태 히스테리시스 틱 (EP15: 12는 악화)"),
		InputPort<double>("AltRecoverM",     900.0,   "이 고도 미만이면 AltRecover (녹아웃 305m)"),
		InputPort<double>("DefBreakRangeM",  1400.0,  "DefensiveBreak 발동 거리"),
	};
}

static float clampf(float v, float lo, float hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

// ── 공식 WEZ (BattleServer TopGun 룰과 동일 수치) ────────────────────
// 대미지 판정은 "탄도 시뮬"이 아니라 LOS 콘 체크다:
//   Phase1(  0~100s): LOS < 1°, 152.4 ~  914.4 m (500~3000 ft)
//   Phase2(100~150s): LOS < 2°, 152.4 ~ 1066.8 m (500~3500 ft)
//   Phase3(150~200s): LOS < 3°, 152.4 ~ 1219.2 m (500~4000 ft)
// 따라서 종말 조준은 "예측점"이 아니라 "적 현재 위치"를 정확히 겨눠야 한다.
struct WezWindow
{
	float coneDeg;
	float rMin;
	float rMax;
};

// ── (EP21 기각) 코너속도 임계를 CAS로 바꿨다가 되돌렸다 ────────────────────
// 참고용으로 남긴다. 다시 시도할 사람은 아래 "왜 실패했나"를 먼저 읽을 것.
// static const float CORNER_CAS_HI = 380.0f;
// static const float CORNER_CAS_LO = 300.0f;

static WezWindow GetWez(double runningTime)
{
	WezWindow w;
	w.rMin = 152.4f;
	if (runningTime < 100.0)      { w.coneDeg = 1.0f; w.rMax = 914.4f; }
	else if (runningTime < 150.0) { w.coneDeg = 2.0f; w.rMax = 1066.8f; }
	else                          { w.coneDeg = 3.0f; w.rMax = 1219.2f; }
	return w;
}

// 코너속도 유지 스로틀. **TAS 기준이다** (아래 EP21 결과를 보고 유지하기로 했다).
//
// ── EP21: CAS로 바꿨다가 참패했다 (시드 50000, n=40) ───────────────────────
//   btjegal   적체력 0.226 -> 0.731 | 승 27 -> 8 | **shutout 0 -> 25**
//   jegalmin  적체력 0.985 -> 0.996 | 승  0 -> 0 |   shutout 32 -> 27
//
// 동기는 옳았다 — A-4 실측(47,900표본)에서 최대 선회율은 **CAS 350kt**에서
// 나왔고 문헌 F-16 코너속도와 일치한다. 그래서 CAS 380/300kt로 잡았다.
//
// **왜 실패했나 (가설, 미검증):** 교전 고도에서는 두 기준이 사실상 같은 값이다.
//     3,704m(btjegal전): TAS 230 == CAS 371kt  vs  새 임계 380kt
//     3,704m           : TAS 185 == CAS 299kt  vs  새 임계 300kt
// 거의 no-op이어야 하는데 27승->8승으로 무너졌다. 차이는 **고도 적응성**이다.
// CAS 기준은 낮은 고도에서 훨씬 자주 걸린다 — 해면 근처면 TAS 200에서도
// CAS 389kt라 스로틀을 0.25로 끊지만, TAS 기준은 안 끊는다. 강하 중에
// 에너지를 계속 버리게 된 것으로 보인다.
//
// 교훈: **"코너속도는 CAS 기준"이 맞더라도 "코너 위에서 스로틀을 끊는다"는
// 조치까지 CAS로 옮겨야 하는 건 아니다.** 코너는 있고 싶은 지점이지 피할
// 지점이 아니라서, 30kt 위에서 0.25로 끊으면 코너 한참 아래로 떨어진다.
// 다시 시도한다면 임계값이 아니라 **감속량**(0.25 대신 0.7 등)부터 손댈 것.
static float CornerHoldThrottle(float speedMs)
{
	if (speedMs > 230.0f) return 0.25f;
	if (speedMs < 185.0f) return 1.0f;
	return 0.55f;
}

// ── (v7) CAS 추정 ─────────────────────────────────────────────────────────
// 교범의 속도 임계값(350kt, 380~420kt, 250kt ...)은 전부 **CAS 기준**인데
// 우리가 받는 건 TAS다. 대회 서버는 9개 값만 주므로 고도로 밀도비를 추정한다.
//   CAS ≈ TAS × √(ρ(alt)/ρ₀),  ISA: T=288.15-0.0065h, p=p₀(T/T₀)^5.2559, ρ=p/(RT)
// 예선 고도 15,000ft(4,572m)에서 계수 ≈ 0.7932 (실측 로그로 검증)
static float TasToCasFactor(float altM)
{
	const float T = 288.15f - 0.0065f * altM;
	if (T <= 1.0f) return 1.0f;
	const float p = 101325.0f * std::pow(T / 288.15f, 5.2559f);
	const float rho = p / (287.05f * T);
	return std::sqrt(rho / 1.225f);
}

static const float MS_TO_KT = 1.0f / 0.51444f;

// ── (v7) 1서클 / 2서클 ────────────────────────────────────────────────────
// AETCTTP §4.8.4.2.4.2.2:
//   "At 350 knots or less, consider forcing a one-circle, min radius fight.
//    If >350 knots ... consider forcing a two-circle fight."
//   "the last fighter to turn sets the fight ... Do not be indecisive."
//
// 예선 실측 속도는 CAS 309kt / 183kt로 **둘 다 1서클이 정답**인데,
// v6는 HardTurn 74~79%로 사실상 2서클(레이트)을 하고 있었다. 빔 WEZ 0.39초의 의심 원인.
static const float ONE_CIRCLE_CAS_KT = 350.0f;
static const int   FIGHT_PLAN_HOLD_TICKS = 120;   // 2초. 우유부단 방지

// 1서클 최소반경 구간 (§4.8.4.2.3.1)
//   "From 350 knots to approximately 250 knots the turn radius remains about the same.
//    Below 250 knots, however, the turn radius opens back up again."
static const float ONE_CIRCLE_CAS_LO = 260.0f;    // 하한 방어(250 + 여유)
// 2서클 지속선회율 구간 (§4.8.4.1.3)
static const float TWO_CIRCLE_CAS_LO = 380.0f;
static const float TWO_CIRCLE_CAS_HI = 430.0f;

// ── (v7 EP8) 에너지 규율 ──────────────────────────────────────────────────
// 실측(EP3): 코너속도(CAS 185 m/s=350kt) **미만 체류 97.6%**, 저속(CAS 90 m/s) 43.3%,
// 실속권 13.5%, 최장 연속 저속 118초. 만성이다.
// 스로틀은 이미 최대였다 -> 범인은 **지속적인 최대 G 선회의 유도항력**이다.
//
// 교범의 답 두 개:
//  §4.6.3.1.5  "blend the aft stick pressure to obtain light buffet, **airspeed
//               sustaining feel**. Cross-check the HUD to ensure airspeed is remaining steady."
//               -> 최대 G가 아니라 **속도가 유지되는 G**로 낮춘다
//  §4.4.1.1    "to sustain the current G load and airspeed, the aircraft **must descend**
//               (change potential to kinetic energy)"
//               -> 음의 Ps는 고도로 갚는다. 녹아웃 305m 대비 고도 여유는 충분하다
//
// 우리는 G를 직접 명령하지 않고 VP를 놓는다. 각오차가 곧 G이므로
// **VP를 기수 쪽으로 블렌드하면 G가 내려간다**(부분 언로드).
static const float SUSTAIN_CAS_LOW = 230.0f;   // 이 아래면 에너지 회복 개입
static const float SUSTAIN_BLEND_SPAN = 90.0f; // 얼마나 느린지에 비례해 완화
static const float SUSTAIN_MAX_BLEND = 0.55f;  // 완전 언로드는 안 한다(적을 놓치면 진다)
static const float SUSTAIN_ALT_ROOM = 2500.0f; // 이 위에서만 강하로 갚는다 (EP8에서 1500->2500 상향)

// (v7 시도1 되돌림) 아직 미사용 — 선회방향 구현 후 다시 쓴다
static float FightThrottle(float casKt, bool oneCircle)
{
	if (oneCircle)
	{
		if (casKt > ONE_CIRCLE_CAS_KT) return 0.15f;   // 과속 -> 감속해 반경을 줄인다
		if (casKt < ONE_CIRCLE_CAS_LO) return 1.0f;    // 250kt 미만은 반경이 다시 커진다
		return 0.55f;                                   // 최적 반경 구간 유지
	}
	if (casKt > TWO_CIRCLE_CAS_HI) return 0.35f;
	if (casKt < TWO_CIRCLE_CAS_LO) return 1.0f;
	return 0.75f;
}

NodeStatus Action::Task_Tactical::tick()
{
	Optional<CPPBlackBoard*> BBopt = getInput<CPPBlackBoard*>("BB");
	if (!BBopt || BBopt.value() == nullptr)
		return NodeStatus::FAILURE;
	CPPBlackBoard* bb = BBopt.value();

	const Vector3 myPos = bb->MyLocation_Cartesian;
	const Vector3 tgtPos = bb->TargetLocaion_Cartesian;

	// no enemy -> fly straight
	if (bb->Enemy.empty())
	{
		bb->VP_Cartesian = myPos + bb->MyForwardVector * 10000.0f;
		bb->IsAimmingMode = false;
		bb->SelectedBehavior = "Straight";
		bb->BehaviorHoldTicks = 0;
		bb->Throttle = 1.0f;
		return NodeStatus::SUCCESS;
	}

	// (C 트랙) 포트는 여기서 한 번에 읽는다. 분기 안에서 읽으면 매 틱 map 조회가 반복된다.
	const float P_SnapAta   = (float)dport(*this, "SnapShotAtaDeg",   40.0);
	const float P_SnapMul   = (float)dport(*this, "SnapShotRangeMul",  1.15);
	const float P_GunAta    = (float)dport(*this, "GunAimAtaDeg",     22.0);
	const float P_GunMul    = (float)dport(*this, "GunAimRangeMul",    1.5);
	const float P_HardAta   = (float)dport(*this, "HardTurnAtaDeg",   45.0);
	const float P_InterceptM= (float)dport(*this, "InterceptRangeM", 3500.0);
	const int   P_HoldTicks = (int)  dport(*this, "HoldTicks",        30.0);
	const float P_AltRecM   = (float)dport(*this, "AltRecoverM",     900.0);
	const float P_DefBreakM = (float)dport(*this, "DefBreakRangeM",  1400.0);

	const float alt = (float)myPos.Z;
	const float dist = bb->Distance;
	const float los = bb->Los_Degree;          // 내 기수 -> 적 시선각 (=ATA)

	// ── (v7) CAS 추정 + 1서클/2서클 판단 ────────────────────────────────
	// 교범 임계값이 전부 CAS 기준이라 TAS를 그대로 쓰면 고도에 따라 어긋난다.
	const float casKt = bb->MySpeed_MS * TasToCasFactor(alt) * MS_TO_KT;
	bb->MyCas_Kt = casKt;
	{
		// 판단은 유지한다 — §4.8.4.2.4.2.2 "Do not be indecisive."
		// 임계값 근처에서 매 틱 뒤집히면 어느 쪽 싸움도 못 한다.
		const int wantOneCircle = (casKt <= ONE_CIRCLE_CAS_KT) ? 1 : 0;
		if (wantOneCircle != bb->IsOneCircle)
		{
			if (bb->FightPlanHold > 0) bb->FightPlanHold -= 1;
			else { bb->IsOneCircle = wantOneCircle; bb->FightPlanHold = FIGHT_PLAN_HOLD_TICKS; }
		}
		else bb->FightPlanHold = FIGHT_PLAN_HOLD_TICKS;
	}
	const bool oneCircle = (bb->IsOneCircle != 0);
	const float speed = bb->MySpeed_MS;
	const WezWindow wez = GetWez(bb->RunningTime);

	// 수평 전방벡터 (고도회복용)
	Vector3 fwdFlat = bb->MyForwardVector;
	fwdFlat.Z = 0.0;
	float fwdLen = (float)std::sqrt(fwdFlat.X * fwdFlat.X + fwdFlat.Y * fwdFlat.Y);
	if (fwdLen > 1e-3f) fwdFlat = fwdFlat * (1.0f / fwdLen);

	// ── 교전 기하 파생값 ─────────────────────────────────────────────
	Vector3 rel = tgtPos - myPos;
	Vector3 losDir = rel;
	if (dist > 1.0f) losDir = losDir * (1.0f / dist);

	// 적 ATA: 적 기수가 나를 얼마나 정확히 겨누는가 (작을수록 내가 위험)
	Vector3 revLos = losDir * -1.0f;
	float enemyAtaDot = (float)bb->TargetForwardVector.dot(revLos);
	enemyAtaDot = clampf(enemyAtaDot, -1.0f, 1.0f);
	const float enemyAta = std::acos(enemyAtaDot) * 57.2957795f;

	// 닫힘속도 (+ = 접근중). 속도벡터 ~= 전방벡터 * 속력 근사
	const Vector3 myVel = bb->MyForwardVector * bb->MySpeed_MS;
	const Vector3 enemyVel = bb->TargetForwardVector * bb->TargetSpeed_MS;
	Vector3 relVel = myVel - enemyVel;
	const float closure = (float)relVel.dot(losDir);

	// (v6 Phase2) 헤딩교차각(HCA): 내 기수 vs 적 기수 사이각.
	//   HCA 큼(>110°) = 서로 반대로 흐름 -> 2서클(레이트 교착) 가능성
	//   HCA 작음       = 같은 방향 -> 1서클(각도전)
	float hcaDot = (float)bb->MyForwardVector.dot(bb->TargetForwardVector);
	hcaDot = clampf(hcaDot, -1.0f, 1.0f);
	const float hca = std::acos(hcaDot) * 57.2957795f;

	// 적이 내 어느 쪽에 있나 (+1=오른쪽, -1=왼쪽) — LeadTurn 역전 방향 결정용
	const float enemySide = ((float)bb->MyRightVector.dot(losDir) >= 0.0f) ? 1.0f : -1.0f;

	// ── (v7 EP7) 적 회전방향 + 머지 감지 ────────────────────────────────
	// §4.8.4.2.2: 1서클 = 두 기체가 **반대 회전방향**으로 돌아 원 하나를 공유.
	//             2서클 = 같은 회전방향 -> 각자 원을 그림(레이트 싸움).
	// EP6에서 속도 목표만 바꿨다가 실패했다. 진짜 분기는 **어느 쪽으로 도느냐**다.
	//
	// 적 회전방향: 기수벡터의 수평성분이 위에서 볼 때 어느 쪽으로 도는가.
	//   cross(prev, cur).Z > 0 이면 반시계(좌선회), < 0 이면 시계(우선회)
	{
		const Vector3 pf = bb->PrevTargetForward;
		const Vector3 cf = bb->TargetForwardVector;
		if (std::fabs(pf.X) + std::fabs(pf.Y) > 1e-6)
		{
			const float crossZ = (float)(pf.X * cf.Y - pf.Y * cf.X);
			// 잡음 억제: 아주 작은 변화는 무시하고 직전값을 유지한다
			if (std::fabs(crossZ) > 1e-5f)
				bb->EnemyTurnSign = (crossZ > 0.0f) ? -1.0f : 1.0f;   // +1 = 시계(우선회)
		}
		bb->PrevTargetForward = cf;
	}

	// 머지(최근접) 통과 감지: 닫힘속도가 +에서 -로 바뀌는 순간
	const bool mergePassed = (bb->PrevClosure > 0.0f && closure <= 0.0f);
	bb->PrevClosure = closure;

	// 머지 직후 **중립 기하**에서만 선회방향을 강제한다.
	// 공격/방어 국면(진단에서 이미 5~25초씩 쏘는 구간)은 건드리지 않는다.
	const bool neutralMerge = mergePassed
		&& dist < 2500.0f
		&& los > 50.0f && enemyAta > 50.0f      // 서로 겨누지 못하는 중립
		&& hca > 90.0f;                          // 마주 지나감
	// ⚠️ 속도 하한 게이트 (EP7 1차 실측으로 추가)
	// 교범의 "350kt 이하면 1서클"은 **선회반경을 쓸 수 있는 속도**를 전제한다.
	// §4.8.4.2.3.1: "Below 250 knots, however, the turn radius opens back up again."
	// 실측: beam_slow(CAS 162~201kt)에 강제했더니 WEZ 0.00s / shutout 10/10으로 완전 붕괴했다.
	// 돌 힘이 없는데 최소반경 싸움을 걸면 멀어지기만 한다 -> 그땐 에너지부터 회복(§4.4).
	const bool canFightRadius = (casKt >= ONE_CIRCLE_CAS_LO);
	if (neutralMerge && bb->MergeTurnTicks <= 0 && bb->EnemyTurnSign != 0.0f && canFightRadius)
	{
		// 1서클을 원하면 적과 **반대** 회전방향, 2서클이면 같은 방향
		bb->MergeTurnSign = (bb->IsOneCircle != 0) ? -bb->EnemyTurnSign : bb->EnemyTurnSign;
		bb->MergeTurnTicks = 150;                // 2.5초. 회전방향을 확정짓는 데 필요한 최소치
	}
	if (bb->MergeTurnTicks > 0) bb->MergeTurnTicks -= 1;

	// ⚠️ (EP7 결론 2026-08-03) MergeTurn 발동을 꺼둔다. 감지 로직은 계측용으로 남긴다.
	//
	// 셀당 10판에선 WEZ 0.51→1.94초(3.8배)로 보였는데, **75판으로 늘리니 사라졌다**:
	//   WEZ 가한 것 0.85→1.16s  개선 11 / 악화 13  p=0.839   (효과 없음)
	//   shutout     34판 → 37판                              (주 지표 악화)
	//   교착 최장    13.24→12.11s 개선 27 / 악화 15 p=0.088   (유일한 방향성)
	//   WEZ 최대     12.1→23.4s (beam_fast), 2.8→21.9s (head_on)  ← 편차만 커졌다
	//
	// 즉 "가끔 크게 터지고 대체로 손해"다. 계획에서 경계하던 "평균 40 / p20 0" 패턴 그대로.
	//
	// 원인 가설: **선회방향을 읽는 시점이 이르다.** §4.8.3.3은 "The Bandit will be the
	// last to turn"이라고 한다. 최근접 통과 순간엔 적이 아직 안 돌았을 수 있어
	// EnemyTurnSign이 잡음이다. 잘못된 방향으로 2.5초를 쓰면 그대로 손해.
	// → 다음 시도: 머지 후 0.5~1초 관찰하고 나서 방향을 확정한다.
	const bool forceMergeTurn = false && (bb->MergeTurnTicks > 0);
	// (EP12) 예선 스위트로도 재평가했으나 동일하게 기각:
	//   WEZ 1.51->1.28s 개선5/악화5 p=1.000, shutout 15->18판
	// 진단 셀(EP7)과 예선 스위트(EP12) 양쪽에서 효과가 없다. 확정 기각.

	// 원거리 인터셉트용 예측점 (접근 단계 전용 — 종말 조준에는 사용 금지)
	const float t_lead = clampf(dist / std::max(speed, 100.0f), 0.3f, 2.0f);
	const Vector3 predEnemy = tgtPos + enemyVel * t_lead;

	// ── 1) 우선순위 기반 전술 결정 ──────────────────────────────────
	// (26/07/13 교전로그 진단 반영:
	//   - 스로틀 100% 고정 -> 300m/s+에서 선회 불가 => 코너속도 관리 추가
	//   - lead 예측점 조준 -> LOS가 리드각만큼 상시 오염, WEZ 진입 0틱 => GunAim은 현재위치 직조준
	//   - Search가 29~42% 점유하며 거리만 유지 => 제거, Intercept/HardTurn으로 대체
	//   - 중립 기하에서 DefensiveBreak 11~16% 낭비 => 적이 실제 조준중일 때만 발동)
	// v5 파생 조건 (26/07/24 5판 진단 반영)
	// - 추락 자멸(BT-Jegal전 2/3판): AltRecover 하한 700->800, 저고도 추격 억제
	// - 2서클 원그리기 교착(jegalmin전): SnapShot 신설 — WEZ는 아스펙트 무관,
	//   기수만 사거리내 적에 얹히면 데미지. 꼬리 안 잡아도 교차 순간 쏜다.
	// - 90° 고아스펙트 패스: LagEntry를 교차 패스까지 확장 (오버슈트 방지)
	const bool inWezRange   = dist < wez.rMax * P_SnapMul;                 // 사거리(+여유) 안
	const bool noseOn       = los < P_SnapAta;                             // 기수가 적에 근접
	const bool highAspectPass = dist < 2500.0f && closure > 150.0f     // 적이 90°로 가로지름
		&& enemyAta > 55.0f && enemyAta < 130.0f && los > 45.0f;
	const bool overspeedMerge = dist < 1800.0f && closure > 220.0f     // 과속 정면 접근
		&& los < 60.0f && enemyAta > 60.0f;

	// (v6 Phase2) 2서클 레이트 교착 탈출 — LeadTurn(선회방향 역전).
	// Phase1의 BreakManeuver(큰 리드 코너컷)는 실패(원그리기 43~53% 그대로): 코너컷은
	// 회전방향을 안 바꿔 여전히 같이 오비트. 진짜 해법은 "선회방향을 역전"해 2서클을
	// 1서클로 바꿔 정면 머지를 강제하는 것. HCA>110°(서로 반대로 흐름)로 2서클을 확인하고,
	// HardTurn이 STALEMATE_TICKS 넘게 지속되면 LeadTurn을 BREAK_DURATION 동안 발동한다.
	const int STALEMATE_TICKS = 150;   // 2.5초 HardTurn 지속 = 교착
	const int BREAK_DURATION  = 75;    // LeadTurn 1.25초 커밋 (짧게 — 시야 회복 빠르게)
	bool forceBreak = false;
	if (bb->BreakHoldTicks > 0)
	{
		forceBreak = true;
		bb->BreakHoldTicks -= 1;
	}
	else if (bb->HardTurnDwell >= STALEMATE_TICKS && hca > 110.0f)   // 교착 + 2서클 확인
	{
		forceBreak = true;
		bb->BreakHoldTicks = BREAK_DURATION;
		bb->HardTurnDwell = 0;
	}

	std::string raw;
	if (alt < P_AltRecM)
		raw = "AltRecover";                                           // (v6) 900m로 조기화 (녹아웃 305m 대비)
	else if (enemyAta < 25.0f && dist < P_DefBreakM && los > 80.0f)
		raw = "DefensiveBreak";   // 적이 내 꼬리에서 조준 중 = 진짜 위협
	// (EP10/EP11 결론) GunRepo 발동을 껐다. 470m/800m 둘 다 WEZ가 나빠졌다.
	//   EP10(470m): WEZ 0.85->0.81 악화24/개선17, 최소거리 변화 없음(180->178m)
	//   EP11(800m): WEZ 0.85->0.56 악화33/개선11 p=0.001, shutout 34->44판
	// 뒤로 빼면 사거리 내 체류는 비슷한데 **사격 기회 자체가 사라진다**.
	// LOS 회전율 가설(200m에서 57°/s라 추적 불가)은 맞을 수 있으나,
	// 붙지 않으면 아예 못 쏘므로 거리를 벌리는 방향은 답이 아니다.
	else if (false)
		raw = "GunRepo";
	else if (inWezRange && noseOn)
		raw = "SnapShot";         // (v5) 사거리내 기수근접 = 즉시 스냅샷 (아스펙트 무관)
	else if (forceMergeTurn)
		raw = "MergeTurn";        // (v7 EP7) 머지 직후 회전방향 확정 — 1서클/2서클을 실제로 만든다
	else if (forceBreak && dist < 4000.0f)
		raw = "LeadTurn";         // (v6 Phase2) 2서클 교착 -> 선회방향 역전으로 1서클 전환
	else if (highAspectPass || overspeedMerge)
		raw = "LagEntry";         // (v5) 과속 관통 + 90° 고아스펙트 패스 -> 지연추적
	else if (dist < wez.rMax * P_GunMul && los < P_GunAta)
		raw = "GunAim";           // 사거리 근처 정밀 추적 (SnapShot 밖의 좁은 창)
	else if (los > P_HardAta && dist < P_InterceptM)
		raw = "HardTurn";         // 기수부터 적에게 (머지 후 재교전 포함)
	else if (dist >= P_InterceptM)
		raw = "Intercept";        // 원거리: 풀리드 인터셉트로 거리 압축
	else
		raw = "LeadPursuit";      // 중거리 22~45도: 리드 추적으로 각도 압축

	// ── 2) 히스테리시스 ─────────────────────────────────────────────
	// 안전/방어/조준 상태는 즉시 전환(콘 1도짜리 조준은 반응성이 생명).
	// 나머지 기동 상태는 30틱 유지해 틱 단위 떨림 방지.
	const std::string last = bb->SelectedBehavior;
	const bool rawHard = (raw == "AltRecover" || raw == "DefensiveBreak" || raw == "GunAim"
		|| raw == "LagEntry" || raw == "SnapShot" || raw == "LeadTurn" || raw == "MergeTurn" || raw == "GunRepo");
	const bool lastSoft = !(last == "AltRecover" || last == "DefensiveBreak" || last == "GunAim"
		|| last == "LagEntry" || last == "SnapShot" || last == "LeadTurn" || last == "MergeTurn" || last == "GunRepo"
		|| last == "PreventLandCrash" || last == "None" || last == "Straight" || last == "");
	std::string behavior;
	if (rawHard)
	{
		behavior = raw;
		bb->BehaviorHoldTicks = 0;
	}
	else if (bb->BehaviorHoldTicks > 0 && lastSoft && last != raw)
	{
		behavior = last;
		bb->BehaviorHoldTicks -= 1;
	}
	else
	{
		behavior = raw;
		bb->BehaviorHoldTicks = P_HoldTicks;
	}

	// (v6 Phase1) HardTurn 지속 카운터 갱신 — 교착 감지용.
	// BreakManeuver 중엔 건드리지 않고, HardTurn이면 누적, 그 외 상태면 리셋.
	if (behavior == "HardTurn")
		bb->HardTurnDwell += 1;
	else if (behavior != "LeadTurn")
		bb->HardTurnDwell = 0;

	// ── 3) 상태 -> VP + 스로틀 ──────────────────────────────────────
	Vector3 vp;
	bool aiming = false;
	float maxDive = 15.0f;
	float hardFloor = 600.0f;
	float throttle = 1.0f;

	if (behavior == "AltRecover")
	{
		// 저고도: 전방 상승. 풀스로틀로 에너지 확보
		vp = myPos + fwdFlat * 1500.0f + Vector3(0.0f, 0.0f, 2500.0f);
		throttle = 1.0f;
	}
	else if (behavior == "DefensiveBreak")
	{
		// 적이 있는 쪽으로 최대선회(브레이크) -> 적 오버슈트 유도.
		// 상승 없이 수평 브레이크: 고도로 에너지를 빼지 않는다.
		const float side = ((float)bb->MyRightVector.dot(losDir) >= 0.0f) ? 1.0f : -1.0f;
		vp = myPos + bb->MyRightVector * (6000.0f * side);
		vp.Z = myPos.Z;
		throttle = 1.0f;   // 방어 선회는 에너지 소모가 크므로 풀스로틀
	}
	else if (behavior == "LagEntry")
	{
		// 지연추적 진입: 적 "꼬리 뒤" 지점을 조준해 선회 공간을 만든다.
		// (26/07/18 gichan vs jegalmin 로그: 고속 접근 -> 관통 -> LOS 120도 이탈 반복.
		//  jegalmin은 LagPursuit로 꼬리를 잡는 반면 우리는 정면 관통이 문제였음)
		// 감속 + 후방점 조준 -> 관통 대신 적 6시로 미끄러져 들어감.
		Vector3 lagPoint = tgtPos - bb->TargetForwardVector * 400.0f;
		vp = lagPoint;
		maxDive = 25.0f;
		throttle = (speed > 200.0f) ? 0.2f : 0.5f;   // 적극 감속이 핵심
	}
	else if (behavior == "GunRepo")
	{
		// (v7 EP10) 사격 repo — §4.6.3.1.11
		//   "The repo must occur in time for the fighter to remain outside the TR bubble.
		//    Exact timing depends upon AA and closure but usually occurs between
		//    1,500 feet and 1,800 feet." (= 457~549 m)
		//
		// 실측 근거: 좌표 수정 후 최소거리가 **150m**까지 붙는다. WEZ 최소사거리가
		// 152.4m이므로 그 안쪽은 완벽히 조준해도 데미지가 0이고, 그 속도로 관통하면
		// 각속도가 폭발해 기수가 따라가지 못한다(사거리 내 ATA 최솟값 5.44°에서 정체).
		//
		// 지연추적점(적 꼬리 뒤)으로 빠져 거리를 되찾는다. §4.6.2.2.10.1은 idle을 권한다.
		Vector3 eFwd = bb->TargetForwardVector;
		eFwd.Z = 0.0;
		const float eLen = (float)std::sqrt(eFwd.X * eFwd.X + eFwd.Y * eFwd.Y);
		if (eLen > 1e-3f) eFwd = eFwd * (1.0f / eLen);

		// (EP11) 470m 트리거는 너무 늦었다 — 최소거리가 전혀 안 변했다(180→178m).
		// 물리적 이유가 있다: 교차속도 200 m/s 기준 LOS 회전율은
		//    200m 거리 -> 57°/s,  900m 거리 -> 12.7°/s
		// 우리 최대 선회율이 약 20°/s이므로 **200m에서는 원리적으로 추적이 불가능**하다.
		// 사거리 내 최소 ATA가 5.44°에서 멈춘 건 제어 한계가 아니라 기하 문제였다.
		// 교범의 Control Zone(762~1,372m)이 정확히 이 이유로 존재한다.
		//
		// -> 800m부터 개입해 **CZ 안쪽(약 800m)을 유지**한다. 크게 벌리지 않는다.
		//    (너무 벌리면 사거리 밖으로 나가 WEZ 기회 자체가 사라진다)
		vp = tgtPos - eFwd * 900.0f;      // 적 꼬리 뒤 900m — CZ 근처로 되돌린다
		vp.Z = myPos.Z + 100.0;
		aiming = false;
		maxDive = 15.0f;
		throttle = 0.2f;                  // 닫힘속도를 죽이되 완전 idle은 아니게
	}
	else if (behavior == "SnapShot")
	{
		// (v5) 교차 스냅샷: WEZ 콘 판정은 아스펙트 무관 -> 적 현재위치 정밀 직조준.
		// 꼬리를 잡으려 원 그리지 말고, 기수가 얹히는 순간 바로 쏜다.
		// 리드 없음(지연보상 최소)으로 콘 오염 최소화. 코너속도 유지해 과속 관통 방지.
		const float t_comp = clampf(dist / 1000.0f, 0.02f, 0.08f);
		vp = tgtPos + enemyVel * t_comp;
		aiming = true;
		maxDive = 30.0f;
		hardFloor = 600.0f;
		// 사거리 안에서 안정 조준하려면 과속 금지. 도주표적만 전속.
		if (enemyAta > 120.0f && myPos.Z > 2200.0f)
			throttle = 1.0f;
		else
			throttle = CornerHoldThrottle(speed);
	}
	else if (behavior == "GunAim")
	{
		// 종말 조준: 적 "현재 위치" 직조준 + 지연보상 소량 리드만.
		// (판정이 LOS 콘 체크이므로 예측점 조준은 리드각만큼 LOS를 오염시킴.
		//  60Hz 1틱 지연 + 제어기 랙 보상으로 0.03~0.12s 리드만 허용 -> 리드각 < ~1도)
		const float t_comp = clampf(dist / 900.0f, 0.03f, 0.12f);
		vp = tgtPos + enemyVel * t_comp;
		aiming = true;
		maxDive = 35.0f;     // 적이 아래 있어도 기수를 내릴 수 있게 완화
		hardFloor = 550.0f;  // PreventLandCrash(500m/TTI7s)가 최종 방어선

		// 스로틀: WEZ 밖이면 전속 접근, 과속 접근이면 감속해 오버슈트 방지.
		// 도주 표적(적 꼬리 완전 노출)은 감속 금지 — 동일 기체 추격전에서
		// 0.7 스로틀은 거리만 벌린다 (26/07/20 서버 3판: closure -22 확인)
		if (dist > wez.rMax)
			throttle = 1.0f;
		else if (closure > 140.0f && dist < 450.0f)
			throttle = 0.3f;
		else if (enemyAta > 120.0f)
			throttle = 1.0f;   // 도주 표적: 전속 유지
		else
			throttle = 0.7f;
	}
	else if (behavior == "LeadTurn")
	{
		// (v6 Phase2) 선회방향 역전으로 2서클 -> 1서클 전환.
		// 2서클에선 둘 다 같은 쪽으로 돌아 서로 못 겨눔. 여기서 "적이 있는 반대쪽"으로
		// 크게 틀어 내 선회방향을 뒤집으면, 적은 원래대로 돌다가 내 정면으로 들어와
		// 정면 머지(=교차 스냅샷)가 만들어진다. 수평 유지(수직기동 미사용).
		// enemySide: 적이 오른쪽(+1)/왼쪽(-1). 반대쪽(-enemySide)으로 VP를 크게 던진다.
		vp = myPos + fwdFlat * 2500.0f + bb->MyRightVector * (-enemySide * 5000.0f);
		vp.Z = myPos.Z;
		aiming = false;
		maxDive = 10.0f;
		throttle = CornerHoldThrottle(speed); // 코너속도로 최대 선회율
	}
	else if (behavior == "MergeTurn")
	{
		// (v7 EP7) 머지 직후, 정해진 **회전방향**으로 확실히 돌린다.
		//
		// 핵심: 여기서는 적 위치를 향하지 않는다. 적을 향해 돌면 양쪽이 서로 마주
		// 돌아 결국 같은 회전방향이 되고, 그게 2서클(레이트 교착)이다.
		// §4.8.4.2.2 "fighters turn in opposite directions at the merge"
		//
		// EP6 실패 교훈: 속도/하강각만 바꾸는 건 겉만 만지는 것. VP 방향을 바꿔야 한다.
		Vector3 rightFlat = bb->MyRightVector;
		rightFlat.Z = 0.0;
		const float rLen = (float)std::sqrt(rightFlat.X * rightFlat.X + rightFlat.Y * rightFlat.Y);
		if (rLen > 1e-3f) rightFlat = rightFlat * (1.0f / rLen);

		vp = myPos + fwdFlat * 700.0f + rightFlat * (bb->MergeTurnSign * 1800.0f);
		vp.Z = myPos.Z;          // 평면 유지 — 1서클은 반경 싸움이라 고도를 팔 이유가 없다
		aiming = false;
		maxDive = 12.0f;
		throttle = FightThrottle(casKt, bb->IsOneCircle != 0);
	}
	else if (behavior == "HardTurn")
	{
		// 최대선회로 기수를 적 현재위치에 (리드 없음 = 최단 수렴).
		// 코너속도 유지가 핵심: 빠르면 선회반경이 커져 각도를 못 줄인다.
		vp = tgtPos;
		aiming = true;
		maxDive = 25.0f;
		throttle = CornerHoldThrottle(speed);

		// ── (v7 EP17) 고도를 CAS로 바꾼다 — **각도는 건드리지 않는다** ──────
		//
		// 상대 비교 진단(같은 시드 5판씩)에서 드러난 것:
		//                    vs btjegal(이김)   vs jegalmin(못이김)
		//   내 고도            3,704m             6,908m
		//   내 속도(TAS)        230 m/s            155 m/s
		//   -> CAS              375 kt             211 kt
		//   사거리 내 내 ATA     4.9°               93.7°
		//
		// btjegal전에선 자연히 강하해 **코너속도(350kt)에 안착**하는데,
		// jegalmin전에선 6,900m에 높고 느린 채로 갇힌다. CAS 211kt는 교범이
		// "Below 250 knots the turn radius opens back up again"이라 한 구간이다.
		// 거기서 상대는 36 m/s 빠르고 두 배로 세게 돈다 -> 레이트 싸움 완패.
		//
		// EP8/EP9는 이걸 고치려다 **VP를 기수 쪽으로 블렌드**해서 각도를 잃었고
		// 그래서 실패했다. 여기서는 **VP의 수평 성분을 그대로 두고** 고도만 낮춘다.
		// 같은 TAS라도 아래로 내려가면 공기가 조밀해져 CAS가 오른다(공짜 이득).
		//
		// 안전장치: 사거리 근처에선 절대 건드리지 않는다(1° 콘을 지켜야 하므로).
		// ⚠️ (EP17 결론) 발동을 껐다. jegalmin전엔 효과가 있었으나 btjegal전 승리가 급감.
		//   vs jegalmin: 최소 ATA 4.63->2.42도 (개선28/악화12, p=0.017) 유의, shutout 32->29
		//   vs btjegal : WEZ 11.10->16.63s 인데 **승리 27->17판**
		//
		// 모순의 원인: 로컬 sim의 실제 데미지는 **Phase1 콘(1도) 고정**으로 계산된다.
		// EP17은 Phase2/3(넓은 콘)에서 WEZ를 크게 늘렸지만(13117->17498, 11798->20375)
		// 실제 데미지를 내는 Phase1 콘 기준으로는 8935->8420틱으로 **줄었다**.
		// 즉 넓은 콘 시간만 벌고 좁은 콘 시간은 잃었다.
		//
		// 교훈: 하네스의 시간게이트 WEZ와 sim의 실제 데미지가 다르다. 채택 판단에는
		//       **승리 수**와 wez_dealt_ticks_phase1only 를 같이 봐야 한다.
		const bool highAndSlow = false && (casKt < 260.0f) && (alt > 4000.0f);
		const bool farEnough   = (dist > 1500.0f);   // 이 거리면 수직 오프셋의 각도비용이 작다
		if (highAndSlow && farEnough)
		{
			// 거리에 비례해 낮춘다 — 각도비용을 일정하게 유지(약 7° 이하)
			const float drop = clampf(dist * 0.12f, 0.0f, 400.0f);
			vp.Z = tgtPos.Z - (double)drop;
			maxDive = 35.0f;
			throttle = 1.0f;
		}

		// ── (v7 EP9) 에너지 규율 — 조준을 해치지 않는 구간에서만 ──────────
		//
		// EP8 실패: CAS<230이면 무조건 VP를 기수 쪽으로 블렌드했더니
		//   에너지는 크게 좋아졌으나(실속권 13.5%→1.7%, 최장저속 118→36초)
		//   **최소 ATA 1.97°→3.21°, shutout 34→38판**으로 조준이 망가졌다.
		//   교범의 ease는 §4.6.3.1.8 "**if the cues are not met**" 일 때 쓰는 것인데
		//   사격 가능 구간에서도 걸어버린 게 원인이다.
		//
		// → 언로드는 **어차피 못 쏘는 각도(ATA>45°)** 에서만 한다.
		//   조준이 가능한 구간에서는 각을 살린다. "Lose sight, lose the fight."
		//
		// ⚠️ (EP9 결론) 이것도 실패. 발동을 껐다.
		//   EP8(무조건 언로드): WEZ 0.85→0.92 개선14/악화22, shutout 34→38
		//   EP9(ATA>45°에서만): WEZ 0.85→0.55 개선13/악화23, shutout 34→35
		//   둘 다 에너지는 확실히 좋아졌다(최저속도 83→99·96→107·84→105 m/s,
		//   실속권 체류 13.5%→1.7%). 그런데 **WEZ는 오히려 나빠졌다.**
		//
		// 해석: 중립 빔 교착은 양쪽 다 저에너지라 아무도 못 쏘는 상태다. 여기서
		// 각을 내주고 에너지를 벌면 **상대만 각을 얻는다**. 에너지는 각도를 살 수
		// 있을 때 가치가 있는데, 이 구도에선 그 전환이 안 일어난다.
		// -> 에너지 회복은 VP(각도)를 희생하지 않는 경로로만 해야 한다.
		//    스로틀은 이미 최대라 남은 건 항력 관리뿐인데 우리 제어에선 손댈 수 없다.
		const bool noShotProspect = (los > 45.0f);
		if (false && casKt < SUSTAIN_CAS_LOW && noShotProspect)
		{
			const float w = clampf((SUSTAIN_CAS_LOW - casKt) / SUSTAIN_BLEND_SPAN,
			                       0.0f, SUSTAIN_MAX_BLEND);
			const Vector3 nose = bb->MyForwardVector * dist;
			vp = myPos + (rel * (1.0f - w) + nose * w);

			// 음의 Ps를 고도로 갚는다. EP8에서 고도가 유의하게(p=0.004) 내려가
			// 여유 기준을 1,500m -> 2,500m로 올렸다.
			if (alt > SUSTAIN_ALT_ROOM)
			{
				maxDive = 35.0f;
				vp.Z = myPos.Z - (double)(400.0f * w);
			}
			throttle = 1.0f;   // 회복 중엔 풀스로틀
		}

		// ⚠️ (v7 시도 1 — 되돌림 2026-08-03)
		// 여기서 1서클/2서클에 따라 maxDive와 스로틀 목표만 바꿔봤다.
		// 페어 비교(30시드): WEZ p=1.000(개선7/악화8), shutout 13→16판,
		// 최저고도 4,135→3,596m(p=0.057). **개선 없음 + 안전 악화**라 되돌렸다.
		//
		// 원인: 1서클은 **속도 관리가 아니라 선회 방향의 문제**다(§4.8.4.2.2 —
		// "fighters turn in opposite directions at the merge, but both ground tracks
		//  in the same direction"). `vp = tgtPos`는 적을 향해 돌 뿐 방향을 고르지 않아서
		// 무엇을 바꾸든 여전히 같은 싸움을 한다. 속도 목표만 손대는 건 겉만 만진 것.
		//
		// 제대로 하려면: 머지 시점 감지 → 적 선회 방향 판별(§4.8.3.3) →
		// 반대로 돌기 → 리드턴으로 동체 정렬. 그게 다음 작업이다.
		// CAS 추정(bb->MyCas_Kt)과 판정(bb->IsOneCircle)은 계측용으로 남겨둔다.
	}
	else if (behavior == "Intercept")
	{
		// 원거리: 풀리드 예측점으로 최단 인터셉트 + 소폭 고도우위
		vp = predEnemy + Vector3(0.0f, 0.0f, 150.0f);
		maxDive = 25.0f;   // 적이 강하 중이면 따라 내려갈 수 있게 (스모크런: 15도로는 강하 추격 불가)
		throttle = 1.0f;
	}
	else // LeadPursuit
	{
		// 중거리 추적: 짧은 리드로 각도/거리 동시 압축
		const float t_mid = clampf(dist / std::max(speed, 150.0f), 0.3f, 1.2f);
		vp = tgtPos + enemyVel * t_mid;

		// (v6 Phase1) 추격 복원 — v5는 low-six 강하추격을 alt>2200m로 막아 "직진 도주 추격"
		//   장점을 통째로 잃었다(V0.3 4판: 적도주 closure -330 못잡음). 동일 기체는 수평
		//   최고속이 같아 강하로 속도를 얻어야만 잡힌다. 그래서 강하 자체가 아니라 "지면충돌"만
		//   막는다: 강하 후 예상고도가 안전(>1300m)하면 어느 고도에서든 강하추격 허용.
		// (v6 Phase1.5) 대회 녹아웃 1000ft(304.8m). 26/07/24 강하추격이 307m 추락 유발
		//   -> 안전바닥을 1300m에서 1800m로 상향, 적이 2000m 밑이면 강하추격 자체 금지.
		const float DIVE_DEPTH   = 300.0f;                          // 적 아래로 파고들 깊이
		const bool  enemyTooLow  = (float)tgtPos.Z < 2000.0f;       // 적이 2000m 밑 = 강하추격 금지
		const bool  diveKeepsSafe = ((float)myPos.Z - DIVE_DEPTH) > 1800.0f; // 강하 후 >1800m
		if (enemyAta > 110.0f && !enemyTooLow && diveKeepsSafe && (float)myPos.Z > tgtPos.Z - 100.0f)
		{
			// 강하추격: 고도를 속도로 환전해 도주 표적을 따라잡는다 (강하후 1800m+ 확보)
			vp.Z = (float)tgtPos.Z - DIVE_DEPTH;
			maxDive = 22.0f;
			throttle = 1.0f;
		}
		else if (enemyAta > 110.0f && (float)myPos.Z > tgtPos.Z)
		{
			// 적이 낮거나 강하 불가 -> 따라 안내려가고 고도유지 수평추격
			// (동일 기체라 적이 먼저 바닥 치게 두는 게 이득. 26/07/24 #5판 근거)
			vp.Z = (float)myPos.Z;
			maxDive = 6.0f;
			throttle = 1.0f;
		}
		else if (dist > 1500.0f)
			throttle = (closure > 300.0f) ? 0.5f : 1.0f;  // 과속 접근 억제(관통 방지)
		else
			throttle = CornerHoldThrottle(speed);
	}

	// ── (v6 Phase1.5) 저고도 전역 보호 (모든 상태 공통) ────────────
	// 대회 녹아웃 1000ft(304.8m). 문턱을 1500->1800m로 올리고 하강각/바닥을 강화.
	if ((float)myPos.Z < 1800.0f)
	{
		if (maxDive > 6.0f)   maxDive = 6.0f;      // 하강각 대폭 제한
		if (hardFloor < 1100.0f) hardFloor = 1100.0f;
	}

	// ── 실속 보호 (모든 상태 공통 오버라이드) ──────────────────────
	// 26/07/20 서버 로그: 상승 VP를 기어오르다 speed 99m/s까지 붕괴(실속 위기).
	// 코너속도 하한(약 150m/s) 밑이면 풀스로틀 + VP를 수평 근처로 낮춰 에너지 회복.
	if (speed < 150.0f && behavior != "AltRecover")
	{
		throttle = 1.0f;
		if (vp.Z > myPos.Z + 100.0f)   // VP가 위를 향하면 수평으로 눌러 가속 우선
			vp.Z = (float)myPos.Z + 100.0f;
	}

	// ── (v7 EP18) 저속 상승 금지 ─────────────────────────────────────
	//
	// 예선은 4,572m에서 시작하는데 jegalmin전에서는 **6,908m로 끝난다**.
	// 느려지면서(TAS 230->155) 2,336m를 올라갔다. 에너지를 두 번 버리는 셈이다.
	// (대조: btjegal전은 3,704m로 내려가 CAS 375kt = 코너속도에 안착한다)
	//
	// EP17은 강제로 강하시켰다가 Phase1 콘 시간을 잃어 실패했다.
	// 여기서는 **내려가라고 하지 않고, 못 올라가게만** 막는다.
	//   · 수평 성분은 전혀 건드리지 않는다 -> 조준 각도 손실 없음
	//   · 이미 아래를 보고 있으면 그대로 둔다 -> 강하는 막지 않음
	//   · 사거리 근처(1도 콘 유지 구간)에서는 개입하지 않는다
	// 즉 "따라 올라가지만 마라"는 최소 개입이다.
	// (EP19) **만성** 저속일 때만 개입한다.
	// EP18은 CAS<250이면 무조건 걸었는데, btjegal전에서도 선회 중 일시적으로
	// 250 아래로 떨어져 개입이 발생했고 승리가 27->20으로 줄었다.
	//   jegalmin전: Ph1 콘틱 59->200  (개선)
	//   btjegal전 : Ph1 콘틱 8935->5896, 승 27->20  (악화)
	// 두 상대가 정반대 처방을 요구한다 -> 상황을 더 좁게 잡아야 한다.
	//
	// jegalmin전은 **계속** 느리고(중앙 TAS 155), btjegal전은 잠깐 느렸다 회복한다
	// (중앙 TAS 230). 그래서 "5초 이상 연속 저속"일 때만 만성으로 보고 개입한다.
	if (casKt < 250.0f) { if (bb->SlowDwellTicks < 100000) bb->SlowDwellTicks += 1; }
	else bb->SlowDwellTicks = 0;

	// ⚠️ (EP19 결론) 발동을 껐다. 에너지/고도 계열 시도 5개가 모두 기각됐다.
	//   EP8  무조건 언로드      : 조준 악화(최소ATA 1.97->3.21도), shutout 34->38
	//   EP9  ATA>45도만 언로드   : WEZ 0.85->0.55s
	//   EP17 강제 강하          : btjegal 승 27->17 (넓은 콘만 벌고 Phase1 콘 8935->8420)
	//   EP18 상승 차단(무조건)   : btjegal 승 27->20, Phase1 콘 8935->5896
	//   EP19 상승 차단(만성만)   : **적 체력 0.226->0.281 악화** (개선16/악화23, p=0.337)
	//
	// EP19는 지표가 엇갈려 판단이 어려웠다. WEZ 11.10->14.68s, Phase1 콘틱 8935->9390,
	// 내 데미지 프록시 0.81->0.89로 전부 개선이었는데, **실제 적 체력은 악화**였다.
	// 프록시는 Phase 가중치를 쓰고 sim은 Phase1 고정이라 또 어긋났다.
	// -> 최종 판정은 tgt_health_final(실제 체력)로 한다. 어떤 WEZ 프록시보다 정확하다.
	//
	// 종합: 두 상대가 정반대 처방을 요구한다. jegalmin전은 높고 느려서 지고,
	//       btjegal전은 이미 자연 강하로 코너속도에 안착해 있어 건드리면 손해다.
	//       상대를 구분하지 않고 거는 개입은 순손실이다.
	// ── (v7 EP20) "지고 있을 때만" 상승 차단 ─────────────────────────
	// EP18/EP19가 실패한 이유는 두 상대를 구분 못 해서였다. 그런데 진단 데이터에
	// 구분자가 이미 있었다:
	//                    vs btjegal(이김)   vs jegalmin(못이김)
	//   적 ATA 중앙        143도(등을 보임)   65.5도(계속 마주봄)
	//   내 ATA 중앙          9.1도             98.4도
	//
	// 교범 승패 단서와 일치한다 (§4.7 / §4.8.4.1.5.1):
	//   이기는 중 = 내 기수가 적을 향하고 적은 등을 보인다
	//   지는 중   = 내 기수가 벗어나 있고 적이 나를 향한다
	//
	// btjegal전에선 적 ATA가 143도라 이 조건이 거짓 -> 개입 안 함(현재가 최적).
	// jegalmin전에선 65.5도라 참 -> 개입. 상대 구분 없이 상황으로 갈린다.
	const bool losingFight = (los > 60.0f) && (enemyAta < 90.0f);
	// ⚠️ (EP20 결론) 게이트는 설계대로 작동했으나 조치 자체가 무효였다. 발동 차단.
	//   btjegal  : **양쪽 시드 모두 40/40, 30/30 완전 동일** -> 게이트가 정확히 걸렀다
	//   jegalmin : 50000번대 shutout 32->30(개선), 10000번대 15->16(악화) -> 노이즈
	//   적 체력  : 양쪽 모두 사실상 변화 없음
	//
	// 이게 에너지 계열 가설을 제대로 반증한다. EP8/9/17/18/19는 "조준을 잘못 겨눴다"로
	// 설명할 수 있었지만, EP20은 **정확히 겨누고도 실제 데미지를 못 움직였다**.
	// 즉 상승 차단(고도->CAS 전환)이라는 조치 자체에 효과가 없다.
	//
	// losingFight 판정식 자체는 유효하다 - btjegal전을 정확히 배제했다.
	// 다른 조치를 시험할 때 게이트로 재사용할 수 있다.
	if (false && losingFight && bb->SlowDwellTicks > 300 && dist > 1200.0f && vp.Z > myPos.Z)
	{
		const float w = clampf((250.0f - casKt) / 100.0f, 0.0f, 1.0f);
		vp.Z = myPos.Z + (vp.Z - myPos.Z) * (double)(1.0f - w);
	}

	MakeVPSafe(bb, vp, maxDive, hardFloor);

	bb->VP_Cartesian = vp;
	bb->IsAimmingMode = aiming;
	bb->SelectedBehavior = behavior;
	bb->Throttle = clampf(throttle, 0.0f, 1.0f);
	return NodeStatus::SUCCESS;
}
