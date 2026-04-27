import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { listExecutionsServer } from "@/lib/executions";
import { ExecutionsList } from "@/components/executions-list";
import { SignOutButton } from "@/components/sign-out-button";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/sign-in");
  }

  const initial = await listExecutionsServer({ limit: 20, offset: 0 });

  return (
    <main className="min-h-screen">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold">ohdo.ai</h1>
            <span className="text-xs text-gray-400">dashboard</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-700">{user.email}</span>
            <SignOutButton />
          </div>
        </div>
      </header>

      <section className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">실행 기록</h2>
          <span className="text-xs text-gray-400">최신 실행이 위에 표시</span>
        </div>

        <ExecutionsList initialItems={initial?.items ?? []} />
      </section>
    </main>
  );
}
