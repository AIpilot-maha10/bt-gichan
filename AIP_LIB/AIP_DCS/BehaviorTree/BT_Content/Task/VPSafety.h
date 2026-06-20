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
	inline void MakeVPSafe(CPPBlackBoard* BB, Vector3& vp,
		float maxDiveDeg = 15.0f, float hardFloor = 600.0f)
	{
		const Vector3 myPos = BB->MyLocation_Cartesian;

		// 1) 하강각 제한
		const float dx = (float)(vp.X - myPos.X);
		const float dy = (float)(vp.Y - myPos.Y);
		const float horiz = std::sqrt(dx * dx + dy * dy);
		const float maxDrop = horiz * std::tan(maxDiveDeg * 3.14159265f / 180.0f);
		const float minZ = (float)myPos.Z - maxDrop;
		if (vp.Z < minZ) vp.Z = minZ;

		// 2) 타겟 고도 대비 하한 (적보다 300m 아래까지만 허용)
		const float tgtFloor = (float)BB->TargetLocaion_Cartesian.Z - 300.0f;
		if (vp.Z < tgtFloor) vp.Z = tgtFloor;

		// 3) 절대 고도 하한
		if (vp.Z < hardFloor) vp.Z = hardFloor;
	}
}
