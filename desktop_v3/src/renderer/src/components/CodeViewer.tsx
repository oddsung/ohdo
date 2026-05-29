// SPDX-License-Identifier: AGPL-3.0-or-later
// Monaco 기반 코드 뷰어/편집기 (handoff §40 #2) — 선택된 step 의 generated_code 표시.
// "편집" 토글 시 읽기 전용 해제 → 저장(PUT update_step) → 세션 invalidate.
import { useEffect, useState } from "react";
import Editor from "@monaco-editor/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Save, X } from "lucide-react";
import { updateStepCode } from "@/api/client";
import { toast } from "@/store/toastStore";
import { Button } from "@/components/ui/button";

interface CodeViewerProps {
  sessionId: string;
  stepId: number | null;
  code: string;
  title?: string;
}

export function CodeViewer({ sessionId, stepId, code, title }: CodeViewerProps) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(code);

  // step 전환 / 외부 코드 변경 시 편집 상태 리셋 (편집 중 잘못된 step 의 코드 저장 방지).
  useEffect(() => {
    setEditing(false);
    setDraft(code);
  }, [code, stepId]);

  const saveMut = useMutation({
    mutationFn: () => updateStepCode(sessionId, stepId as number, draft),
    onSuccess: () => {
      setEditing(false);
      toast.success("코드 저장됨");
      qc.invalidateQueries({ queryKey: ["session", sessionId] });
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (e) => toast.error(`저장 실패: ${(e as Error).message}`),
  });

  const canEdit = stepId != null && !!code;

  return (
    <div className="flex h-full flex-col bg-discord-rail">
      <header className="flex h-9 items-center justify-between border-b border-black/30 px-3 text-xs text-discord-muted">
        <span>
          {title ?? "코드"} · {editing ? "편집 중" : "읽기 전용"}
        </span>
        {canEdit && (
          <div className="flex items-center gap-1">
            {editing ? (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  className="h-6 px-2 text-xs"
                  disabled={saveMut.isPending}
                  onClick={() => saveMut.mutate()}
                >
                  <Save className="mr-1 h-3 w-3" />
                  {saveMut.isPending ? "저장 중…" : "저장"}
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-6 w-6"
                  title="취소"
                  onClick={() => {
                    setEditing(false);
                    setDraft(code);
                  }}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-2 text-xs"
                onClick={() => setEditing(true)}
              >
                <Pencil className="mr-1 h-3 w-3" /> 편집
              </Button>
            )}
          </div>
        )}
      </header>
      {saveMut.isError && (
        <div className="bg-red-950/30 px-3 py-1 text-xs text-red-300">
          저장 실패: {(saveMut.error as Error).message}
        </div>
      )}
      <div className="flex-1">
        {code ? (
          <Editor
            height="100%"
            defaultLanguage="python"
            theme="vs-dark"
            value={editing ? draft : code}
            path={`step-${stepId}`}
            onChange={(v) => {
              if (editing) setDraft(v ?? "");
            }}
            options={{
              readOnly: !editing,
              fontSize: 13,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              lineNumbers: "on",
              renderWhitespace: "none",
              automaticLayout: true,
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-discord-muted">
            코드가 있는 step 을 선택하세요.
          </div>
        )}
      </div>
    </div>
  );
}
