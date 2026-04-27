import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import {
  getExecutionServer,
  listLogsServer,
  listCapturesServer,
} from "@/lib/executions";
import { CancelButton } from "@/components/cancel-button";
import { CapturesGrid } from "@/components/captures-grid";
import { ExecutionStatusBadge } from "@/components/execution-status-badge";
import { ExecutionLogsTail } from "@/components/execution-logs-tail";
import { SignOutButton } from "@/components/sign-out-button";
import { formatDateTime, formatDuration } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function ExecutionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await getCurrentUser();
  if (!user) redirect("/sign-in");

  const { id } = await params;
  const exec = await getExecutionServer(id);
  if (!exec) notFound();

  const [logs, captures] = await Promise.all([
    listLogsServer(id, { limit: 200, offset: 0 }),
    listCapturesServer(id),
  ]);

  return (
    <main className="min-h-screen">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-lg font-semibold hover:underline">
              ohdo.ai
            </Link>
            <span className="text-xs text-gray-400">execution</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-700">{user.email}</span>
            <SignOutButton />
          </div>
        </div>
      </header>

      <section className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1 min-w-0">
            <div className="flex items-center gap-3">
              <ExecutionStatusBadge status={exec.status} />
              <code className="text-sm font-mono text-gray-700 break-all">
                {exec.execution_id}
              </code>
            </div>
            {exec.error_summary ? (
              <p className="text-sm text-red-700">{exec.error_summary}</p>
            ) : null}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <CancelButton
              executionId={exec.execution_id}
              initialStatus={exec.status}
            />
            <Link
              href="/dashboard"
              className="text-sm text-gray-600 hover:underline"
            >
              ← 목록
            </Link>
          </div>
        </div>

        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <Card label="총 스텝" value={exec.total_steps ?? "—"} />
          <Card label="실행됨 / 성공 / 실패" value={
            `${exec.executed_steps ?? "—"} / ${exec.successful_steps ?? "—"} / ${exec.failed_steps ?? "—"}`
          } />
          <Card label="총 소요" value={formatDuration(exec.total_time_ms)} />
          <Card label="시작" value={formatDateTime(exec.started_at)} />
          <Card label="종료" value={formatDateTime(exec.finished_at)} />
          <Card label="from / to step" value={
            `${exec.from_step ?? "처음"} / ${exec.to_step ?? "끝"}`
          } />
        </dl>

        <div className="space-y-3">
          <h3 className="text-sm font-medium text-gray-700">로그</h3>
          <ExecutionLogsTail
            executionId={exec.execution_id}
            initialStatus={exec.status}
            initialItems={logs?.items ?? []}
          />
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-medium text-gray-700">
            캡처 ({captures?.items.length ?? 0})
          </h3>
          <CapturesGrid
            executionId={exec.execution_id}
            initialStatus={exec.status}
            initialItems={captures?.items ?? []}
          />
          <p className="text-xs text-gray-400">
            카드 클릭 시 새 탭에서 원본 이미지 보기. 진행 중 실행은 자동 새로고침됩니다.
          </p>
        </div>
      </section>
    </main>
  );
}

function Card({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-4">
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="mt-1 text-sm text-gray-900 break-all">{value}</dd>
    </div>
  );
}
