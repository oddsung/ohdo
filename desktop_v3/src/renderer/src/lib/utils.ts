// SPDX-License-Identifier: AGPL-3.0-or-later
// shadcn/ui 표준 cn() 헬퍼 — clsx + tailwind-merge.
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
