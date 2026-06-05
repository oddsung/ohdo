// 타임스탬프 콘솔 + 파일 로거. 한 실행(run)당 runs/<runId>/loop.log 에 누적.

import { appendFileSync, mkdirSync } from "fs";
import { join } from "path";
import { RUNS_DIR } from "./paths";

type Level = "info" | "warn" | "error" | "step";

const ICON: Record<Level, string> = {
  info: "ℹ️ ",
  warn: "⚠️ ",
  error: "🚨",
  step: "🎯",
};

export class Logger {
  private logFile: string | null = null;

  constructor(runId?: string) {
    if (runId) {
      const dir = join(RUNS_DIR, runId);
      mkdirSync(dir, { recursive: true });
      this.logFile = join(dir, "loop.log");
    }
  }

  private ts(): string {
    // Date.now 는 환경상 허용. 로컬 시간 HH:MM:SS.mmm.
    const d = new Date();
    const p = (n: number, w = 2) => String(n).padStart(w, "0");
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
  }

  private emit(level: Level, msg: string): void {
    const line = `[${this.ts()}] ${ICON[level]} ${msg}`;
    if (level === "error") process.stderr.write(line + "\n");
    else process.stdout.write(line + "\n");
    if (this.logFile) {
      try {
        appendFileSync(this.logFile, line + "\n");
      } catch {
        /* 로그 파일 쓰기 실패는 무시 */
      }
    }
  }

  info(msg: string): void {
    this.emit("info", msg);
  }
  warn(msg: string): void {
    this.emit("warn", msg);
  }
  error(msg: string): void {
    this.emit("error", msg);
  }
  step(msg: string): void {
    this.emit("step", `── ${msg} ──`);
  }
}
