# bt-gichan

2026 AI Pilot Top Gun Challenge — **gichan** 1v1 도그파이트 BehaviorTree AI.

DLL(`AIP_DCS`)이 BT를 통해 VP(추적점)를 생성하면, `StickController`가 그 VP를 향해 비행하도록 Roll/Pitch/Yaw/Throttle을 만든다.

## 구조

```
AIP_LIB/
├─ AIP_DCS/                         # BT DLL 프로젝트 (Visual Studio, Release|x64)
│  ├─ AIP_DCS.sln
│  ├─ BehaviorTree/
│  │  ├─ CPPBehaviorTree.cpp        # init/Step + PreventLandCrash(지상충돌 방지)
│  │  └─ BT_Content/
│  │     ├─ Task/                   # 전술 기동 노드 (아래 표)
│  │     ├─ Decorator/              # DECO_LOSCheck / AngleOffCheck / DistanceCheck / AltCheck
│  │     ├─ Service/                # SelectTarget, AngleOffUpdate 등 블랙보드 갱신
│  │     └─ BlackBoard/
│  └─ Geometry/Controller_CY.*      # VP→스틱 변환 제어기
├─ PropertySheets/
└─ DogFightEnv/Release/
   ├─ Rule_gichan.xml               # gichan 전술 BT 트리 (DLL이 직접 로드)
   ├─ run_unreal_inference.py       # 교전 클라이언트 (--engage-log 지원)
   ├─ analyze_engagement.py         # 교전 사후 분석기
   └─ src/dogfight/tools/
      └─ engagement_monitor.py      # 틱 단위 CSV 로깅 + 실시간/사후 요약
```

## 전술 BT (Rule_gichan.xml)

고도 안전을 최우선(PRIORITY 0)으로 두고, 3-Phase 데미지 시스템에 맞춘 8개 브랜치로 구성.

| Task 노드 | 용도 |
|-----------|------|
| `Task_AltRecover` | 저고도 비상 상승 (wings-level 평탄화 후 상승) |
| `Task_DefensiveBreak` | 6시 적 탐지 시 방어 이탈 |
| `Task_Pursuit` | Phase1/2 정밀 추적 |
| `Task_LeadPursuit` | 리드 퍼슈트 (WEZ 진입) |
| `Task_HighYoYo` / `Task_LowYoYo` | 에너지 관리 |
| `Task_OffsetPursuit` | 오버슈트 회피 |

모든 추적 VP는 `VPSafety.h`의 `MakeVPSafe()`로 하강각/고도 하한을 강제 클램프.

## 지상 충돌 방지 (PreventLandCrash)

`StickController`는 기체가 기울어지면 당기지(pull) 못해 추락하는 약점이 있다.
`CPPBehaviorTree::PreventLandCrash()`가 컨트롤러 출력단에서 직접 가로채:
하강률 기반 충돌예측(tti) 또는 저고도 시 **wings-level 롤 → 풀 당김**으로 강제 회복한다.

## 빌드 & 실행

```powershell
# 빌드 (Release|x64) → AIP_DCS.dll
msbuild AIP_LIB\AIP_DCS\AIP_DCS.sln /p:Configuration=Release /p:Platform=x64
# 산출물을 AIP_gichan.dll 로 복사 후 교전 실행
python run_unreal_inference.py --mode bt --bt-dll AIP_gichan.dll `
  --bt-rule-xml Rule_gichan.xml --server-ip 127.0.0.1 --team-name gichan `
  --ownship-force-side 1 --target-force-side 2 --engage-log
```
