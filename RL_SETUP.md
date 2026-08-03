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

## 되돌리기

`.venv-rl` 폴더 삭제. 시스템 환경은 전혀 건드리지 않았다.
