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

## 알려진 한계

- **vs jegalmin류 상대는 무승부**다. 적체력 0.994로 데미지를 못 넣는다.
  병목은 종말 추적 유지(ATA<30° 구간을 5.81초밖에 못 지킨다. btjegal은 20.13초).
  에너지·선회 계열 처방은 전부 반증됐다 — 메모리 `jegalmin_bottleneck.md` 참조.
- 소폭 잔여 손실: `energy_down` −2.15s, `floor_fight` −1.14s, `alt_split_low` −0.73s
