//AspectAngle 업데이트 하는 서비스 노드

#include "AspectAngleUpdate.h"

namespace Action
{
	PortsList AspectAngleUpdate::providedPorts()
	{
		return {
			InputPort<CPPBlackBoard*>("BB")
		};
	}

	NodeStatus AspectAngleUpdate::tick()
	{
		Optional<CPPBlackBoard*> BB = getInput<CPPBlackBoard*>("BB");

		Vector3 MyLocation = (*BB)->MyLocation_Cartesian;				//내 위치
		Vector3 TargetLocation = (*BB)->TargetLocaion_Cartesian;		//타겟 위치
		Vector3 TFV = (*BB)->TargetForwardVector;						//타겟의 Forward Vector
		Vector3 TUV = (*BB)->TargetUpVector;							//타겟의 Up Vector

		Vector3 TargetToMyPlane = MyLocation - TargetLocation;			//타겟위치에서 내위치까지의 벡터
		float P = TargetToMyPlane.dot(TUV);								//Up Vector방향 길이 구하기
		Vector3 Proj_MyLocation = MyLocation - P * TUV;					//내 위치를 적기의 Up 벡터를 법선 벡터를 가지고 적기의 위치를 지나는 평면으로 프로젝션

		Vector3 TPM = Proj_MyLocation - TargetLocation;					//프로젝션된 내 위치와 타겟사이의 벡터

		float AA = TPM.angleBetween(TFV);								//두 벡터 사이의 각 구하기 -> AA

		(*BB)->MyAspectAngle_Degree = AA* 57.2958;						//디그리 값으로 사용하기 위하여 변환

		// ── (v7 A-1) 교범 기준 AA — 적 **꼬리**에서 잰 각(0°=내가 적 6시) ──
		// 위 MyAspectAngle_Degree는 적 **기수** 기준이라 교범과 보완각이다.
		// 교범 임계값("AA>60°면 repo" 등)을 위 변수에 그대로 쓰면 정반대로 동작한다.
		// 신규 로직은 반드시 이쪽만 쓸 것.
		//
		// ⚠️ 처음엔 `180 - MyAspectAngle_Degree`로 냈다가 고쳤다(diag_aspect.py로 확인).
		//    위 값은 **적 Up 벡터에 수직인 평면으로 투영**한 뒤 잰 각인데, 공중전에서
		//    적은 항상 뱅크되어 있으므로 그 평면은 수평이 아니다. 결과적으로
		//    **AA가 적의 롤 자세에 따라 변한다** — 교범 AA는 롤과 무관해야 한다.
		//    실측: 투영본 vs 3D 차이 중앙 15.8°, p90 51° (LOS 앙각 중앙 16.3°, p90 52.7°).
		//    그래서 투영 없이 3D로 직접 잰다.
		Vector3 TargetToMe = MyLocation - TargetLocation;
		float AAfromTail = TargetToMe.angleBetween(-TFV);
		(*BB)->AspectFromTail_Deg = AAfromTail * 57.2958;

		return NodeStatus::SUCCESS;
	}

}