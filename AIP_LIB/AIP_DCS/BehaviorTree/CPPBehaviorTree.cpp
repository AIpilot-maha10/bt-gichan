// Fill out your copyright notice in the Description page of Project Settings.


#include "CPPBehaviorTree.h"

#include <exception>
#include <cmath>


Vector3 UCPPBehaviorTree::LLAtoCartesian(Vector3 LLA, Vector3 BaseLLA)
{
	double eccentricitysquare, N, M;
	eccentricitysquare = 1.0 - pow(6356752.3142, 2) / pow(6378137.0, 2);
	N = 6378137.0 / sqrt(1.0 - eccentricitysquare * pow(sin(BaseLLA.X * PI / 180.0), 2)); // prime vertical radius of curvature
	M = 6378137.0 * (1.0 - eccentricitysquare) / pow(1 - eccentricitysquare * pow(sin(BaseLLA.X * PI / 180.0), 2), 3 / 2);

	double dlat, dlon;
	dlat = LLA.X - BaseLLA.X;
	dlon = LLA.Y - BaseLLA.Y;

	double dN, dE, dD;
	dN = (M + BaseLLA.Z) * dlat * PI / 180.0;
	dE = (N + BaseLLA.Z) * cos(BaseLLA.X * PI / 180.0) * dlon * PI / 180.0;
	dD = (LLA.Z - BaseLLA.Z);
	Vector3 res(dN, dE, dD);
	return res;
}

// Sets default values for this component's properties
UCPPBehaviorTree::UCPPBehaviorTree()
{
	ID = -1;
	ForceID = -1;

	f2m = 3.28084;
	EQ_R = 6.378137E+6;
	P_R = 6.3567523142E+6;
	fr = 298.257223563;
	Req = 6.378137E+6;
	d2r = 3.1415926535897931 / 180.0;
	m2f = 3.28084;


	elev0 = 0.2;
	aile0 = 0.0;
	eccen = 1.0 - P_R * P_R / (EQ_R * EQ_R);
	bInitialized = false;
	mGroundAvoidActive = false;
	RuleXmlPath = "";

	BB = new CPPBlackBoard();
}


UCPPBehaviorTree::~UCPPBehaviorTree()
{
	delete BB;
}


void UCPPBehaviorTree::init()
{
	bInitialized = false;

	try
	{
		/*
		노드 입력 : 구현해둔 노드들을 Factory 객체에 입력해주는 과정
		
		새로 생성한 노드를 여기에 입력해주세요!!!!!!
		*/
		Factory.registerNodeType<Action::SelectTarget>("SelectTarget");
		Factory.registerNodeType<Action::DistanceUpdate>("DistanceUpdate");
		Factory.registerNodeType<Action::CheckSight>("CheckSight");
		Factory.registerNodeType<Action::AngleOffUpdate>("AngleOffUpdate");
		Factory.registerNodeType<Action::DirectionVectorUpdate>("DirectionVectorUpdate");
		Factory.registerNodeType<Action::AspectAngleUpdate>("AspectAngleUpdate");
		Factory.registerNodeType<Action::DECO_BFMCheck>("DECO_BFMCheck");
		Factory.registerNodeType<Action::DECO_DistanceCheck>("DECO_DistanceCheck");
		Factory.registerNodeType<Action::DECO_LOSCheck>("DECO_LOSCheck");
		Factory.registerNodeType<Action::DECO_AngleOffCheck>("DECO_AngleOffCheck");
		Factory.registerNodeType<Action::DECO_AltCheck>("DECO_AltCheck");
		Factory.registerNodeType<Action::Task_Empty>("Task_Empty");
		Factory.registerNodeType<Action::Task_Pursuit>("Task_Pursuit");
		Factory.registerNodeType<Action::Task_LeadPursuit>("Task_LeadPursuit");
		Factory.registerNodeType<Action::Task_HighYoYo>("Task_HighYoYo");
		Factory.registerNodeType<Action::Task_LowYoYo>("Task_LowYoYo");
		Factory.registerNodeType<Action::Task_OffsetPursuit>("Task_OffsetPursuit");
		Factory.registerNodeType<Action::Task_DefensiveBreak>("Task_DefensiveBreak");
		Factory.registerNodeType<Action::Task_AltRecover>("Task_AltRecover");
		Factory.registerNodeType<Action::Task_Search>("Task_Search");
		Factory.registerNodeType<Action::Task_Tactical>("Task_Tactical");



		//파일로 트리 구조 정의 (RuleXmlPath 우선, 미설정 시 기본값)
		// 중요: {BB} 포트가 노드 생성 시점부터 동일 블랙보드를 참조하도록 createTreeFromFile에 직접 전달.
		// (생성 후 rootBlackboard()->set 만 하면 포트 리매핑이 안 되어 트리가 자식 노드를 실행하지 못함 → VP=0 추락)
		auto TreeBlackboard = BT::Blackboard::create();
		TreeBlackboard->set<CPPBlackBoard*>("BB", BB);
		tree = Factory.createTreeFromFile(RuleXmlPath.empty() ? "./Rule_gichan.xml" : RuleXmlPath.c_str(), TreeBlackboard);

		bInitialized = true;
		std::cout << "Behavior Tree Initialized Successfully" << std::endl;
	}
	catch (const std::exception& e)
	{

		std::cout << "Behavior Tree Initialization Failed: " << e.what() << std::endl;

		std::cout << "It appears that the process failed while parsing the XML." << std::endl;
		std::cout << " -Please check whether the XML file is located in the correct path." << std::endl;
		std::cout << " -Please check whether the XML file is calling any node with an invalid or incorrect name." << std::endl;
		std::cout << " -Please check whether the node was added to the Factory when building the DLL." << std::endl;
		throw;
	}
	
}

