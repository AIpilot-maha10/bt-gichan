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

// ─────────────────────────────────────────────────────────────────────────
// (A-0 수정) 위치 좌표계 자동판별 + 변환
//
// 문제: Step()이 입력 Location을 그대로 블랙보드에 넣고 있었다. 주석엔 "좌표계 변환"
// 이라 적혀 있지만 실제 변환이 없었다. 로컬 sim은 LLA(위도°, 경도°, 고도m)를 주므로
// bb->MyLocation_Cartesian에 (37.9, 128.2, 8600)이 들어간다.
//
// 결과(2026-08-02 GetDebugScalars로 실측):
//   - Distance   : BT 486m  vs 실제 1922m  (비율 0.25) — 위경도 '도' 차이가 거의 0이라
//                  거리가 고도차에 지배당한다
//   - Los_Degree : BT 중앙 89.8° vs 실제 111.7° — LOS 벡터가 거의 수직이 되어
//                  ATA가 항상 90° 부근으로 붙는다
//   - HCA/속도   : 정상 (자세·속도는 위치와 무관하므로)
//
// 즉 거리·각도 기반 판단이 전부 무의미했다. SnapShot이 실제 3,170m·ATA 108°에서
// 발동하던 이유다. VP는 "내 위치 + 미터 오프셋"이라 차분이 상쇄되어 방향만은
// 우연히 맞아떨어졌고, 그래서 비행 자체는 그럴듯해 보였다.
//
// 대회 서버는 직교미터를 주므로(BT-Jegal에서 확인) 무조건 변환하면 서버에서 깨진다.
// → 입력 범위로 판별한다. 판별은 **내 위치 기준으로 한 번만** 하고 모든 기체에
//   동일 적용한다(틱 안에서 좌표계가 섞이지 않게).
//
// Z는 고도(양수=위)로 유지한다 — 기존 코드가 MyLocation_Cartesian.Z를 고도로 쓰고 있어
// 여기서 NED(Down 양수)로 바꾸면 저고도 가드가 반대로 동작한다.
// ─────────────────────────────────────────────────────────────────────────
static bool LooksLikeLLA(const Vector3& p)
{
	// 위도 |X|<=90, 경도 |Y|<=180. 직교미터라면 교전공간상 이 범위에 들어오기 어렵다
	// (원점 반경 90m 이내면 오판 가능하나, 그 경우 양측이 충돌 직전이라 무의미).
	return std::fabs(p.X) <= 90.0 && std::fabs(p.Y) <= 180.0;
}

