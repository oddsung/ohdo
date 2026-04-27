import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { NewExecutionForm } from "@/components/new-execution-form";
import { SignOutButton } from "@/components/sign-out-button";

export const dynamic = "force-dynamic";

export default async function NewExecutionPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/sign-in");

  return (
    <main className="min-h-screen">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="text-lg font-semibold hover:underline"
            >
              ohdo.ai
            </Link>
            <span className="text-xs text-gray-400">새 실행</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-700">{user.email}</span>
            <SignOutButton />
          </div>
        </div>
      </header>

      <section className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">새 실행 만들기</h2>
          <Link
            href="/dashboard"
            className="text-sm text-gray-600 hover:underline"
          >
            ← 대시보드
          </Link>
        </div>
        <p className="text-sm text-gray-600">
          가장 최근에 활동한 agent 가 자동 선택됩니다.
        </p>
        <NewExecutionForm />
      </section>
    </main>
  );
}