bool UCPPBehaviorTree::IsInitialized() const
{
	return bInitialized;
}

StickValue UCPPBehaviorTree::Step(PlaneInfo MyInfo, int NumofOtherPlane, PlaneInfo* OthersInfo, Vector3& VP, float& Throttle)
{
	PlaneInfo Myinfo;
	Myinfo.Location = MyInfo.Location;
	Myinfo.Rotation = EulerAngle(MyInfo.Rotation.Yaw, MyInfo.Rotation.Pitch, MyInfo.Rotation.Roll);
	Myinfo.AngleAcceleration = MyInfo.AngleAcceleration;
	Myinfo.Speed = MyInfo.Speed;
	Myinfo.Team = MyInfo.Team;
	Myinfo.Resv0 = MyInfo.Resv0;		//ID
	Myinfo.Resv1 = MyInfo.Resv1;		//HP
	Myinfo.Resv2 = MyInfo.Resv2;		//OperationMode

	//다른 비행기들 위치 좌표계 변환
	PlaneInfo others[4];
	for (int i = 0; i < NumofOtherPlane; i++)
	{
		Vector3 Enemylocation_Cartesian = OthersInfo[i].Location;
		others[i].Location = Enemylocation_Cartesian;
		others[i].Rotation = EulerAngle(OthersInfo[i].Rotation.Yaw, OthersInfo[i].Rotation.Pitch, OthersInfo[i].Rotation.Roll);
		others[i].Speed = OthersInfo[i].Speed;
		others[i].Team = OthersInfo[i].Team;
		others[i].Resv0 = OthersInfo[i].Resv0;
		others[i].Resv1 = OthersInfo[i].Resv1;
		others[i].Resv2 = OthersInfo[i].Resv2;
	}

	//블랙보드의 아군기, 적군기 List 초기화
	BB->Friendly.clear();
	BB->Enemy.clear();

	//블랙보드에 내 정보(위치, 자세, 속력, 팀) 업데이트
	BB->MyLocation_Cartesian = MyInfo.Location;
	BB->MyRotation_EDegree = EulerAngle(Myinfo.Rotation.Yaw, Myinfo.Rotation.Pitch, Myinfo.Rotation.Roll);
	BB->MyAngleAcceleration = Myinfo.AngleAcceleration;
	BB->MySpeed_MS = Myinfo.Speed;
	BB->Team = (TeamColor)Myinfo.Team;

	//아군기 리스트에 내 정보 추가. Friendly의 index 0번은 무조건 나 자신
	BB->Friendly.push_back(Myinfo);

	//생존중인 비행기들의 적아 구분
	for (int i = 0; i < NumofOtherPlane; i++)
	{
		if (others[i].Resv1 > 0)
		{
			if (others[i].Team == Myinfo.Team)
			{
				BB->Friendly.push_back(others[i]);
			}
			else
			{
				BB->Enemy.push_back(others[i]);
			}
		}
		else
		{

		}
	}


	bool AimmingMode;

	StickValue R;

	//블랙보드에 입력된 정보를 바탕으로 비헤비어트리 Run
	RunCPPBT(VP, Throttle, AimmingMode);


	R = Controller.GetStick(
		BB->MyLocation_Cartesian,
		Vector3(BB->MyRotation_EDegree.Roll * DEG2RAD,
			BB->MyRotation_EDegree.Pitch * DEG2RAD,
			BB->MyRotation_EDegree.Yaw * DEG2RAD),
		VP);

	//지상 충돌 방지: 위험하면 컨트롤러 출력을 강제 회복값으로 덮어쓴다
	PreventLandCrash(R, Throttle);

	return R;

}

