# ohdo SaaS 확장 작업 기록

이 폴더는 ohdo.ai 데스크톱 RPA 를 **하이브리드 SaaS**(클라우드 컨트롤 플레인 + 로컬 Agent) 로 확장해 나가는 과정의 설계·의사결정·진행 로그를 모아두는 공간입니다.

## 왜 별도 폴더인가

- [docs/ROADMAP.md](../ROADMAP.md) 는 **장기 방향성** 문서 (Phase 0~5, KPI, 리스크).
- `docs/saas/` 는 **실제 구현 작업의 기록** 입니다. 어느 세션에 무엇을 만들었고, 왜 그렇게 결정했고, 다음에 무엇을 이어갈지.
- 사용자가 SaaS 를 처음 만들기 때문에, 맥락을 잃지 않고 천천히 누적해 가는 것이 최우선.

## 구조

```
docs/saas/
├── README.md                     # 이 파일 (인덱스)
├── CHANGELOG.md                  # 세션별 누적 로그
├── decisions/                    # ADR (Architecture Decision Record)
│   ├── 0001-preserve-existing-core.md
│   └── 0002-appservice-facade-approach.md
├── architecture/                 # 구조 설계 문서
│   └── 01-app-service-and-storage.md
├── protocols/                    # 프로토콜 스펙
│   └── AGENT_PROTOCOL.md         # (예정)
└── installer/                    # 설치 프로그램 전략
    └── 00-strategy.md            # (예정)
```

## 읽는 순서 (처음 오는 사람용)

1. [ROADMAP.md §2 하이브리드 아키텍처](../ROADMAP.md#2-%EC%95%84%ED%82%A4%ED%85%8D%EC%B2%98-%EA%B6%8C%EC%9E%A5%EC%95%88-%ED%95%98%EC%9D%B4%EB%B8%8C%EB%A6%AC%EB%93%9C-%EC%97%90%EC%9D%B4%EC%A0%84%ED%8A%B8--%ED%81%B4%EB%9D%BC%EC%9A%B0%EB%93%9C-%EC%BB%A8%ED%8A%B8%EB%A1%A4-%ED%94%8C%EB%A0%88%EC%9D%B8) — 왜 하이브리드여야 하는가
2. [decisions/0001-preserve-existing-core.md](decisions/0001-preserve-existing-core.md) — 왜 기존 코드를 건드리지 않기로 했는가
3. [decisions/0002-appservice-facade-approach.md](decisions/0002-appservice-facade-approach.md) — 그럼 어떻게 확장할 것인가
4. [architecture/01-app-service-and-storage.md](architecture/01-app-service-and-storage.md) — 첫 번째 레이어 설계
5. [CHANGELOG.md](CHANGELOG.md) — 실제로 무엇을 만들었는가

## 작업 원칙 (요약)

1. **wrap-first, 필요 시 수정 허용.** 기본은 새 파일 추가로 감싸되, SaaS 연동에 불가피하면 기존 `core/`·`ui/`·`main.py` 도 수정 가능. 단 **사전 고지 + 회귀 테스트 그린 + CHANGELOG 기록 + 범위 최소화** 4조건 필수. 자세한 건 [ADR 0001](decisions/0001-preserve-existing-core.md).
2. **증분 검증.** 각 단계 후 `python -m tests.test_runner --suite core` 가 그린이어야 다음 단계로.
3. **문서가 먼저.** 코드 한 줄 쓰기 전에 설계 문서에 의도가 남아 있어야 함.
4. **ROADMAP 과의 정합성.** 구조가 달라지면 [ROADMAP.md](../ROADMAP.md) §10 변경 로그도 함께 업데이트.
