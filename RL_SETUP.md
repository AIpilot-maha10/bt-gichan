# RL 학습환경 구축 (계획 D-1) — 완료 기록

> 2026-08-04. `.venv-rl` 생성 완료. 아래는 재현 절차와 **배포본 문서의 함정**.

## 절차

```bash
py -3.12 -m venv C:\develop\AIpilot\.venv-rl
.venv-rl\Scripts\python.exe -m pip install -r AIP_LIB\DogFightEnv\Release\requirements.txt

# ★ 필수 추가 단계 — requirements.txt에 없다
.venv-rl\Scripts\python.exe -m pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu121
```

## ⚠️ 함정 1 — requirements.txt는 CPU 전용 torch를 설치한다

`requirements.txt`에 `torch>=2.3,<3.0`만 있어 pip이 **PyPI 기본 휠(CPU)** 을 받는다.
CUDA 휠은 별도 인덱스(`download.pytorch.org/whl/cu121`)가 필요한데 그 지시가 어디에도 없다.

계획은 "GPU 확인: `torch.cuda.is_available()`"이라고만 적어뒀는데,
**확인만 하면 False가 나오고 원인을 모른다.** 실제로 이 상태를 만났다.

| | 잘못 설치 | 올바른 설치 |
|---|---|---|
| 버전 | `2.13.0+cpu` | `2.5.1+cu121` |
| `cuda.is_available()` | False | **True** |

GPU가 있는데 CPU로 몇 시간 학습하다 뒤늦게 발견하는 게 이 함정의 대가다.

## ⚠️ 함정 2 — venv 격리가 필수다

| | 시스템 python | 요구사항 |
|---|---|---|
| Python | 3.13.9 | 3.12 |
| numpy | 2.3.5 | **2.2.6** |

시스템 환경에 그냥 설치하면 numpy가 다운그레이드되어 다른 작업이 깨진다.

## 검증 완료

```
torch 2.5.1+cu121   numpy 2.2.6   ray 2.54.0   gymnasium 1.2.2
CUDA 사용가능  True
GPU  NVIDIA GeForce RTX 4060 Ti  VRAM 8.0 GB  (드라이버 591.86)
행렬곱 스모크 OK
```

## 다음 (계획 D-2 / D-3)

- `student/my_reward.py` — 현재 2항목 스텁. BT에서 배운 걸 이식:
  추락 압도적 벌점 / WEZ는 3-Phase 시간게이트 / ATA 그라디언트 / 저고도 304.8m 기준
- `student/my_curriculum.py` — 현재 2스테이지 스텁. `MY_SCENARIO_POOL`은 없으므로 직접 만든다
- **학습 상대**: `AIP_BASE_target`은 무기력하다(양쪽 0승, 적체력 1.000 — 8/4 재확인).
  이번 세션에서 상대 로스터를 5개로 늘려뒀으니 커리큘럼 상단에 쓸 것:
  `jegalmin` / `btjegal` / `v6` / `v1` / `v71`
  (구버전 gichan은 `Rule_gichan_legacy.xml` 필요 — A-1 노드가 없다)
- 산출물은 **D드라이브로** (`artifacts_dir`를 `D:\aipilot-artifacts\rl\...`)
- `--num-env-runners 4` (6c12t, JSBSim은 CPU 바운드. RAM 여유 고려)

## ✅ 파이프라인 스모크 통과 (D-1+D-2+D-3 연결 확인)

```
python train_curriculum.py --algorithm ppo --observation-mode tactical16   --reward-module student.my_reward --stages-module <스모크모듈>   --num-env-runners 1 --output-name smoke --output-tag t1
```

2반복 완료, 번들 저장, `=== Curriculum training completed ===`.
보상 모듈·커리큘럼 모듈·`env_overrides`(상대 DLL 교체) 모두 정상 작동.

### 스모크에서 발견한 문제 2건

**① `damage_scale` 키 누락 → 학습기록 저장 실패(경고)**
`training_record.py:123`이 `reward_summary['damage_scale']`을 읽는다.
우리는 가해/피격을 분리(`damage_dealt_scale`/`damage_recv_scale`)했으므로
호환용 `damage_scale` 키를 추가했다. **수정 완료.**

**② 산출물이 C드라이브에 저장된다 — `artifacts_dir`로 못 옮긴다**

`train_curriculum.py:564`가 하드코딩돼 있다:
```python
self.curriculum_dir = ROOT / "artifacts" / "curriculum" / output_name / output_tag
```
`ROOT`는 `Release/`(C드라이브)이고 출력 루트를 바꾸는 CLI 인자가 없다.
`env_overrides["artifacts_dir"]`는 **env 로그에만** 적용되고 번들·체크포인트에는 안 먹는다.

| | 실제 저장 위치 |
|---|---|
| 번들·체크포인트·training_log | `Release/artifacts/curriculum/...` (**C드라이브**) |
| env 로그 | `artifacts_dir` 지정값 (D드라이브) |

**✅ 실측으로 해소됐다.** `checkpoint_interval=1`로 2반복을 돌려 쟀다:

| | 실측 |
|---|---|
| 체크포인트 2개 + 번들 | **3.9MB** |
| 체크포인트 1개 | **약 1.8MB** |
| 본 캠페인 예상 (1,750반복 / interval 25 → 약 70개) | **약 130MB** |
| 번들·로그 포함 | **200MB 미만** |

계획은 "체크포인트가 수십 GB까지 늘 수 있다"고 봤지만 **실제는 200MB 수준**이다.
C드라이브 하드코딩은 문제가 되지 않는다. **옮길 필요 없다.**

**③ 학습기록(training record) 저장은 커리큘럼 학습에서 원래 안 된다**

`training_record.py:150`이 `result_history` 항목의 `item['iteration']`을 읽는데,
`train_curriculum.py:832`는 `metric_window`를 그대로 넘기고 거기엔 그 키가 없다.
(`train_rllib.py:1295`는 넣는다 — **단일 스테이지 학습용으로 쓰인 코드**다)

→ **배포본의 비호환이고 보상 설정으로는 못 고친다.**
   경고만 뜨고 **학습·체크포인트·번들은 정상**이다. 기록 문서만 안 남는다.

단, `MY_REWARD_CONFIG`에 아래 키는 넣어뒀다 — `training_record.py`가 대괄호로
직접 읽어 없으면 더 앞에서 실패한다(`.get()`이 아니다):
`description` / `step_penalty` / `damage_scale` / `low_altitude_penalty` /
`win_reward` / `loss_reward` / `draw_reward`

## 되돌리기

`.venv-rl` 폴더 삭제. 시스템 환경은 전혀 건드리지 않았다.
