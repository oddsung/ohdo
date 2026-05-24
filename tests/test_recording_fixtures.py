# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화 JSONL 픽스처 회귀 스위트.

[2026-05-24 handoff §35] PR-19i 가 commit_recording 시점에 보존한 raw events
JSONL 을 ``tests/fixtures/recordings/<name>.jsonl`` 에 복사해두면 transform
파이프라인 변경 시마다 자동 회귀. 사용자 GUI 실측 1회 = 영구 회귀 테스트로
재활용 (시간 제약 사용자 친화).

## 픽스처 추가 방법

1. ohdo 에서 시나리오 녹화 → commit_recording → ``data/sessions/<id>/
   raw_events_<rec_id>.jsonl`` 자동 생성됨 (PR-19i).
2. 파일을 ``tests/fixtures/recordings/<scenario_name>.jsonl`` 로 복사.
3. 같은 디렉터리에 ``<scenario_name>.expected.json`` sidecar 작성::

       {
         "description": "사람용 설명",
         "min_steps": 1,
         "max_steps": 10,
         "must_contain_in_any_code": ["pyautogui.write", "..."],
         "must_have_destructive": false,
         "must_have_ime": false,
         "must_have_idle_gap": false
       }

   - ``min_steps`` / ``max_steps``: transform 결과 step 개수 범위
   - ``must_contain_in_any_code``: 모든 step 의 generated_code 합본 안 필수 substring
   - ``must_have_destructive``: ``is_destructive_step`` 가 어떤 step 에 대해 None X
   - ``must_have_ime``: 어떤 raw event 의 ``ime_open=True``
   - ``must_have_idle_gap``: 어떤 step 의 ``wait_after_ms`` not None (PR-19c)

4. ``python -m tests.test_runner --suite recording_fixtures`` 실행 → 통과 확인.

## 회귀 가드 효과

- Transform pipeline (`_split_into_batches` / `_emit_*` / merge / IME / dedup)
  변경 시 사용자 의도가 깨지지 않는지 자동 검증.
- 픽스처 = 사용자 실제 행동의 결정성 스냅샷. 1 회 녹화 = 영구 회귀.
- UI / lifecycle 자체는 커버 X — pure transform 만 (CI 가능).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.recorder_transform import is_destructive_step  # noqa: E402
from core.recording_replay import load_raw_events_from_jsonl, replay_jsonl  # noqa: E402
from tests.test_runner import TestCase  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "recordings"


def _list_fixtures() -> list[Path]:
    """``*.jsonl`` 픽스처 (정렬). 없으면 빈 리스트 — smoke 통과 보장."""
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.jsonl"))


def _load_sidecar(jsonl_path: Path) -> dict | None:
    """``<name>.expected.json`` sidecar — 없으면 None (assertions 스킵)."""
    sidecar = jsonl_path.with_suffix(".expected.json")
    if not sidecar.exists():
        return None
    return json.loads(sidecar.read_text(encoding="utf-8"))


class RecordingFixturesTest(TestCase):
    """작업 녹화 JSONL 픽스처 회귀."""

    suite = "recording_fixtures"

    def setup_test(self):
        pass

    def teardown_test(self):
        pass

    def test_01_fixtures_smoke(self):
        """모든 ``.jsonl`` 픽스처가 replay_jsonl 성공 + 결과 step 일관성.

        가드:
        - 픽스처 존재 (synthetic_*.jsonl 최소 2개)
        - 각 픽스처 → replay_jsonl 예외 없음
        - 결과가 list[Step] 타입
        - 각 step 의 ``generated_code`` non-empty (빈 step emit 안 됨)
        """
        fixtures = _list_fixtures()
        self.assert_true(
            len(fixtures) >= 2,
            f"[fixture] synthetic_*.jsonl 최소 2개 존재 필수. 실제: {len(fixtures)}",
        )

        for fx in fixtures:
            self.step(f"smoke: {fx.name}")
            try:
                steps = replay_jsonl(fx)
            except Exception as exc:  # noqa: BLE001 — 픽스처 손상 진단
                self.assert_true(
                    False, f"[fixture {fx.name}] replay_jsonl 예외: {type(exc).__name__}: {exc}"
                )
                continue
            self.assert_true(
                isinstance(steps, list),
                f"[fixture {fx.name}] replay_jsonl 결과 list 필수. type: {type(steps).__name__}",
            )
            for i, s in enumerate(steps, start=1):
                self.assert_true(
                    bool(s.generated_code or s.step_code),
                    f"[fixture {fx.name}] step {i} generated_code non-empty. "
                    f"실제: code={s.generated_code!r}",
                )

    def test_02_fixtures_assertions(self):
        """``<name>.expected.json`` sidecar 의 assertions 검증.

        sidecar 없으면 해당 픽스처는 smoke 만 (이 테스트에서 skip).
        sidecar 있으면 min/max_steps, must_contain_in_any_code,
        must_have_destructive / must_have_ime / must_have_idle_gap 검증.
        """
        fixtures = _list_fixtures()
        sidecar_count = 0

        for fx in fixtures:
            sidecar = _load_sidecar(fx)
            if sidecar is None:
                continue
            sidecar_count += 1
            desc = sidecar.get("description", "(no description)")
            self.step(f"{fx.name}: {desc}")

            steps = replay_jsonl(fx)

            # min/max_steps
            min_s = sidecar.get("min_steps", 0)
            max_s = sidecar.get("max_steps", 10**6)
            self.assert_true(
                min_s <= len(steps) <= max_s,
                f"[{fx.name}] step 개수 {min_s}~{max_s} 범위. 실제: {len(steps)}",
            )

            # must_contain_in_any_code — 모든 step 의 코드 합본에서 substring 검색
            all_code = "\n".join((s.generated_code or s.step_code or "") for s in steps)
            for needle in sidecar.get("must_contain_in_any_code", []) or []:
                self.assert_true(
                    needle in all_code,
                    f"[{fx.name}] 어떤 step 의 코드에 {needle!r} 필수.\n--- code ---\n{all_code}",
                )

            # must_have_destructive — is_destructive_step 가 어떤 step 에서 사유 반환
            if sidecar.get("must_have_destructive", False):
                any_destructive = any(is_destructive_step(s) is not None for s in steps)
                self.assert_true(
                    any_destructive,
                    f"[{fx.name}] 적어도 한 step 이 destructive (is_destructive_step != None) 필수.",
                )

            # must_have_ime — raw events 중 ime_open=True 가 하나라도 있어야 함
            if sidecar.get("must_have_ime", False):
                raw = load_raw_events_from_jsonl(fx)
                any_ime = any(ev.ime_open for ev in raw)
                self.assert_true(
                    any_ime,
                    f"[{fx.name}] 적어도 한 raw event 의 ime_open=True 필수.",
                )

            # must_have_idle_gap — 어떤 step 의 wait_after_ms not None
            if sidecar.get("must_have_idle_gap", False):
                any_wait = any(s.wait_after_ms is not None for s in steps)
                self.assert_true(
                    any_wait,
                    f"[{fx.name}] 적어도 한 step 의 wait_after_ms not None 필수 "
                    f"(idle_boundary_ms 초과 gap → PR-19c 충전).",
                )

        self.assert_true(
            sidecar_count >= 1,
            f"[fixture] sidecar .expected.json 최소 1개 존재 필수. 실제: {sidecar_count}",
        )
