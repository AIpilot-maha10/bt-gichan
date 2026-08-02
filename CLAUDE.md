# CLAUDE.md — AI Pilot Top Gun Challenge 2026

AI Pilot Top Gun Challenge 2026 대회용 **F-16 1v1 공중전(dogfight) AI** 코드베이스.
JSBSim 비행역학 시뮬레이터 위에서 **BT(Behavior Tree)** 와 **RL(강화학습)** 두 트랙으로 AI 파일럿을 개발한다.

---

## 📝 노션 개발일지 기록 규칙 (필수)

**비행기(BT/RL)를 수정하거나 사용자가 교전로그를 주면, 작업 완료 후 반드시 노션에 새 페이지로 기록한다.**

- 부모 페이지: **"🛠️ BT 트랙 가이드"** (page_id: `3a00adbca4ca81ef94e3e45ccffba2fd`) — 팀 허브 "AI Pilot Top Gun Challenge 2026"의 하위
- 기록 대상:
  - **비행기 수정 시**: 무엇을/왜 바꿨는지, 상태머신 변경점, 검증 결과 (예: "🛩️ gichan BT 최신 상태 상세 (v4)")
  - **교전로그 분석 시**: 판별 결과 표(dmg/WEZ틱/최소거리), 핵심 관찰, 다음 개선 포인트 (예: "📊 교전로그 분석 — 7/23 서버 3판")
  - **문제 진단 시**: 원인/해결계획 (예: "🚨 상대 비행기 2기 문제 진단")
- 제목 형식: 이모지 + 내용 + 날짜. 페이지는 항상 **새로 생성** (기존 페이지 덮어쓰기 금지, 개발일지이므로 누적)
- **교전로그 분석 시 반드시 분석한 CSV 파일명을 페이지에 명시** (예: `engagement_logs/engage_gichan_YYYYMMDD_HHMMSS.csv`) — 재현·추적 가능하도록
- 도구: Notion MCP `notion-create-pages` (parent page_id 위 값)

---

## ✈️ 공중전 교리 기준 (답변·개발 시 무조건 적용)

