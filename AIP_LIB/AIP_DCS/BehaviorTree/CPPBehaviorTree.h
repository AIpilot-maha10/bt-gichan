// Fill out your copyright notice in the Description page of Project Settings.

#pragma once
#include <iostream>
#include "./behaviortree_cpp_v3/bt_factory.h"
#include "./BT_Content/Task/TaskNodes.h"
#include "./BT_Content/Service/ServiceNodes.h"
#include "./BT_Content/Decorator/DecoratorNodes.h"
#include "../Geometry/Vector3.h"
#include "../Geometry/EulerAngle.h"
#include "../Geometry/Quaternion.h"
#include "./BT_Content/BlackBoard/CPPBlackBoard.h"
#include "./BT_Content/Functions.h"
#include "../Geometry/Controller_CY.h"


#define OriLAT 37.91455691666666
#define OriLOn 128.18188127777776

/*
	Unreal Engien 4 의 비헤비어트리로 만든 RAIP를 C++ 기반의 공짜 비헤비어트리로 구현하기 위한 클래스

	init()				: 트리 xml과 각 노드들을 load하고 블랙보드를 초기화 하는 부분
	RunCPPBT()			: 비헤비어트리를 통하여 추적점 생성
	Step()				: 생성된 추적점을 쫓아가는 스틱값 생성
	PreventLandCrash()	: 지상 충돌 방지 기능 함수
	getBT_Text()		: 비헤비어트리 어너테이션 기능으로 블랙보드에 저장된 비헤비어트리의 결정 과정 String을 불러오는 부분
	SetACM()			: 유무인 복합에서 인간 조종사가 아군기의 ACM(EF/SF)를 수동으로 결정하기 위한 함수
	SetTarget()			: 유무인 복합에서 인간 조종사가 아군기의 Target을 수동을 결정하기 위한 함수
*/
class  UCPPBehaviorTree
{

private:
	double f2m;
	double EQ_R;
	double P_R;
	double fr;
	double Req;
	double d2r;
	double m2f;
	double elev0;
	double aile0;
	double eccen;
	bool bInitialized;
	bool mGroundAvoidActive;	//지상충돌 회피 오토파일럿 활성화 상태(히스테리시스용)

private:
	//Lat, Lon, 고도는 meter
	Vector3 LLAtoCartesian(Vector3 LLA, Vector3 BaseLLA);

public:	
	int ID;			//리눅스환경에서 사용하는 변수
	int ForceID;		//리숙스환경에서 사용하는 변수
	// Sets default values for this component's properties
	UCPPBehaviorTree();
	~UCPPBehaviorTree();
	
	BT::BehaviorTreeFactory Factory;	//C++ 비헤비어트리 객체 클래스
	BT::Tree tree;	// C++ 비헤비어트리 트리
	CPPBlackBoard* BB;	// C++ 비헤비어 트리의 기본 블랙보드 방식이 쓰레기 수준이라 따로 블랙보드 클래스를 구현하여 사용
	StickController Controller; // 제어기. 비헤비어트리에서 VP(추적점)을 생성하면 그 VP를 향하여 움직이게 하는 Roll Pitch Yaw 커멘드 값을 생성
	std::string RuleXmlPath;	// 로드할 Rule XML 경로. 비면 ./Rule_gichan.xml 사용 (SetRuleXmlPath로 클라별 지정)
public:	
	
	
	//트리 xml과 각 노드들을 load하고 블랙보드를 초기화 하는 부분
	void init();	
	bool IsInitialized() const;

	/*
	비헤비어트리를 통하여 추적점 생성
		VP			: Cartesian 좌표계, meter
		Throttle	: 0~1 사이의 쓰로틀값
		AimmingMode : 제어기의 조종 모드를 결정
	*/
	void RunCPPBT(Vector3& VP, float& Throttle, bool& AimmingMode); //서비스 노드 역할, 디시전 트리

	/*
	(A-0) 진단용 — 블랙보드 내부 스칼라를 외부로 노출한다.

	왜 필요한가: 하네스 측정에서 BT가 보는 거리/각도가 실제 기하와 어긋나는 것이
	확인됐다(SnapShot이 실제 3,762m·ATA 98.8°에서 발동. 임계는 1,052m·40°).
	배율이 일정하지 않아 단순 단위 버그가 아닌데, 내부값을 볼 수단이 없어 원인을 못 좁힌다.
	이걸 안 만들면 재설계한 v7도 똑같이 깜깜이가 된다.

	out에 아래 순서로 채우고 채운 개수를 반환한다. n이 작으면 그만큼만 채운다.
	  0 Distance          1 Los_Degree(ATA)   2 Los_Degree_Target  3 MyAngleOff(HCA)
	  4 MyAspectAngle     5 RunningTime       6 MySpeed_MS         7 Throttle
	  8~10 VP_Cartesian   11~13 MyLocation    14~16 TargetLocation
	  17 EnemyInSight     18 BehaviorHoldTicks 19 HardTurnDwell
	  20 MyCas_Kt         21 IsOneCircle
	*/
	int FillDebugScalars(double* out, int n) const;
	static const int DEBUG_SCALAR_COUNT = 22;

	/*
	비헤비어트리에서 생성된 VP를 향하여 비행기가 바라보도록 비행기가 움직이게 하는 스틱값을 생성하는 함수
		MyInfo					: 내 비행기 정보 (위치 자세 속도 팀 정보등)
		NumofOtherPlane			: 전장에서 내 비행기가 아닌 다른 비행기들의 개수
		OthersInfo				: 내 비행기가 아닌 다른 비행기들의 정보 리스트(Array)
		VP						: 디버그용 Ref 변수
		Throttle				: 디버그용 Ref 변수
	*/
	StickValue Step(PlaneInfo MyInfo, int NumofOtherPlane, PlaneInfo* OthersInfo, Vector3 & VP, float & Throttle);

	/*
	지상 충돌 방지 오토파일럿.
	BT/StickController가 기울어진(banked/inverted) 상태에서 당기지 못해 추락하는 문제를
	컨트롤러 출력단에서 강제로 가로채서 회복시킨다.
	- 현재 고도뿐 아니라 "하강률 기반 충돌 예측 시간"으로 일찍 개입(급강하 조기 차단)
	- 회복 시: 먼저 wings-level로 롤 → 똑바로 서면 풀 당김(climb)
	- 히스테리시스: 한번 켜지면 안전고도 회복까지 유지(porpoise 방지)
	반환값: 회피가 활성화되어 R을 덮어썼으면 true
	*/
	bool PreventLandCrash(StickValue& R, float& Throttle);

	Vector3 GetVP();

	//현재 실행 중인 Task(전략) 이름 반환 — 모니터링/분석용
	const char* GetSelectedBehavior() const;

	//비헤비어트리 델타타입 설정 함수
	void SetDeltaTime(double DT);
};