bool UCPPBehaviorTree::PreventLandCrash(StickValue& R, float& Throttle)
{
	// ── 튜닝 파라미터 ───────────────────────────────────────────────
	const float HARD_FLOOR_M   = 350.0f;   // 절대 하한(녹아웃 1000ft=305m 바로 위)
	const float ENGAGE_TTI_SEC = 7.0f;     // 충돌예측시간 < 이 값이면 즉시 개입
	const float ENGAGE_ALT_M   = 500.0f;   // 이 고도 이하면 무조건 개입
	const float RELEASE_ALT_M  = 1200.0f;  // 이 고도 위로 회복하면 해제(히스테리시스)
	const float UPRIGHT_DEG    = 80.0f;    // 이 롤각 이내면 "똑바로 섰다"고 보고 풀당김
	// ───────────────────────────────────────────────────────────────

	const float alt   = (float)BB->MyLocation_Cartesian.Z;
	float       roll  = (float)BB->MyRotation_EDegree.Roll;   // deg
	const float pitch = (float)BB->MyRotation_EDegree.Pitch;  // deg, 음수=기수하강
	const float speed = (float)BB->MySpeed_MS;

	// 하강률(m/s, +면 하강): 속도 × sin(-pitch)
	const float sink = -speed * (float)std::sin(pitch * DEG2RAD);

	// 바닥까지 충돌예측시간
	float tti = 9999.0f;
	if (sink > 1.0f)
		tti = (alt - HARD_FLOOR_M) / sink;

	// ── 활성/해제 판정(히스테리시스) ───────────────────────────────
	const bool danger = (alt < ENGAGE_ALT_M) || (tti < ENGAGE_TTI_SEC);
	if (danger)
		mGroundAvoidActive = true;
	else if (alt > RELEASE_ALT_M && sink <= 0.0f)   // 안전고도 위 + 더이상 안 내려감
		mGroundAvoidActive = false;

	if (!mGroundAvoidActive)
		return false;

	// ── 강제 회복 기동 ─────────────────────────────────────────────
	// roll을 -180~180으로 정규화
	while (roll > 180.0f)  roll -= 360.0f;
	while (roll < -180.0f) roll += 360.0f;

	// 1) wings-level로 롤(짧은 방향). cmdR 부호: +면 roll 증가, -면 roll 감소.
	float rollCmd = -roll / 45.0f;
	if (rollCmd > 1.0f)  rollCmd = 1.0f;
	if (rollCmd < -1.0f) rollCmd = -1.0f;

	// 2) 피치: 똑바로 섰을 때만 풀당김(-1). 뒤집힌 동안 당기면 더 내려가므로 살짝만.
	float pitchCmd;
	if (std::abs(roll) < UPRIGHT_DEG)
		pitchCmd = -1.0f;                       // upright → 최대 상승
	else
		pitchCmd = -0.05f;                      // inverted → 우선 롤 수평부터

	R.RollCMD   = rollCmd;
	R.PitchCMD  = pitchCmd;
	R.RudderCMD = 0.0f;
	Throttle    = 1.0f;                          // 회복 중엔 풀 쓰로틀로 에너지 확보

	BB->SelectedBehavior = "PreventLandCrash";   // 모니터링: 강제회복 발동 표시

	return true;
}

Vector3 UCPPBehaviorTree::GetVP()
{
	Vector3 Vp = (*BB).VP_Cartesian;
	return Vp;
}

const char* UCPPBehaviorTree::GetSelectedBehavior() const
{
	return BB->SelectedBehavior.c_str();
}



 void UCPPBehaviorTree::RunCPPBT(Vector3& VP, float& Throttle, bool& AimmingMode)
{
	
	BB->RunningTime += BB->DeltaSecond;	//시뮬레이선 타임에 따른 델타 타임 설정
	
	try
	{
		tree.tickRoot(); //트리 작동
		VP = BB->VP_Cartesian;	// VP 값

		// BT(Task_Tactical)가 결정한 전술 스로틀 사용.
		// (기존: 1.0 하드코딩 -> 26/07/13 로그에서 전 구간 throttle=1.0,
		//  300m/s+ 과속으로 선회 불가 -> WEZ 진입 0틱의 주원인이었음)
		Throttle = BB->Throttle;
		if (Throttle < 0.0f || Throttle > 1.0f || Throttle != Throttle)
			Throttle = 1.0f;	// 미설정/이상값 방어
	}
	catch (const std::exception& e)
	{
		//원인을 알 수 없는 예외가 발생할 경우 VP를 (0,0,0)으로 설정하고 Throttle을 1로 설정하여 일단 최대한 안전하게 행동하도록 설정
		VP = Vector3(0,0,0);	// VP 값
		Throttle = 1.0f;	//

		std::cout << "ERROR!!!!!!!!! Behavior Tree Execution Failed: " << e.what() << std::endl;
		std::cout << "Temp Result VP : (0,0,0), Throttle : 1" << std::endl;
		
		throw;
	}

	

	
}

 void UCPPBehaviorTree::SetDeltaTime(double DT)
 {
	 BB->DeltaSecond = DT;
 }