StickValue UCPPBehaviorTree::Step(PlaneInfo MyInfo, int NumofOtherPlane, PlaneInfo* OthersInfo, Vector3& VP, float& Throttle)
{
	// 대회 datum (LibMain의 값과 동일해야 한다)
	const Vector3 DatumLLA(37.91455691666666, 128.18188127777776, 0.0);
	const bool inputIsLLA = LooksLikeLLA(MyInfo.Location);

	PlaneInfo Myinfo;
	Myinfo.Location = inputIsLLA ? LLAtoCartesian(MyInfo.Location, DatumLLA) : MyInfo.Location;
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
		// 내 위치로 판별한 좌표계를 동일 적용 (틱 안에서 좌표계가 섞이면 안 된다)
		Vector3 Enemylocation_Cartesian = inputIsLLA
			? LLAtoCartesian(OthersInfo[i].Location, DatumLLA)
			: OthersInfo[i].Location;
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
	// ⚠️ 반드시 변환된 Myinfo(소문자 i)를 쓴다. 파라미터 MyInfo(대문자 I)는 원본 LLA다.
	//    이름이 대소문자만 다른 두 변수가 공존해 실수하기 쉽다.
	BB->MyLocation_Cartesian = Myinfo.Location;
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
	// 대회 공식 규정: 해수면 1000ft(304.8m) 이하 도달 시 추락 처리.
	// (v6 Phase1.5) 26/07/24 서버: 강하추격 부활 후 307m 추락 재발(PLC 발동해도 못 살림).
	//   -> 개입을 더 조기화 + 회복을 더 강력하게(중간 뱅크에서도 당김).
	const float KNOCKOUT_M     = 304.8f;          // 대회 녹아웃 고도(1000ft)
	const float HARD_FLOOR_M   = KNOCKOUT_M + 145.0f;  // TTI 계산용 목표 바닥(=450m)
	const float ENGAGE_TTI_SEC = 11.0f;    // 충돌예측시간 < 이 값이면 즉시 개입
	const float ENGAGE_ALT_M   = 1000.0f;  // 이 고도 이하면 무조건 개입
	const float RELEASE_ALT_M  = 1600.0f;  // 이 고도 위로 회복하면 해제(히스테리시스)
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

	// 1) wings-level로 롤(짧은 방향). /30으로 공격적으로 수평화.
	float rollCmd = -roll / 30.0f;
	if (rollCmd > 1.0f)  rollCmd = 1.0f;
	if (rollCmd < -1.0f) rollCmd = -1.0f;

	// 2) 피치 — 항공역학 원칙: "언로드하며 롤 수평 -> 수평 근처에서만 당김".
	//    26/07/24 추락 분석: 뒤집힌 상태(|roll| 97~158°)에서 풀당김(-1.0)을 하는 바람에
	//    위가 아니라 지면으로 파고들어 3초에 654m 급강하 -> 추락. 또한 풀당김 중엔 고G로
	//    롤 권한이 무너져 수평 복귀조차 실패(=관측된 "떨림"). 그래서:
	//      |roll|>90  : 언로드(0) — 당기면 지면으로 파고듦. 롤에 모든 권한을 준다
	//      45~90      : 아주 약하게만
	//      <45        : 그제서야 최대 상승
	//    (긴급이라고 뱅크 무관 풀당김하는 로직은 제거 — 그게 추락 원인이었다)
	float pitchCmd;
	const float absRoll = std::abs(roll);
	if (absRoll > 90.0f)
		pitchCmd = 0.0f;                        // 인버티드: 절대 당기지 않음(언로드)
	else if (absRoll > 45.0f)
		pitchCmd = -0.2f;                       // 고뱅크: 약하게(롤 권한 확보 우선)
	else
		pitchCmd = -1.0f;                       // 수평 근처: 최대 상승

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

// (A-0) 진단용 스칼라 덤프. 순서는 헤더 주석 참조.
// 성능 영향 없음 — 외부에서 호출할 때만 읽는다.
int UCPPBehaviorTree::FillDebugScalars(double* out, int n) const
{
	if (out == nullptr || n <= 0 || BB == nullptr) return 0;

	const double v[DEBUG_SCALAR_COUNT] = {
		(double)BB->Distance,
		(double)BB->Los_Degree,
		(double)BB->Los_Degree_Target,
		(double)BB->MyAngleOff_Degree,
		(double)BB->MyAspectAngle_Degree,
		(double)BB->RunningTime,
		(double)BB->MySpeed_MS,
		(double)BB->Throttle,
		(double)BB->VP_Cartesian.X, (double)BB->VP_Cartesian.Y, (double)BB->VP_Cartesian.Z,
		(double)BB->MyLocation_Cartesian.X, (double)BB->MyLocation_Cartesian.Y, (double)BB->MyLocation_Cartesian.Z,
		(double)BB->TargetLocaion_Cartesian.X, (double)BB->TargetLocaion_Cartesian.Y, (double)BB->TargetLocaion_Cartesian.Z,
		BB->EnemyInSight ? 1.0 : 0.0,
		(double)BB->BehaviorHoldTicks,
		(double)BB->HardTurnDwell,
		(double)BB->MyCas_Kt,			// (v7) 추정 CAS
		(double)BB->IsOneCircle,		// (v7) 1=1서클 0=2서클
	};

	const int count = (n < DEBUG_SCALAR_COUNT) ? n : DEBUG_SCALAR_COUNT;
	for (int i = 0; i < count; ++i) out[i] = v[i];
	return count;
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

