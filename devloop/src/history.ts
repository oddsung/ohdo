// 실행 이력 — runs/loop-history.json 에 RunRecord 를 누적, runs/<runId>/run.json 에 단건 저장.

import { mkdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { RUNS_DIR } from "./paths";
import type { IterationRecord, RunRecord } from "./types";

const HISTORY_FILE = join(RUNS_DIR, "loop-history.json");

export class History {
  private record: RunRecord;
  private runDir: string;

  constructor(init: RunRecord) {
    this.record = init;
    this.runDir = join(RUNS_DIR, init.runId);
    mkdirSync(this.runDir, { recursive: true });
    this.flush();
  }

  addIteration(it: IterationRecord): void {
    this.record.iterations.push(it);
    if (typeof it.claude?.costUsd === "number") {
      this.record.totalCostUsd = (this.record.totalCostUsd ?? 0) + it.claude.costUsd;
    }
    this.flush();
  }

  finish(outcome: RunRecord["outcome"], finishedAt: string): void {
    this.record.outcome = outcome;
    this.record.finishedAt = finishedAt;
    this.flush();
    this.appendToGlobal();
  }

  get current(): RunRecord {
    return this.record;
  }

  private flush(): void {
    writeFileSync(join(this.runDir, "run.json"), JSON.stringify(this.record, null, 2));
  }

  private appendToGlobal(): void {
    let all: RunRecord[] = [];
    try {
      all = JSON.parse(readFileSync(HISTORY_FILE, "utf8")) as RunRecord[];
      if (!Array.isArray(all)) all = [];
    } catch {
      all = [];
    }
    // 같은 runId 가 이미 있으면 교체.
    const idx = all.findIndex((r) => r.runId === this.record.runId);
    if (idx >= 0) all[idx] = this.record;
    else all.push(this.record);
    mkdirSync(RUNS_DIR, { recursive: true });
    writeFileSync(HISTORY_FILE, JSON.stringify(all, null, 2));
  }
}
