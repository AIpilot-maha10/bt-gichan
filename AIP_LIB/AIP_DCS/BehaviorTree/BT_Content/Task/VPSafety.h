#pragma once
#include "../BlackBoard/CPPBlackBoard.h"
#include <cmath>

namespace Action
{
	// StickController(Controller_CY)는 "롤로 양력벡터를 VP에 맞춘 뒤 당기기만" 하는
	// pull-only 제어기다. 따라서 VP를 기체보다 한참 아래에 찍으면 기체가 인버티드로
	// 롤한 뒤 그대로 당겨서 땅으로 처박힌다(=관측된 -42deg 다이브 추락).
	//
	// MakeVPSafe()는 모든 Task가 VP를 확정하기 직전에 호출해서:
	//   1) 기체 -> VP 하강각이 maxDiveDeg를 넘지 않게 클램프 (인버티드 다이브 방지)
	//   2) 타겟 고도보다 너무 아래로는 안 내려가게 (적이 위에 있으면 같이 위로)
	//   3) 절대 고도 하한선(hardFloor) 아래로는 VP를 찍지 않음 (녹아웃 1000ft=305m 방어)
	// ── (v7 EP24) 에너지 회복 강하 ────────────────────────────────────────────
	// 실측 근거 (diag_energyflow / diag_climbsource, 시드 50000~, 8판씩):
	//
	//              0-25s        50-100s      150-200s
	//   btjegal전  5,180m/226kt  3,622m/421kt  1,478m/423kt   <- 내려가며 속도를 얻는다 (이김)
	//   jegalmin전 5,230m/214kt  6,311m/233kt  8,622m/189kt   <- 올라가며 속도를 잃는다 (못이김)
	//
	// 핵심: jegalmin전에서 **비에너지는 오히려 증가한다**(6,309 -> 9,779).
	//   에너지를 잃는 게 아니라 전부 고도로 저장하고 속도로 쓰지 않는다.
	//   8,622m에서 CAS 189kt면 선회가 불가능하다(Nz 1.75, 헛당김 0.0%).
	//
	// 원인은 VP 배치가 아니다 — 두 교전의 VP 높이가 사실상 같다(위 46.4% vs 47.3%,
	//   중앙 -33m vs +4m)는데 고도는 6,880m 반대로 간다.
	//   범인은 아래 클램프 2번: tgtFloor = 적고도 - 300 이라 **적이 오르면 나도 갇힌다.**
	//   jegalmin은 싸움을 수직으로 끌고 가고 우리는 클램프에 묶여 따라 올라간다.
	//
	// 교범 §4.4.1.1: "to sustain the current G load and airspeed, the aircraft
	//   **must descend** (change potential to kinetic energy)"
	//
	// ⚠️ EP20(상승 차단)이 무효였던 이유가 여기서 설명된다 — VP가 이미 동고도(+4m)라
	//   '차단'에 걸릴 게 없었다(btjegal 40/40 완전 동일이 그 증거). **막는 것과
	//   능동적으로 내려가는 것은 다르다.** 그래서 이번엔 VP를 실제로 끌어내린다.
	//
	// 안전: 고도 여유가 큰 국면에만 건다. btjegal전 종반(1,478m)에는 발동하지 않아
	//   이기고 있는 교전을 건드리지 않는다. 추락 0판 유지가 불변 조건이다.
	// (EP26) 목표치를 300 -> 350kt. **실측 코너에 맞춘다.**
	//   EP24에서 300으로 잡은 건 근거 없는 임의값이었다. A-4 실측 코너는 CAS 350kt다.
	//   그 결과 EP24 적용 후 150-200s의 CAS가 337kt로 올라오자 needSpeed가 거짓이 되어
	//   **정작 속도가 필요한 국면에서 회복이 꺼졌다.** 코너 50kt 아래에서 멈추고 있었다.
	//   선회율은 이 50kt에 직접 걸린다 — 현재 11.5°/s vs jegalmin 14.3°/s.
	static const float ED_CAS_TARGET_KT = 350.0f;   // 이 아래면 회복 개입 (= A-4 실측 코너)
	static const float ED_CAS_FLOOR_KT = 150.0f;    // 여기서 개입 강도 최대
	static const float ED_MIN_MARGIN_M = 3000.0f;   // 녹아웃(305m) 위로 이만큼 여유가 있을 때만
	static const float ED_MAX_DIVE_DEG = 30.0f;     // 이 국면에선 하강각 제한을 푼다 (기본 15)
	static const float ED_MAX_DROP_M = 800.0f;      // VP를 내 아래로 최대 이만큼

