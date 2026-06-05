// Playwright-Electron fixture — desktop_v3 빌드본을 외부에서 기동한다.
// 하네스는 desktop_v3 의 electron 바이너리와 out/main/index.js 를 그대로 띄울 뿐,
// desktop_v3 코드/설정에 끼어들지 않는다(독립 동작 원칙).

import { test as base, expect, type ElectronApplication, type Page } from "@playwright/test";
import { _electron as electron } from "playwright";
import {
  DESKTOP_MAIN_ENTRY,
  DESKTOP_V3_DIR,
  REPO_ROOT,
  VENV_PYTHON,
  electronBinary,
} from "../../src/paths";

interface OhdoFixtures {
  electronApp: ElectronApplication;
  window: Page;
}

export const test = base.extend<OhdoFixtures>({
  electronApp: async ({}, use) => {
    const app = await electron.launch({
      executablePath: electronBinary(),
      args: [DESKTOP_MAIN_ENTRY],
      cwd: DESKTOP_V3_DIR,
      // 빌드본 main 이 .venv python 으로 api_server 브리지를 띄우도록 핀.
      env: {
        ...process.env,
        OHDO_PYTHON: VENV_PYTHON,
        OHDO_PROJECT_ROOT: REPO_ROOT,
      } as Record<string, string>,
    });
    await use(app);
    await app.close();
  },

  window: async ({ electronApp }, use) => {
    const win = await electronApp.firstWindow();
    await win.waitForLoadState("domcontentloaded");
    await use(win);
  },
});

export { expect };
