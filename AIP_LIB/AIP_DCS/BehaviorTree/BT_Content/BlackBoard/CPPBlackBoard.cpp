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


	
}

CPPBlackBoard::~CPPBlackBoard()
{
}
