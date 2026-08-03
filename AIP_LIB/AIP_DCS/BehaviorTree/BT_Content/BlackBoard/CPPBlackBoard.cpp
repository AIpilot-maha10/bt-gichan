#include "CPPBlackBoard.h"

CPPBlackBoard::CPPBlackBoard()
{
	RunningTime = 0;
	DeltaSecond = 0.0166666;

	MyLocation_Cartesian		= Vector3(0,0,0);
	TargetLocaion_Cartesian		= Vector3(0, 0, 0);
	VP_Cartesian				= Vector3(0, 0, 0);

	MyForwardVector = Vector3(0, 0, 0);
	MyUpVector		= Vector3(0, 0, 0);
	MyRightVector	= Vector3(0, 0, 0);

	TargetForwardVector = Vector3(0, 0, 0);
	TargetUpVector		= Vector3(0, 0, 0);
	TargetRightVector	= Vector3(0, 0, 0);

	MyRotation_EDegree		= EulerAngle(0,0,0);
	TargetRotation_EDegree	= EulerAngle(0, 0, 0);

	MySpeed_MS		= 0;
	TargetSpeed_MS	= 0;

	Distance = 0;
	Throttle = 0;


	Los_Degree = 0;
	Los_Degree_Target = 0;

	MyAngleOff_Degree = 0;
	MyAspectAngle_Degree = 0;

	BFM = NONE;
	ACM = EF;

	Team = UNKNOWN;

	IsAimmingMode = false;
	SelectedBehavior = "None";
	BehaviorHoldTicks = 0;
	HardTurnDwell = 0;
	BreakHoldTicks = 0;

	MyCas_Kt = 0.0f;
	IsOneCircle = 1;		//예선 실측 속도가 둘 다 350kt 이하라 1서클이 기본
	FightPlanHold = 0;

	PrevTargetForward = Vector3(0, 0, 0);
	EnemyTurnSign = 0.0f;
	PrevClosure = 0.0f;
	SlowDwellTicks = 0;
	MergeTurnTicks = 0;
	MergeTurnSign = 0.0f;

	//(v7 A-1) LOSR 이력 초기화. 판 사이 이월을 끊는 게 목적이라 Count/Head를 반드시 0으로
	for (int i = 0; i <= LOSR_BASE; ++i)
	{
		LosHistVec[i] = Vector3(0, 0, 0);
		LosHistAta[i] = 0.0f;
		LosHistTime[i] = 0.0;
	}
	LosHistCount = 0;
	LosHistHead = 0;
	LosRate_DegPerSec = 0.0f;
	LosRateMag_DegPerSec = 0.0f;

	AspectFromTail_Deg = 0.0f;

	MyEnergy_M = 0.0f;
	TargetEnergy_M = 0.0f;
	EnergyAdvantage_M = 0.0f;

	for (int i = 0; i <= LOSR_BASE; ++i)
	{
		MyFwdHist[i] = Vector3(0, 0, 0);
		TgtFwdHist[i] = Vector3(0, 0, 0);
		TurnHistTime[i] = 0.0;
	}
	TurnHistCount = 0;
	TurnHistHead = 0;
	MyTurnRate_DegPerSec = 0.0f;
	TargetTurnRate_DegPerSec = 0.0f;
	MyTurnRadius_M = 0.0f;
	TargetTurnRadius_M = 0.0f;
	MyNz_Est = 1.0f;

	Closure_MS = 0.0f;
	FightType = FT_Neutral;
	FightTypeHold = 0;
	OpeningLatch = 0;


	
}

CPPBlackBoard::~CPPBlackBoard()
{
}
