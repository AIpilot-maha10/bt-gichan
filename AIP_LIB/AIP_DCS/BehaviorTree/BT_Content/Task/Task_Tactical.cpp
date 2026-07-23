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
static float CornerHoldThrottle(float speedMs)
{
	if (speedMs > 230.0f) return 0.25f;
	if (speedMs < 185.0f) return 1.0f;
	return 0.55f;
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

	// 원거리 인터셉트용 예측점 (접근 단계 전용 — 종말 조준에는 사용 금지)
	const float t_lead = clampf(dist / std::max(speed, 100.0f), 0.3f, 2.0f);
	const Vector3 predEnemy = tgtPos + enemyVel * t_lead;

	// ── 1) 우선순위 기반 전술 결정 ──────────────────────────────────
	// (26/07/13 교전로그 진단 반영:
	//   - 스로틀 100% 고정 -> 300m/s+에서 선회 불가 => 코너속도 관리 추가
	//   - lead 예측점 조준 -> LOS가 리드각만큼 상시 오염, WEZ 진입 0틱 => GunAim은 현재위치 직조준
	//   - Search가 29~42% 점유하며 거리만 유지 => 제거, Intercept/HardTurn으로 대체
	//   - 중립 기하에서 DefensiveBreak 11~16% 낭비 => 적이 실제 조준중일 때만 발동)
	std::string raw;
	if (alt < 700.0f)
		raw = "AltRecover";
	else if (enemyAta < 25.0f && dist < 1400.0f && los > 80.0f)
		raw = "DefensiveBreak";   // 적이 내 꼬리에서 조준 중 = 진짜 위협
	else if (dist < 1800.0f && closure > 220.0f && los < 60.0f && enemyAta > 60.0f)
		raw = "LagEntry";         // 과속 접근 -> 적 꼬리 뒤를 조준해 관통(fly-through) 방지
	else if (dist < wez.rMax * 1.3f ? (los < 45.0f) : (los < 15.0f && dist < wez.rMax * 1.6f))
		raw = "GunAim";           // 종말 조준: 사거리 안은 넓게(45도), 조금 밖은 좁게(15도)
	else if (los > 45.0f && dist < 3500.0f)
		raw = "HardTurn";         // 기수부터 적에게 (머지 후 재교전 포함)
	else if (dist >= 3500.0f)
		raw = "Intercept";        // 원거리: 풀리드 인터셉트로 거리 압축
	else
		raw = "LeadPursuit";      // 중거리 15~45도: 리드 추적으로 각도 압축

	// ── 2) 히스테리시스 ─────────────────────────────────────────────
	// 안전/방어/조준 상태는 즉시 전환(콘 1도짜리 조준은 반응성이 생명).
	// 나머지 기동 상태는 30틱 유지해 틱 단위 떨림 방지.
	const std::string last = bb->SelectedBehavior;
	const bool rawHard = (raw == "AltRecover" || raw == "DefensiveBreak" || raw == "GunAim"
		|| raw == "LagEntry");
	const bool lastSoft = !(last == "AltRecover" || last == "DefensiveBreak" || last == "GunAim"
		|| last == "LagEntry" || last == "PreventLandCrash" || last == "None"
		|| last == "Straight" || last == "");
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
	else if (behavior == "HardTurn")
	{
		// 최대선회로 기수를 적 현재위치에 (리드 없음 = 최단 수렴).
		// 코너속도 유지가 핵심: 빠르면 선회반경이 커져 각도를 못 줄인다.
		vp = tgtPos;
		aiming = true;
		maxDive = 25.0f;
		throttle = CornerHoldThrottle(speed);
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

		// 도주 표적(적ATA>120°)은 동일 기체라 수평 추격으로 못 잡는다.
		// (26/07/20 서버 3판: 꼬리 8.5° 잡고도 closure -22로 거리 벌어짐)
		// 유일한 물리적 해법 = 적보다 약간 아래로 파고들어 고도를 속도로 환전(low-six).
		if (enemyAta > 120.0f && myPos.Z > tgtPos.Z - 200.0f)
		{
			vp.Z = (float)tgtPos.Z - 250.0f;   // 적 6시 아래로 파고들기
			maxDive = 30.0f;
			throttle = 1.0f;
		}
		else if (dist > 1500.0f)
			throttle = (closure > 300.0f) ? 0.5f : 1.0f;  // 과속 접근 억제(관통 방지)
		else
			throttle = CornerHoldThrottle(speed);
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
