#pragma once
#include "../../../Geometry/Vector3.h"
#include "../../../Geometry/EulerAngle.h"
#include <vector>
#include <string>

using namespace BT_Geometry;

enum BFM_Mode
{
	OBFM,
	HABFM,
	DBFM,
	DETECTING,
	SCISSORS,
	NONE

};

enum ACM_Mode
{
	EF,
	SF
};

enum TeamColor
{
	BLUE,
	RED,
	UNKNOWN
};

enum S_BFM_Mode
{
	S_OBFM,
	S_HABFM,
	S_DBFM,
	S_Others
};

enum WeaponMode
{
	Gun,
	Missile
};

// (v7 A-1) 국면 분류. FightClassify가 정하고 블랙보드 FightType에 넣는다.
// 순서는 진단 출력에서 그대로 쓰이므로 중간에 값을 끼워넣지 말 것(뒤에 추가만).
enum FightTypeEnum
{
	FT_Neutral = 0,		//중립 - 아직 어느 싸움인지 정해지지 않았다
	FT_Merge,			//머지 접근 중 - 양측 고아스펙트로 빠르게 닫히는 중
	FT_OneCircle,		//1서클(최소반경). 교범: CAS<=350kt면 이쪽
	FT_TwoCircle,		//2서클(레이트). CAS>350kt
	FT_Chase,			//내가 뒤 - 적 꼬리 쪽에서 추격
	FT_Defensive		//적이 내 뒤 - 방어
};

/*
비행기들 객체 정보
자세, 위치, 속도, 팀, resv0(리눅스에서 ID), Resv1(비행기의 HP), Resv2(유인기/무인기)
*/
struct PlaneInfo
{
public:
	
	Vector3			Location;	//LLA Alt : Meter, 비헤비어트리로 입력할때는 LLA로 입력하지만 내부에서 사용할때는 Cartesian으로 사용
	
	EulerAngle		Rotation;	//Degree
	Vector3			AngleAcceleration;	//PQR
	
	float			Speed;		//m/s
	
	int				Team;		// 0 , 1
	float			Resv0;		//리눅스에서 ID로 쓰고있음
	float			Resv1;		//HP
	float			Resv2;		//유인기인지 무인기인지 판단용 0 : AI, 1 : Human

	PlaneInfo()
	{
		Location = Vector3(0, 0, 0);
		Rotation = EulerAngle(0, 0, 0);
		Speed = 0;
		Team = 0;
		Resv0 = 0;
		Resv1 = 0;
		Resv2 = 0;
	}
};

struct MissileTarget
{
public:
	int ListIndex;
	int DISID;
};

/*
그지같은 구조의 트리&블랙보드 구조를 개선해보기 위하여 만든 블랙보드 객체
비헤비어트리의 블랙보드 값을 여기에 선언-정의하고 이 블랙보드를 노드에서 호출하여 사용
모든 자세는 Degree이고 평면기준 자세를 기본으로 함

트리뿐만이 아니고 블랙보드의 변수들도 최대 2대 2까지만 상정하고 변수를 생성해둠
*/
class CPPBlackBoard
{
public:
	CPPBlackBoard();
	~CPPBlackBoard();

public:
	double RunningTime;										//해당 시뮬레이션 실행시간
	double DeltaSecond;										//비헤비어트리 작동 틱 판단 및 시간 계산용

	std::vector<PlaneInfo> Friendly;						//아군기들 정보 Array
	std::vector<PlaneInfo> Enemy;							//적기들 정보 Array

	Vector3 MyLocation_Cartesian;							//내 위치 정보 Cartesian
	Vector3 TargetLocaion_Cartesian;						//타겟 적기 위치 정보 Cartesian
	Vector3 VP_Cartesian;									//추적점 위치 정보 Cartesian

	Vector3 MyForwardVector;								//내 전방 방향 벡터
	Vector3 MyUpVector;										//내 업 방향 벡터
	Vector3 MyRightVector;									//내 오른쪽 방향 벡터

