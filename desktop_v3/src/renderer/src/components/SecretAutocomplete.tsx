// SPDX-License-Identifier: AGPL-3.0-or-later
// 시크릿 @자동완성 입력창 (handoff §62, 백로그 #21b) — v2 secret_insert_popup 의 v3 등가.
// 기존 Textarea 를 감싸 입력 중 `@<prefix>` 토큰을 감지하면 시크릿 라벨 드롭다운을 띄우고,
// 선택 시 `{{secret:label}}` placeholder 로 치환한다. core 무관(프론트 — /secrets 목록 재사용).
// placeholder 는 generate 시 core 가 vault 값으로 해결(get_secret 패턴) — 평문 노출 없음.
import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";
import { fetchSecrets } from "@/api/client";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
}

/** 커서 직전의 `@<prefix>` 토큰을 찾는다 (v2 find_at_trigger 등가).
 *  `@` 는 줄 시작 또는 공백 뒤에 와야 하고, 뒤따르는 문자는 [a-z0-9_]* 만 허용. */
function findAtTrigger(text: string, caret: number): { at: number; prefix: string } | null {
  const before = text.slice(0, caret);
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  if (at > 0 && !/\s/.test(before[at - 1])) return null; // @ 앞은 공백/시작
  const prefix = before.slice(at + 1);
  if (!/^[a-z0-9_]*$/.test(prefix)) return null; // 공백/특수문자 들어오면 토큰 종료
  return { at, prefix };
}

export function SecretAutocomplete({ value, onChange, onSubmit, disabled, placeholder }: Props) {
  const { t } = useTranslation();
  const taRef = useRef<HTMLTextAreaElement>(null);
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [prefix, setPrefix] = useState("");
  const [atPos, setAtPos] = useState(0);
  const [active, setActive] = useState(0);

  // 시크릿 라벨 목록 — 드롭다운 열릴 때만 조회(값은 안 옴).
  const { data } = useQuery({ queryKey: ["secrets"], queryFn: fetchSecrets, enabled: open });
  const labels = (data?.labels ?? []).filter((l) => l.startsWith(prefix));

  // 입력/커서 변경 시 @ 트리거 재평가.
  const reevaluate = () => {
    const ta = taRef.current;
    if (!ta) return;
    const trig = findAtTrigger(ta.value, ta.selectionStart ?? ta.value.length);
    if (trig) {
      setAtPos(trig.at);
      setPrefix(trig.prefix);
      setOpen(true);
      setActive(0);
    } else {
      setOpen(false);
    }
  };

  useEffect(() => {
    if (open) setActive((a) => Math.min(a, Math.max(labels.length - 1, 0)));
  }, [labels.length, open]);

  const insertLabel = (label: string) => {
    const ta = taRef.current;
    const caret = ta?.selectionStart ?? value.length;
    const placeholderText = `{{secret:${label}}}`;
    const next = value.slice(0, atPos) + placeholderText + value.slice(caret);
    onChange(next);
    setOpen(false);
    // 삽입 위치 뒤로 커서 이동.
    requestAnimationFrame(() => {
      const pos = atPos + placeholderText.length;
      if (taRef.current) {
        taRef.current.focus();
        taRef.current.setSelectionRange(pos, pos);
      }
    });
  };

  return (
    <div className="relative flex-1">
      {open && labels.length > 0 && (
        <ul
          id={listId}
          className="absolute bottom-full left-0 z-20 mb-1 max-h-44 w-full overflow-y-auto rounded-md border border-zinc-700 bg-zinc-950 py-1 shadow-xl"
        >
          {labels.map((l, i) => (
            <li key={l}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault(); // textarea blur 방지
                  insertLabel(l);
                }}
                onMouseEnter={() => setActive(i)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm ${
                  i === active ? "bg-indigo-600/30 text-zinc-100" : "text-zinc-300 hover:bg-zinc-800/60"
                }`}
              >
                <KeyRound className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                <span className="flex-1 truncate">{l}</span>
                <code className="text-[11px] text-zinc-600">{`{{secret:${l}}}`}</code>
              </button>
            </li>
          ))}
        </ul>
      )}
      <Textarea
        ref={taRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          // onChange 후 DOM 값 기준 재평가 (setState 비동기라 e.target 사용).
          requestAnimationFrame(reevaluate);
        }}
        onClick={reevaluate}
        onKeyUp={(e) => {
          // 방향키 등으로 커서만 움직일 때도 재평가 (Arrow/Enter 는 onKeyDown 에서 선처리).
          if (!["ArrowUp", "ArrowDown", "Enter", "Escape"].includes(e.key)) reevaluate();
        }}
        onKeyDown={(e) => {
          if (open && labels.length > 0) {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, labels.length - 1));
              return;
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
              return;
            }
            if (e.key === "Enter" || e.key === "Tab") {
              e.preventDefault();
              insertLabel(labels[active]);
              return;
            }
            if (e.key === "Escape") {
              e.preventDefault();
              setOpen(false);
              return;
            }
          }
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
          }
        }}
        placeholder={placeholder}
        disabled={disabled}
        rows={2}
        aria-label={t("chat.placeholder")}
      />
    </div>
  );
}
