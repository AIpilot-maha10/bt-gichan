# 대회 준비 체크리스트 (bt-v7.2 기준)

> 2026-08-04 작성. 태그 `bt-v7.2` 상태에서 검증한 내용.
> 예선 8/27~28 · 본선 9/17

## 실행 명령

```
python run_unreal_inference.py --mode bt \
  --bt-dll AIP_gichan.dll --bt-rule-xml Rule_gichan.xml \
  --server-ip <서버IP> --team-name <팀명> \
  --ownship-force-side <1 또는 2> --target-force-side <반대값> \
  --engage-log
```

인자 유효성 확인됨(`--help`로 대조). `--engage-log`는 사후 분석용이라 켜두는 게 좋다.

## 제출 전 반드시 채울 것

`student/my_submission.py`:

| 항목 | 현재 | 조치 |
|---|---|---|
| `TEAM_NAME` | `"team01"` | **팀명으로 교체** |
| `SERVER_IP` | `"221.151.77.208"` | **대회 서버 IP 확인 후 교체** |
| `MODE` | `"bt"` | 그대로 |
| `BT_DLL` | `"AIP_gichan.dll"` | 그대로 |
| `BT_RULE_XML` | `"Rule_gichan.xml"` | 그대로 |
| `AI_TYPE` | `AIType.RuleBased` | 그대로 (AIType에 BehaviorTree 항목 없음) |

## 파일 확인 (Release 루트)

DLL/XML은 **반드시 짝으로** 배포한다. `Rule_gichan.xml`이 A-1 노드 4종
(`LosRateUpdate`/`EnergyUpdate`/`TurnGeomUpdate`/`FightClassify`)을 참조하므로
**XML만 새것이고 DLL이 구버전이면 "Node not recognized"로 하드 크래시**한다.

- `AIP_gichan.dll` (394,752 bytes @ bt-v7.2)
- `Rule_gichan.xml` (736 bytes @ bt-v7.2)
- `JSBSimAIPLib.dll`, `aircraft/`, `engine/` — 이동·삭제·이름변경 금지

보관본: `D:/aipilot-artifacts/dll-archive/bt-v7.2/`
복귀: `git checkout bt-v7.2` 후 재빌드, 또는 보관본 복사

## bt-v7.2 검증 결과

| 항목 | v7.1 | bt-v7.2 |
|---|---|---|
| 신규 시드 btjegal 승 (n=40) | 20 | **32판** |
| 신규 시드 적체력 | 0.328 | **0.142** |
| diag 12셀 합계 | 79.20s | **83.84s** |
| 예선 중립 셀 head_on / beam_slow | 0.77 / 0.21 | **5.53 / 3.07** |
| 추락 | 0 | **0** (eval 560판·diag 180판·regress 4건) |

## ✅ 개전 래치 — 서버 전제 검증 완료

**개전 0.5초 고도차 래치(EP33~36)의 전제가 실제 서버 로그로 확인됐다.**

7/30 서버 교전 5건(`engagement_logs/`)을 재분석한 결과, 개전 0.5초 시점에
**양측 고도차 ±0m, Es 차 ±10m**로 전부 "대칭"으로 잡힌다.
임계값(고도 300m / Es 500m)에 한참 못 미친다.
→ 에너지 회복 강하가 서버에서도 정상 발동한다.

**서버 교전 후 즉시 재확인하는 법** (재빌드 불필요):

```
python tools/sparring/check_server_latch.py engagement_logs/
```

"전부 대칭(2)"이 나오면 정상. 비대칭이 나오면 `FightClassify.cpp`의
`LATCH_ALT_M`(300m) 또는 `LATCH_AT_SEC`(0.5초) 조정이 필요하다.

## ⚠️ 아직 안 한 것

**현재 빌드로 서버 실전 교전.** 위는 *전제* 검증이고, bt-v7.2가 서버에서
실제로 어떻게 싸우는지는 확인되지 않았다. 로컬 하네스 결과
(신규 시드 btjegal 승 20→32)가 서버에서 재현되는지 봐야 한다.

## 🔴 미해결 위험 — v7.1과의 머리맞대기에서 진다

**bt-v7.2는 두 제공 상대(btjegal/jegalmin)에는 크게 낫지만, 우리 이전 버전
v7.1과 직접 붙이면 진다.** 사이드를 뒤집어도 같다.

| 방향 (n=40, 시드 50000) | 결과 |
|---|---|
| v7.2가 ownship vs v7.1 | **3승 16패** (적체력 0.813, 내체력 0.413) |
| v7.1이 ownship vs v7.2 | **15승 4패** (적체력 0.380, 내체력 0.702) |

반면 같은 v7.2가 btjegal에는 32/40승(v7.1은 20/40)이고 diag 12셀도 더 높다.
**가위바위보 관계다.**

### 원인 미규명

"에너지 회복 강하로 고도를 헌납한다"고 가설을 세웠으나 **반증됐다** —
거울 대전에서 고도차는 ±100~250m로 작고 진동하며 CAS도 10~30kt 이내다.
**두 빌드가 거의 똑같이 나는데 승부는 15-4로 갈린다.** 에너지 상태로 설명 안 된다.

### 함의

- 대회 상대는 미지다. **고도·에너지를 우리처럼 다루지 않는 상대에게 약할 수 있다.**
- 다만 btjegal/jegalmin은 실제 다른 팀의 BT이고, 거기서는 v7.2가 명백히 낫다.
- v7.1은 우리 자신의 이전 버전이라 대회 상대의 대표성이 없다.

### 판단이 필요한 지점

이 결과만으로 v7.1로 롤백하는 건 근거가 약하다(btjegal 20 vs 32승을 버리게 된다).
다만 **제3의 상대를 더 확보해 검증 폭을 넓히는 게** 다음 우선순위다.
`AIP_BASE.dll`, `AIP_gichan_v6.dll` 등으로 3~4상대 체제를 만들 것.

## 알려진 한계

- **vs jegalmin류 상대는 무승부**다. 적체력 0.994로 데미지를 못 넣는다.
  병목은 종말 추적 유지(ATA<30° 구간을 5.81초밖에 못 지킨다. btjegal은 20.13초).
  에너지·선회 계열 처방은 전부 반증됐다 — 메모리 `jegalmin_bottleneck.md` 참조.
- 소폭 잔여 손실: `energy_down` −2.15s, `floor_fight` −1.14s, `alt_split_low` −0.73s
