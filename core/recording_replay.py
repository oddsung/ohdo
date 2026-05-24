# SPDX-License-Identifier: AGPL-3.0-or-later
"""[PR-19m 2026-05-24] raw events JSONL 사후 재변환 helper + CLI.

handoff §33 P9 — PR-19i 가 commit_recording 시점에 ``data/sessions/<id>/
raw_events_<rec_id>.jsonl`` 로 raw events 를 보존함. 이 모듈은 보존된 JSONL
을 읽어 다시 transform 으로 흘림 → 옵션 비교 / 디버깅 / 잘못 commit 된
세션 복구 / 미래 UI replay 백엔드.

사용:

- Pure helper (UI 재사용용)::

    from core.recording_replay import load_raw_events_from_jsonl, replay_jsonl
    steps = replay_jsonl(Path("data/sessions/.../raw_events_xxx.jsonl"))

- CLI::

    python -m core.recording_replay <jsonl_path> [--idle-boundary-ms N]
        [--drop-empty] [--no-group-keys] [--out result.json]

"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from core.recorder_models import RawEvent, RecordingSession, TransformOptions
from core.recorder_transform import transform
from core.session_manager import Step


def load_raw_events_from_jsonl(jsonl_path: Path) -> list[RawEvent]:
    """JSONL 한 줄당 한 RawEvent 로 deserialize. 빈 줄 skip.

    pydantic ``RawEvent.model_validate_json`` 으로 strict 파싱 — 손상된 라인은
    ``ValidationError`` 발생 (sub-helper 가 try/except 로 감쌀 수 있음).
    """
    events: list[RawEvent] = []
    text = jsonl_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(RawEvent.model_validate_json(line))
    return events


def replay_jsonl(
    jsonl_path: Path,
    opts: Optional[TransformOptions] = None,
    self_window_titles: Optional[list[str]] = None,
) -> list[Step]:
    """JSONL → RawEvent → RecordingSession → transform → Step 리스트.

    ``RecordingSession.id`` 는 파일명 (``raw_events_<id>.jsonl``) 에서 추출,
    ``started_at`` / ``stopped_at`` 은 첫/마지막 event 의 ts 로 추정 — transform
    이 metadata 를 보지 않으므로 정확도는 무관 (replay 출력에 영향 X).

    빈 파일 / 0 event → 빈 리스트.
    """
    events = load_raw_events_from_jsonl(jsonl_path)
    if not events:
        return []
    rec_id = jsonl_path.stem
    if rec_id.startswith("raw_events_"):
        rec_id = rec_id[len("raw_events_") :]
    rec = RecordingSession(
        id=rec_id,
        started_at=events[0].ts,
        stopped_at=events[-1].ts,
        events=events,
    )
    return transform(rec, opts=opts, self_window_titles=self_window_titles)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core.recording_replay",
        description="raw events JSONL 사후 재변환 (PR-19m, handoff §34).",
    )
    parser.add_argument(
        "jsonl_path",
        type=Path,
        help="raw_events_<rec_id>.jsonl 경로 (PR-19i 가 commit 시점에 저장)",
    )
    parser.add_argument(
        "--idle-boundary-ms",
        type=int,
        default=TransformOptions().idle_boundary_ms,
        help="idle 휴지 step 경계 (ms). 기본 3000",
    )
    parser.add_argument(
        "--no-group-keys",
        action="store_true",
        help="group_consecutive_keys 비활성화 (키 한 개씩 별개 step)",
    )
    parser.add_argument(
        "--drop-empty",
        action="store_true",
        help="drop_empty_space_clicks 활성화 (element_meta=None click 모두 drop)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="결과 step 리스트 JSON 저장 경로. 없으면 stdout 요약 (step 번호 + user_request)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry — 0 성공 / 1 파일 없음 / 2 파싱 실패."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    jsonl_path: Path = args.jsonl_path
    if not jsonl_path.exists():
        print(f"[recording_replay] 파일 없음: {jsonl_path}", file=sys.stderr)
        return 1

    opts = TransformOptions(
        idle_boundary_ms=args.idle_boundary_ms,
        group_consecutive_keys=not args.no_group_keys,
        drop_empty_space_clicks=args.drop_empty,
    )

    try:
        steps = replay_jsonl(jsonl_path, opts=opts)
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"[recording_replay] 파싱/변환 실패: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps([asdict(s) for s in steps], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[recording_replay] {len(steps)} step → {args.out}")
    else:
        print(f"[recording_replay] {jsonl_path.name} → {len(steps)} step")
        for i, s in enumerate(steps, start=1):
            req = s.user_request or "(no request)"
            print(f"  [{i:02d}] {req}")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    sys.exit(main())