	inline void MakeVPSafe(CPPBlackBoard* BB, Vector3& vp,
		float maxDiveDeg = 15.0f, float hardFloor = 600.0f)
	{
		const Vector3 myPos = BB->MyLocation_Cartesian;

		// 0) 에너지 회복 강하 판정 (위 주석 참조)
		const float altAboveKnockout = (float)myPos.Z - 304.8f;
		const bool needSpeed = (BB->MyCas_Kt > 1.0f && BB->MyCas_Kt < ED_CAS_TARGET_KT);
		const bool haveRoom = (altAboveKnockout > ED_MIN_MARGIN_M);

		// ── (EP28) 내가 이미 에너지 우위면 환수하지 않는다 ──────────────────────
		// 진단 격자가 EP24/EP26의 대가를 드러냈다 (같은 하네스·셀·시드, v7.1 대비):
		//   energy_up      25.20s -> 0.42s
		//   alt_split_high 23.81s -> 0.07s
		//   alt_split_low  13.44s -> 0.73s
		//   floor_fight    14.36s -> 0.90s
		//   off_inside_tc  10.74s -> 1.04s
		//   (반면 중립 구도는 개선: off_outside_tc 5.36->20.68, head_on 0.37->1.32,
		//    beam_fast 0.47->1.16 — 예선 시나리오가 여기 속한다)
		//
		// 원인: 높은 곳/유리한 곳에서 시작하면 CAS가 350kt 미만이라 회복 강하가
		//   발동해 **우위를 버리고 내려간다.** 퍼치를 스스로 포기하는 것이다.
		//
		// 교범 §4.2.3: "가용 에너지는 ①공격적 이익 ②방어적 필요 ③머지 준비 에만 쓴다.
		//   그 외에는 유지하거나 늘린다." **앞서 있으면 환수가 아니라 사용해야 한다.**
		//
		// A-1의 EnergyAdvantage_M(비에너지 차, 미터)이 정확히 이 판별에 쓰인다.
		// 대조 검증에서 불일치 0.0%로 확인된 값이다.
		const bool behindOnEnergy = (BB->EnergyAdvantage_M < 0.0f);

		// ── (EP33) 개전 시 고도 우위로 시작했으면 그 판 내내 강하를 억제한다 ──────
		// EP32에서 래치 자체는 작동이 확인됐다 — diag 5개 셀이 EP28과 소수점까지 같고
		// alt_split_high만 3.81 -> 9.38로 바뀌었다. 문제는 판정 시점(8초)이었다.
		// EP33은 개전 0.5초로 당긴다. 예선 IC는 양측 동고도라 열세(2)로 잡혀
		// 예선 동작은 EP28과 동일해야 한다(검증 가능한 예측).
		const bool startedWithHeight = (BB->OpeningLatch == 1);

		const bool energyDive = needSpeed && haveRoom && behindOnEnergy && !startedWithHeight;
		if (energyDive)
		{
			if (maxDiveDeg < ED_MAX_DIVE_DEG) maxDiveDeg = ED_MAX_DIVE_DEG;

			// 부족한 만큼 비례해서 VP를 아래로 끌어내린다
			float deficit = (ED_CAS_TARGET_KT - BB->MyCas_Kt)
				/ (ED_CAS_TARGET_KT - ED_CAS_FLOOR_KT);
			if (deficit < 0.0f) deficit = 0.0f;
			if (deficit > 1.0f) deficit = 1.0f;
			const float drop = ED_MAX_DROP_M * deficit;
			const float wantZ = (float)myPos.Z - drop;
			if (vp.Z > wantZ) vp.Z = wantZ;
		}

		// 1) 하강각 제한
		const float dx = (float)(vp.X - myPos.X);
		const float dy = (float)(vp.Y - myPos.Y);
		const float horiz = std::sqrt(dx * dx + dy * dy);
		const float maxDrop = horiz * std::tan(maxDiveDeg * 3.14159265f / 180.0f);
		const float minZ = (float)myPos.Z - maxDrop;
		if (vp.Z < minZ) vp.Z = minZ;

		// 2) 타겟 고도 대비 하한 (적보다 300m 아래까지만 허용)
		//    ★ 에너지 회복 중에는 건너뛴다 — 이 클램프가 바로 "적을 따라 올라가는"
		//      족쇄다. 적이 수직으로 끌고 갈 때 여기 묶이면 영영 못 내려온다.
		if (!energyDive)
		{
			const float tgtFloor = (float)BB->TargetLocaion_Cartesian.Z - 300.0f;
			if (vp.Z < tgtFloor) vp.Z = tgtFloor;
		}

		// 3) 절대 고도 하한
		if (vp.Z < hardFloor) vp.Z = hardFloor;
	}
}