	Vector3 TargetForwardVector;							//타겟 적기 전방 방향 벡터
	Vector3 TargetUpVector;									//타겟 적기 업 방향 벡터
	Vector3 TargetRightVector;								//타겟 적기 오른쪽 방향 벡터

	EulerAngle MyRotation_EDegree;							//내 자세, 평면 기준 자세 ,Degree
	EulerAngle TargetRotation_EDegree;						//타겟 적기 자세, 평면 기준 자세, Degree

	Vector3 MyAngleAcceleration;

	float MySpeed_MS;										//내 속도, meter/sec
	float TargetSpeed_MS;									//타겟 적기 속도. meter/sec

	float Distance;											//타겟 적기와의 거리, meter
	float Throttle;											//Throttle, 0~1
	

	float Los_Degree;										//타겟에 대한 LOS값
	float Los_Degree_Target;								//타겟이 나에 대한 LOS

	float MyAngleOff_Degree;								//타겟과의 기수 교차각
	float MyAspectAngle_Degree;								//타겟에 대한 AA값

	bool EnemyInSight;
	bool EnemyInSight_Target;

	BFM_Mode BFM;											//현재 BFM (OBFM, HABFM, DBFM, DETECTING, SCISSORS, NONE)
	ACM_Mode ACM;											//현재 ACM (EF, SF)


	TeamColor Team;											//팀 컬러 (BLUE, RED, UNKNOWN)


	float AltSpeed;											//고도 변화량


	bool IsAimmingMode;

	std::string SelectedBehavior;							//현재 실행 중인 Task(전략) 이름 — 모니터링/분석용
	int BehaviorHoldTicks;									//전술 상태 최소 유지 카운터 (떨림 방지 히스테리시스)
	int HardTurnDwell;										//(v6 Phase1) HardTurn 연속 지속 틱 — 레이트 교착 감지용
	int BreakHoldTicks;										//(v6 Phase1) BreakManeuver 최소 유지 틱

	//(v7) 1서클/2서클 판단 — AETCTTP §4.8.4.2.4.2.2
	//대회 서버는 9개 값만 주므로 CAS를 고도로 추정한다. 교범 임계값이 전부 CAS 기준이라 필수.
	float MyCas_Kt;											//추정 CAS (knot). TAS × √(ρ(alt)/ρ₀)
	int   IsOneCircle;										//1=1서클(최소반경) 0=2서클(레이트)
	int   FightPlanHold;									//판단 유지 틱 — 교범 "우유부단이 최악"

	//(v7 EP7) 선회 방향 결정 — §4.8.3.3 / §4.8.4.2.2
	//1서클 = 두 기체가 **반대 회전방향**으로 돌아 하나의 원을 공유
	//2서클 = 같은 회전방향 -> 각자 원을 그림(레이트 싸움)
	Vector3 PrevTargetForward;								//적 기수벡터 직전값 (회전방향 산출용)
	float   EnemyTurnSign;									//적 회전방향 +1=시계(위에서 볼 때) -1=반시계, 0=미정
	float   PrevClosure;									//직전 닫힘속도 — 머지(최근접) 통과 감지용
	int     SlowDwellTicks;								//(v7 EP19) CAS 250kt 미만 연속 틱 — 일시적 저속과 만성 저속 구분
	int     MergeTurnTicks;									//머지 후 선회방향 강제 남은 틱
	float   MergeTurnSign;									//그때 내가 돌 방향

