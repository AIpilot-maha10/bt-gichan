#include "Task_Tactical.h"
#include "VPSafety.h"
#include <algorithm>
#include <cmath>
#include <string>

PortsList Action::Task_Tactical::providedPorts()
{
	return { InputPort<CPPBlackBoard*>("BB") };
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

static WezWindow GetWez(double runningTime)
{
	WezWindow w;
	w.rMin = 152.4f;
	if (runningTime < 100.0)      { w.coneDeg = 1.0f; w.rMax = 914.4f; }
	else if (runningTime < 150.0) { w.coneDeg = 2.0f; w.rMax = 1066.8f; }
	else                          { w.coneDeg = 3.0f; w.rMax = 1219.2f; }
	return w;
}

// 코너속도 유지 스로틀: F-16 최대 선회율은 대략 185~230 m/s 부근.
// 빠르면 감속(선회반경 축소), 느리면 가속(에너지 회복).
// ⚠️ (v7) TAS 기준이라 고도에 따라 오차가 커진다. 신규 로직은 아래 CAS 기반을 쓴다.
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
	const bool forceMergeTurn = (bb->MergeTurnTicks > 0);

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
	const bool inWezRange   = dist < wez.rMax * 1.15f;                 // 사거리(+여유) 안
	const bool noseOn       = los < 40.0f;                             // 기수가 적에 근접
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
	if (alt < 900.0f)
		raw = "AltRecover";                                           // (v6) 900m로 조기화 (녹아웃 305m 대비)
	else if (enemyAta < 25.0f && dist < 1400.0f && los > 80.0f)
		raw = "DefensiveBreak";   // 적이 내 꼬리에서 조준 중 = 진짜 위협
	else if (inWezRange && noseOn)
		raw = "SnapShot";         // (v5) 사거리내 기수근접 = 즉시 스냅샷 (아스펙트 무관)
	else if (forceMergeTurn)
		raw = "MergeTurn";        // (v7 EP7) 머지 직후 회전방향 확정 — 1서클/2서클을 실제로 만든다
	else if (forceBreak && dist < 4000.0f)
		raw = "LeadTurn";         // (v6 Phase2) 2서클 교착 -> 선회방향 역전으로 1서클 전환
	else if (highAspectPass || overspeedMerge)
		raw = "LagEntry";         // (v5) 과속 관통 + 90° 고아스펙트 패스 -> 지연추적
	else if (dist < wez.rMax * 1.5f && los < 22.0f)
		raw = "GunAim";           // 사거리 근처 정밀 추적 (SnapShot 밖의 좁은 창)
	else if (los > 45.0f && dist < 3500.0f)
		raw = "HardTurn";         // 기수부터 적에게 (머지 후 재교전 포함)
	else if (dist >= 3500.0f)
		raw = "Intercept";        // 원거리: 풀리드 인터셉트로 거리 압축
	else
		raw = "LeadPursuit";      // 중거리 22~45도: 리드 추적으로 각도 압축

	// ── 2) 히스테리시스 ─────────────────────────────────────────────
	// 안전/방어/조준 상태는 즉시 전환(콘 1도짜리 조준은 반응성이 생명).
	// 나머지 기동 상태는 30틱 유지해 틱 단위 떨림 방지.
	const std::string last = bb->SelectedBehavior;
	const bool rawHard = (raw == "AltRecover" || raw == "DefensiveBreak" || raw == "GunAim"
		|| raw == "LagEntry" || raw == "SnapShot" || raw == "LeadTurn" || raw == "MergeTurn");
	const bool lastSoft = !(last == "AltRecover" || last == "DefensiveBreak" || last == "GunAim"
		|| last == "LagEntry" || last == "SnapShot" || last == "LeadTurn" || last == "MergeTurn"
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
		bb->BehaviorHoldTicks = 30;
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

	MakeVPSafe(bb, vp, maxDive, hardFloor);

	bb->VP_Cartesian = vp;
	bb->IsAimmingMode = aiming;
	bb->SelectedBehavior = behavior;
	bb->Throttle = clampf(throttle, 0.0f, 1.0f);
	return NodeStatus::SUCCESS;
}
