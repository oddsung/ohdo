# ohdo PySide6 Port

원본 PyQt6 ohdo 의 **PySide6 포팅 버전**. 라이선스 유연성 (LGPL — SaaS / 폐쇄 소스 운영 호환) 확보를 위한 별도 디렉토리.

## 왜 별도 디렉토리?

- **원본 보존**: `../` (PyQt6 ohdo) 는 그대로 유지 → 비교/회귀 baseline
- **양쪽 동시 운영 가능**: 같은 `data/` (junction) 공유, 별도 venv
- **migration 안전**: 실패 시 이 디렉토리만 삭제하면 원상복구

## 라이선스 차이

| | 원본 (PyQt6) | 이 포트 (PySide6) |
|---|-------------|-----------------|
| 라이선스 | GPL v3 또는 상용 (Riverbank) | **LGPL v3** 또는 상용 (Qt Company) |
| 폐쇄 소스 배포 | 상용 라이선스 필요 | 동적 링크면 OK |
| SaaS-only | 의무 없음 (AGPL 아님) | 의무 없음 |

자세한 비교: 사용자 결정 (`docs/ROADMAP.md` §1 라이선스 전략) 따라 어느 쪽 유지할지 결정 예정.

## 실행

### 첫 사용 (venv 이미 생성됨)

```powershell
cd c:\Users\NeodaVinci\ohdo\pyside6_port
.venv\Scripts\python.exe main.py
```

### Test 실행

```powershell
.venv\Scripts\python.exe -m tests.test_runner --suite core
```

### 원본 (PyQt6) 과 비교

```powershell
# 원본 PyQt6
cd c:\Users\NeodaVinci\ohdo
.venv\Scripts\python.exe main.py

# PySide6 포트 (이 디렉토리)
cd c:\Users\NeodaVinci\ohdo\pyside6_port
.venv\Scripts\python.exe main.py
```

양쪽 동시 실행 가능 — `data/` junction 으로 같은 세션 공유.

## 디렉토리 구조

```
pyside6_port/
├── main.py, ui/, core/, tests/, config/, docs/, scripts/
├── recognition/, actions/                ← 원본과 동일 (sed 변환만)
├── data/                                  ← junction → ../data (공유)
├── requirements.txt                       ← PySide6 명시
├── .venv/                                 ← PySide6 환경 (별도)
└── README.md                              ← 이 파일
```

## Migration 변경사항 (자동 sed 적용 됨)

| 패턴 | 변경 전 | 변경 후 |
|------|--------|--------|
| Module import | `from PyQt6.X import Y` | `from PySide6.X import Y` |
| Signal | `pyqtSignal` | `Signal` |
| Slot | `pyqtSlot` | `Slot` |
| Property | `pyqtProperty` | `Property` |
| QAction 위치 | `QtWidgets.QAction` | `QtGui.QAction` |
| exec | `.exec_()` | `.exec()` |
| 패키지 검증 | `("PyQt6", "PyQt6")` | `("PySide6", "PySide6")` |

**enum**: 원본 코드가 이미 long-form (`Qt.WindowType.X`) 사용 → PySide6 호환 그대로.

## 검증 상태

- [x] **자동 회귀 테스트**: core suite 59/59 그린 (PySide6 환경)
- [x] **PyQt6 잔여 0**: 모든 import / Signal / docstring 변환됨
- [ ] **수동 GUI 테스트**: 사용자 검증 대기
  - element picker 동작
  - 블록 뷰 단독 실행
  - Excel 셀 detection
  - F3 wait + ESC stop
  - 코드 뷰 ↔ 블록 뷰 상호작용

## 향후

원본 PyQt6 와 PySide6 포트가 안정적으로 동작 확인되면, ROADMAP §1 라이선스 전략에 따라:
- **AGPL 유지** 결정 시: 원본 (PyQt6) 만 유지하고 이 디렉토리 제거
- **폐쇄 소스/상용 가능성** 시: 이 디렉토리를 main 으로 승격 + 원본 제거
- **양쪽 유지**: 라이선스 옵션 사용자 선택 가능