	// ── (v7 A-1) LOSR — 교범이 "모든 판단의 기본축"이라 부르는 지표 ──────────
	// 턴서클 진입("후방 LOSR 증가"), 리드턴 시작("급격한 후방 LOSR"),
	// 2서클 승리단서("전방 LOSR + AA<90"), TCX 종료("후방 LOSR 발생")가 전부 이것 기반.
	//
	// ⚠️ 위경도가 1e-6도(≈0.11m)로 양자화되어 들어온다. 인접 틱으로 각도를 재면
	//    노이즈가 실제값의 6배로 낀다(A-4 실측에서 데였다) → 12틱(0.2초) 기선을 쓴다.
	static const int LOSR_BASE = 12;						//기선 틱수
	Vector3 LosHistVec[LOSR_BASE + 1];						//LOS 벡터 이력 (angleBetween이 정규화를 겸하므로 그대로 저장)
	float   LosHistAta[LOSR_BASE + 1];						//같은 시점 ATA — 전/후방 부호 판정용
	double  LosHistTime[LOSR_BASE + 1];						//같은 시점 RunningTime — 가변 dt 대응
	int     LosHistCount;									//채워진 개수 (기선이 찰 때까지 0을 낸다)
	int     LosHistHead;									//링버퍼 머리
	float   LosRate_DegPerSec;								//부호 있는 LOSR. +=후방(적이 내 6시로 흐름) −=전방
	float   LosRateMag_DegPerSec;							//크기만 (부호 무관 비교용)
	float   Closure_MS;										//닫힘속도 m/s. +면 가까워지는 중 (LOSR과 같은 12틱 기선)

	// ── (v7 A-1) 교범 기준 AA — 적 **꼬리** 기준(0°=내가 적 6시) ────────────
	// MyAspectAngle_Degree는 적 **기수** 기준이라 교범과 보완각이다.
	// 교범 임계값은 반드시 이쪽에만 적용할 것. (AspectAngleUpdate가 채운다)
	float   AspectFromTail_Deg;

	// ── (v7 A-1) 에너지 ──────────────────────────────────────────────────────
	// 비에너지 Es = alt + v²/2g. 고도와 속도를 한 축으로 묶은 값.
	// 교범 §4.2.3: 에너지는 ①공격적 이익 ②방어적 필요 ③머지 준비 에만 쓴다.
	float   MyEnergy_M;
	float   TargetEnergy_M;
	float   EnergyAdvantage_M;								//내 Es − 적 Es. +면 내가 유리

	// ── (v7 A-1) 선회 기하 ───────────────────────────────────────────────────
	// 실제 비행경로에서 잰다(가정한 G가 아니라 실측). LOSR과 같은 12틱 기선.
	// 교범의 TR(턴서클 반경)·CZ 위치 계산의 전제이고, "적 선회반경 안으로
	// 들어가면 반전 기회를 준다"(§4.8.2) 같은 판단이 이걸 요구한다.
	Vector3 MyFwdHist[LOSR_BASE + 1];
	Vector3 TgtFwdHist[LOSR_BASE + 1];
	double  TurnHistTime[LOSR_BASE + 1];
	int     TurnHistCount;
	int     TurnHistHead;
	float   MyTurnRate_DegPerSec;							//내 선회율
	float   TargetTurnRate_DegPerSec;						//적 선회율
	float   MyTurnRadius_M;									//내 선회반경 = V / ω
	float   TargetTurnRadius_M;								//적 선회반경
	float   MyNz_Est;										//추정 하중배수 = √(1+(Vω/g)²). 서버는 Nz를 안 주므로 선회율로 역산

	// ── (v7 A-1) 국면 분류 ───────────────────────────────────────────────────
	// 교범 §4.3 첫 문장: "BFM은 정해진 기동의 집합이 아니다. 거리·각도·닫힘의 문제를
	// 만들거나 푸는 동적 조합이다." -> 상태를 더 쌓지 말고 "지금 어떤 종류의 싸움인가"를
	// 먼저 정하고 그에 맞는 해법을 고른다.
	// ⚠️ 현재는 분류만 한다. Task_Tactical은 아직 이 값을 읽지 않는다(순수 지표).
	int     FightType;										//FightTypeEnum
	int     FightTypeHold;									//전환 히스테리시스 — 교범 "우유부단이 최악"

	// ── (v7 EP33) 개전 시 고도 우위 래치 ─────────────────────────────────────
	// EP27~EP31이 전부 순간 게이트라 실패했고, EP32에서 래치가 작동한다는 건
	// 확인됐다(alt_split_high 1.38 -> 9.38). 다만 판정을 8초에 해서 예선이 깨졌다.
	// 빔 머지에서 8초면 초기 기하가 이미 사라진 뒤다 -> **개전 직후로 당긴다.**
	int     OpeningLatch;									//0=미정 1=우위로 시작 2=열세로 시작

};