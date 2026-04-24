import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { SignOutButton } from "@/components/sign-out-button";

export default async function DashboardPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/sign-in");
  }

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

      <section className="max-w-5xl mx-auto px-6 py-10 space-y-4">
        <h2 className="text-xl font-semibold">환영합니다</h2>
        <p className="text-sm text-gray-600">
          이 페이지는 M3.1.2 기본 shell 입니다. M3.1.3 에서 실행 목록이 여기에 표시됩니다.
        </p>

        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div className="rounded-md border border-gray-200 bg-white p-4">
            <dt className="text-xs text-gray-500">user_id</dt>
            <dd className="mt-1 text-sm font-mono break-all">{user.id}</dd>
          </div>
          <div className="rounded-md border border-gray-200 bg-white p-4">
            <dt className="text-xs text-gray-500">이메일</dt>
            <dd className="mt-1 text-sm">{user.email}</dd>
          </div>
          <div className="rounded-md border border-gray-200 bg-white p-4">
            <dt className="text-xs text-gray-500">계정 생성일</dt>
            <dd className="mt-1 text-sm">
              {new Date(user.created_at).toLocaleString("ko-KR")}
            </dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