> 근거: 미공군 **AETCTTP 11-1** (T-38C IFF), Boelcke *Dicta*, Boyd E-M 이론.
> 전체 분석: 노션 [📚 개발일지 — 공중전 교리 원전 연구](https://app.notion.com/p/3af0adbca4ca81c8a65cca920db16146)
> **단일 진실원천**: [📐 용어·지표 표준 (B·A 공통 계약)](https://app.notion.com/p/3af0adbca4ca812380d0c17604087cfd)

### BFM 3대 공리 (§4.2)

1. **Lose Sight, Lose the Fight** — 적을 놓치면 진다
2. **Maneuver in Relation to the Bandit** — 기동은 항상 적 기준으로 (절대좌표 아님)
3. **★Energy versus Nose Position** — *"매 순간 에너지와 기수위치 중 무엇이 더 중요한지 알고 있어야 한다"*
   - 에너지는 **①공격적 이익 ②방어적 필요 ③머지 준비** 에만 쓴다. 그 외엔 유지하거나 늘린다
   - **전술 판단을 할 때 이 질문에 먼저 답하고 시작할 것**

### 🔴 용어 계약 — 우리 변수는 이름과 실제가 다르다

| 우리 변수 | 실제 = 교범 용어 | 주의 |
|---|---|---|
| `Los_Degree` | **ATA** (0°=적이 내 정면) | ✅ WEZ 판정 주축 |
| `Los_Degree_Target` | **적 ATA** | ✅ |
| `MyAngleOff_Degree` | **HCA** (0°=동일침로, 180°=정면) | ⚠️ 이름은 "AngleOff"지만 AOT 아님 |
| `MyAspectAngle_Degree` | 🔴 **180° − 교범 AA** | 교범은 **꼬리** 기준, 우리는 **기수** 기준 |

- **교범 임계값을 `MyAspectAngle_Degree`에 그대로 쓰면 정반대로 동작한다.** 신규 코드는 `AspectFromTail_Deg`(교범 기준)만 사용
- 🔴 **`GeoMathUtil._get_heading_cross_angle`은 정면머지에서 0을 반환한다** (`sign=np.sign(0)`). Python 쪽에서 HCA가 필요하면 `acos(dot(fwd,fwd))`로 직접 계산. BT의 C++ 계산은 정상
- `GeoMathUtil._get_aspect_angle`은 **부호가 있다** → 비교 전 `abs()`

### 즉시 참조 수치 (교범값 → 우리 단위)

| 항목 | 교범 | 우리 단위 |
|---|---|---|
| Control Zone | 2,500~4,500ft, 25~45° 콘 | **762~1,372m** |
| 유효사격 3조건 (Rule of Threes) | 거리 3,000ft **+** 아스펙트 30~45° **+** 안정된 닫힘 | **914m** |
| 사격 중단(repo) | 1,500~1,800ft 또는 AA>60° | **457~549m** |
| 사격 버스트 / ease 지속 | 각 2~3초 | **120~180틱** (60Hz) |
| 1서클 ↔ 2서클 분기 | ≤350kt→1서클, >350kt→2서클 | ⚠️ **CAS 기준** |
| 360° 선회 / 격추 목표 | 약 28초 / 720° 이내 | **≈1,680틱 / ≈3,360틱** |
| 최근접 금지(버블) | 1,000ft | **305m** |
| 이탈 고려 | HCA→90° & >6,000ft | **1,829m** |
| 녹아웃 고도 | 1,000ft | **304.8m** (대회 공식) |

### 매 틱 크로스체크 구조 (§4.5)

- **적 6개**: 거리 · AA · AOT · HCA · **LOSR** · closure — *"적의 게임플랜을 드러낸다"*
- **내 3개**: G · LV(양력벡터=우리의 VP 방향) · 속도 (+연료·바닥고도)
- **LV 제어 법칙** (§4.7): 너무 빠름→G 최대+출력↓+**LV 올림** / G 부족·너무 느려짐→**LV가 너무 높다**→낮춤

### ⛔ 우리 대회에서 무효인 교리 — 잘못 이식하지 말 것

| 교범 | 우리 대회 |
|---|---|
| 탄도 전제 → **리드 추적** 사격 | **LOS 콘 판정** → **순수 추적**(적 *현재 위치* 조준). 리드각은 LOS를 오염시켜 WEZ 진입을 막는다 |
| "꼬리를 잡아라"가 목표 | 콘 안이면 **측면·고아스펙트도 유효 데미지**. 꼬리 집착이 교착을 만든다 |
| 미사일·레이더·편대 전술 | 전부 무효 (1v1 건 전용) |
| 실속/스핀 회복 절차 | 시뮬 한계 내에서만 유효 |

### 판단 우선순위

**추락 0 > 피격 최소 > WEZ 획득.** *"살아있고 비행기가 멀쩡하면 이기고 있는 것"* (§4.7 DBFM)
방어 우선순위: SURVIVE → 초반 공격 무력화 → 후속 WEZ 거부 → 후속 무장 무력화 → 중립화/이탈/공격전환

### 🔍 후속조사 트리거

교전로그에서 아래 증상이 관측되면 **해당 원전을 그때 조사**하고, 결과를 노션 하위페이지로 남긴다.
상세 매핑: 메모리 `doctrine_followup_triggers.md`

| 증상 | 원전 | 상태 |
|---|---|---|
| 서로 원만 그리는 교착 | AETCTTP §4.8.4 (TCX/Ease) | ✅ |
| 방어 국면에서 계속 피격 | AETCTTP §4.7 (DBFM) | ✅ |
| 판단 순서 혼란 | AETCTTP §4.5 (크로스체크) | ✅ |
| 사격 기회 놓침 / 과조준 / CZ 진입 실패 | AETCTTP §4.6 (OBFM) | ✅ (8/2) |
| **만성 저속·에너지 고갈** | **AETCTTP §4.4 (Power/Energy)** | ✅ (8/2) |
| 수직기동·요요 세부 설계 | Shaw *Fighter Combat* | ⬜ 미조사 |
| 1v1 넘는 기동 조합 | AETCTTP §4.9 (ACM) | ⬜ 미조사 |
| 저속·고AOA 조종성 | F-16 비행교범 | ⬜ 미조사 |

### ⚡ 에너지 규율 (§4.4·§4.6 — 8/2 조사, 최우선 적용)

- **선회는 최대 G가 아니라 "airspeed sustaining feel"** — 5G로 잡고 속도가 유지되는 수준으로 낮춘다 (§4.6.3.1.5)
- **풀스로틀+최대당김인데 LOSR 진전이 없으면 → 멈추고 에너지 회복**(repo). "adequate radial G is not available" (§4.6.3.1.11)
- **음의 Ps는 강하로 갚는다** — "must descend (change potential to kinetic energy)" (§4.4.1.1). 고도 여유가 있으면 하강각 클램프를 풀 것
- **스로틀은 속도가 아니라 버핏(선회 강도)의 함수** — smooth/light→IDLE, light-mod→MIL, mod-heavy→MAX (§4.6.3.1.9.2)
- **Ease 종료는 타이머가 아니라 후방 LOSR 증가** (§4.6.3.1.8)
- **바닥 전환 10° 규칙** — 하강각 10°당 305m 위에서 전환 시작 (§4.6.3.1.12.4). 바닥 근처에선 G가 아니라 속도를 유지

---

## 핵심 도메인 개념

| 용어 | 의미 | 근거 |
|------|------|------|
| **VP** (Victory Point / 추적점) | BT가 생성하는 3D 좌표. StickController가 이 점을 향해 Roll/Pitch/Yaw/Throttle을 만든다 | `CPPBehaviorTree.h` L72-77 |
| **Phase 1/2/3** | 대회 3단계 데미지 시스템. LOS(시선각)·거리 조건에 따라 배율(1.0/0.3/0.1)이 다름 | `engagement_monitor.py` L19-23 |
| **WEZ** (Weapon Engagement Zone) | 무장 사용 가능 구역 — angle_deg, min_range_m, max_range_m 로 정의 | `student_sac_mlp.yaml` L38-41 |
| **ATA** (Antenna Train Angle) | 내 기수 → 적 시선각(LOS). 0이면 코 앞에 적 | `GeoMathUtil.py` |
| **AA** (Aspect Angle) | 적 기수 기준으로 본 나의 각도 | `GeoMathUtil.py` |
| **BFM** | Basic Fighter Maneuver (OBFM/HABFM/DBFM) — BT 블랙보드 열거형 | `CPPBlackBoard.h` L9-16 |
| **JSBSim** | 오픈소스 비행역학 모델. `JSBSimAIPLib.dll`로 래핑, `FighterSim.py`가 Python 바인딩 | `FighterSim.py`, `JSBSimWrapper.py` |
| **StickController** | VP를 향해 바라보도록 Roll/Pitch/Yaw CMD를 생성하는 제어기 | `Controller_CY.h` |
| **PreventLandCrash** | 지상충돌 방지 오토파일럿 — 하강률 기반 예측 + wings-level 강제 회복 | `CPPBehaviorTree.cpp` L208-266 |
| **action_repeat** | 학습 step_ratio=6과 맞추어 6개 PlaneInfo pair마다 새 policy 호출 | `run_unreal_inference.py` L41-47 |

---

## 디렉토리 구조

```
AIpilot/                                    # 프로젝트 루트 (git)
├── AIP_LIB/
│   ├── AIP_DCS/                            # ★ BT DLL 프로젝트 (Visual Studio, Release|x64)
│   │   ├── AIP_DCS.sln / .vcxproj
│   │   ├── LibMain.cpp                     # DLL 진입점 — export 함수들
│   │   ├── BehaviorTree/
│   │   │   ├── CPPBehaviorTree.cpp/h       # BT 초기화/Step/PreventLandCrash
│   │   │   └── BT_Content/
│   │   │       ├── Task/                   # 전술 기동 노드 (Task_Tactical, Task_Search 등)
│   │   │       ├── Decorator/              # DECO_LOSCheck, AngleOffCheck, DistanceCheck, AltCheck
│   │   │       ├── Service/                # SelectTarget, DistanceUpdate, CheckSight 등
│   │   │       └── BlackBoard/             # CPPBlackBoard (공유 상태)
│   │   └── Geometry/
│   │       ├── Controller_CY.h             # StickController (VP → 스틱 변환)
│   │       ├── Vector3.h, Matrix3.h        # 수학 유틸
│   │       └── CoordinateConverter.h
│   ├── PropertySheets/                     # MSBuild 속성시트 (Essential_release.props 등)
│   ├── bin/
│   │   ├── Release.x64/AIP_DCS.dll         # Release 빌드 산출물
│   │   └── debug.x64/AIP_DCS.dll
│   ├── DogFightEnv/
│   │   └── Release/                        # ★ RL 학습환경 + 실행 스크립트
│   │       ├── run_unreal_inference.py      # Unreal 서버 교전 클라이언트
│   │       ├── run_local_dogfight.py        # 로컬 1v1 교전 시뮬레이션
│   │       ├── train_rllib.py               # 단일 스테이지 PPO/SAC 학습
│   │       ├── train_curriculum.py          # 단계형 커리큘럼 학습
│   │       ├── analyze_engagement.py        # 교전 CSV 사후 분석기
│   │       ├── DogFightEnvWrapper.py        # Gymnasium 환경 래퍼
│   │       ├── FighterSim.py                # JSBSim Python 바인딩 (51-state)
│   │       ├── GeoMathUtil.py               # ATA/AA/HCA/거리 기하 계산
│   │       ├── JSBSimWrapper.py             # JSBSim DLL ctypes 래퍼
│   │       ├── Rule_gichan.xml              # gichan 전술 BT 트리
│   │       ├── Rule_forTraining.xml         # 학습용 BT 트리
│   │       ├── Maha_10.xml                  # jegalmin 전술 BT Rule XML
│   │       ├── AIP_BASE.dll                 # 기본 ownship BT DLL
│   │       ├── AIP_BASE_target.dll          # target(상대편) BT DLL
│   │       ├── AIP_gichan.dll               # gichan 빌드 DLL
│   │       ├── AIP_jegalmin.dll             # jegalmin 빌드 DLL
│   │       ├── JSBSimAIPLib.dll             # JSBSim 비행역학 DLL
│   │       ├── aircraft/                    # JSBSim 기체 정의 (f16, f15, fa50)
│   │       ├── engine/                      # JSBSim 엔진 정의 (F100-PW-229 등)
│   │       ├── student/                     # ★ 학생 수정 파일
│   │       │   ├── my_reward.py
│   │       │   ├── my_observation.py
│   │       │   ├── my_curriculum.py
│   │       │   ├── my_submission.py
│   │       │   └── my_train.py
│   │       ├── experiments/                 # YAML 실험 템플릿 (6개)
│   │       ├── engagement_logs/             # 교전 CSV 로그 저장
│   │       ├── logs/                        # BT/패킷 디버그 로그
│   │       ├── artifacts/                   # 학습 산출물 (모델/로그/대시보드)
│   │       ├── scripts/run_experiment.py    # YAML 실험 실행기
│   │       ├── tools/                       # 대시보드 등 도구
│   │       └── src/dogfight/
│   │           ├── ai/                      # ActionProvider, native_bt, bt_rule_manager 등
│   │           ├── envs/                    # observation, reward, termination, single_agent_env
│   │           ├── sim/                     # state_schema
│   │           ├── tools/                   # engagement_monitor
│   │           ├── unreal/                  # UDP 클라이언트, 프로토콜, policies
│   │           └── config.py
│   └── Windows/                             # Unreal DogFightViewer 관련 바이너리 (빌드 종속)
├── update/                                  # 외부 배포본 (BattleServer, 구버전 BT/RL환경)
├── 1일차 강의 자료/                          # 교육 자료 (동영상)
├── 2일차 강의 자료/                          # 매뉴얼, HTML, docx
└── README.md                                # 프로젝트 개요
```

---

## JSBSim 51-State 배열 상세

JSBSim 시뮬레이션은 **대회 서버에서 제공하는 것보다 훨씬 풍부한 정보를 제공**한다. `FighterSim.py`의 `_update_state()` 메서드(L156-233)가 FDM 출력을 51개 state 배열로 매핑한다.

> 근거: `FighterSim.py` L156-233, `state_schema.py`

### 위치 (NED 좌표계, meter)
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 0 | N | meter | North (datum: lat=37.9146°, lon=128.1819°) |
| 1 | E | meter | East |
| 2 | D | meter | Down (양수 = 아래) |

### 자세 (오일러각, 평면좌표 기준)
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 3 | Roll (phi) | deg | 기수방향 축, 우수계. -180~180 |
| 4 | Pitch (theta) | deg | 우익방향 축, 우수계. -180~180 |
| 5 | Yaw (psi) | deg | 하방축, 우수계. -180~180 |

### 체축 속도 (Body-axis velocity)
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 6 | u | m/s | 기수방향 (+전방) |
| 7 | v | m/s | 우익방향 (+오른쪽) |
| 8 | w | m/s | 하방향 (+아래) |

### 각속도 (Angular rate)
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 9 | p | deg/s | Roll rate |
| 10 | q | deg/s | Pitch rate |
| 11 | r | deg/s | Yaw rate |

### 비행 정보
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 12 | KCAS | m/s | 교정대기속도 (knot → m/s 변환됨) |
| 13 | AOA | deg | 받음각 (Angle of Attack, -90~90) |
| 14 | AOS | deg | 옆미끄럼각 (Angle of Sideslip, -90~90) |

### 조종면 명령/위치
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 15 | LatCtrlCmd | -1~1 | 에일러론 스틱 명령 (RightTurn +) |
| 16 | AileronPosition | deg | 에일러론 편향각 (-60~60) |
| 17 | LonCtrlCmd | -1~1 | 엘리베이터 스틱 명령 (PitchUp +) |
| 18 | ElevatorPosition | deg | 엘리베이터 편향각 (-60~60) |
| 19 | DirCtrlCmd | -1~1 | 러더 페달 명령 (RightTurn +) |
| 20 | RudderPosition | deg | 러더 편향각 (-60~60) |

### 엔진 1 (F100-PW-229)
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 21 | SpeedCtrlCmd1 | -1~1 | 스로틀1 명령 |
| 22 | Engine1_N1RPM | RPM | 엔진1 N1 (0~100) |
| 23 | **Fuel** | **lbs** | **잔여 연료 (파운드)**. 소모에 따라 지속 감소 → **기체 중량 변화** |
| 24 | Ax | m/s² | X축(기수방향) 가속도. **중력가속도 포함** |
| 25 | Ay | m/s² | Y축 가속도 |
| 26 | Az | m/s² | Z축 가속도 |

### 추가 비행정보
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 27 | KTAS | m/s | 진대기속도 (True Airspeed). **고도에 따른 공기밀도 차이** 반영 |
| 28 | GNDS | m/s | 지상속도 |
| 29 | MachNum | - | 마하수 (0~4). 고도별 음속 차이 반영 |
| 30 | VV | m/min | 수직속도 (NED Down, 양수=하강) |
| 31 | **Nz** | **G** | **법선방향 하중배수** (-20~20). 선회 G / 기동 한계 판단 |
| 32 | **Ny** | **G** | **측방향 하중배수**. 슬립/코디네이트 턴 판단 |

### 엔진 상세 + 스피드브레이크
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 33 | Engine1_N2RPM | RPM | 엔진1 N2 |
| 34 | Engine1_FuelFlow | m³/s | 엔진1 연료유량. **연료 소비율** |
| 35 | SpeedCtrlCmd2 | -1~1 | 스로틀2 명령 |
| 36 | Engine2_N1RPM | RPM | 엔진2 N1 |
| 37 | Engine2_N2RPM | RPM | 엔진2 N2 |
| 38 | Engine2_FuelFlow | m³/s | 엔진2 연료유량 |
| 39 | SpeedBrakeCtrlCmd | -1~1 | 스피드브레이크 명령 |
| 40 | SpeedBrakePosition | deg | 스피드브레이크 편향 (0~60) |

### 기타
| 인덱스 | 항목 | 단위 | 설명 |
|--------|------|------|------|
| 41 | SimTime | sec | 시뮬레이션 시간 |
| 42 | Lat | deg | 위도 |
| 43 | Lon | deg | 경도 |
| 44 | Alt | meter | 고도 (MSL) |
| 45 | Health | 0~1 | 체력 (Phase 데미지로 감소) |
| 46-50 | (reserved) | - | 예약 |

### 대회 서버가 제공하는 정보 (Perfect State Information)

> 근거: 1일차 강의 PPTX Slide 22

대회 서버는 **양 기체에 대해 동일한 9개 값을 60Hz로 전송**한다 (센서 노이즈/불확실성 없음):

```
Plane1/Plane2: Location(X,Y,Z), Rotation(Roll, Pitch, Yaw), Velocity(u,v,w)
```

- 접속기가 이 정보를 AI에 전달 → AI가 CMD(Roll/Pitch/Yaw/Throttle) 반환 → 서버가 JSBSim 1프레임 연산
- 관측 모드(`tactical16` 등)는 이 원본 9개 값을 신경망 입력으로 가공하는 방법의 차이

### 대회 vs 로컬 JSBSim 정보 차이

대회 서버는 위 9개 값만 제공하지만, **로컬 JSBSim 환경에서는 51개 state 전체를 양측 기체 모두에 대해 가져올 수 있다**. 로컬에서만 접근 가능한 주요 추가 정보:
- **에너지 관리**: 고도 + v²/2g 로 비에너지 계산 가능 (`engagement_monitor.py` L211-213)
- **연료 소모**: `state[23]` Fuel(lbs)이 매 스텝 감소 → 기체 총중량 변화 → 선회율/가속도 변화. 연료를 소모하면서 기체가 가벼워짐
- **G 하중**: `state[31]` Nz(법선가속도, -20~20G)로 기동 강도 제한/최적화 가능
- **밀도 고도**: KCAS(교정대기속도) vs KTAS(진대기속도) 차이로 고도별 공기밀도 효과 확인 가능. 고도가 높아지면 공기밀도 낮아져 같은 TAS에서 CAS는 감소
- **AOA/AOS**: 받음각과 옆미끄럼각으로 실속/조종 한계 감지 가능
- **엔진 연료유량**: `state[34]` Engine1_FuelFlow로 실시간 연비 모니터링
- **중력가속도/가속도**: `state[24-26]` Ax/Ay/Az에 중력 성분 포함, 고도에 따른 미세 변화 반영

---

## 모니터링 시스템 (engagement_monitor)

> 근거: `src/dogfight/tools/engagement_monitor.py`, `run_unreal_inference.py`, `analyze_engagement.py`, `bt_action_provider.py`

### 아키텍처

```
run_unreal_inference.py
  └─ --engage-log 플래그
       └─ EngagementMonitor 생성
            └─ EngagementPolicy (CommandPolicy 래퍼)
                 ├─ inner.compute_command(context) → CMD 반환
                 ├─ inner._last_action_info에서 VP/Task 추출
                 └─ monitor.record(context, cmd, action_info) → CSV 기록 + 실시간 출력
```

### EngagementMonitor (engagement_monitor.py)

- **TickRecord** 데이터클래스: 매 틱마다 40+ 필드를 CSV로 기록
  - 양측 위치/자세/속도 (own_*, enemy_*)
  - 교전 기하: distance, ata_deg, aa_deg, enemy_ata_deg
  - Phase/데미지: phase_active, dmg_dealt, dmg_received
  - 명령값: cmd_roll/pitch/yaw/throttle
  - **BT 내부정보**: task (현재 전략명), vp_x/y/z (VP좌표), vp_dist, vp_dive_deg
  - **파생값**: closure_ms (닫힘속도), own_energy_m/enemy_energy_m (비에너지)
- **record()**: 매 틱 호출. Phase 판정, 데미지 누적, 닫힘속도 계산, CSV 즉시 flush
- **실시간 출력**: `print_interval` 틱마다 한 줄 요약 (task, dist, closure, ATA, alt, speed, energy, phase, dmg)
- **stop() → _print_summary()**: 교전 종료 시 전체 통계 (승패 판정, Phase별 WEZ 틱, 비행 평균/최소, 안전위반, Task별 체류시간)

### EngagementPolicy

- 기존 `CommandPolicy`를 래핑하여 모니터링을 투명하게 주입
- `inner._last_action_info`에서 BT의 VP 좌표와 Task 이름을 읽어옴
- BT ActionProvider가 `ActionResult.info`에 `vp`, `task` 키를 포함시킴 → `ProviderCommandPolicy._last_action_info`에 보관

### analyze_engagement.py

- CSV 사후 분석 CLI: `python analyze_engagement.py engagement_logs/engage_gichan_*.csv`
- 디렉토리를 주면 최신 CSV를 자동 선택
- Task별 체류시간, 전환 시퀀스, Phase 통계 등 출력

### run_local_dogfight.py --deep-log

- `--deep-log` 플래그: JSBSim 심층 텔레메트리(연료/G/마하/받음각/에너지)를 별도 CSV로 기록
- 로컬 교전에서만 사용 가능 (JSBSim state 직접 접근)

---

## BT (Behavior Tree) 트랙

### DLL 구조

> 근거: `LibMain.cpp`, `CPPBehaviorTree.cpp/h`, `Task_Tactical.cpp/h`

**DLL export 함수:**
```cpp
CreateBehaviorTree(int OwnerID, int ForceID)    // BT 인스턴스 생성
Step(oPlaneData& MyData, int NumOfOthers, ...) -> ControlValue  // 1스텝 실행 → Roll/Pitch/Rudder/Throttle
GetVP(oPlaneData& MyData) -> Vector3            // 현재 VP 좌표 반환
SetRuleXmlPath(const char* path)                // Rule XML 경로 지정 (CreateBT 전 호출)
GetCurrentTaskName(int OwnerID) -> const char*  // 현재 실행 중 Task명 (모니터링용)
ChangeData(...) -> oPlaneData                   // NavigationData → oPlaneData 변환
Reset() / RemoveBT(int OwnerID)
```

### Rule XML 구조

> 근거: `Rule_gichan.xml`

```xml
<root main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <SelectTarget BB="{BB}"/>          <!-- 적기 선택 -->
      <DirectionVectorUpdate BB="{BB}"/> <!-- 방향벡터 갱신 -->
      <DistanceUpdate BB="{BB}"/>        <!-- 거리 갱신 -->
      <CheckSight BB="{BB}"/>            <!-- 시야 확인 -->
      <AngleOffUpdate BB="{BB}"/>        <!-- 교차각 갱신 -->
      <AspectAngleUpdate BB="{BB}"/>     <!-- AA 갱신 -->
      <Task_Tactical BB="{BB}"/>         <!-- 전술 결정 (C++ if/else 상태머신) -->
    </Sequence>
  </BehaviorTree>
</root>
```

### 공식 WEZ 룰 (시간 기반 Phase)

> 근거: 대회 공식 사이트(aipilot2026.kau.ac.kr), jegalmin `TopGunShotWindow.h`, `engagement_monitor.py`

| Phase | 시간 | LOS 콘(반각) | 사거리 |
|-------|------|--------------|--------|
| 1 | 0~100초 | **< 1°** | 152.4~914.4m (500~3000ft) |
| 2 | 100~150초 | < 2° | 152.4~1066.8m (~3500ft) |
| 3 | 150~200초 | < 3° | 152.4~1219.2m (~4000ft) |

**데미지 판정은 탄도 시뮬이 아니라 LOS 콘 체크** → 종말 조준은 적의 "현재 위치"를 겨눠야 함 (예측점 조준은 리드각만큼 LOS를 오염시켜 WEZ 진입 불가).

### Task_Tactical 상태머신 (2026-07-18 개편)

> 근거: `Task_Tactical.cpp`. 26/07/13 교전로그 진단(WEZ 진입 0틱, throttle 1.0 고정, Search 29~42% 고착) 반영 전면 개편

우선순위 기반 전술 결정. VP + **전술 스로틀(BB->Throttle)** 동시 결정:

| 조건 | 행동 | VP | 스로틀 |
|------|------|-----|--------|
| alt < 700m | **AltRecover** | 전방+2500m 상승 | 1.0 |
| 적ATA<25° & dist<1400 & LOS>80° | **DefensiveBreak** | 적 방향 수평 브레이크 6000m | 1.0 |
| dist<1800 & closure>220 & LOS<60° & 적ATA>60° | **LagEntry** | 적 꼬리 뒤 400m (지연추적) | 0.2~0.5 (적극 감속) |
| 사거리×1.3 안 LOS<45° (또는 ×1.6 안 LOS<15°) | **GunAim** | 적 현재위치+지연보상(0.03~0.12s) | 거리/닫힘속도별 0.3~1.0 |
| LOS>45° & dist<3500m | **HardTurn** | 적 현재위치 (리드 0) | 코너속도 유지 (0.25~1.0) |
| dist≥3500m | **Intercept** | 풀리드 예측점 +150m, maxDive 25° | 1.0 |
| 그 외 (LOS 15~45°) | **LeadPursuit** | 짧은 리드(0.3~1.2s) | closure>300 시 0.5, dist>1500 풀, 이하 코너유지 |

**로컬 검증 결과 (vs jegalmin 최신 빌드, 200초)**: 적 WEZ급 조준 60틱→**0틱**(LagEntry 효과), 사거리 내 LOS<15° 근접조준 0→38틱. 양측 데미지 0으로 무승부 (WEZ 콘 1° 진입은 미달성 — 후속 과제)

**핵심 설계 원칙**:
- **코너속도 유지** (`CornerHoldThrottle`): 230m/s 초과 시 0.25, 185m/s 미만 시 1.0, 사이 0.55 — 과속 시 선회반경 증가로 각도 못 줄이는 문제 해결
- **GunAim은 즉시 전환** (히스테리시스 미적용): 1° 콘 조준은 반응성이 생명. GunAim에서 maxDive=35°/hardFloor=550m로 완화 (pull-only 컨트롤러가 아래쪽 적 조준 가능하게)
- **DefensiveBreak는 실위협만**: 적 기수가 나를 조준 중(적ATA<25°)일 때만 — 중립 기하 방어 낭비 제거
- 히스테리시스 30틱은 soft 상태(HardTurn/Intercept/LeadPursuit)에만 적용

**스로틀 배선**: `RunCPPBT()`가 `Throttle = BB->Throttle` 사용 (기존 1.0 하드코딩 제거, `CPPBehaviorTree.cpp`)

**VP 안전**: 모든 VP는 `MakeVPSafe()`로 하강각/고도 하한 클램프 적용

### PreventLandCrash

> 근거: `CPPBehaviorTree.cpp` L208-266

StickController가 기울어진 상태에서 pull을 못 하는 한계를 보완하는 안전장치:
- **개입 조건**: alt < 500m 또는 TTI(충돌예측시간) < 7초
- **해제 조건**: alt > 1200m && 하강률 ≤ 0 (히스테리시스)
- **회복 기동**: ① wings-level 롤 (|roll|<80° 될 때까지) → ② 풀 당김(pitch=-1) + 풀 쓰로틀

### 빌드 & 실행

```powershell
# 1) Visual Studio Release|x64 빌드
msbuild AIP_LIB\AIP_DCS\AIP_DCS.sln /p:Configuration=Release /p:Platform=x64
# → AIP_LIB\bin\Release.x64\AIP_DCS.dll

# 2) Release 폴더로 복사 (사용자가 빌드 완료 알리면 Claude Code에 복사 요청)
copy AIP_LIB\bin\Release.x64\AIP_DCS.dll AIP_LIB\DogFightEnv\Release\AIP_gichan.dll

# 3) 교전 실행 (DogFightViewer.exe 실행 + OpenServer 후)
python run_unreal_inference.py --mode bt --bt-dll AIP_jegalmin.dll --bt-rule-xml Maha_10.xml --server-ip 127.0.0.1 --team-name jegalmin --ownship-force-side 2 --target-force-side 1 --engage-log
```

---

## RL (강화학습) 트랙

### 관측 모드

> 근거: `src/dogfight/envs/observation.py`

| 모드 | 차원 | 특징 |
|------|------|------|
| `classic12` | 12 | ownship/target 절대위치 + 정규화 자세 |
| `relative14` | 14 | 상대위치 delta + 양측 자세 + 거리/ATA/AA/LOS |
| `tactical16` | 16 | (권장) ownship 자세+속도+고도+체력, 상대 delta, ATA/AA/LOS, target 체력, WEZ 진입 플래그, 추적점수 |
| `custom` | 가변 | `student/my_observation.py` 모듈 사용 |

### 행동 공간

```
Box([-1, 1]^4)
  [0] roll    — -1:left  +1:right
  [1] pitch   — -1:aft   +1:forward
  [2] rudder  — -1:left  +1:right
  [3] throttle — 내부에서 [0,1] 변환
```

### 종료 조건

> 근거: `src/dogfight/envs/termination.py`

| 조건 | terminated/truncated |
|------|---------------------|
| FDM Update Fail | terminated |
| ownship/target 고도 < min_altitude | terminated |
| ownship/target health ≤ 0 (destroyed) | terminated |
| fuel = 0 | terminated |
| sim_time > max_engage_time | truncated |
| episode_step_limit 초과 | truncated |

---

## 수정 가능 vs 수정 금지 파일

### ✅ 수정 가능 (학생/개발자 영역)

> 근거: `README.md` "학생이 주로 수정할 파일" 테이블

| 파일 | 용도 |
|------|------|
| `student/my_reward.py` | 보상 함수 |
| `student/my_observation.py` | 커스텀 관측 벡터 |
| `student/my_curriculum.py` | 커리큘럼 스테이지 |
| `student/my_submission.py` | 제출 설정 |
| `student/my_train.py` | (선택) 간단 학습 wrapper |
| `experiments/*.yaml` | 실험 설정 |
| `AIP_DCS/BehaviorTree/BT_Content/Task/` | BT 전술 노드 (C++) |
| `AIP_DCS/BehaviorTree/BT_Content/Decorator/` | BT 데코레이터 (C++) |
| `AIP_DCS/BehaviorTree/BT_Content/Service/` | BT 서비스 노드 (C++) |
| `AIP_DCS/BehaviorTree/BT_Content/BlackBoard/` | 블랙보드 변수 |
| `Rule_*.xml` | BT 트리 구조 정의 |

### ❌ 수정 금지

> 근거: `README.md` "DLL, XML, aircraft/, engine/, JSBSim script XML은 이름 변경, 이동, 삭제하지 마세요"

| 대상 | 이유 |
|------|------|
| `JSBSimAIPLib.dll` | 비행역학 DLL — 수정 불가 |
| `AIP_BASE.dll`, `AIP_BASE_target.dll` | 기본 BT DLL (다른 팀 대전용) |
| `aircraft/`, `engine/` | JSBSim 기체/엔진 정의 |
| `FighterSim.py`, `JSBSimWrapper.py` | JSBSim Python 바인딩 |
| `DogFightEnvWrapper.py` | Gymnasium 환경 래퍼 |
| `GeoMathUtil.py` | 기하 계산 유틸리티 |
| `src/dogfight/envs/` | 환경 내부 (observation, reward 기본, termination) |
| `src/dogfight/unreal/` | UDP 클라이언트/프로토콜 |
| `Geometry/Controller_CY.h` | StickController (VP→스틱 제어기) |

---

## 학생 수정 파일 — 함수 시그니처/계약

### student/my_reward.py

> 근거: `student/my_reward.py` L33-73

```python
MY_REWARD_CONFIG = {
    "step_penalty": -0.01,
    "win_reward": 100.0,
    "loss_reward": -100.0,
    "draw_reward": -10.0,
}

def compute_reward(
    ownship_state,       # np.ndarray[51] — JSBSim 51-state (위 인덱스 표 참조)
    target_state,        # np.ndarray[51]
    ownship_damage: float,  # 이번 스텝 받은 데미지
    target_damage: float,   # 이번 스텝 준 데미지
    geo_info,            # GeometryInfo 인스턴스
    wez_config: dict,    # {"angle_deg", "min_range_m", "max_range_m"}
    reward_config: dict, # MY_REWARD_CONFIG 병합값
    terminated: bool,
    truncated: bool,
    end_condition: str,  # "ownship destroyed", "target destroyed", "max time out" 등
) -> tuple[float, dict]:
    # 반환: (total_reward, {"step": ..., "terminal": ..., ...})
```

**geo_info 사용 가능 메서드** (근거: `GeoMathUtil.py`):
```python
geo_info._get_distance(ownship_state, target_state)           # → float (meter)
geo_info._get_antenna_train_angle(own, tgt, proj=False)       # → float (deg) — ATA
geo_info._get_aspect_angle(own, tgt, proj=False)              # → float (deg) — AA
geo_info._get_heading_cross_angle(own, tgt, proj=False)       # → float (deg) — HCA
geo_info._get_los_angle(own, tgt)                             # → (az, el) (deg)
```

### student/my_observation.py

> 근거: `student/my_observation.py` L19-39

```python
OBSERVATION_MODE = "student8"    # 사용자 정의 모드명
OBSERVATION_SIZE = 8             # build_observation 반환 벡터 길이 — 반드시 일치해야 함
OBSERVATION_LOW = -1.0
OBSERVATION_HIGH = 1.0

def build_observation(ownship_state, target_state, geo_info, wez_config=None):
    # 반환: np.ndarray[OBSERVATION_SIZE], dtype=float32
```

### student/my_curriculum.py

> 근거: `student/my_curriculum.py` L26-67

```python
def get_stages() -> list[CurriculumStage]:
    # CurriculumStage 필드:
    #   index, name, description, target_mode, episode_step_limit,
    #   max_iterations, checkpoint_interval, reward_overrides,
    #   randomization, advance_conditions, advance_window
```

### student/my_submission.py

> 근거: `student/my_submission.py` L58-91

설정 변수:
```python
TEAM_NAME = "team01"
SERVER_IP = "221.151.77.208"
SERVER_PORT = 9999
MODE = "rl"                        # "rl" | "bt" | "hybrid"
BUNDLE_DIR = "artifacts/models/team01/v1"
OBSERVATION_MODE = "tactical16"    # 학습 시 사용한 모드와 동일해야 함
BT_DLL = "AIP_BASE.dll"
BT_RULE_XML = "Rule_forTraining.xml"
ACTION_REPEAT = 6                  # step_ratio=6과 일치
```

---

## 실험 YAML 파일 (6개)

> 근거: `experiments/` 디렉토리 실제 파일

| 파일 | 알고리즘 | 네트워크 | 비고 |
|------|----------|----------|------|
| `student_sac_mlp.yaml` | SAC | MLP [256,256] | 기본 시작점 |
| `student_ppo_mlp.yaml` | PPO | MLP | 기본 시작점 |
| `student_sac_lstm.yaml` | SAC | LSTM | RLlib 패치 필요 (고급) |
| `student_ppo_lstm.yaml` | PPO | LSTM | |
| `student_mixed_initial_sac_mlp.yaml` | SAC | MLP | 다양한 초기 시나리오 |
| `student_mixed_initial_sac_lstm.yaml` | SAC | LSTM | 고급 |

---

## 교전 서버 (BattleServer V0.2 / DogFightViewer)

> 근거: 1일차 강의 PPTX Slide 60, 실제 폴더 구조 확인

### 파일 위치

```
C:\develop\AIpilot\update\BattleServer_V0.2\
├── DogFightViewer/          # 뷰어 리소스 폴더
├── Engine/                  # 언리얼 엔진 런타임
├── DogFightViewer.exe       # ★ 교전 서버 겸 뷰어 실행파일 (166KB)
├── Manifest_NonUFSFiles_Win64.txt
└── Manifest_UFSFiles_Win64.txt
```

> "BattleViewerServer V2"라고 부르지만, 실제 배포 폴더명은 `BattleServer_V0.2`, 실행파일은 `DogFightViewer.exe`이다.

### 실행 순서

1. `DogFightViewer.exe` 더블클릭 → 교전 서버 실행
2. 시나리오 선택 (예: HABFM)
3. **OpenServer** 버튼 클릭 (포트 9999 오픈). 1~3 순서는 자유
4. 접속기에서 `run_unreal_inference.py` 실행 (아래 명령어 참조)
5. 1:1 교전은 양측에서 각각 접속기를 실행

### 주의사항

- `DogFightViewer/`, `Engine/`, `Manifest_*.txt`는 exe 실행에 필수 — 이동·삭제·이름변경 금지
- 서버 IP는 OpenServer 화면에 표시됨 → 접속기의 `--server-ip` 인자에 입력
- 대회 당일 네트워크 불안정 2회 이상 또는 연결 불가 시 탈락 처리

---

## 자주 쓰는 실행 명령어

> 근거: `run_unreal_inference.py` argparse, `README.md`, `run_local_dogfight.py` argparse

### BT 교전 (Unreal 서버 연결)

```powershell
# DogFightViewer.exe 실행 + OpenServer 후:
python run_unreal_inference.py --mode bt --bt-dll AIP_jegalmin.dll --bt-rule-xml Maha_10.xml --server-ip 127.0.0.1 --team-name jegalmin --ownship-force-side 2 --target-force-side 1 --engage-log
```

### RL 학습

```powershell
# YAML 실험 (권장)
python scripts\run_experiment.py experiments\student_sac_mlp.yaml
python scripts\run_experiment.py experiments\student_sac_mlp.yaml --dry-run

# 직접 실행
python train_rllib.py --algorithm sac --iterations 50 --observation-mode tactical16 --target-mode behavior_tree --target-behavior-dll AIP_BASE_target.dll --output-name team01 --output-tag v1
```

### 로컬 교전 검증

```powershell
python run_local_dogfight.py --ownship-backend rl --ownship-bundle-dir artifacts\models\team01\v1 --target-backend bt --save-log
python run_local_dogfight.py --ownship-backend rl --ownship-bundle-dir artifacts\models\team01\v1 --target-backend bt --deep-log

# gichan vs jegalmin 로컬 BT 대전 (사이드별 Rule XML — 2026-07-18 추가 옵션)
python run_local_dogfight.py --ownship-backend bt --ownship-bt-dll AIP_gichan.dll --ownship-bt-rule-xml Rule_gichan.xml --target-backend bt --target-bt-dll AIP_jegalmin.dll --max-engage-time 200 --save-log
# 주의: jegalmin DLL은 SetRuleXmlPath 미지원 → CWD의 Rule.xml(=Maha_10.xml 사본)을 자동 로드
# 결과 로그: artifacts/logs/<날짜>_ownship/target_*.csv (tacview 형식)
```

### 교전 로그 분석

```powershell
python analyze_engagement.py engagement_logs/engage_gichan_20260620_150000.csv
python analyze_engagement.py engagement_logs/    # 최신 CSV 자동 선택
```

### DLL 빌드 & 배포

```powershell
# 1) Visual Studio Release|x64 빌드
msbuild AIP_LIB\AIP_DCS\AIP_DCS.sln /p:Configuration=Release /p:Platform=x64
# → 산출물: AIP_LIB\bin\Release.x64\AIP_DCS.dll

# 2) 빌드된 DLL을 Release 폴더로 복사 (사용자가 빌드 완료를 알리면 Claude Code에 복사 요청)
copy AIP_LIB\bin\Release.x64\AIP_DCS.dll AIP_LIB\DogFightEnv\Release\AIP_gichan.dll
```

---

## 절대 어기면 안 되는 제약

> 근거: `README.md`, `student/my_submission.py`, `run_unreal_inference.py`

1. **observation_mode 일치**: 학습·로컬검증·Unreal 제출에서 동일한 observation_mode(+ observation_module)를 사용해야 한다. 차원이 다르면 정책이 동작하지 않음.
2. **action_repeat = 6**: 학습 `step_ratio=6`과 Unreal 추론 `--action-repeat 6`을 일치시켜야 한다.
3. **DLL/XML/aircraft/engine 이동/삭제 금지**: Release 루트에 있어야 한다.
4. **Rule XML은 CreateBehaviorTree 전에 SetRuleXmlPath로 지정**: `bt_action_provider.py`가 자동 처리.
5. **custom observation 차원 변경 시 기존 checkpoint 호환 불가**: 차원이 바뀌면 새 학습 필요.
6. **Unreal 서버 접속 시 force-side 주의**: `--ownship-force-side`와 `--target-force-side`를 서버 배정에 맞춰야 한다.

---

## Bundle/제출 구조

> 근거: `README.md` L186-189

```
artifacts/
├── models/<output-name>/<output-tag>/       # lightweight bundle (metadata.json + policy_weights.pkl.gz)
├── checkpoints/<output-name>/<output-tag>/  # native checkpoint (RLlib 전체 상태)
├── logs/<output-name>/<output-tag>/         # training_log.csv
└── dashboard/<output-name>_<output-tag>/    # 대시보드 데이터
```

---

## Git 커밋 히스토리 (최근)

```
fb6bf38 Split Search by range: close-range off-nose -> HardTurn (tight max-rate turn)
536a0c2 Add A-step: enemy intercept prediction + state hysteresis to Task_Tactical
07b6dde Fix BT execution + add tactical decision node, monitoring, infra
29af31b Add .gitignore, README, and PropertySheets (build property sheets)
bac09da Initial commit: gichan BT AI for 2026 Top Gun Challenge
```

주요 변경 파일 (최근 4커밋):
- `Task_Tactical.cpp/h` — 전술 결정 상태머신 신규 추가
- `Task_Search.cpp/h` — Search 기동 노드 추가
- `CPPBehaviorTree.cpp/h` — PreventLandCrash 추가, GetSelectedBehavior 추가
- `LibMain.cpp` — SetRuleXmlPath, GetCurrentTaskName export 추가
- `engagement_monitor.py` — VP/Task/에너지/닫힘속도 필드 추가
- `bt_action_provider.py` — BT 모니터링 인프라 (VP/Task 전달)
- `native_bt.py` — SetRuleXmlPath, GetCurrentTaskName 바인딩
- `run_unreal_inference.py` — engage-log 플래그 + EngagementPolicy 연결
- `run_local_dogfight.py` — deep-log 옵션 추가
- `policies.py` — ProviderCommandPolicy + _last_action_info 보관
