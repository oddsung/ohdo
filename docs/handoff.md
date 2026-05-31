# Claude Code 세션 인계 문서 (Handoff)

> **사용법**: 새 Claude 세션 시작 시 첫 입력으로 "이 파일 읽고 이어서 작업" 하라고 하세요.
> 이 문서는 Claude 의 auto-memory 가 컴퓨터 간 옮겨지지 않아 새 세션에서 컨텍스트 빠르게 복원하기 위한 용도입니다.
> 마지막 업데이트: 2026-05-31 (서른다섯 번째 작업 — 자세한 변경은 §5 변경 이력 + §11~§72 인계 노트 참조). baseline: **core 227/227 + scenarios 73/73 + recording_fixtures 2/2 그린** (§72 신규 — **picker 요소 셀렉터 결정적 강제 = 탭닫기 오클릭 진짜 해결**: 사용자 반론(엔진 교체 불필요, v2 검증됨, step2≡step4)이 정당. 재조사로 **엔진 무능 아님** 확정 — 동일 세션 STEP2("+") 는 `auto_id="AddButton"` 정확 사용·성공, STEP4("x") 는 `control_type="Document"`·실패. 차이는 프롬프트 신호-잡음: STEP4 프롬프트에 Document 31회 vs CloseButton 1회(직전 step 들이 Document 클릭+manually_edited "반드시 유지" → AI 가 다수 패턴 추종). fix(사용자 선택=결정적 셀렉터, api_server only/core 0줄): `selector_enforce.py` 가 생성 후 그 step 의 `element=win.child_window(...)` 를 픽 요소 auto_id/title 로 교정(마커영역 한정, guard·idempotent), `generate.py` WS 가 호출+step_code 재추출. test_232 +1(core **227/227**), 프론트 무변경. **사용자: 브리지 재시작 후 STEP4 재생성 → 탭 닫힘.**) (§71 신규 — **step delta 추출 dangling-block 버그 fix(core, 첫 core 변경·사용자 승인) + 탭닫기 미동작=AI 타겟팅**: 세션 ba7f4dc8 탭닫기 미동작 조사. ① **core 버그**: `extract_code_delta` 가 prev 중복 라인 제거 시 제어 헤더는 남기고 본문만 제거 → 연속 클릭 step 의 walk-up/click 본문이 동일해 dangling block → SyntaxError(저장 step_code 깨짐). fix: block-aware(유지된 헤더 블록 본문은 보존, module-level 중복만 제거). test_231 +1(core **226/226**), v2 공유 무회귀. **단 이게 run-time 원인은 아님** — run-time `extract_step_delta_code` 는 마커 추출+컴파일검증으로 깨진 step_code 우회. ② **실제 탭닫기 미동작 원인**: AI 가 picker 로 고른 "x"(이름=탭닫기, auto_id=CloseButton) + §68 지시 완벽 전달에도 무시하고 `control_type="Document"` 클릭 코드 생성 → 텍스트영역 클릭, 탭 안 닫힘 = **엔진 준수 한계(미해결)**. 엔진 교체/수동편집/결정적 codegen 논의 필요. **브리지 재시작 필요.**) (§70 신규 — **캡처에 picker 붉은 오버레이 찍힘**: §69 후 이미지는 보이나 "+" 캡처에 빨간 테두리. 원인은 §66 타이밍 — `_capture_element_image` 의 mss grab 시점에 Electron 붉은 박스 오버레이가 아직 안 닫힘(렌더러가 /pick/click 응답 후 닫음). fix(api_server only, core 0줄): pick_pump 가 `get_overlay_hwnd()` 노출(finally 클리어 제거) + `routes/pick._hide_pick_overlay()` 가 grab 직전 오버레이를 `ShowWindow(SW_HIDE)`(cross-process)+0.12s 재합성 대기 후 grab(복원 안 함, 미등록 graceful). test_230 +1(core **225/225**), ruff 그린, 프론트 무변경. **사용자: Python 브리지 재시작 후 재픽 — 빨간 테두리 없이 "+"만 찍히는지 확인.**) (§69 신규 — **캡처 이미지 "깨진 표시" = CSP img-src 에 blob: 누락**: §68 재빌드 후 썸네일 박스는 정상이나 이미지가 broken-image 아이콘. 원인은 순수 CSP — `index.html` 의 `img-src 'self' data:` 에 blob: 가 없어 CaptureThumb 의 object URL(`blob:`) `<img>` 가 차단(서빙 엔드포인트·CORS·파일은 TestClient 로 정상 검증). fix: `img-src 'self' data: blob:` 한 줄(코드 무수정). build 그린·번들 반영 확인, core 224/224 불변. **사용자 재빌드/새로고침 후 "+" 이미지 표시 확인**. P1 오클릭은 §68 AI 준수 이슈로 별개.) (§68 신규 — **캡처 썸네일 고정크기 + 셀렉터 단순화 방지**(§67 재빌드 후 사용자 실측 ba7f4dc8): ① 캡처 이미지가 "검은 세로줄"로만 = `CaptureThumb` 너비 미고정 버그 → `h-20 w-28` 고정 박스 + img `object-contain fill`(작은 "+"도 업스케일·표시영역 일정). ② "+" 대신 엉뚱 Button 클릭 = **§66/§67 버그 아님** — 프롬프트 로그 실측상 §67 풍부한 컨텍스트(auto_id=AddButton + title 템플릿) 정상 주입됐으나 **AI(agy)가 템플릿 무시하고 generic `child_window(control_type="Button", found_index=0)` 로 단순화** → 첫 Button 오클릭(=AI 준수 문제, 근본은 prompts.json generic vs specific 템플릿 충돌=core/v2 공유라 사용자 결정 필요). v3-only 완화: `_build_element_context` 말미에 anti-pattern 금지 지시 추가(best-effort). test_229 확장(core **224/224**), tsc/build/ruff 그린, core 0줄. **사용자: 재빌드 후 재픽·재생성 — ②가 여전히 generic 이면 prompts.json 강화/엔진 논의.**) (§67 신규 — **pick race fix + 풍부한 element_context**: 사용자 실측(메모장 "+" pick→"클릭하기")에서 ① 요소 이미지 미표시 ② AI 가 "+" 무시하고 Document 클릭. **워크플로우 4에이전트로 단일 근본원인 규명**: `ChatPanel.send()` 가 `mutate()` 직후 동기 `clearPending()` 하는데 React Query 는 mutationFn 을 다음 microtask 에 실행 → mutationFn 이 pending 을 읽을 땐 이미 null → element_context=null(→AI 가 가이드 폴백 Document 복제) + imagePath=undefined(→attach 미호출, captures=[]). **Fix #1**: send() 가 mutate 시점에 pending/images 스냅샷 떠 mutate 인자로 전달(race 제거). **Fix #2(v2 동등)**: pick 이 한 줄 라벨 대신 core `get_element_info_text` 로 "## 선택된 UI 요소" 섹션+코드템플릿(가이드 #17 이 참조하는)을 element_context 로 반환(rect 리스트→dict 정규화+guard, core 0줄). test_229 +1(core **224/224**), tsc/build/ruff 그린. **사용자: 앱 재빌드/재시작(브리지 포함) 후 step2 재생성 필요.**) (§66 신규 — **step 카드 UX 3건**(사용자 보고): ① AI 설명 기본 숨김(step 선택 시만) ② 👤/🤖 컬러 이모지 → lucide User/Bot 단색 아이콘(Library/Initial 통일) [①② 커밋 e4dc28f] ③ **선택 요소 스크린샷 캡처+표시**: pick 은 원래 메타만 잡고 이미지 미캡처였음 → `/pick/click` 가 session_id 받으면 요소 rect 를 `capture_pump` 로 grab→세션 captures 저장(`image` 반환), 생성된 step 에 **표시 전용**(AI 무전송)으로 `POST .../steps/{id}/capture` attach, 새 `GET .../captures/{file}` 서빙(인증 fetch→blob), `CaptureThumb` 고정높이(h-20)+object-contain 으로 카드 높이 안정. §60 카메라 캡처도 같은 captures 라 함께 표시됨. core 0줄(`get_captures_dir`/`update_step` 공개 API 재사용), test_228 +1(core **223/223**), tsc/build/ruff 그린. 좌측 레일 폭 72→56px 축소(커밋 ff0db59)도 동일 세션.) (§65 신규 — **설정 다이얼로그 한글화**: 사용자 보고("설정 메뉴에 한글화 안 된 항목 많다") fix. §56 제네릭 설정 에디터가 `default_settings.json` 영문 원본 키를 라벨로 그대로 노출하던 것 → ko/en 카탈로그에 `settingsKeys` 맵(섹션+엔진+전 필드) 신규 + SettingsDialog 가 `labelFor(k)` 로 라벨 렌더(원본 키는 tooltip 보존, 미등록 키 graceful 폴백). desktop_v3 전용, core 0줄, tsc/build 그린.) (§64 신규 — **Phase E 배포 freeze 실측/de-risk**: §46 이 미룬 freeze 를 이 개발 환경(Windows, GUI 불가지만 freeze 는 CLI)에서 실제로 빌드·부팅·동봉까지 돌려 막힘 제거. core/PySide6/ui_v2 **0줄**. ① `pyinstaller>=6.0` 을 `build` extra 로 선언(문서의 `uv run pyinstaller` 가 미선언이라 실패하던 것) ② spec 죽은 hidden import `pywinpty`(배포명, import 모듈은 `winpty`) 제거 ③ **§63 기커밋 tsc 버그** 발견·수정 — `ChatPanel` 이 옛 `stopCommit` 구조분해(rename 누락), electron-vite=esbuild 가 타입 stripping 해 §63 "tsc 그린"이 오claim → `stopReview` 로 수정(녹화중단 버튼 런타임 throw 버그) ④ **packaged data-dir** = frozen 기본값이 번들 내부(`_internal/data`, 업데이트 시 세션 소실/쓰기불가 위험) → Electron `bridgeCommand` 가 `--data-dir %APPDATA%/ohdo/data` 전달(브리지 기지원, **TS만**) ⑤ `npm install` 로 §46 이 안 돌린 lockfile 동기화. **검증**: freeze exit 0 + frozen `ohdo-bridge.exe` 단독부팅 /health·/sessions·/environment(core 스캐너 frozen 실동작) + `electron-builder --dir` exit 0 동봉 확인(`resources/pybridge/ohdo-bridge.exe`) + tsc/electron-vite/core 222/222/ruff 그린. **신규 `docs/BUILD.md` 런북**(`.venv` 강조, freeze→복사→NSIS, winCodeSign symlink 트러블슈팅) + README 빌드 섹션. **남은: NSIS 설치본 GUI 실측(사용자 머신) + config 영속성(번들 내부 read, `--config-dir` 후속) + 코드서명**.) (§63 신규 — v3 패리티 백로그 P1 #22 녹화 review 다이얼로그: 녹화 종료를 "즉시 commit"에서 "검토 후 commit"으로. core 가 이미 stop_recording(변환된 step 반환)/commit_recording(세션 커밋)로 분리돼 있어 core 0줄. RecordingController stop("preview")(stop+변환, 커밋X)/commit_steps + POST /recording/stop_preview·/recording/commit 신규. 프론트 recordStore stopReview/commitReview/discardReview, RecordingReviewDialog(신규 — step 코드/설명 편집·삭제·순서변경 후 확정), Step 재구성은 알려진 필드만(메타 round-trip). test_227 +1(core 222/222). **#13/#19/#21/#22 모두 완료 — P1+ 백로그 소진.**) (§62 신규 — v3 패리티 백로그 P1 #21b 시크릿 @자동완성 + 평문 감지: ChatPanel 입력창을 SecretAutocomplete(신규)로 교체 — `@<prefix>` 입력 시 시크릿 라벨 드롭다운(↑↓/Enter/Tab/Esc) → 선택 시 `{{secret:label}}` placeholder 삽입(core 가 generate 시 vault 값 해결, 평문 노출 X). 전송 시 `POST /secrets/scan`(secrets_detector.detect 위임, **값 미노출**=미리보기만)로 평문 시크릿 감지 → 발견 시 마스킹 권고 confirm. core 0줄. test_226 확장(scan 라우트+무노출 가드). #21 완료. 남은: #22 녹화 review.) (§61 신규 — v3 패리티 백로그 P1 #21a 시크릿 볼트 CRUD: core ADR0003 `AppService.secrets_vault`(KeyringVault, OS keyring) 를 GET/POST/DELETE `/secrets` 로 노출(core 0줄). **값은 절대 renderer 로 반환 안 함**(label 목록만) — 실행 주입은 기존 push_secrets 배선 재사용. 신규 routes/secrets.py + SecretsDialog(레일 KeyRound 버튼 + 팔레트, label 패턴검증/마스킹입력/등록·삭제) + i18n secrets.*. test_226 +1(core 221/221, set→list→delete 라운드트립 + 값 미노출 가드). 남은: #21b @자동완성, #22 녹화 review.) (§60 신규 — v3 패리티 백로그 P1 #13 첨부 이미지(스크린 영역 캡처): 드래그 영역 캡처 오버레이(capture_overlay.html/ts, 클릭통과 아님) → main 이 DIP→물리픽셀 변환 → POST /capture/region → mss grab → 세션 captures 저장 → generate(images=[...])로 전달. core 0줄(generate_step images 파라미터 + 공개 get_captures_dir 재사용). 신규 api_server/capture_pump.py + routes/capture.py, GenerateRequest.images + WS/POST generate 배선, ChatPanel 카메라 버튼 + 이미지 chip. test_225 +1(core 220/220), tsc/build/ruff 그린.) (§59 신규 — 좌측 서버 레일(oh 로고 세로영역) 회수: 자리표시자였던 레일을 #2 "전역 네비/유틸 바"로 활용 — 로고=홈(세션 선택 해제), 하단에 도움말/환경점검/설정/언어/테마 아이콘(기존 사이드바 푸터에 밀집했던 것)을 이동. 사이드바 푸터는 브리지 상태(HealthDot)만 남김. 신규 `ServerRail.tsx`(App 인라인에서 승격), i18n `sidebar.home` 추가. 워크스페이스 도입 시 로고 아래 워크스페이스 아이콘 추가로 #1(프로젝트 전환기) 승격 예정 — 그래서 레일 제거 대신 Discord 레이아웃 유지. 순수 프론트(core/api_server 0줄), tsc/build 그린.) (§58 신규 — v3 패리티 백로그 P1 #19 온보딩 위저드: 첫 실행 시 자동으로 뜨는 4단계 위저드(환영+언어선택 / 환경점검 / AI엔진선택 / 완료+첫 세션 생성). 순수 프론트 — 환경점검(GET /environment)·엔진전환(GET·POST /ai/*)·세션생성은 모두 기존 엔드포인트 재사용, core/api_server 0줄. localStorage `ohdo.onboarded` 플래그로 1회만 자동, 사이드바 ? 버튼 + 팔레트 "시작 안내 보기"로 재오픈. uiStore onboardingOpen + i18n onboarding.* 카탈로그. tsc/build 그린(프로젝트 lint 스크립트 없음), core 219/219 유지.) (§57 신규 — v3 패리티 백로그 P1 #17 멀티 세션 탭: uiStore openTabs[] + selectSession 이 탭 자동 추가 + closeTab(활성 닫으면 인접 전환). TabBar 컴포넌트(채팅/코드 영역 위, 탭 전환/닫기). App 레이아웃 col 래핑. 세션 삭제 시 closeTab 으로 탭 정리. 순수 프론트, core 0줄. tsc/build 그린.) (§56 신규 — v3 패리티 백로그 P1 #20 설정 화면 확장: SettingsDialog 가 AI 엔진만 노출하던 것을 ai 외 모든 top-level 섹션(image/recognition/execution/ui/output_project/logging/element_picker/...)으로 확장 — 접이식 ConfigSection + path 기반 setByPath + 문자열배열 ArrayField(쉼표편집) + bool/num/str Field 재사용. 백엔드 GET/PUT /settings 는 §47 기구현(test_218), 순수 프론트 확장. tsc/build 그린.) (§55 신규 — v3 패리티 백로그 P1 #15 프로젝트 내보내기/가져오기: routes/sessions.py 에 POST /sessions/{id}/export(export_workflow, output_dir 하위 안전 폴더명+clobber 회피) + POST /sessions/import(import_workflow, session.json 가드). core 0줄. Electron main 에 fs:pick-directory(dialog)/fs:reveal(shell) IPC + preload pickDirectory/revealPath. 프론트 사이드바 import(헤더)/export(행) 버튼 + 팔레트 명령. test_224 +1 — export→import 라운드트립.) (§54 신규 — v3 패리티 백로그 P1 #18 환경 점검: routes/environment.py 신규 (GET /environment = core 공개 get_scanner().full_scan() 위임 — Python/패키지/CLI AI 상태, AppService 미경유). core 0줄. 프론트 EnvironmentDialog (사이드바 Activity 버튼 + 팔레트 명령, on-demand 스캔 + 로딩/재검사). test_223 +1 — 라우트+scanner 공개 API+get_system_info(full_scan 미호출).) (§53 신규 — v3 패리티 백로그 P1 #14 AI 엔진 퀵스위치: routes/ai.py 신규 (GET /ai/engines = list_ai_engines 위임, POST /ai/engine = switch_ai_engine 런타임 전환 + settings.json ai.selected 영속으로 설정 다이얼로그/재시작 일관). core 0줄. 프론트 EngineSwitcher 헤더 드롭다운(녹화중 숨김). test_222 +1 — read-only/실패 경로만(실 config 무변조).) (§52 신규 — v3 패리티 백로그 P1 #12 세션 복제: core 에 duplicate 메서드가 없어 api_server 가 공개 API 조합으로 구현 — POST /sessions/{id}/duplicate(create_session + steps/workflow_metadata 깊은 복사 + save_session, 캡처/스크립트 폴더 best-effort 복사). core 0줄. 프론트 사이드바 복제 버튼 + 커맨드 팔레트 명령(locale별 (copy)/(사본) 제목). test_221 +1.) (§51 신규 — v3 패리티 백로그 P1 #16 커맨드 팔레트(Ctrl+K): CommandPalette 컴포넌트(검색+↑↓+Enter+Esc) — 새 세션/실행·중단/녹화 시작·중단/요소선택/설정/테마·언어 전환/세션 이동을 컨텍스트별 노출. useShortcuts 에 Ctrl+K(입력 포커스 무관) 추가, uiStore paletteOpen/settingsOpen lift(사이드바 기어와 공용), 기존 스토어/액션 재사용. 순수 프론트(백엔드 무관, core 0줄). tsc/build 그린.) (§50 신규 — v3 패리티 백로그 P1 잇기: #10 코드 복사 버튼(CodeViewer 헤더 Copy, navigator.clipboard, 순수 프론트) + #11 Library/Initial 블록 카드(GET /sessions/{id}/blocks → get_library_block_code/get_initial_block_code 위임, ChatPanel 상단 read-only 카드 + uiStore selectedBlock 상호배타 선택 + CodePane read-only 표시). core 0줄, test_220 +1.) (§49 신규 — element picker 풀 복원(투명 오버레이 + 실시간 붉은 박스 하이라이트, v2 동등). fix1~9 실측 루프: ⓐ hover rect dict 정규화 ⓑ F3 일시정지(메뉴 펼친 후 선택) ⓒ **마우스 정지 진짜 원인 = CallNextHookEx argtypes 미지정 → x64 lParam(포인터) OverflowError → fix9 로 해결** (fix6~8 GIL 진단은 오진) ⓓ 녹화 시작 시 메인 minimize / 코드 실행 완료 시 메인 focus. **미해결(보류)**: 작업표시줄 위 hover 박스 z-order — Shell_TrayWnd 가 SetWindowPos(HWND_TOPMOST)로도 안 덮임. core 0줄 불변, test_219 가드.) (§48 신규 — element picker 클릭 시 캡처 절충안: pick_pump.py 전역 LL 마우스 후크, POST /pick/click·/pick/cancel.) (§47 신규 — v3↔v2 기능 패리티 백로그 (서브에이전트 3개 교차조사, 격차 22항목을 (A)브리지 미노출/(B)백엔드 없음·순수UI 로 분류 + 우선순위표). (A)유형 P0 일괄 구현 착수: step 삭제/이동/삽입/재생성 + 세션 삭제/이름변경 + from 실행 버튼 + 경고상세/패키지 표시. core 0줄 불변.) (§46 신규 — Phase E 배포 셋업: electron-builder 설정 (win nsis + extraResources pybridge) + main 의 bridgeCommand() packaged/dev 분기 (app.isPackaged 시 frozen ohdo-bridge.exe spawn) + PyInstaller spec/entry (api_server+core onedir freeze, hidden-import 다수). freeze/설치 실측은 사용자 머신 (이 환경 GUI 불가). core/PySide6 0줄 수정.) (§45 신규 — Phase D i18n + 애니메이션: desktop_v3 react-i18next (신규 ko/en 카탈로그, 시스템 locale 감지 + localStorage + 사이드바 언어 토글). UI 한국어 → t()/i18n.t 전환 (UI 한국어 0, 주석만). 핵심 트랜지션 (PickOverlay fade / Toaster·LogConsole slide). core/PySide6 0줄 수정, TS 전용. tsc+build 그린.) (§44 신규 — AI 생성 진행상황 스트리밍: WS /ws/generate 가 generate_step 의 on_progress 콜백("프롬프트 구성 중"/"AI 호출 중 N자")을 실시간 전송. core generate() 토큰 스트리밍 미지원 + agy CLI(PTY) 토큰 스트리밍 불가 → 사용자 결정으로 토큰 대신 진행상황 (core 0줄 수정). ChatPanel POST→WS 전환, 로딩 영역 라이브 진행 표시. test_211 +1.) (§43 신규 — api_server 리팩토링: server.py(568줄)를 deps.py + routes/{health,sessions,steps,pick,recording,execution}.py 로 분리, server.py 는 55줄(state 셋업 + include_router)로 축소. 엔드포인트/동작 100% 동일 (13 routes parity + E2E 검증). 스키마는 server.py 에 하위호환 re-export. 기능 변화 0.) (§42 신규 — **녹화 실제 캡처 fix**: §41 의 "InputHookManager 자체 펌프 스레드" 가정이 틀렸음 — LL 훅은 SetWindowsHookEx 호출 스레드에서 메시지 펌프가 돌아야 콜백 발화. FastAPI 브리지엔 펌프 없음 → 입력 0 캡처 (사용자 실측). fix: `api_server/recording_pump.py` RecordingController 가 전용 스레드에서 start_recording(훅 설치)+PeekMessage 펌프+stop_recording(훅 해제) 수행. E2E 검증: 키입력 6회 → event_count 6 + stop_commit → step 2개 생성 확인. core/PySide6 0줄 수정.) (§41 신규 — TS UI v3 #3 잔여 = 작업 녹화 lifecycle: api_server REST (recording start/status/marker/stop_commit/cancel) + desktop_v3 녹화 버튼/구분점/이벤트 카운트 polling. recorder 의 InputHookManager 자체 pump 스레드로 브리지에서 동작. is_recording/recording_event_count 는 @property (() 호출 금지). core/PySide6 0줄 수정, test_210 +1. Monaco "Loading" CDN/CSP fix 는 §41 에 함께 기록.) (§40 신규 — TS UI v3 Phase B 확장: #1 step 실행 + live 로그 (WS /ws/execute) + #2 코드 편집·저장 (Monaco editable + PUT update_step) + #3 element picker (카운트다운 캡처 /pick) + #4 polish (토스트 + 단축키 + 다크/라이트 테마 토글). core/PySide6 0줄 수정, test_208/209 +2. 다음: 녹화 lifecycle + 사용자 GUI 실측.) (§39 신규 — TS UI v3 Phase B 1차 증분: api_server 에 GET /sessions/{id} + POST /sessions + POST /sessions/{id}/generate (AI 코드 생성, async generate_step 위임) 추가 + settings/prompts 주입. desktop_v3 에 shadcn/ui + Monaco + Discord 3-column (사이드바/채팅/코드뷰어) + AI 생성 루프 (동기 요청+로딩). core/PySide6 0줄 수정, test_207 +1. 다음: 사용자 GUI 실측 (세션 생성 -> 자연어 요청 -> 코드 화면 표시).) (§38 신규 — TS UI v3 Phase A 셋업 완료: `api_server/` FastAPI 브리지 (GET /health + /sessions, 토큰 인증, READY 마커 포트 협상) + `desktop_v3/` Electron 38 + React 19 + TS + Vite 6 + Tailwind + Zustand + TanStack Query 보일러플레이트. core/PySide6 0줄 수정, test_206 회귀 가드 +1. 다음 세션 Phase B 핵심 화면 MVP — 사용자 GUI 실측 `npm run dev` 먼저.) (§37 신규 — TS UI v3 트랙 전환 결정: Electron + React + TS + Tailwind + Zustand, 같은 repo `desktop_v3/`, Discord-like UX. 다음 세션 Phase A 셋업부터 시작. §36 hotfix series 완료 — agy ConPTY 우회 (pywinpty + cmd bat 래퍼) 로 stdout 캡처 성공, CLI AI 일반화 + Gemini→Agy rename + preset UI + test_204/205) (§34 PR-19m +1 = test_202 raw events 사후 재변환 helper + CLI; §33 PR-19l +1 = test_201 generated_code destructive 패턴; §32 PR-19k +1 = test_200 한글 IME pyperclip placeholder; §31 PR-19i +1 = test_199 raw events JSONL 저장; §30 PR-19h +1 = test_198 destructive ⚠️ badge + commit confirm; §29 PR-19c +1 = test_197 idle gap → wait_after_ms 충전; §28 PR-19j +1 = test_195 regenerate in-place fix, PR-19b +1 = test_196 빠른 double-click 감지) (PySide6 단독 `.venv` 기준 — PR-11~18 = +37 + GUI 실측 1차 fix +5 (test_182~186) + PR-19a-g +8 (test_187~194) = 144→194). **2026-05-23~24 PR-19a → PR-19g 7개 fix 모두 완료, 사용자 GUI 실측 검증 통과** — 녹화 + 입력 + 실행 흐름이 처음으로 사용자 의도대로 동작. (a) PR-19a `core/pywinauto_codegen.py` helper 추출 + recorder 통합. (b) PR-19d `Step.element_meta` 보존 + AI 재생성 path adapter (PR-19d 의 hybrid mode 는 미테스트 — 옵션 3 후속). (c) PR-19e `_safe_str_literal` (json.dumps escape) — Win11 메모장 Document name 의 `\r` SyntaxError 회귀 차단 + `_build_connect_block` 이 `process_id` 우선 connect chain (탭 이름만 잡힌 case 처리). (d) **PR-19f modifier 키 인식 — Ctrl+A 등 hotkey 변환** (recorder 가 `GetAsyncKeyState` 로 modifier 캡처 → RawEvent.modifiers 채움; transform 이 `pyautogui.hotkey('ctrl', 'a')` emit). Session.recording_meta list 필드 + commit_recording metadata 보존. (e) **PR-19g UWP `Light Dismiss` / `PopupRoot` noise filter** — 메모장 닫힘 회귀 차단 (실측 v2-새세션-005917). 자세한 §27 신규. **다음 세션 출발점 — P1 옵션 3 실증 결과 분석 (진행 중)** → P2 PR-19h destructive UX / P3 PR-19b F-6 dedup / P4 PR-19c idle wait / P5 PR-19i raw events JSONL / P6 CJK IME. 자세한 §27 끝 "다음 세션 출발점". **2026-05-23 PR-19a 완료 — recorder_transform 코드 품질 1차**: 자세한 §26. **2026-05-20~23 사용자 GUI 실측 1차 — 녹화 lifecycle 6 fix 완료** (test_182~186). 자세한 §24 "다음 세션 출발점" + §25. **2026-05-19 사용자 결정 — TS UI 트랙 진행 순서**: ① GUI 실측 (진행 중) → ② AppService API 보강 → ③ 2~3주 뒤 PR-19 (FastAPI 라우터) + PR-20 (Vite + React + TS, web_ui/). **풀 TS 재작성 X — recorder/element_picker/win_inspector 는 Python 유지**, TS 는 UI 레이어만. **5/19 (오후): ADR 0004 Phase R2 PR-18 완료 — DPI/멀티모니터 안정화. `core/input_hooks.py` 에 `ensure_dpi_awareness()` (SetProcessDpiAwarenessContext PER_MONITOR_AWARE_V2 우선, SHCore SetProcessDpiAwareness fallback) + `get_dpi_for_point(x, y)` (MonitorFromPoint + GetDpiForMonitor) helper 추가. `get_hook_manager()` 가 idempotent 로 매 호출 ensure_dpi_awareness 트리거. drain thread 가 click event 의 `monitor_dpi` 캡처 (RawEvent 새 필드). `recorder_transform` 의 fallback `pyautogui.click(x, y)` 에 비표준 DPI 시 코멘트 첨부 (`# captured at DPI=144 (150%)`). **R2 완료 — PR-16w + PR-17 + PR-18 모두 완료.** 자세한 §24.** **5/19 (오전): PR-17 마이그레이션 모드 event queue + async EFP. LL hook callback 은 RawEvent 생성 + 큐 enqueue 만 (sub-ms, fast return). 별도 drain thread 가 큐를 빼며 element_capture_fn 호출 + session.events 적재. Windows ~300ms LL hook 타임아웃 안전 + 빠른 자동화 스크립트 (Power Automate / pywinauto / AutoHotkey) 입력 따라잡기 가능.** **5/18: ADR 0004 Phase R2 PR-16w 완료 — 창 포커스 자동 경계 (SetWinEventHook EVENT_SYSTEM_FOREGROUND + SKIPOWNPROCESS) + F8 키보드 hook 에서 marker 자동 변환. PR-13 의 `auto_window_focus_boundary` / `enable_f8_marker` TransformOptions 가 비로소 end-to-end 작동 (이전엔 PR-13 에서 분리 로직만 구현되어 있었고 캡처 path 가 없어서 dead code 였음). 자세한 §24.** **5/16: ADR 0004 Phase R1 (5 PR) 완료 후 R2 진입 — PR-16a (element 메타 캡처 갭 메움) 추가. PR-11~15 + PR-16a (`core/element_inspect.py` 신규 + `_do_start_recording` 에서 capture_element_at 을 element_capture_fn 으로 주입 — UIA EFP 로 control_type/name/automation_id/window_title/hwnd/exe_name/rect/is_password_field 채움. 이전엔 element_meta=None 으로 떨어져 recorder_transform 이 좌표 fallback 만 생성하던 갭 해소). 자세한 §24.** **5/13~5/14: ADR 0003 Phase 1+2 완료 — 시크릿 처리 + element placeholder end-to-end (PR-1~10, test_117~144, 28 신규 테스트). 자세한 §23.** **wireframe D1~D26 100% 구현 완료**. 5/7~5/8: Phase 0 인프라 표준화 5/7 sub-phase 완료 — pyproject.toml + uv + pre-commit + ruff (lint+format) + LICENSE (AGPL-3.0) + SPDX 헤더 113 파일 + GitHub Actions CI + .devcontainer. **5/8~5/9: Phase 1 5/5 sub-task 모두 완료** — 저장소 추상화 + UI-Core 분리 (Chunk A 5/8 + Chunk B 5/9) + Pydantic 모델 + 설정 레이어 + Agent 브리지. **5/9 시장 타깃 결정**: 한국 niche → **글로벌 + 한국 dual-locale**. 영어 README + UI/메시지 i18n 작업이 Phase 2 진입 직전 필수. **Phase 2 진입은 [docs/commercial_review.md](commercial_review.md) GO/NO-GO 게이트 통과 후 결정** (5/9 글로벌 dual-locale 반영 갱신). **5/9~5/10: Phase 1.8 OpenAI 호환 (DeepSeek) 등록 + 코드 생성 품질 루프 — Step A/B + B1+B2+B4 + P4 + P1a/P1b/P3 + G1/G2/G2.5 + G5 (11 unit, test_86~96)**. **5/10~5/11: Phase 1.8 G7 코드 정적 분석 + 사용자 경고 + 재생성 흐름 — G7-A/B/C/D (4 unit, test_97~100)**. **5/11: Phase 1.8 후속 fix 모음 — G4 + G7-E (E1/E2) + G6 + F2 + G7-UX + F1 (7 unit, test_101~106). handoff §16 잔존 갭 #1~#6 + 후속 fix 옵션 6개 모두 완료**. 자세한 §18. **5/12 (오전): Phase 1.9 C-1 i18n 인프라 시작 — core/i18n.py + locale/{en,ko}.json (1 unit, test_107). 또한 5/12 결정: 최종 PySide6 만 사용 (PyQt6 보관). PySide6 port 회귀 가드 11 catch-up (test_97~107). commit b11b980. 자세한 §19.** **5/12 (오후) Plan 1 완료 — PySide6 (LGPL) 메인 전환 (commits 16d5349 → 833174a → f759ebb → d6642f0 + 50b3115). pyside6_port/ → root, PyQt6 → legacy_pyqt6/, PyQt6 dep → optional extra. 자세한 §20.** **5/12 (오후~저녁) Phase 1.9 C-2 완료 — `.gitattributes` 추가 (autocrlf 항구 해결) + ui_v2 i18n 183 catalog 키 (en/ko) + startup locale 자동 감지 + test_108/109 회귀 가드 추가. 8 commits (b8ce57f → 2d9cece). 자세한 §21.** **5/12 (저녁~밤) GUI 핵심기능 테스트 세션 — 사용자가 ohdo (`--ui v2`) 직접 띄워 cmd 실행 / 메모장 / element picker / step 관리 시나리오 반복 테스트하며 발견한 7 fix (test_110~116, **미커밋**): (1) kernel IPC RESULT marker isolation (실패가 ✅ 로 오보고) (2) Windows console-launch 규칙 (cmd/powershell 은 `CREATE_NEW_CONSOLE` 필수 — kernel_worker 가 콘솔 없는 piped subprocess) (3) ui_v2 `self.settings` AttributeError → `self._load_settings()` (4) 재생성 = in-place 대체 (`replaces_step_id` — 새 step 추가 X) (5) F3 picker 후 main window 잔존 → `showMinimized()` (6) step card 🗑 삭제 버튼 복원 (v2 누락) + ⬆⬇ 레이아웃 (7) `delete_step` generated_code chain 재구성 (삭제된 step 코드 잔존 회귀). core 116/116 + scenarios 73/73 그린. 자세한 §22.**

## 1. 프로젝트 한 줄 요약

**ohdo** — AI (Gemini CLI) 와 대화하면서 Windows 데스크톱/웹 자동화 코드를 단계별로 생성/실행하는 PyQt6 기반 RPA 솔루션. SaaS 확장 계획 진행 중 ([docs/ROADMAP.md](ROADMAP.md) §1, AGPL-3.0 데스크톱 + 상업 SaaS 오픈코어 전략 — **2026-05-05 사용자 결정 확정**).

## 2. 작업 환경 (사용자 preference)

- **터미널**: PowerShell (복붙용 명령은 PowerShell 문법 — `Activate.ps1`, `$env:X`, `Copy-Item`)
- **Python 의존성 (5/7 Phase 0 sub-phase 1 도입)**: `pyproject.toml` + `uv` (lockfile: `uv.lock`). 새 머신 셋업: `uv sync` → `.venv/` 자동 생성. 실행: `.venv\Scripts\python.exe ...`.
  - **레거시 `venv/`** (점 없음) 도 그대로 유지 — 5/6 까지 사용한 기존 환경. 둘 다 baseline 그린. 새 setup 은 `.venv/` 권장.
  - 시스템 `python` 은 고장난 3.8 32-bit — 절대 사용 X.
- **em-dash (—) cp949 인코딩 금지**: test/log/print 메시지에 사용 X. hyphen (-) 사용. (docstring/markdown 은 OK)
  - 5/7 부터 `tests/test_runner.py` 가 `sys.stdout.reconfigure(errors='replace')` 로 fallback 처리 — em-dash 가 ERROR 안 내고 `?` 로 표시됨. 그래도 가능한 hyphen 권장.
- **commit**: 사용자 명시 요청 시에만 (CLAUDE.md 규칙)
- **PySide6 포트 동기화**: 코드 수정 시 `pyside6_port/` 도 sed 로 자동 sync (PyQt6→PySide6, pyqtSignal→Signal 등)

## 3. 코드 구조 핵심

```
ohdo/
├── main.py
├── ui/                              — PyQt6 GUI
│   ├── main_window.py               — 1211줄 (2058 → 1823 → 1538 → 1211, 분해 Step 4 완료)
│   ├── ui_inspection_handler.py     — element picker + window inspector 핸들러 (Step 2)
│   ├── block_execution_handler.py   — 코드/블럭 실행 controller 16개 메서드 (Step 3, 478줄)
│   ├── ai_call_handler.py           — AI 호출 controller 6개 메서드 (Step 4, 412줄)
│   ├── element_picker.py            — element 검출 (EFP 토글 + walker)
│   ├── code_viewer.py               — 코드 뷰 / 블럭 뷰 + BlockCard / _WaitSpinBox
│   └── ...
├── core/
│   ├── workflow_engine.py           — block 실행 + step delta 추출
│   ├── execution_kernel.py          — kernel subprocess 관리 (env OHDO_PARENT_PID 전달)
│   ├── kernel_worker.py             — exec subprocess (step 종료 후 AllowSetForegroundWindow)
│   ├── import_manager.py            — extract_code_delta, _smart_dedent, _unwrap_main_function, extract_initial_block
│   ├── session_manager.py           — Step.wait_after_ms, Session.settings.step_delay_ms
│   └── ...
├── tests/
│   └── test_core.py                 — 65 tests, 모두 그린
├── pyside6_port/                    — LGPL 라이선스 PySide6 포트 (수동 sed sync)
│   ├── data/                        — junction → ../data (세션 공유)
│   └── (별도 venv 없음 — GUI 검증은 사용자 직접 환경에서)
└── docs/
    ├── ROADMAP.md                   — SaaS 장기 계획
    ├── triage.md                    — 작업 history (이거 먼저 보면 최근 변경 흐름 파악)
    └── handoff.md                   — 이 파일
```

## 4. 핵심 contract (회귀하면 안 되는 baseline)

### 4.1 Element picker baseline (test_42~48)
- **EFP (IUIAutomation::ElementFromPoint)** 호출 동안만 `WS_EX_TRANSPARENT` 토글 (try/finally), walker 들은 토글 밖. 매 tick 토글 회귀하면 picker 의 mouseover 누수 회귀, 토글 0 으로 가면 Excel 셀 detection 회귀.
- **F3 wait + post_pause_mode**: 항상 TRANSPARENT 켬 (방향 B 통합) + WH_MOUSE_LL hook 으로 click 차단 + 키보드 hook 은 picker 전체 lifecycle 유지.
- settings: `uia_max_depth=15`, `uia_time_budget_ms=500`, `descendants area threshold=5000 px²`, `cdp_enabled=false (default)`.

### 4.2 Jupyter mode (블럭 단독 실행) — test_51~54, 64, 66, 67
AI 생성 코드가 step 별 단독 실행되려면 **6가지 함수/필터 모두** 필요:
1. `extract_code_delta` — prefix + SequenceMatcher fallback
2. `extract_step_delta_code(step, prev_step)` — generated_code diff 재계산
3. `_smart_dedent` — try 블록 안 라인 indent 정리
4. `_unwrap_main_function` — `def main(): ...; main()` 패턴 unwrap (AST)
5. **except 캡처 변수 stale 라인 필터링** — 5/4 추가, NameError 'e' 회귀 방지
6. **prev_set 필터의 컨트롤 헤더 화이트리스트** — 5/4 밤 추가 (test_67). `try:`, `except`, `else:`, `if`, `for`, `while`, `with`, `def`, `class` 등 컨트롤 헤더는 prev 에 동일 패턴 있어도 보존 (제거하면 새 try/if/for 블록의 본문이 module-level 로 평면화되어 try/except 의미 깨짐).

추가로 **prompt 측 예방** (5/4 밤, test_66):
- `prompt_builder.build_step_prompt` [3] 규칙 섹션 + `prompts.json/system_context` 절대 규칙 9~10 에 jupyter 호환 가이드 박힘:
  - `def main(): ...; main()` 금지 (모듈 레벨 작성) — `_unwrap_main_function` 의존도 낮춤
  - except 변수(e, ex 등) 는 except 블록 안에서만 사용 — stale 라인 필터 의존도 낮춤
  - 후속 스텝은 이전 변수(driver, app, dlg) 재정의 X — globals 잃음 방지 (사후 필터 없음, 더 위험)

### 4.3 closeEvent 단일 정의 (test_62)
이전 두 번 정의되어 buggy. 통합 closeEvent: 세션 저장 + 커널 정리.

### 4.4 Step wait 시스템 (test_63)
3단계 우선순위: `step.wait_after_ms > session.settings.step_delay_ms > settings.execution.step_delay_ms`. UI 는 `_WaitSpinBox` (focus 시 selectAll) + `editingFinished` (입력 중 카드 재생성 X) + 개별 변경 시 `_refresh_block_view` 호출 안 함 (포커스 유지).

### 4.5 Win11 ForegroundLock 우회 (test_65)
subprocess (`kernel_worker`) 가 step 코드 안에서 `pyautogui.click/write/press` 같은 SendInput 호출하면 `SetForegroundWindow` 권한이 ohdo → kernel_worker 로 이전됨. 이후 ohdo 의 `mw.activateWindow()` 가 거부되어 작업표시줄 flash 만 발생. **Fix**:
- [core/execution_kernel.py](../core/execution_kernel.py) `start()`: subprocess `env` 에 `OHDO_PARENT_PID = str(os.getpid())` 전달.
- [core/kernel_worker.py](../core/kernel_worker.py): exec() finally 절에서 `ctypes.windll.user32.AllowSetForegroundWindow(parent_pid)` 호출 — 부모 (ohdo) 에 명시적 권한 양도. ohdo 의 다음 1회 `activateWindow` 통과 보장.
- 회귀 시 이 패턴 유지 — `OHDO_PARENT_PID` 키, `AllowSetForegroundWindow` 호출, `sys.platform == "win32"` 가드 모두 필수.

### 4.6 Block 실행 controller 분리 (Step 3, test_50/55/56/57/63)
[ui/main_window.py](../ui/main_window.py) 의 코드/블럭 실행 path 16개 메서드를 [ui/block_execution_handler.py](../ui/block_execution_handler.py) (`BlockExecutionHandler`) 로 분리. main_window 는 위임 stub 만 (`def _on_xxx: self.block_executor.on_xxx()`). 회귀 테스트는 `inspect.getsource(BlockExecutionHandler.method)` 로 검사 (self → mw 변환된 패턴, 예: `mw.lower()`).

### 4.7 AI 호출 controller 분리 (Step 4, test_68)
[ui/main_window.py](../ui/main_window.py) 의 AI 호출 path 6개 메서드를 [ui/ai_call_handler.py](../ui/ai_call_handler.py) (`AICallHandler`) 로 분리. 메서드: `on_cancel_ai`, `on_user_message`, `call_ai_thread` (백그라운드), `on_ai_response`, `on_step_executed`, `apply_manual_edit_patches`. main_window 는 위임 stub 만 (`def _on_xxx: self.ai_handler.on_xxx()`). 회귀 테스트는 `inspect.getsource(AICallHandler.method)` 로 검사 + `mw.xxx` 패턴. main_window unused imports (`asyncio`, `threading`, `Step`) 정리됨.

### 4.8 코드 편집 시 두 필드 동시 업데이트 + manually_edited 우선 + import 보존 (test_69)
사용자 수정 보호를 위한 4중 안전장치:

1. **두 필드 동시 업데이트** ([ui/main_window.py](../ui/main_window.py)):
   - `_on_block_step_code_edited`: `step_code` + 재구성한 `generated_code` (imports 보존 + prev_body + new_step_code).
   - `_on_step_code_edited`: `generated_code = new` + 재계산한 `step_code` + `step_imports` (extract_code_delta + extract_import_delta).
2. **`extract_step_delta_code` 우선순위 (0) manually_edited** ([core/workflow_engine.py](../core/workflow_engine.py)):
   - `manually_edited=True` + `step_code` 있으면 step_code 무조건 우선 반환 (compile 검증 통과 시 즉시).
   - generated_code 의 stale marker (1순위) / diff (2순위) 보다 앞 — 사용자 의도가 AI 원본보다 우선.
3. **화면 갱신 호출**: `_on_block_step_code_edited` 끝에 `self._refresh_code_viewer()`, `_on_step_code_edited` 끝에 `self._refresh_block_view()` — 위젯이 stale 한 채 남아 사용자가 변경을 못 보는 회귀 방지.
4. **import 보존**: 블럭 카드는 import 표시 안 함 → 사용자가 수정 시 import 안 건드림. 재구성 시 원본 step.generated_code 의 import 들을 prev_imports + old_imports + new_step_imports merge 로 모두 살림. 안 그러면 `extract_library_block` 이 imports 잃어 실행 시 NameError (5/4 사용자 2차 보고 'Application/Keys is not defined' 의 원인).

이 4개 모두 사용자가 어느 뷰에서 수정해도 다른 뷰 + 실행 결과가 일관되게 동기화되도록 보장. 한 가지만 빠지면 회귀 (5/4 사용자 보고 1차/2차/3차 모두 이 4중 fix 로 해소).

### 4.13 D3 — Step 카드 사용자 요청 + AI 설명 통합 (test_24~26)
[Step](../core/session_manager.py) dataclass 에 D3 (와이어프레임 §2.1) 의 핵심 데이터 필드 2개 추가:

- `user_request: str = ""` — 사용자가 입력한 자연어 요청
- `ai_description: str = ""` — AI 응답의 본문 (코드 제외 텍스트)

기본값 `""` — backwards compat. 옛 세션 JSON 에 이 필드 없어도 `Session(**{...})` 가 dataclass field 로 필터해 default 적용. v1 의 `conversation` 리스트도 그대로 보존 (양쪽 path 유지).

[AppService.generate_step](../core/app_service.py) 가 D3 path 의 단일 진입점:
1. `PromptBuilder.build_step_prompt` 로 prompt 구성 (이전 step + 시스템 지시 포함)
2. `AIEngineManager.generate(prompt, images)` 호출
3. `response.success` → Step 생성 — `user_request` / `ai_description` (= response.description) / `generated_code` (= response.code) / `required_packages` 채움
4. `add_step` 으로 자동 저장
5. `(Optional[Step], AIResponse)` 반환 — 실패 시 (None, response)

ui_v2 의 `_on_send_message` 가 이 메서드만 호출 — Step 생성 로직 / 코드 추출 / 세션 저장은 AppService 가 캡슐화. 새 UI 가 v1 의 prompt_builder/ai_engine 직접 import 안 해도 됨.

### 4.12 ui_v2 PoC — UI redesign 1차 슬라이스 (test_21~23)
[ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) — wireframes_v2.md 의 D1~D26 결정 반영한 새 UI PoC. **AppService 만 사용** (ADR 0001 강제 — test_21 가 forbidden import 패턴 검사).

**진입점**: `python main.py --ui v2` ([main.py](../main.py) 에 분기 추가).

**구현된 결정 (PoC 범위)**:
- D1 코드+블럭 뷰 통합 — 단일 스크롤 (라이브러리/Initial/Step 카드 세로 나열)
- D3 사용자 요청 + AI 설명 + 코드 step 카드 통합
- D5 콘솔 토글 (Ctrl+\`, default 닫힘)
- D6 인라인 칩 영역 (입력창 위, stub)
- D7 단축키 (Ctrl+R/F5 실행, F9 중지, Ctrl+Enter 전송, Ctrl+, 설정, Ctrl+K palette, Ctrl+\` 콘솔)
- D11 Initial '여기서 실행' 제거 — '⏯ 단독' 만
- D19 AI 설명 1~2줄 preview + ▼ 펼침 (toggle button)
- D24 Initial 자동 추출 비어있지 않을 때만 표시

**미구현 (후속 슬라이스)**: D4 다중 세션 탭, D8 Command palette 실 구현, D9 토스트, D10 시스템 테마 자동, D14 onboarding wizard, D17 토스트 confirm, D20 사이드바 last state, D21 + 탭 메뉴, D22 우클릭, D23 drag reorder, D25 빈 상태 일러스트.

**stub 처리** (실 동작은 후속 AppService 메서드 추가 시 연결):
- 전체 실행 / 단독 (step>0) / 여기서부터 실행 — `_log` 만 출력
- 사용자 메시지 전송 — `_log` 만 (AppService.generate_step 추가 후 연결)
- 캡처 / 요소 선택 — v1 의 ScreenCaptureOverlay/ElementPickerOverlay 후속 연결
- Settings — v1 의 SettingsDialog 재사용 예정

**실 동작하는 부분**:
- 세션 목록 / 더블클릭 로드 / 새 세션 생성 / closeEvent (커널 정리 + 세션 저장)
- Initial 단독 실행 — `AppService.run_initial_block_sync` 호출 (Phase 2.5 contract)
- 카드 자동 갱신 (세션 변경 시)
- 콘솔 토글
- 단축키 5종 + Ctrl+N

**styling**: wireframes_v2.md §8 디자인 토큰 (Catppuccin Mocha) 인라인 QSS. 후속 슬라이스에서 styles_v2.qss 분리.

### 4.11 AppService façade (Phase 1, test_17~20)
[core/app_service.py](../core/app_service.py) 의 `AppService` 클래스 — UI ↔ Core 분리 진입점. ADR 0001 ([docs/saas/decisions/0001-preserve-existing-core.md](saas/decisions/0001-preserve-existing-core.md)) 의 wrap-first 정책: **기존 UI 는 건드리지 않음**, 새 호출자 (FastAPI 라우터 / Agent runner / ui_v2) 만 AppService 사용.

**구조**:
- `SessionRepository` ([core/storage/base.py](../core/storage/base.py)) 추상화 — `LocalJsonRepository` (기본), 향후 `PostgresRepository` / `HttpRemoteRepository`.
- AppService 는 stateless façade — 매 호출마다 session/kernel 객체 인자로 받음. 상태는 호출자 (handler/UI) 보유.
- AIEngineManager 주입은 선택 — 미주입 시 AI 메서드는 안전한 fallback (`get_ai_engine_name() → None`) 또는 `RuntimeError` (mutating 작업).

**메서드 카테고리**:
1. **세션/스텝 CRUD** (위임): `create_session`, `save_session`, `get_session`, `list_sessions`, `delete_session`, `add_step`, `update_step`, `delete_step`, `insert_step`, `move_step`.
2. **코드 추출** (pure 함수 façade): `get_library_block_code`, `get_initial_block_code`, `get_step_delta_code`. UI 가 workflow_engine/import_manager 직접 import 안 하도록.
3. **블럭 실행** (kernel 외부 주입): `run_initial_block_sync(session, initial_code, kernel, on_log=)` — Phase 2.5 contract (§4.9) 의 라이브러리 자동 선행 + Initial 실행. kernel lifecycle / threading 은 호출자 책임.
4. **AI ops** (AIEngineManager 위임): `generate(async)`, `switch_ai_engine`, `cancel_ai`, `get_ai_engine_name`, `list_ai_engines`.

**ui_v2 가 따라야 할 패턴**: `from core.app_service import AppService` 만 import. `from core.session_manager import ...` / `from core.workflow_engine import ...` 등은 금지 (façade 우회 = ADR 위반).

### 4.10 OpenAI 호환 API 어댑터 (D2, test_75)
[core/adapters/openai_compat_adapter.py](../core/adapters/openai_compat_adapter.py) 의 `OpenAICompatAdapter`:

- **단일 어댑터, 다 서비스**: base_url + api_key 만 받아 OpenAI/DeepSeek/Groq/OpenRouter/Mistral/Together/Perplexity 클라우드 + Ollama/LM Studio 로컬 모두 지원. 모두 `POST {base_url}/chat/completions` 호출.
- **9 프리셋** (`PRESETS` 모듈 상수): Settings UI 드롭다운에서 선택 시 base_url + model 자동 채움. `_PRESET_LABELS` 로 표시 라벨 정확화 (DeepSeek, LM Studio (local) 등).
- **api_key 우선순위**: 직접 입력 (`config["api_key"]`) > 환경변수 (`config["api_key_env"]` 기본 `OPENAI_API_KEY`). 비어있어도 OK (로컬 Ollama/LM Studio).
- **base_url 끝 슬래시 자동 제거**: `chat/completions` 합칠 때 `//` 회피.
- **이미지 첨부**: OpenAI multimodal 포맷 (`content` array `[{type:"text"}, {type:"image_url", image_url:{url:"data:image/png;base64,..."}}]`). vision 지원 모델만 의미있음.
- **HTTP 라이브러리**: `requests` (이미 deps), `asyncio.to_thread` 로 async 호환. httpx/openai SDK 의존성 회피.
- **Cancel**: 플래그 기반 (응답 후 검사). 실시간 mid-request 중단은 향후 httpx 전환 시.
- **API key 저장 위치**: settings.json 평문. keyring 통합은 §6 #5 결정 대기.

### 4.9 Initial 블럭 단독 실행 (Phase 2.5, test_74)
사용자가 driver/options 등 setup 변수를 재정의하고 싶을 때 첫 step 안 돌리고 Initial 블럭만 실행. 4가지 contract:

1. **상수**: `INITIAL_BLOCK_STEP_ID = -1` ([core/execution_kernel.py](../core/execution_kernel.py)) — `LIBRARY_BLOCK_STEP_ID = 0` 와 같은 가상 step_id 패밀리.
2. **UI 노출**: `BlockCard` 가 `step_id > 0 or step_id == -1` 조건으로 "⏯ 단독" 버튼 표시. step_id == -1 전용 tooltip ("Initial 블럭 단독 실행 (driver/options 등 변수 재초기화)"). Library (step_id == 0) 은 여전히 제외 — "한 번만 실행되는 setup" 이라 의미 없음 유지.
3. **Signal 라우팅**: `BlockViewWidget.refresh()` 가 `init_card.run_single_requested` 를 step 카드와 같은 `self.run_single_step_requested` 시그널로 forward. main_window → `BlockExecutionHandler.on_run_single_step(-1)` → 분기 → `on_run_initial_block()`.
4. **실행 path**: `_run_initial_block_thread` 가 `LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps` 일 때 `extract_library_block(session)` 으로 라이브러리 선행 (NameError 회귀 방지 — 카드는 imports 표시 안 함). Initial 코드는 카드의 `code_edit.toPlainText()` 로 사용자 편집 반영. `kernel.execute_block(initial_code, step_id=INITIAL_BLOCK_STEP_ID)`. finally 절에서 `blocks_finished.emit()` (test_73 의 run/stop 자동 리셋과 일관).

다른 step 들의 `kernel.executed_steps` 는 안 건드림 — Initial 만 재실행이고 step 1..N 의 silent replay 도 안 함.

## 5. 최근 작업 내역 (5/2 ~ 5/5)

| 일자 | 작업 |
|------|------|
| 5/2 | PySide6 migration (pyside6_port/), Phase 2 (Initial 블럭 추출), main_window 분해 Step 1 (closeEvent) + Step 2 (UIInspectionHandler 235줄) |
| 5/3 | Step wait 시스템 (3단계 우선순위 + UI), 코드 뷰↔블럭 뷰 상호작용 fix (signal-slot blocks_finished) |
| 5/4 | NameError 'e' fix (extract_code_delta 의 except 변수 필터), wait UI 개선 (_WaitSpinBox + editingFinished + 좌측 정렬) |
| 5/4 (저녁) | main_window 분해 Step 3 (BlockExecutionHandler, 1880→1538줄, 16개 위임 stub), Win11 ForegroundLock 우회 (foreground 복원 보류 해제), test 64 → 65 |
| 5/4 (밤) | AI prompt 강화 — jupyter mode 호환 가이드라인 3종 (`prompt_builder` + `prompts.json/system_context`), test_66 추가 (66/66 그린) |
| 5/4 (밤) | extract_code_delta 컨트롤 헤더 보존 fix — prev_set 필터가 try:/except 헤더 제거해 본문이 module-level 평면화되는 버그 수정. test_67 추가 (67/67 그린) |
| 5/4 (밤) | main_window 분해 Step 4 — AICallHandler (412줄) 신규, 6개 메서드 위임 stub. main_window 1538 → 1211 (-327줄). unused imports 정리. test_68 추가 (68/68 그린). |
| 5/4 (밤) | 코드 편집 desync fix — `_on_block_step_code_edited` / `_on_step_code_edited` 가 step_code + generated_code 두 필드 동시 업데이트. 사용자 보고 (네이버 검색 시나리오: 삼성전자 → 하이닉스 수정이 무시되는 회귀) 해결. test_69 추가 (69/69 그린). |
| 5/4 (밤) | 코드 편집 desync 2차 fix — 1차 fix 후에도 ① 코드 뷰어 탭 갱신 안 됨 ② 실행 시 잘못된 코드 추출 (사용자 보고). `extract_step_delta_code` 에 우선순위 (0) manually_edited + step_code 무조건 우선 추가. 두 핸들러에 _refresh_code_viewer/_refresh_block_view 호출 추가. 3중 안전장치 (§4.8). |
| 5/4 (밤) | 코드 편집 desync 3차 fix — 2차 fix 후에도 사용자 보고 'NameError: name Application/Keys is not defined'. 원인: 새 generated_code 가 prev_step + step_code 만 합쳐 step 의 import 들을 잃음. block 카드는 import 표시 안 하므로 사용자가 수정 안 함. Fix: 원본 step.generated_code 의 import 보존 (prev_imports + old_imports + new_step_imports merge). 4중 안전장치 (§4.8). test_69 갱신. |
| 5/4 (밤) | Selenium prompt 가이드 보강 — AI 가 driver.get() 직후 추측성 element ID (예: 'nm_main_tab') 로 WebDriverWait 사용 → 10초 timeout 회귀 (사용자 보고). prompt_builder 에 "추측성 ID 금지, time.sleep 또는 body/html 사용" 가이드 추가. test_70 (70/70 그린). |
| 5/4 (밤) | Gemini CLI 모델 명시 — headless 모드 default 가 preview 모델 (gemini-3-flash-preview) 로 잡혀 Google 인프라 capacity 부족으로 429/180s timeout 회귀 (사용자 보고). adapter `__init__` 에 `self.model` + `_build_args` 헬퍼 추가. settings.json default = `gemini-2.5-flash` 안정 모델. test_71. **note**: `_build_args` 정의만 추가, 실제 두 subprocess.Popen path (stdin/-p) 에서 호출 안 됨 — 다음 작업으로 production path 적용 필요. |
| 5/4 (밤) | 세션 추가/삭제 시 블럭 뷰 초기화 회귀 — 사용자 보고: `_new_session` / `_on_session_delete` 의 `self.code_viewer.clear()` 가 step 카드만 비웠음, 블럭 뷰는 이전 세션 카드 stale. Fix: `CodeViewer.clear()` 가 `block_view.refresh("", [], "", 500)` 도 호출 (try/except fallback 으로 `block_view.clear()`). test_72 (72/72 그린). |
| 5/5 | 실행 종료 시 run/stop 버튼 자동 리셋 안전망 — 사용자 보고: 모든 step 완료 후에도 stop 버튼이 활성/run 버튼이 비활성 채로 남는 회귀. Fix: `AICallHandler.on_step_executed` (코드 뷰 path) 끝에 `mw.code_viewer.set_running(False)` catch-all 추가. `BlockExecutionHandler.on_blocks_finished` (블럭 뷰 path) 에 `mw.code_viewer.update()` 시각 갱신 강제. test_73 (73/73 그린). |
| 5/5 | Gemini adapter `_build_args` production path 적용 — 5/4 밤 작업 미완성 마감. 두 subprocess.Popen 호출 (stdin / -p) 가 여전히 raw `[gemini_exec, ...]` 리터럴 사용 중이라 -m 플래그가 실제 호출에서 누락 가능했던 문제 해결. 둘 다 `self._build_args(...)` 경유. test_71 확장 — production path source 검증 추가 (raw 리터럴 부재 + `_build_args` 호출 패턴 존재). core 73/73 유지. PySide6 sync. |
| 5/5 | ROADMAP §1 라이선스 전략 결정 확정 — 사용자와 AGPL/폐쇄/오픈코어 비교 후 **오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS)** 확정. v1.0 은 100% AGPL-3.0 무료, SaaS 라인 긋기는 Phase 2 진입 시점에 결정. ROADMAP §1/§10 갱신, handoff §6 #1 결정 완료 표시. LICENSE 파일/코드 헤더 추가는 미실행 (사용자 결정 대기). |
| 5/5 | Phase 2.5: Initial 블럭 단독 실행 — driver/options 등 setup 변수를 재정의하고 싶을 때 첫 step 안 돌리고 Initial 블럭만 실행하는 path 추가. `INITIAL_BLOCK_STEP_ID = -1` 상수 신설, BlockCard 의 "⏯ 단독" 버튼이 step_id == -1 도 활성화 (전용 tooltip), BlockViewWidget.refresh 가 init_card.run_single_requested 라우팅, BlockExecutionHandler 에 `on_run_initial_block` + `_run_initial_block_thread` 추가 (라이브러리 미초기화 시 자동 선행 → NameError 회귀 방지). 카드 텍스트로 사용자 편집 반영. test_74 (74/74 그린). PySide6 sync. |
| 5/5 | UI redesign 준비 Step 0 #1: [docs/feature_catalog.md](feature_catalog.md) 초안 작성 — 현재 PyQt6 UI 의 모든 화면/위젯/단축키/시그널/다이얼로그/데이터 흐름 카탈로그 (14 섹션, ASCII 레이아웃 다이어그램 포함). redesign 와이어프레임 cover 검증의 baseline 로 사용. §13 에 redesign 시 결정 필요 항목 명시. |
| 5/5 | UI redesign 결정 3건 확정 (사용자 합의) — feature_catalog §13: **D1 코드+블럭 뷰 통합** (블럭 뷰 베이스로 단일 뷰), **D2 OpenAI 호환 API 어댑터 추가** (base_url + api_key, DeepSeek/Groq/OpenRouter/Ollama 등 다 지원), **D3 요청-코드 step 매칭 표시** (각 step 카드에 사용자 요청 + AI 설명 + 코드 모두 통합 — ChatPanel ↔ CodeViewer 좌우 분리 → step 카드 통합). 미결정 13건 남음 (API 키 저장 위치, 단축키 체계, 다중 세션 UX 등). |
| 5/5 | **D2 구현**: OpenAI 호환 어댑터 신규 — [core/adapters/openai_compat_adapter.py](../core/adapters/openai_compat_adapter.py) (`requests` + asyncio.to_thread, multimodal 이미지 base64 변환, 9 프리셋 OpenAI/DeepSeek/Groq/OpenRouter/Mistral/Together/Perplexity/Ollama/LM Studio). `ADAPTER_REGISTRY` 등록, settings.json default 갱신, [SettingsDialog](../ui/settings_dialog.py) AI 탭에 OpenAI 호환 GroupBox 추가 (프리셋 드롭다운 → base_url/model 자동 채움, api_key Password 모드, model/timeout/max_tokens/temperature). test_75 (75/75 그린). PySide6 sync. **API key 저장은 settings.json 평문 — keyring 통합은 §6 #5 결정 대기.** |
| 5/5 | UI redesign 결정 13건 일괄 확정 (사용자 합의, [feature_catalog.md §13](feature_catalog.md)) — D4~D16: **다중 세션 탭 / 콘솔 토글 (Ctrl+\`) / 인라인 요소 칩 / 단축키 5종 추가 (Ctrl+Enter 전송, Ctrl+R 실행, Ctrl+, 설정, Ctrl+K palette, F5 재실행) / Command palette 도입 / 토스트 + QMessageBox 병행 / 시스템 테마 자동 감지 / Initial '여기서 실행' 제거 / 캡처 워크플로우 유지 / 웹은 데스크톱뷰 우선 + 모바일 read-only / 3단계 onboarding wizard / settings.json 평문 (v1.0) → SaaS 시 keyring / BYO 우선 + SaaS hidden 프리셋**. 미결정 0건 — 와이어프레임 작업 진입 가능. |
| 5/5 | UI redesign 준비 Step 0 #2: [tests/test_scenarios.py](../tests/test_scenarios.py) 16 시나리오 신규 — behavior-level 테스트 (UI 우회). test_core 의 inspect.getsource 패턴은 코드 위치 변경에 깨지지만 scenarios 는 입출력 동작만 검증 → AppService 추출/UI redesign 회귀 안전망. 6 그룹: 세션 lifecycle (3) / delta·library·initial 추출 (5) / manually_edited 우선순위 (2) / AIEngineManager 라우팅 (2) / OpenAICompat HTTP mock (3 — 응답 파싱/HTTP 에러/이미지 multimodal 포맷) / wait timing (1). test_runner 에 'scenarios' suite 등록. 16/16 그린. PySide6 sync. |
| 5/5 | UI redesign Step 0/D #4 와이어프레임 1차 초안: [docs/wireframes_v2.md](wireframes_v2.md) — 12 섹션 텍스트 와이어프레임 (메인 윈도우 / Step 카드 v2 / Settings / Onboarding 3단계 wizard / Command palette / Toast / 단축키 17개 / 디자인 토큰 / D1~D16 결정 매핑). §10 에 와이어프레임 도중 발견한 새 결정 10건 (D17 후보). 다음: 사용자 검토 → §10 결정 → Excalidraw 정식 와이어프레임 → AppService 추출 (Step 1) → ui_v2/ PoC. |
| 5/5 | UI redesign 결정 10건 + onboarding 일괄 확정 (D17~D26): 사용자 요청 클릭 토스트 confirm / wait 드롭다운 5+사용자정의 / AI 설명 1~2줄 preview / 사이드바 last state 기억 / + 탭 메뉴 / 우클릭 4항목 / drag+버튼 둘 다 / Initial 자동 표시 / 빈 상태 일러스트 / 테마 토글 settings 만. onboarding 메모장/네이버/빈 세션 3개 확정. **미결정 0건 — Excalidraw 정식 와이어프레임 또는 AppService 추출로 진입 가능.** |
| 5/5 | **Step 1: AppService façade 확장** (Phase 1) — 기존 [core/app_service.py](../core/app_service.py) (세션/스텝 CRUD + `LocalJsonRepository` 이미 존재, ADR 0001/0002 wrap-first 정책) 에 메서드 추가: 코드 추출 (`get_library_block_code` / `get_initial_block_code` / `get_step_delta_code`) + 단독 실행 (`run_initial_block_sync` — Phase 2.5 contract façade) + AI ops (`generate` / `switch_ai_engine` / `cancel_ai` / `get_ai_engine_name` / `list_ai_engines`). AIEngineManager 주입 선택 — 미주입 시 안전 fallback. test_scenarios 에 4 시나리오 추가 (test_17~20: CRUD / 코드 추출 / fake kernel 로 run_initial_block_sync / AI façade). scenarios 20/20 그린, core 75/75 유지. PySide6 sync. handoff §4.11 contract 추가. **기존 BlockExecutionHandler 등은 건드리지 않음** (ADR 0001) — 새 ui_v2 만 AppService 사용. |
| 5/5 | **ui_v2 PoC** (UI redesign 1차 슬라이스, [§4.12](.)) — 신규 [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) 단일 파일 PoC (~600줄). **AppService 만 사용** (test_21 가 forbidden import 강제 검사). [main.py](../main.py) 에 `--ui v2` 플래그 분기. 구현: 메인 윈도우 + 사이드바 (세션 목록) + 카드 스크롤 (라이브러리/Initial/Step 통합) + 채팅 입력 + 콘솔 토글 + 단축키 8개 + 디자인 토큰 인라인 QSS. **실 동작**: 세션 CRUD, 카드 자동 갱신, Initial 단독 실행 (`AppService.run_initial_block_sync` 호출). **stub**: 전체 실행, 메시지 전송 AI 호출, 캡처/요소 선택, Settings (후속 슬라이스에서 AppService.generate_step 추가 + v1 dialog/overlay 재사용 연결). test_21~23 신규 (scenarios 23/23 그린). PySide6 sync. |
| 5/5 | **D3 데이터 모델 + ui_v2 AI 호출 연결** — [Step](../core/session_manager.py) dataclass 에 `user_request` + `ai_description` 필드 추가 (default `""`, backwards compat). [AppService.generate_step](../core/app_service.py) 신규 — async, `PromptBuilder` 사용, AI 호출 → 성공 시 Step 생성 (user_request/ai_description/generated_code/required_packages 채움) + `add_step` 으로 세션 저장, 실패 시 `(None, response)` 반환. [ui_v2._on_send_message](../ui_v2/main_window_v2.py) stub 제거 → 실제 AppService.generate_step 호출 + 백그라운드 thread + step_done signal 로 UI 갱신 (입력 비활/재활). test_24 (mock AI → Step 생성 + D3 필드 보존), test_25 (AI 실패 시 step None + 세션에 추가 안 됨), test_26 (Step dataclass 필드 + default 검증). scenarios 26/26 그린. PySide6 sync. |
| 5/5 | **ui_v2 실행 stub 채우기 — 전체/단독/여기서부터** — [AppService.run_blocks](../core/app_service.py) (async) + `stop_blocks` 신규: WorkflowEngine.execute_session_blocks 위임, lazy engine 생성. ui_v2 의 `_on_run_all` (start=1,stop=None) / `_on_run_from` (start=N,stop=None) / `_on_run_single` (start=N,stop=N) / `_on_stop` (engine.stop()) 모두 실 동작 — 공통 `_start_run` 헬퍼로 백그라운드 thread + lower → run_blocks → step_done 으로 UI 복원. per-step status 는 콘솔 로그만 (카드 rebuild 회피, 완료 시 1번 refresh). test_27 (fake kernel — Step 2 단독 시 1 silent + 2 정상 + 3 미호출), test_28 (engine 미생성 stop_blocks no-op). scenarios 28/28 그린. PySide6 sync. |
| 5/5 | **ui_v2 stub 채우기 — 캡처/요소픽/Settings (v1 재사용)** — UI 컴포넌트 재사용은 ADR 우회 OK (데이터 안 다룸). [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py): `_on_capture` → v1 `ScreenCaptureOverlay` (lower → 캡처 → data/captures/v2_capture_*.png 저장 → pending_images 추가 → chip 표시), `_on_elempick` → v1 `ElementPickerOverlay` (settings.element_picker 옵션 적용 → pending_elements 추가 → chip), `_on_open_settings` → v1 `SettingsDialog` (settings.json + prompts.json 로드 → exec → save → AIEngineManager 재초기화 → 액션바 콤보 갱신). `_on_send_message` 확장 — pending images 가 generate_step images 인자로, pending elements 가 user_request 의 "📌 선택된 요소: ..." prefix 로 (D6). 전송 후 pending 비움 + chip_area 자동 갱신. test_29 (stub 제거 + v1 import + pending 로직), test_30 (send_message 의 pending 처리). scenarios 30/30 그린. PySide6 sync. |
| 5/5 | **ui_v2 카드 가로 스크롤 회귀 fix** (사용자 보고: 카드들이 좌우로 너무 길어 불필요한 가로 스크롤 발생). 원인: QPlainTextEdit 의 sizeHint (~80자, ~600px) + QToolButton (긴 AI preview) 의 word-wrap 미지원 → 카드 폭이 viewport 초과. 4 fix: ① `cards_scroll.HorizontalScrollBarPolicy = AlwaysOff` ② StepCardV2 자체 `setSizePolicy(Preferred,Preferred)` + `setMinimumWidth(0)` ③ `_tame_text_widget` 헬퍼 — req_edit / ai_full QPlainTextEdit 에 `LineWrapMode.WidgetWidth` + 가로스크롤 끄기 + `setSizePolicy(Expanding,Preferred)` + `setMinimumWidth(0)` ④ AI preview QToolButton → `QLabel(wordWrap=True) + mousePressEvent` 교체, preview 길이 120 → 80 자. 코드 영역은 NoWrap + 내부 가로스크롤 유지 (가독성). |
| 5/5 | **D9/D17/D20/D25 일괄 구현** — ui_v2 후속 슬라이스 4 결정 한 번에 박음. ① **D9 Toast** — [Toast](../ui_v2/main_window_v2.py) 위젯 (info/success/warning/error 4 타입, action 버튼 옵션, auto-dismiss 4초/8초) + `ToastManager` (우하단 stack, host resize 시 위치 갱신). ② **D17 사용자 요청 클릭 → 재생성** — `StepCardV2.regenerate_requested(int, str)` signal, user_request QPlainTextEdit 클릭 가능 (PointingHandCursor + tooltip), `MainWindowV2._on_regenerate` 가 토스트 confirm ("재생성" 버튼 + 8초 timeout = cancel). `_send_request` 헬퍼로 send_message + regenerate 공유. ③ **D20 사이드바 toggle** — `_toggle_sidebar` (Ctrl+B + 액션바 ☰ 버튼), `settings.ui.sidebar_collapsed` persist, init 에서 last state 적용. ④ **D25 빈 상태** — `_show_empty_state(title, description, examples=[...])`, 세션 없거나 step 0개 시 표시, 예시 시나리오 3개 (메모장/네이버/윈도우 검사) 클릭 시 입력창 자동 채움 + 포커스. 기존 알림 토스트 교체 (캡처 저장, 요소 선택, 설정 저장, step_done). test_31~33 (Toast 클래스 / D17 D20 D25 메서드 존재 / sidebar persist 패턴). scenarios 33/33 그린. PySide6 sync. |
| 5/5 | **D8 + D14 후속 슬라이스 일괄** — ui_v2 의 마지막 두 큰 stub 끝냄. ① **D8 Command palette** — 신규 [ui_v2/command_palette.py](../ui_v2/command_palette.py) `CommandPalette` (frameless QDialog, 검색 입력 + 그룹 분류 리스트 + ↑↓/Enter/Esc 키, 부모 윈도우 상단 1/4 위치, fuzzy substring 매칭 PoC). `MainWindowV2._on_command_palette` 가 items 동적 구성 — 9개 명령 (실행/중지/커널/세션/설정/캡처/요소픽/사이드바/콘솔, 단축키 표시) + 모든 세션 (더블클릭 = 로드) + 모든 AI 엔진 (✓ 현재 표시). Ctrl+K stub 제거 → 실 호출. ② **D14 Onboarding wizard** — 신규 [ui_v2/onboarding.py](../ui_v2/onboarding.py) `OnboardingWizard` (3 페이지 QStackedWidget — 환경 안내 / 엔진 선택 라디오 / 시나리오 선택, 진행 표시 1/3, 건너뛰기 / 이전 / 다음·시작 버튼, `selected_engine`/`selected_scenario` 결과 외부 노출). `should_show(settings)` static helper 가 `settings.ui.onboarding_done` 플래그 검사. MainWindowV2 init 에서 `QTimer.singleShot(0, _maybe_show_onboarding)` — wizard 결과로 AI 엔진 전환 + 새 세션 + 입력창 자동 채움. 한 번 띄우면 `onboarding_done = True` 저장 → 다음 실행 스킵. test_34 (CommandPalette 인터페이스), test_35 (Ctrl+K wiring + items 그룹), test_36 (OnboardingWizard SCENARIOS 3개 + should_show 토글 + 트리거 패턴). scenarios 36/36 그린. PySide6 sync. **ui_v2 의 모든 D 결정 (D1~D26) 구현 완료** — 남은 항목은 D4 다중 세션 탭 (별도 슬라이스). |
| 5/5 | **D4 다중 세션 탭 + D21 + 탭 메뉴 + D22 탭 우클릭** — ui_v2 의 마지막 큰 redesign. ① **D4 세션별 커널 분리**: `MainWindowV2._kernel: Optional` → `_kernels: dict[str, ExecutionKernel]`. `_get_or_create_kernel` / `_on_kernel_reset` / `closeEvent` 모두 활성 세션 키 기반. ② **QTabBar** (액션바 아래) — `setMovable(True)` (D4 drag reorder) + `setTabsClosable(True)` + 그룹별 styling. `_tabs_state: dict` (탭별 pending images / pending elements / message 입력 텍스트), `_tab_session_ids: list` (탭 인덱스 ↔ session_id 매칭). `_open_session_tab(sid)` (이미 열린 탭이면 그 탭 활성화), `_switch_session(sid)` (pending swap + 카드 재구성 + 사이드바 highlight 동기화). ③ **D21 + 탭 버튼 메뉴**: 새 세션 (빈) / 사이드바 검색 / 템플릿 서브메뉴 (메모장 한글 입력 / 네이버 검색). 템플릿 클릭 → 새 세션 + 입력창 자동 채움. ④ **D22 탭 우클릭 메뉴**: 닫기 / 이름 변경 (QInputDialog) / 복제 (모든 step + D3 필드 복사) / 워크플로우 내보내기 (PoC: 세션 폴더 통째로 shutil.copytree). 사이드바 더블클릭 → `_open_session_tab` (새 탭 또는 기존 탭 전환). 첫 실행 시 첫 세션을 첫 탭으로 자동 로드. test_37 (탭 인프라 + state dict + movable/closable), test_38 (D21 + D22 메뉴), test_39 (세션별 커널 분리 패턴). scenarios 39/39 그린. PySide6 sync. **ui_v2 의 D1~D26 모든 결정 구현 완료** (D23 step drag reorder 만 별도 슬라이스). |
| 5/5 | **D23 step reorder 버튼 fallback** — wireframe §10 #7 의 "drag-drop + ⬆⬇ 버튼 둘 다" 중 버튼 부분 우선. `StepCardV2.reorder_requested(step_id, direction)` signal 추가, footer 에 ⬆⬇ QToolButton (step_id > 0 만, transparent border). MainWindowV2._on_step_reorder → AppService.move_step (기존 함수, "up"/"down" direction) → 세션 다시 로드 → 카드 재구성 → 토스트. 더 이상 이동 불가 시 warning 토스트. test_40 신규 (signal + 핸들러 + 버튼 텍스트 + AppService 위임 검증). scenarios 40/40 그린. PySide6 sync. **drag-drop 본체는 후속 슬라이스** — Qt drag-drop 의 cards_container override 복잡도 때문에 분리. |
| 5/5 | **사용자 보고 fix + 전송/중지 토글** — ① 캡처/요소 선택 버튼 가시성 (transparent → 명확한 배경/테두리/40x40 크기/이모지 18px, hover primary 색상). QToolTip 글로벌 스타일 추가 (어두움 회피). ② `_on_elempick` 강제 종료 fix — `ElementPickerOverlay` 가 받는 인자가 `(parent, settings)` 인데 v2 가 `uia_max_depth=` kwargs 잘못 전달해 TypeError. 전체 settings 통째로 전달 + try/except 안전망. ③ 전송 ↔ 중지 토글 — `self.send_btn` 보유, `_set_send_state(generating)` 헬퍼, `_is_generating` 플래그. AI 호출 중 같은 버튼이 빨간 "⏹ 중지" 로 변환 + 클릭 시 `AppService.cancel_ai()`. `_send_request` 시작 시 True, `_on_step_done` 에서 False 자동 복원 (멱등). test_41. |
| 5/5 | **D23 drag-drop 본체** — wireframe §10 #7 의 마지막 미구현 결정. `AppService.reorder_step(session_id, step_id, target_step_id)` 신규 — pop+insert+renumber 단일-shot (move_step 다중 호출은 `_renumber_steps` 가 step_id 재할당해서 깨짐). [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `CardDropContainer(QWidget)` 신규 — `setAcceptDrops(True)`, `dragEnter/Move/dropEvent`, `step_reorder_drop(int, int)` signal, drop y 위치로 target step 결정. `StepCardV2.mousePressEvent` / `mouseMoveEvent` — 헤더 영역 (~36px) 좌클릭 + drag distance > startDragDistance 시 `QDrag` 시작 (mime `application/x-ohdo-step` + 카드 미니 미리보기). `cards_container = CardDropContainer()`, `step_reorder_drop` → `MainWindowV2._on_step_reorder_to` → `AppService.reorder_step` + 세션 재로드 + 카드 재구성. test_42 (AppService.reorder_step 동작 검증 + signal/handler/connect 패턴). scenarios 42/42 그린. PySide6 sync. **wireframe D1~D26 모든 결정 100% 구현 완료**. |
| 5/5 | **Syntax highlighting + 코드 편집** (사용자 보고: 코드가 흰색만 + 편집 불가). v1 의 `PythonHighlighter` (Catppuccin Mocha 5 카테고리 — 키워드/문자열/숫자/주석/함수) 와 BlockCard 편집 토글 패턴을 v2 에 이식. ① `PythonHighlighter(QSyntaxHighlighter)` 신규 — v1 코드 재사용 + COLORS 토큰 매핑. ② StepCardV2: `code_edit.document()` 에 highlighter 인스턴스 부착 (`self._highlighter` 보유 = GC 방지), `_readonly_style` / `_editing_style` 분리 (편집 모드 = 2px primary 테두리), `_toggle_edit` / `_enter_edit_mode` / `_exit_edit_mode` (높이 180→320 확장, "✏️ 수정" → "✅ 저장" 토글), `code_edited(int, str)` signal. Library (step_id == 0) 제외, Initial/Step 모두 편집 가능. ③ MainWindowV2._on_block_code_edited — AppService.update_step(sid, step_id, {step_code, manually_edited=True}) → 세션 재로드 → 카드 재구성. Initial 직접 편집은 후속 (현재 안내 토스트만). test_43 (PythonHighlighter QSyntaxHighlighter 상속 + 5 룰 + 키워드 + signal + 핸들러 + GC 방지 패턴). scenarios 43/43 그린. PySide6 sync. |
| 5/5 | **세션 영구 삭제** (사용자 요청). `MainWindowV2._on_session_delete(session_id)` — QMessageBox.question 으로 destructive confirm (D9 결정 따름) → 열린 탭 있으면 `_on_tab_close(idx)` 먼저 (커널 정리 + state 제거) → `AppService.delete_session` → 사이드바 갱신 + 토스트 (warning). 사이드바 QListWidget 우클릭 컨텍스트 메뉴 활성화 (`_on_sidebar_context_menu`) — 열기 / 이름 변경 / 복제 / 내보내기 / 🗑 영구 삭제 5 항목 (이름변경/복제/내보내기는 D22 의 _on_tab_* 재사용). 탭 우클릭 메뉴에 separator + "🗑 세션 영구 삭제" 항목 추가 (탭 닫기와 분리). test_44 (핸들러 존재 + 메뉴 wiring + AppService.delete_session 실 동작 검증). scenarios 44/44 그린. PySide6 sync. |
| 5/6 | **tmp/ 폴더 + AI 대화 로그 자동 저장** (사용자 요청). ① 프로젝트 루트의 tmp_*/step[0-2]_* 임시 파일 56 개를 [tmp/debug_artifacts/](../tmp/debug_artifacts/) 로 정리. ② [.gitignore](../.gitignore) 에 `tmp/` 추가. ③ [AppService](../core/app_service.py) 에 `_save_conversation_log()` 헬퍼 신규 — `generate_step()` 마다 prompt + AI 응답 + 추출 코드를 단일 .md 파일로 [tmp/conversations/](../tmp/conversations/) 에 저장. 파일명: `{YYYYMMDD_HHMMSS}_step{N}_{session_short}.md`. 백업 [step0_prompt.txt + step0_generated_code.py] 분리 패턴을 통합 — 메타 헤더 (타임스탬프/세션ID/제목/엔진/이미지/길이) + 사용자 요청 + 전체 프롬프트 + AI 응답 원본 + 추출된 코드 + AI 설명. 로깅 실패는 generate_step 본래 동작을 막지 않음 (try/except + on_progress 알림만). `_safe_get_ai_engine_name()` 으로 mock/오류 시 fallback. test_70 (mock AI + 임시 LocalJsonRepository → tmp/conversations/ 에 .md 생성 + 모든 섹션 헤더 + session_id + 사용자 요청 + 코드 본문 검증). scenarios 70/70 + core 75/75 그린. **새 세션부터 모든 AI 호출이 자동 로깅됨 → 추후 디버깅·재현·프롬프트 품질 분석 가능**. |
| 5/5 (밤) | **AI 환각 import 자동 교정** (사용자 보고: 메모장 세션 OK 후 wooyang 브라우저 세션 선택 → 실행 시 `ImportError: cannot import name 'FindBestMatchException' from 'pywinauto.findbestmatch'` → 모든 step cascade fail). 원인: AI 가 pywinauto 의 존재하지 않는 exception 클래스명 (`FindBestMatchException`) 을 환각해서 `from pywinauto.findbestmatch import FindBestMatchException` 생성. 실제 이름은 `MatchError`. 라이브러리 블럭 ImportError → `from selenium...import Options` 등 후속 import 모두 skip → step 1 의 `Options()` NameError, step 2 의 `Application().connect()` 도 except 절에서 `FindBestMatchException` 참조하다 NameError. **윈도우↔브라우저 간섭 X — 단일 세션 내 환각 import 문제**. 3 layer fix: ① **workflow_engine.fix_hallucinated_imports** 신규 — `_HALLUCINATED_PYWINAUTO_NAMES = {'FindBestMatchException': 'MatchError'}` 매핑, 단어 경계 정규식으로 import + except 양쪽 자동 치환. self-멱등 (이미 교정된 코드 재변환 X). 라이브러리 블럭과 delta_code 양쪽에 적용 → 기존 wooyang 세션도 즉시 효과. ② **prompts.json guideline 19** — pywinauto 실제 exception 카탈로그 명시 (`MatchError`, `ElementNotFoundError`, `ElementAmbiguousError`, `WindowAmbiguousError`, `WindowNotFoundError`, `AppNotConnected`, `AppStartError`) + 환각 금지 강조 + 불확실하면 `Exception` 사용 권장. ③ test_68 (transform 동작 + 멱등 + 무관 코드 보존), test_69 (prompt 카탈로그 가이드). scenarios 69/69 + core 75/75 그린. |
| 5/5 (밤) | **picker descent 가드 + element resolution fallback** (사용자 보고: walk-up 해도 메뉴 클릭 안 됨, "부모 walk up 실패" 후 ElementNotFoundError). 원인 — picker 로그 분석: `EFP → MenuItem '파일' (area=4704)` 정상 검출 후 raw walker 가 더 작은 leaf TextBlock (area=1617) 으로 descend 해서 채택 → control_type='Text' 로 저장. 그러나 pywinauto `child_window(title='파일', control_type='Text')` 로는 그 leaf 못 찾음 (picker 는 uiautomation 직접 호출, pywinauto IUIAutomation 의 lazy resolution 경로 다름) → ElementNotFoundError. walk-up 코드는 `element.element_info` 접근 시점에 이미 실패. 2 layer fix: ① **element_picker 의 descent 가드** — `_CLICKABLE_CONTROL_TYPES` (MenuItem/Button/MenuBarItem/TabItem/ListItem/Hyperlink/Edit/등) frozenset + `_is_clickable_element()` helper. raw/descendants 폴백 + multi_backend 후보 비교에서 "현재 candidate 가 clickable 이고 새 candidate 는 비클릭" 이면 면적이 작아도 채택 거부. EFP 가 잡은 MenuItem '파일' 보존 → AI 가 `control_type="MenuItem"` 코드 생성 → pywinauto 정상 lookup. ② **win_inspector element resolution fallback** — `_resolve_element()` 함수 생성: 원본 selector → control_type 빼고 title-only → title_re 정규식 순으로 시도, 각 candidate 마다 `element_info.control_type` 강제 resolution 검증. 기존 세션 (control_type='Text' 저장된) 도 title-only fallback 으로 복구. test_66 (picker descent 가드 + clickable types + helper), test_67 (win_inspector resolution fallback chain). scenarios 67/67 + core 75/75 그린. PySide6 sync (sed 로 PyQt6→PySide6 import 변환). |
| 5/5 (밤) | **비클릭 leaf element 클릭 가능 부모 promote** (사용자 보고: Win11 메모장 [Text] "파일"/"보기" 메뉴 클릭 안 됨, 같은 메모장 [Button] "설정" 은 작동). 원인: picker 가 호버 시 가장 깊은 leaf (Text/Image/Pane) 를 잡는데 메뉴바의 "TextBlock 파일" 같은 leaf 라벨은 클릭 핸들러가 부모 MenuBarItem/MenuItem 에 있음 → leaf center 좌표 클릭이 hit-testing 죽은 영역에 떨어져 routed event 가 부모로 propagate 안 됨. [Button] "설정" 은 자체에 핸들러 있어 작동. 2 layer fix: ① **win_inspector template** — 클릭 직전 walk-up 패턴 추가. `_clickable_types = {Button, MenuItem, MenuBarItem, TabItem, ListItem, CheckBox, RadioButton, Hyperlink, Edit, ComboBox, SplitButton, TreeItem}`. element 의 control_type 이 set 에 없으면 최대 6 단계까지 parent() 로 walk up 해서 첫 클릭 가능 ancestor 를 `click_target` 으로. promotion 후 `click_target.rectangle()` 로 center 계산, fallback 도 `click_target.click()` 호출. 이미 클릭 가능한 타입은 promote 안 함 → 회귀 X. ② **prompts.json guideline 18** — Text/Image/Pane leaf → 부모 promote 패턴 강제. test_64 (template walk-up + click_target + clickable types + promote skip 회귀 검증), test_65 (prompt 가이드 영구). scenarios 65/65 + core 75/75 그린. **새 세션부터 메뉴바 라벨 / 아이콘 / 그룹 등 leaf 픽도 부모 클릭 핸들러 도달**. |
| 5/5 (밤) | **비브라우저 앱 title hardcoding fix — title_re program 명만 매칭** (사용자 보고: 새 메모장 세션 step 2 가 step 1 이 연 새 빈 메모장에서 보기 메뉴 못 찾음 → ElementNotFoundError). 원인: win_inspector 가 element 픽 시점의 full window title (예: `*hello world - 메모장`) 을 그대로 hardcode. step 1 이 새 메모장 열어 title 이 `제목 없음 - 메모장` 으로 바뀌니 connect 매칭 실패. 2 layer fix: ① **win_inspector 분기** — `is_browser_process` 면 full title 유지 (페이지별 식별), 아니면 `parent_title.split(' - ')[-1]` 로 program 명 추출 → `re.escape` 후 `title_re=r".*<program>"` 로 안전 매칭. 메모장 → `.*메모장`, IDE/계산기 등 동일. ② **prompts.json guideline 17** — full title hardcoding 금지 + program 명만 사용 강제 명시. 실측 검증: 메모장 `title_re='.*메모장'` / Chrome `title="업무전산 시스템 - Chrome"` (브라우저는 그대로). test_62 (template 패턴 검증), test_63 (prompt 가이드). scenarios 63/63 + core 75/75 그린. **새 세션부터 비브라우저 앱이 새/기존 인스턴스 무관 매칭**. |
| 5/5 (밤) | **데스크톱 click 전략 fix — pyautogui PRIMARY** (사용자 보고: Win11 메모장 "보기" 메뉴 클릭 안 됨). 원인: win_inspector 데스크톱 template 이 `element.click()` (WM 메시지 / UIA InvokePattern) 을 PRIMARY 로, pyautogui 는 권한 에러일 때만 fallback. UWP/XAML (Win11 메모장) 에서 element.click() 이 silent 실패 — 예외 안 나는데 클릭 효과 없음 → fallback 트리거 X → "보기" 메뉴 안 열림. 또 `control_type="Text"` 같은 라벨 컨트롤 클릭 시 부모 MenuItem 으로 invoke 전달 안 됨. 2 layer fix: ① **win_inspector.py 데스크톱/브라우저 통합 분기** — 둘 다 pyautogui.click(center_x, center_y) PRIMARY, element.click() fallback. pyautogui 의 OS 레벨 SendInput 이 좌표 hit-test 라 Text 라벨 → 부모 MenuItem 까지 자동 도달. ② **prompts.json system_context guideline 16** — element.click() silent 실패 함정 명시 + pyautogui PRIMARY 강제. test_60 (template 코드 검증 — element.click() 권한 fallback 패턴 부재 + pyautogui PRIMARY 명시), test_61 (prompt 가이드 영구성). scenarios 61/61 + core 75/75 그린. **새 세션부터 데스크톱 element 도 pyautogui.click 우선 → UWP 앱 메뉴/버튼 정상 클릭**. |
| 5/5 (밤) | **step_code/step_imports 누락 회귀 fix — 백업 패턴 복원** (사용자 보고: "웹브라우저 새로고침 현상이 2~3번 반복" + "각 step 에 이전 모든 step 코드들이 추가되는 형태"). 원인: ui_v2 redesign 시 [AppService.generate_step](../core/app_service.py#L370) 가 `generated_code` 만 채우고 `step_code`/`step_imports` 는 빈 채로 저장. 백업 [ohdo_20260505_backup/ohdo/ui/ai_call_handler.py:248~287] 에서는 AI 응답 받자마자 `extract_imports` + `extract_code_delta` 로 분리해서 step 별 delta + 새 import 만 저장. 현재는 비어있어 [extract_step_delta_code](../core/workflow_engine.py) 의 priority 1 (marker) 가 깨질 때 fallback 으로 priority 4 (전체 generated_code) → 누적 코드 전체 실행 → driver.maximize/get 중복 → 페이지 새로고침 반복. 회귀 fix: ① **AppService.generate_step 백업 패턴 이식** — `extract_imports`/`extract_code_delta`/`extract_import_delta` 호출, **last-non-empty step 을 prev 로 사용** (empty step 끼어 있어도 안전), 호출자 stale session 회피 위해 디스크에서 fresh load. ② **workflow_engine.execute_session_blocks** — empty step skip 시 `prev_step_dict` 갱신 X (다음 step 의 diff 가 깨지지 않게). test_58 (delta + 새 imports 분리), test_59 (empty prev step skip + last-non-empty 사용). scenarios 59/59 + core 75/75 그린. **새 세션부터 step_code/step_imports 자동 채워짐 → 라이브러리 카드 + step 카드 분리 아키텍처 복원**. |
| 5/5 (밤) | **SW_RESTORE → IsIconic 분기 fix** (사용자 보고: 'work.wooyang.co.kr' ID 입력 안 됨 + "전체창이 축소됨"). 원인: pywinauto template 의 `user32.ShowWindow(hwnd, 9)` (SW_RESTORE) 가 maximized Chrome 을 normal 사이즈로 축소 → 직전에 계산한 element 좌표 (1440, 901) 가 무효화 → 클릭이 빈 곳에 가서 focus 못 받음 → `pyautogui.write('doosung.oh')` 가 어디에도 안 들어감. step 3 (PW) 는 새로 좌표 재계산해서 정상 동작. 3 layer fix: ① **workflow_engine.make_show_window_safe** 신규 — 모든 `ShowWindow(hwnd_var, 9)` 를 `if user32.IsIconic(hwnd_var): SW_RESTORE; else: SW_SHOW` 로 자동 변환 (변수명/모듈 prefix 보존, 자기 멱등). ② **win_inspector.py 데스크톱/owner-drawn template** — IsIconic 분기 + element.rectangle() 호출을 활성화 후로 이동 (최신 좌표 보장). ③ **prompts.json system_context guideline 15** — SW_RESTORE 함정 명시 + IsIconic 권장 패턴 + 좌표 계산 순서 가이드. test_56 (transformer + 변수명/멱등/SW_HIDE 미변환), test_57 (prompt + template 영구 가이드). scenarios 57/57 + core 75/75 그린. **기존 세션도 다음 실행부터 즉시 효과**. |
| 5/5 (밤) | **다중 브라우저 회귀 fix — idempotent driver guard** (사용자 보고: "전체 실행" 후 웹브라우저가 3 개 띄워짐). 원인: step 1 의 `driver = webdriver.Chrome(...)` 가 매 실행마다 새 인스턴스 생성. "전체 실행" 두세 번 클릭하거나 silent replay 가 일어나면 누적. 누적된 다중 driver 가 step 2 의 `Application().connect(title="...")` ambiguous 도 유발. 3 layer fix: ① **workflow_engine.make_browser_init_idempotent** 신규 — 실행 직전 모든 delta_code/library_block 의 `driver = webdriver.{Chrome|Firefox|Edge|Safari|Remote}(...)` 호출을 paren-aware 로 추출해 `try: _ = driver.window_handles; except Exception: <원본 호출>` 가드로 감쌈. 이미 감싼 코드는 prefix 검사로 중복 적용 방지 (자기 멱등). 멀티라인/nested 호출/comment/string literal 전부 처리. ② **win_inspector.py 브라우저 템플릿** (line 449~) — 향후 AI 생성 코드도 idempotent 패턴으로 시작. ③ **prompts.json system_context guideline 14** — AI 에게 idempotent driver 패턴 명시 ("'전체 실행' 두 번 눌러도 1 개" 사용자 사례 포함). test_54 (transformer 동작 + 멱등성 + 멀티라인 + Firefox), test_55 (prompt + template 영구 가이드 회귀 안전망). scenarios 55/55 그린, core 75/75 유지. **기존 e862c477 세션도 다음 실행부터 즉시 효과** (코드 재생성 불필요). |

상세는 [docs/triage.md](triage.md) 참조.

## 6. 미해결 / 사용자 결정 대기

1. ~~**ROADMAP §1 라이선스 전략 결정**~~ → **2026-05-05 결정 확정**: 오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS). v1.0 은 100% AGPL-3.0, SaaS 유료/무료 라인은 Phase 2 진입 시점에 결정. (LICENSE 파일/코드 헤더 추가는 미실행 — 사용자 결정 대기)
2. **PySide6 포트 GUI 검증**: 양쪽 동작 비교 — 사용자 직접 GUI 테스트 필요. 별도 venv 없어서 import sanity 도 사용자 환경에서.
3. ~~**foreground 복원 보류**~~ → **5/4 저녁 해결됨** (§4.5 참조). 사용자 GUI 테스트 통과.
4. **5/4-5/5 작업 사용자 GUI 검증 미확인**: 다음 항목들은 자동 회귀 테스트는 그린이지만 실제 GUI 동작은 사용자 테스트 미완료 — 새 세션에서 첫 sanity check 시 같이 확인하면 좋음:
   - 코드 편집 desync 4중 안전장치 (§4.8) — 블럭 뷰/코드 뷰에서 코드 수정 → 양쪽 동기화 + 실행 정확
   - 세션 추가/삭제 시 블럭 뷰 초기화
   - 실행 종료 시 run/stop 버튼 자동 리셋 (코드 뷰 + 블럭 뷰 양쪽)
   - Gemini CLI 모델 명시 — `gemini-2.5-flash` 로 명시 호출되는지 (5/5: `_build_args` 가 두 production path 에 적용됨, source 검증 test_71 통과 — 실 capacity 회귀 재현 여부 사용자 확인)
   - **Phase 2.5: Initial 블럭 단독 실행** (§4.9) — Initial 블럭 카드의 "⏯ 단독" 버튼 클릭 → driver/options 등 재초기화되는지. 라이브러리 미초기화 상태 / 초기화된 상태 양쪽 시나리오 확인. 다른 step status 안 건드리는지.
4. **PySide6 양쪽 동기화 정책**: 코드 수정 시 어디 먼저 적용할지. 현재 PyQt6 원본 먼저 → 수동 sed 로 sync (자동 스크립트 없음).
5. **API key 저장 위치 (D2 후속)**: 현재 `settings.json` 평문. OS keyring (Windows Credential Manager) 으로 옮길지 사용자 결정 대기. v1.0 공개 전 결정 권장 (보안 디폴트).
   - **2026-05-13 진척**: [ADR 0003](saas/decisions/0003-secrets-handling.md) + [설계 — Phase 1+2](saas/architecture/24-secrets-phase-1-2.md) 작성 — API key 와 사용자 시크릿 (ID/PW/토큰) 을 동일 vault (KeyringVault) 의 다른 namespace 로 통합 (`ohdo:apikey:<engine>` vs `ohdo:secret:<label>`) 권장. ADR Proposed 상태 — 사용자 검토 후 Accepted 전환 + Phase 1 (1일) → Phase 2 (3일) → Phase 3 (3일) 순.
6. **장기 AI 모델 (D2 후속)**: BYO API 키만 / ohdo 크레딧 SaaS / 둘 다 — 미정. 현 어댑터는 BYO 우선 설계지만 SaaS 모드 ('proxy' base_url) 로 확장 가능.

## 7. 다음 작업 후보 (우선순위 순)

| 우선순위 | 작업 | 비고 |
|---------|------|-----|
| 1 | **ui_v2 사용자 GUI 검증** — `python main.py --ui v2` 실행 → 와이어프레임 의도와 비교. **이제 실 동작**: AI 호출 / 전체+단독+여기서부터 실행 / 캡처 / 요소픽 / Settings 모두. 어색한 부분 / 빠진 인터랙션 / 디자인 토큰 fine-tune 피드백. | 핵심 검증. PoC 의 stub 영역은 D8 Command palette / D9 토스트 / D14 onboarding 등 미구현 항목만. |
| 2 | **AppService 후속** — 미흡한 분리 영역 추가. `export_workflow` (D22 의 stub 채우기 — main.py + requirements.txt + run.bat 패키징, v1 export_project 활용), `import_workflow` (외부 폴더에서 세션 import). | D22 의 export 가 현재 폴더 통째로 복사 stub. 정식 패키징 필요. |
| 4 | **UI redesign 준비 Step 0 #3: baseline UI 스크린샷** — `data/baseline_ui/` 에 v1 메인 화면 + 다이얼로그들 캡처. 시각 비교 baseline. | 사용자 GUI 작업 (Claude 가 캡처 못 함). |
| 5 | **Excalidraw/Figma 정식 와이어프레임** — wireframes_v2.md 텍스트 → 시각. ui_v2 PoC 와 병행. | 사용자 작업 권장. |
| 6 | AI prompt 강화 + delta fix 효과 측정 — `ai_integration` suite 으로 실제 생성 코드 검증 | 5/4 밤 가이드/필터 추가 후 실 데이터로 회귀율 확인. |
| 7 | LICENSE 파일 (AGPL-3.0) + README 라이선스 섹션 + 모든 source 파일 SPDX 헤더 | Phase 0 시작 시 묶어서 처리 권장 (uv/devcontainer/CI 와 함께). |
| 8 | Phase 0 본격 진입 — `pyproject.toml + uv`, devcontainer, pre-commit, GitHub Actions CI | ROADMAP Phase 0. 데스크톱 안정화 ~80% 도달 시. |
| 9 | SaaS M3.2+ 재개 | Phase 0/1 완료 후. |
| 10 | **AI 자동 에러 복구 기능** (5/6 사용자 아이디어) — step 실행 중 에러 발생 시 AI 가 에러 메시지 + 해당 step 코드 + 누적 컨텍스트 보고 자동으로 코드 수정 + 재시도. | `prompts.json` 의 `error_recovery` 템플릿 (line 6) 은 이미 존재하지만 자동 trigger 없음. 설계 필요: (a) 자동/수동 trigger 토글, (b) retry budget (예: 최대 2회), (c) 사용자 confirm 옵션, (d) 어떤 에러를 자동 처리하고 어떤 건 사용자 개입 요청할지 분류. AppService.generate_step 흐름에 통합. |

**5/5 완료**:
- ~~Gemini adapter `_build_args` production path 적용~~ — 두 Popen 호출 모두 `_build_args` 경유, test_71 production path 검증 추가.
- ~~ROADMAP §1 라이선스 전략 결정~~ — 오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS) 확정.
- ~~Phase 2.5: Initial 블럭 단독 실행~~ — INITIAL_BLOCK_STEP_ID=-1, BlockCard 단독 버튼 확장, on_run_initial_block + library 자동 선행. test_74 (74/74 그린).
- ~~UI redesign Step 0 #1: feature_catalog.md~~ — 현재 UI 전체 카탈로그 (14 섹션). 사용자 검증 후 Step 0 #2/#3 진행.
- ~~D2 OpenAI 호환 어댑터 구현~~ — `OpenAICompatAdapter` + 9 프리셋 + Settings UI. test_75 (75/75 그린).
- ~~UI redesign 13건 일괄 결정 (D4~D16)~~ — feature_catalog.md §13 미결정 0건.
- ~~Step 0 #2: tests/test_scenarios.py~~ — 16 시나리오 behavior-level 테스트. scenarios suite 등록, 16/16 그린.
- ~~D 와이어프레임 1차 초안: wireframes_v2.md~~ — 텍스트 와이어프레임 12 섹션.
- ~~D17~D26 + onboarding 확정~~ — 와이어프레임 도중 발견 10건 + onboarding 추천 3개 모두 권장안.
- ~~Step 1: AppService façade 확장~~ — 코드 추출/실행/AI ops 메서드 추가. test_scenarios 20/20. ADR 0001 준수 (기존 UI 미수정).
- ~~ui_v2 PoC 1차 슬라이스~~ — 메인 윈도우 + 카드 + 입력 + 단축키 + Initial 단독 실행 동작. `--ui v2` 분기. test_21~23. scenarios 23/23.
- ~~D3 데이터 모델 + ui_v2 AI 호출~~ — Step 에 user_request/ai_description 필드, AppService.generate_step, ui_v2 메시지 전송 실 동작. test_24~26. scenarios 26/26.
- ~~ui_v2 실행 stub 채우기~~ — AppService.run_blocks/stop_blocks, ui_v2 _on_run_all/from/single/stop 실 동작. test_27~28. scenarios 28/28.
- ~~ui_v2 캡처/요소픽/Settings stub 채우기~~ — v1 overlay/dialog 재사용. pending images/elements + chip 갱신. test_29~30. scenarios 30/30.
- ~~ui_v2 카드 가로 스크롤 회귀 fix~~ — 사용자 보고. 4 fix 적용 (sizePolicy, _tame_text_widget, scroll AlwaysOff, AI preview QLabel).
- ~~D9/D17/D20/D25 일괄 구현~~ — Toast/ToastManager, 사용자 요청 클릭 재생성, 사이드바 toggle persist, 빈 상태 + 예시 카드. test_31~33. scenarios 33/33.
- ~~D8 Command palette + D14 Onboarding wizard~~ — Ctrl+K 실 호출 + 첫 실행 wizard. test_34~36. scenarios 36/36. ui_v2 의 D 결정 거의 cover (D4 다중 세션 탭만 별도).
- ~~D4 다중 세션 탭 + D21 + D22~~ — QTabBar + 세션별 커널 dict + 탭별 pending state + + 탭 메뉴 + 우클릭 메뉴. test_37~39. scenarios 39/39. **D1~D26 거의 cover** (D23 drag reorder 만 남음).
- ~~D23 step reorder ⬆⬇ 버튼 fallback~~ — drag-drop 의 일부. 버튼만 먼저, drag-drop 본체는 후속. test_40. scenarios 40/40.
- ~~사용자 보고 fix + 전송/중지 토글~~ — 캡처 버튼 가시성, elempick 강제종료 fix, send_btn 토글. test_41. scenarios 41/41.
- ~~D23 drag-drop 본체~~ — CardDropContainer + StepCardV2 drag source + AppService.reorder_step. test_42. scenarios 42/42. **D1~D26 100% cover**.
- ~~Syntax highlighting + 코드 편집~~ — v1 의 PythonHighlighter + BlockCard 편집 토글 패턴 v2 에 이식. test_43. scenarios 43/43.
- ~~세션 영구 삭제~~ — _on_session_delete + 사이드바 우클릭 + 탭 우클릭 메뉴. test_44. scenarios 44/44.

## 8. 첫 작업 권장

새 세션에서 추천 흐름:

1. **이 파일 + docs/triage.md 빠르게 읽기**
2. `venv\Scripts\python.exe -m tests.test_runner --suite core` (75/75) + `--suite scenarios` (70/70) 실행 → **baseline 무손상 검증**. venv 경로는 `venv/` (점 없음).
3. 사용자에게 직전 GUI 테스트 결과 확인 (§11 참조).

## 11. 5/5 밤 ~ 5/6 새벽 작업 인계 (이전 세션 마지막)

**컨텍스트**: 사용자가 ohdo 의 메모장/브라우저 자동화 시나리오를 반복 테스트하면서 발견된 회귀들을 8 layer 로 fix. 매 fix 후 사용자가 새 세션 만들어 검증하는 루프 진행. 마지막 작업은 [tmp/conversations/](../tmp/conversations/) 자동 로깅 추가 — 다음 사용자 테스트부터 prompt + AI 응답이 자동 저장됨.

**적용된 8 layer fix (모두 PyQt6 + PySide6 sync, scenarios 70/70 + core 75/75 그린)**:

| # | fix | 영향 | 검증 |
|---|-----|------|------|
| 1 | idempotent driver guard ([workflow_engine.make_browser_init_idempotent](../core/workflow_engine.py)) | "전체 실행" 두세 번 클릭 또는 silent replay 시 새 브라우저 안 뜸 | test_54/55 |
| 2 | SW_RESTORE → IsIconic 분기 ([workflow_engine.make_show_window_safe](../core/workflow_engine.py) + win_inspector template) | maximized 창이 normal 로 축소되어 좌표 무효화되는 회귀 방지 | test_56/57 |
| 3 | step_code/step_imports 분리 ([AppService.generate_step](../core/app_service.py)) — 백업 패턴 복원 | 라이브러리/step 카드 분리 아키텍처 회복, 새로고침 반복 회귀 fix | test_58/59 |
| 4 | 데스크톱 click pyautogui PRIMARY (win_inspector template) | UWP/XAML 의 element.click() silent 실패 회피 | test_60/61 |
| 5 | 비브라우저 title_re program 명 매칭 (win_inspector) | 메모장처럼 title 에 문서 내용이 들어가는 앱 매칭 안정화 | test_62/63 |
| 6 | leaf element 클릭 가능 부모 walk-up promote (win_inspector + picker descent 가드) | Text 라벨 픽 → 부모 MenuItem 으로 자동 promote | test_64/65/66/67 |
| 7 | AI 환각 import 자동 교정 (workflow_engine.fix_hallucinated_imports) | `FindBestMatchException` → `MatchError` cascade fail 방지 | test_68/69 |
| 8 | tmp/ 정리 + AI 대화 자동 로그 (AppService._save_conversation_log) | generate_step 마다 prompt + 응답 단일 .md 로 저장 | test_70 |

**사용자 검증 상태 (다음 세션에서 첫 확인)**:
- ✅ 메모장 메뉴 (파일/보기) 클릭 — 5/6 새벽 picker descent 가드 fix 후 정상 (사용자 확인됨)
- ⚠️ wooyang 브라우저 세션 (eb17030a) — `FindBestMatchException` cascade 회귀. 다시 실행하면 workflow_engine 의 hallucinated_imports 교정으로 자동 복구돼야 함. **사용자 미검증**.
- ⚠️ tmp/conversations/ 로그 — 신규 기능. 다음 사용자 테스트 시 실제 .md 파일 생성 확인 필요.

**미해결 / 후속 후보**:
- guideline 14~19 가 prompts.json system_context 에 누적돼 있음. AI 가 매번 1.7만~2만자 이상의 거대한 프롬프트를 받고 있어 응답 속도/품질 영향 우려. **다음 작업 후보**: 가이드라인 통합/압축 검토.
- 기존 wooyang 세션은 step_code 가 비어있어 (이전 generate_step 시 백업 패턴 미적용 시점) 일부 fallback 경로만 사용. 새로 생성하는 세션부터 정상 분리.
- ui_v2 GUI 사용자 테스트 미검증 (§6 #4 항목들). 메모장/브라우저 시나리오 외에 다른 워크플로우 (계산기/IDE 등) 검증 필요.

**5/6 새 세션에서 권장 첫 행동**:
1. baseline 테스트 (`core` + `scenarios`) 실행해서 그린 확인
2. 사용자에게 "어제 fix 들 (특히 8 layer 마지막 — wooyang 세션 재실행 + tmp/conversations 로그 확인) 어떻게 됐는지" 물어보기
3. 그에 따라 후속 fix 또는 다음 작업 후보 (§7) 진입

## 12. 5/6 일과 작업 누적 정리 (prompt 압축 + 모델 변경 + element 메타 강화)

**컨텍스트**: 5/6 종일 사용자 GUI 테스트 + 가이드 강화 루프 + prompt size 폭증으로 인한 Gemini corrupt 응답 root fix. 최종적으로 9 step 까지 깨짐 없이 진행 가능 + prompt size 28% 감소 + AI 응답 quality 회복.

### 적용된 fix (시간순)

| # | 작업 | 영향 | 위치 |
|---|---|---|---|
| 1 | **prompts.json system_context 압축** — 가이드 19개 누적 정상화 (1~19 정상순서, 메타 정보 제거, #11+#19 / #15+#16 통합) + archive 보존 (`config/prompts_archive/prompts_2026-05-06_pre-compression.json`) | 5,911 → 4,900 chars 시작 (이후 가이드 강화로 늘어남) | [config/prompts.json](../config/prompts.json), [config/prompts_archive/](../config/prompts_archive/) |
| 2 | **#13 ASCII/CJK 분기** — `pyautogui.write` 한글 silent skip → ASCII 만 write, CJK 는 `pyperclip.copy + Ctrl+V` | 한글 텍스트 입력 정상화 | prompts.json #13, [core/win_inspector.py](../core/win_inspector.py) (입력 템플릿) |
| 3 | **#14 데스크톱 idempotent + UWP wait 안정성** — 가이드 #14(b) Application.connect try/except 강제, #14(c) UWP `wait('visible')` 권장 | "메모장 실행" 매번 새 인스턴스 회귀 fix | prompts.json #14 |
| 4 | **#18 다이얼로그 처리 트리거** — 5가지 트리거 (자연어 조건/명시 키워드/picker context mismatch/직전 step modal flow/`parent_window_control_type='Dialog'`) + `_find_dialog` 패턴 | 모달 다이얼로그 자동 분기 처리 | prompts.json #18 |
| 5 | **#19 hotkey 표준 키 이름** — `'control'` (X) / `'ctrl'` (O) 명시 + ✅/❌ 예시 | Ctrl+Shift+S 같은 단축키가 's' 만 입력되는 회귀 fix | prompts.json #19 |
| 6 | **prompt_builder 환경 정보** — `_build_env_info_lines()` cache 추가. Python/pywinauto/selenium/pyautogui/pyperclip 버전 자동 detect 후 매 prompt prepend | AI 가 정확한 라이브러리 시그니처 사용 | [core/prompt_builder.py:23](../core/prompt_builder.py#L23) |
| 7 | **#11 메서드 시그니처 명시** — `Application.connect`/`window`/`Desktop().window`/`child_window`/`wait`/`find_elements` 가 받는 kwargs 정확히 나열. timeout 받는 곳 ✅/안 받는 곳 ❌ | `Desktop().window(timeout=N)` invalid kwarg 회귀 fix | prompts.json #11 |
| 8 | **F-3 변수 명명 규칙** — `app` = `Application` 객체, `win` = `WindowSpecification`. `Desktop().window(...)` 결과는 `win` 으로 명명 (절대 `app` 으로 X — 후속 step 의 `app.window()` 호출이 자식 검색이 되어 0 windows found 회귀) | prompt_builder 의 Windows 가이드와 system_context 일관성 회복 | prompts.json #14(b), [core/prompt_builder.py:248](../core/prompt_builder.py#L248) |
| 9 | **E-1 새 step 강제** — "사용자의 새 요청은 누적 코드와 동일해 보여도 반드시 새 step 마커 + 본문 추가" 명령. 빈 step / step 생략 금지 | AI 가 같은 요청 반복 시 새 step 안 만들고 누적 코드만 반환하는 회귀 fix | [core/prompt_builder.py:124](../core/prompt_builder.py#L124) |
| 10 | **E-2 extract_step_delta_code fallback 차단** — generated_code 전체 fallback 을 `prev_step is None` (첫 step) 만 valid 로 제한. prev_step 있으면 빈 string 반환 (fail-fast) | AI 가 새 step 안 만들 때 누적 코드 통째 step_code 저장되는 회귀 fix | [core/workflow_engine.py:1141](../core/workflow_engine.py#L1141) |
| 11 | **자동 교정 확장** — `fix_hallucinated_imports` 가 `FindBestMatchException` + `FindBestMatch` + `FindBestMatch.MatchError` 모두 `MatchError` 로 변환 | AI 의 새 환각 패턴 (5/6) 자동 fix | [core/workflow_engine.py:1029](../core/workflow_engine.py#L1029) |
| 12 | **picker parent_window_control_type capture + Dialog 안내** — `top_level_parent().element_info.control_type` 도 capture. element_context 에 모달 다이얼로그 안내 추가 (가이드 #18 자동 트리거) | picker 가 dialog 안 element 잡으면 AI 가 자동으로 `_find_dialog` 패턴 사용 | [ui/element_picker.py:1227](../ui/element_picker.py#L1227), [core/win_inspector.py:633](../core/win_inspector.py#L633) |
| 13 | **format_element_label helper** — chat_panel/ai_call_handler/ui_inspection_handler 의 inline element 표시 로직 통합. Dialog 부모 인 경우 "(Dialog: ...)" suffix, name 없으면 parent_title 빌림 | UI 표시 일관성 + 정보 풍부 | [core/win_inspector.py:38](../core/win_inspector.py#L38) (helper) + ui/ 3 파일 |
| 14 | **win_inspector 텍스트 입력 placeholder 강화** — `text = 'your_text_here'` → `text = '<<USER_TEXT>>'`. ⚠ 명시 + 조건부 사용 명령 + 키 입력 전용 가이드 분리 | AI 가 placeholder template 을 그대로 코드에 박는 회귀 fix | [core/win_inspector.py:898](../core/win_inspector.py#L898) |
| 15 | **prompt 본문 압축** — `_compress_accumulated_code(keep_last_n=1)` 추가. 마지막 1 step body 만 keep, 이전 step body → 한 줄 마커 (`# === Step N: <task> (본문 생략 — 이미 실행됨) ===`) | prompt 35K → 26K (28% 감소). step 수 늘어도 선형 증가 X | [core/prompt_builder.py:688](../core/prompt_builder.py#L688) |
| 16 | **이미지 첨부 OFF** — `AppService.generate_step` 이 AI 호출 시 `images=None` 전달 (session log 에는 path keep, UI 표시 + 미래 image-based matching 시 활용) | vision latency 5-15s 감소 + Gemini context 부담 감소 | [core/app_service.py:418](../core/app_service.py#L418) |
| 17 | **모델 변경: gemini-2.5-flash → gemini-3.1-pro-preview** + 회귀 가드 완화 (`startswith("gemini-2")` → `startswith("gemini-")`. CLI default 자동 매핑은 여전히 차단, 사용자 명시 preview 만 허용) | 응답 quality 향상 (corrupt/broken 회피). latency 증가 trade-off | [config/settings.json:7](../config/settings.json#L7), [tests/test_core.py:2293](../tests/test_core.py#L2293) |
| 18 | **AppService.save_session 추가** — handoff §3 에 명시됐지만 누락된 메서드. ui_v2 의 세션 이름 변경 등에서 AttributeError 발생 fix | 세션 rename + 사이드바 액션 정상 작동 | [core/app_service.py:78](../core/app_service.py#L78) |

### 검증 결과 — 9 step 세션에서 압축 효과 확인

| 비교 | 압축 전 (9f08ab5d, 8 step) | 압축 후 (de751707, 9 step) |
|---|---|---|
| 평균 prompt | 27,926자 | **23,700자** |
| 최대 prompt | 35,995자 (step 7 corrupt) | **26,427자 (step 9 정상)** |
| step 7 응답 | 24자 (`<ctrl46>` corrupt) | 5,301자 (정상) |
| step 8 응답 | 26,203자 (broken IndentationError) | 5,678자 (정상) |
| 9 step 도달? | ❌ corrupt 7 / broken 8 | ✅ 정상 |

**선형 증가 곡선 → flat 곡선** 으로 전환. step 7-8 기준 ~28% 감소.

### 회귀 가드 갱신
- core 75/75 ✅ / scenarios 70/70 ✅
- test_71 (gemini model) — `gemini-` prefix 만 검증 (preview 허용)

### 미해결 / 후속 작업

**후보 (handoff §7 #10)**: AI 자동 에러 복구 기능 — step 실행 실패 시 AI 가 자동 코드 수정 + 재시도. `prompts.json` 의 `error_recovery` 템플릿은 이미 존재, trigger 흐름만 추가 필요.

### 5/6 → 5/7 새 세션 시작 권장 흐름

1. `core` + `scenarios` baseline 그린 확인 (75/75 + 70/70)
2. 사용자에게 "5/6 fix 들 GUI 검증 결과 어떻게 됐는지" 묻기 (특히 prompt 압축 효과 + 모델 변경 후 응답 quality)
3. 그 결과에 따라:
   - 사용자 만족 → 다음 작업 후보 (§7) 진입 (Phase 0 / D2 / AI 자동 에러 복구 §10 등)
   - 추가 fix 필요 → 사용자 보고 분석 + fix

## 13. 5/7 D22 export/import 워크플로우 정식 구현

**컨텍스트**: 5/6 GUI 검증 결과 큰 문제 없음 → §7 후속 작업 진입. §7-10 (AI 자동 에러 복구) 는 사용자 보류 → §7-2 진행.

### 적용된 변경

| # | 작업 | 영향 | 위치 |
|---|---|---|---|
| 1 | `SessionManager.export_as_project` 확장 — session.json + captures/ + scripts/ 도 같이 복사 | export 결과가 실행 가능 + import 가능 단일 번들 | [core/session_manager.py:527](../core/session_manager.py#L527) |
| 2 | `SessionManager.import_session_folder` 신규 — 외부 export 폴더 → 새 UUID 로 data/sessions/ 복사 + 옛 UUID 일괄 치환 (captures 절대 경로 cover) | 다른 PC 워크플로우 가져오기 가능. 같은 export 두 번 import 도 충돌 X | [core/session_manager.py](../core/session_manager.py) |
| 3 | `AppService.export_workflow(session_id, output_dir, settings=None)` + `import_workflow(source_dir, new_title=None)` 신규 façade | UI 가 단일 진입점만 의존 (ADR 0001 준수) | [core/app_service.py](../core/app_service.py) |
| 4 | ui_v2 `_on_tab_export` 교체 — stub `shutil.copytree` → `app_service.export_workflow` | D22 stub 정식판으로 승격 | [ui_v2/main_window_v2.py:1453](../ui_v2/main_window_v2.py#L1453) |
| 5 | ui_v2 `_on_import_workflow` 신규 + + 탭 메뉴 "📥 워크플로우 가져오기..." 액션 | 가져오기 짝 추가 | [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) |
| 6 | core test_76 (export 결과 main.py + session.json + captures 모두 검증), test_77 (import 새 UUID + 절대경로 재작성 + new_title) | 회귀 가드 | [tests/test_core.py](../tests/test_core.py) |
| 7 | scenarios test_71 (`_on_tab_export` 가 AppService 사용 + stub copytree 제거 검증), test_72 (가져오기 액션 + AppService 호출 검증) | 회귀 가드 | [tests/test_scenarios.py](../tests/test_scenarios.py) |

### export 결과 폴더 구조

```
{title}_{session_id_short}/
├── main.py                # 실행 가능 코드 (기존)
├── requirements.txt       # 패키지 목록 (기존)
├── README.md              # 가이드 (기존)
├── run.bat                # 윈도우 실행 스크립트 (기존)
├── session.json           # 🆕 가져오기 메타
├── captures/              # 🆕 스크린샷 (있을 때)
└── scripts/               # 🆕 원본 스크립트 (있을 때)
```

### 회귀 가드 갱신
- core 77/77 ✅ / scenarios 72/72 ✅
- PySide6 port sync 완료 (`cp` for core/, `sed` for ui_v2/)

### §7-6 ai_integration suite 실측 (5/7)

**결과**: 9/9 PASS — 5/6 fix 회귀 X. 단, 두 가지 테스트 인프라 fix 발견.

| # | 발견 | 원인 | fix |
|---|---|---|---|
| 1 | test_01/test_08 가 `'cp949' codec can't encode '—'` 로 ERROR | Windows 콘솔 cp949 가 AI 응답의 em-dash 처리 불가 | [tests/test_runner.py](../tests/test_runner.py) 모듈 로드 시 `sys.stdout/stderr.reconfigure(errors='replace')` |
| 2 | test_08 의 `_validate_generated_code` 가 `import` 무조건 강제 → trivial 코드 (예: `print(sum(range(1,11)))`) 에서 false negative | AI 가 합리적으로 unnecessary import 생략한 경우도 fail | [tests/test_ai_integration.py](../tests/test_ai_integration.py) `import` 검증을 hard assert → soft `[INFO]` log (try/except/print 패턴과 일관) |

각 step 의 AI 응답 자체는 모두 합격 — prompt 압축 + 모델 변경 + 가이드 강화의 실 효과 확인.

### §7-7 부분 (5/7) — LICENSE + README

| 작업 | 위치 |
|---|---|
| AGPL-3.0 공식 텍스트 (gnu.org 661 line) | [LICENSE](../LICENSE) + [pyside6_port/LICENSE](../pyside6_port/LICENSE) |
| 루트 README.md — 프로젝트 소개 + 설치/실행 + 테스트 + 로드맵 + 라이선스 섹션 | [README.md](../README.md) |
| **SPDX 헤더** | Phase 0 sub-phase 3 으로 이관 (ruff/pre-commit 도구 셋업 후 일괄) |

### §7-8 Phase 0 sub-phase 1 (5/7) — pyproject.toml + uv

**컨텍스트**: ROADMAP §7.2 의 권장 스택 도입 시작. 이후 Sub-phase 2 (pre-commit + ruff) → 3 (SPDX 헤더) → 4 (GitHub Actions CI) → 5 (devcontainer) 순서.

| 변경 | 위치 | 효과 |
|---|---|---|
| `pyproject.toml` 신규 — `[project]` 메타 + `dependencies` (requirements.txt 이주) + `[tool.uv] package = false` (Phase 1 의 `core/` 분리 전까지 packaging 비활성) | [pyproject.toml](../pyproject.toml) | uv / Dependabot / 보안 스캐너가 인식하는 표준 메타 |
| `uv.lock` 생성 (1050 line, 64 packages 해석) | [uv.lock](../uv.lock) | 재현 가능한 정확한 버전 고정 |
| pyside6_port 도 같은 패턴 — `pyside6_port/pyproject.toml` + `pyside6_port/uv.lock` (PyQt6 → PySide6 만 차이) | [pyside6_port/pyproject.toml](../pyside6_port/pyproject.toml) | 라이선스 비교 baseline 유지 |
| README + handoff §2 install 흐름 갱신 — `uv sync` 권장, 레거시 `venv/` 도 그대로 유지 | [README.md](../README.md), 본 §2 | 사용자 muscle memory 보호 + 신규 setup 은 권장 path |

**검증**:
- core 77/77 ✅ + scenarios 72/72 ✅ (양쪽 venv 모두 — 레거시 `venv/` + uv-managed `.venv/`)
- pyside6_port 의 `uv.lock` 은 lockfile 만 생성 (`.venv/` 미설치 — 사용자가 `uv sync` 시점에 활성화)

### §7-8 Phase 0 sub-phase 2 (5/7) — pre-commit + ruff

**컨텍스트**: lint + format 자동화. mypy 는 Phase 1 의 type hint 도입과 묶음.

| 변경 | 위치 | 효과 |
|---|---|---|
| `pyproject.toml` 의 `[tool.ruff]` 섹션 — 보수적 ruleset (E/F/W/I) + per-file-ignores (E402 in tests/ + ui/main_window.py, F401 in element_picker.py + ws_client.py) + `[tool.ruff.format]` (double quote) | [pyproject.toml](../pyproject.toml) | 30K 라인 legacy 에 너무 엄격하게 켜는 것 회피, Phase 1 type hint 시 점진 강화 |
| `[project.optional-dependencies].dev` — `ruff>=0.6.0` + `pre-commit>=3.7.0` | [pyproject.toml](../pyproject.toml) | `uv sync --extra dev` 로 dev 도구 일괄 설치 |
| `.pre-commit-config.yaml` 신규 — ruff lint+format + 표준 위생 hooks (trailing-whitespace, end-of-file-fixer, large file guard 1MB) | [.pre-commit-config.yaml](../.pre-commit-config.yaml) + [pyside6_port/.pre-commit-config.yaml](../pyside6_port/.pre-commit-config.yaml) | 매 commit 자동 검증 |
| `ruff check --fix` 1회 일괄 적용 — 520 issue 중 468 auto-fix | 코드베이스 전체 | I001 (import 정렬) 270, F541 54, W293 38, F401 105 등 자동 수정 |
| 남은 47 manual issue 처리 — `l` → `ln` (E741), 디버그 docstring 공백 (W293), `ovr_geo`/`x_log,y_log` 미사용 변수 제거 (F841), unused `Qt` import 제거 (F401), per-file-ignore 추가 | core/import_manager.py + core/workflow_engine.py + ui/element_picker.py + main.py + tests/test_ai_integration.py | 0 lint issue 도달 |
| `ruff format` 1회 일괄 적용 — 106 파일 reformat (double quote, indent, line break 표준화) | 코드베이스 전체 | 향후 incremental 변경만 format 검사 |
| 3 scenarios 테스트 fix — format 으로 깨진 string-pattern matching (test_43/44/66) 을 quote/whitespace-agnostic 으로 갱신 | [tests/test_scenarios.py](../tests/test_scenarios.py) | format 무관 검증 |
| pyside6_port sync — pyproject.toml/.pre-commit + 모든 코드 reformat (uv.lock 75 packages 재해석) | [pyside6_port/](../pyside6_port/) | 양쪽 일관성 |
| `pre-commit install` 실행 — `.git/hooks/pre-commit` 등록 | (git config) | 매 commit 시 자동 검증 발동 |

**검증**:
- ruff check . → All checks passed! (0 issue)
- ruff format --check . → 114 files already formatted (0 diff)
- core 77/77 ✅ + scenarios 72/72 ✅
- mypy 보류 (Phase 1 type hint 도입 시점에 추가)

### §7-8 Phase 0 sub-phase 3 (5/8) — SPDX 헤더 일괄

**컨텍스트**: 모든 `.py` 파일에 `# SPDX-License-Identifier: AGPL-3.0-or-later` 추가. 향후 dual-licensing / 법무 검토 / 외부 코드 유입 차단의 법적 근거.

| 작업 | 결과 |
|---|---|
| 일회용 스크립트 (`.tmp_spdx_apply.py`) — shebang 다음 줄 OR 첫 줄 삽입. 제외: `venv/`, `.venv/`, `ohdo_20260505_backup/`, `packages/`, `tmp/`, `data/`, 루트 debug 스크립트 (test_click_diagnosis.py 등) | 113개 .py 파일 일괄 추가, 0 skip (이미 있는 파일 X) |
| Python `write_text()` 가 Windows 에서 CRLF 로 쓰는 문제 → ruff format 으로 LF 통일 | 113 files reformatted |
| 스크립트 실행 후 즉시 삭제 (`.tmp_spdx_apply.py` 정리) | 일회성 작업 정리 |

**검증**:
- 113 .py 파일 모두 SPDX 라인 포함 (grep 검증)
- ruff check . → All checks passed!
- ruff format --check . → 114 files already formatted
- core 77/77 ✅ + scenarios 72/72 ✅

**적용 위치 예시** (shebang 유무 분기):
```python
# main.py (shebang 있음):
#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI RPA Solution - Main Entry Point ..."""

# core/app_service.py (shebang 없음):
# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI·서버 공용 애플리케이션 진입점 (Facade) ..."""
```

### §7-8 Phase 0 sub-phase 4 (5/8) — GitHub Actions CI

**컨텍스트**: 매 push / PR 마다 자동 회귀 가드. main 머지 전 lint + test 통과 강제.

| 변경 | 위치 | 효과 |
|---|---|---|
| `.github/workflows/ci.yml` 신규 — 3 job 매트릭스: `lint`(ubuntu) + `test-ubuntu` + `test-windows` | [.github/workflows/ci.yml](../.github/workflows/ci.yml) | push/PR 자동 검증 |
| `lint` job — `ruff check .` + `ruff format --check .` (빠른 피드백, ~30s) | (위 파일) | lint 실패 시 test job 차단 (`needs: lint`) |
| `test-ubuntu` job — Qt system deps (libgl1/libegl1/libxkbcommon0/libdbus-1-3/libfontconfig1/libxcb-cursor0) + `QT_QPA_PLATFORM=offscreen` 환경 + uv sync + core/scenarios 실행 | (위 파일) | cross-platform 회귀 검증 (Phase 1+ backend Linux 호환성 사전 확보) |
| `test-windows` job — uv sync + core/scenarios (pywinauto/pyautogui 의존성 native 검증) | (위 파일) | Windows-specific 동작 검증 |
| 테스트 결과 artifact 업로드 — `tests/results/*.json` 14일 보관 | (위 파일) | CI 실패 시 결과 디버그 가능 |
| README CI 배지 추가 — CI status / AGPL v3 / Python 3.12+ | [README.md](../README.md) | 프로젝트 상태 visibility |

**보류**:
- `ai_integration` suite — Gemini CLI 셋업 + API key secret 필요 (로컬 수동 유지)
- GUI 자동화 suite (notepad/calculator/browser) — Windows GUI 환경 필수
- `pyside6_port` — venv 미설치 (사용자 수동 셋업). CI 미포함

**검증** (로컬):
- ruff check . → All checks passed!
- ruff format --check . → 114 files already formatted
- `uv run python -m tests.test_runner --suite core` → 77/77 ✅
- `uv run python -m tests.test_runner --suite scenarios` → 72/72 ✅
- ci.yml YAML 유효성 검증

**최초 commit / push 시**:
- GitHub Actions 가 자동 트리거됨. 첫 ubuntu test 가 PyQt6 system deps 누락 등 환경 문제로 fail 할 수 있음 → 그땐 `apt-get install` 라인 보강.

### §7-8 Phase 0 sub-phase 5 (5/8) — Dev Container

**컨텍스트**: cross-platform 개발 환경 표준화 마무리. 클릭 한 번에 동일 환경 (Codespaces / VS Code Dev Containers).

| 변경 | 위치 | 효과 |
|---|---|---|
| `.devcontainer/devcontainer.json` 신규 — Python 3.12 (mcr.microsoft.com/devcontainers/python:1-3.12-bookworm) + uv (astral-sh/uv:0 feature) + Qt system deps | [.devcontainer/devcontainer.json](../.devcontainer/devcontainer.json) | Codespaces / VS Code Dev Containers 표준 환경 |
| postCreateCommand — apt-get install Qt deps + `uv sync --extra dev` + `pre-commit install` | (위 파일) | 컨테이너 첫 부팅 시 의존성 + dev 도구 + git hook 자동 셋업 |
| VS Code 확장 5종 — Python / Pylance / Ruff / GitLens / even-better-toml | (위 파일) | 일관된 에디터 경험 |
| editor 설정 — ruff 가 default formatter, formatOnSave, codeActionsOnSave (organize imports + auto fix) | (위 파일) | 매 저장 시 자동 lint/format |
| `QT_QPA_PLATFORM=offscreen` 환경변수 — headless Qt 모듈 import 호환 | (위 파일) | 컨테이너에서 ui_v2 모듈 import 정상 |
| README Codespaces 배지 + 설치 (Codespaces / Dev Container) 섹션 + 2분할 전략 명시 | [README.md](../README.md) | 신규 기여자 진입점 |

**2분할 전략 (ROADMAP §7.2)**:
- 컨테이너 (Linux) = `core/` + 미래 `backend/` + `web/` 개발 + `core` / `scenarios` 테스트
- 로컬 Windows = `pywinauto` / `pyautogui` 의존하는 GUI 자동화 테스트 + 데스크톱 앱 실행

**검증**:
- devcontainer.json JSON 유효성 (jsonc 주석 strip 후 파싱) ✅
- ruff check . → All checks passed!
- ruff format --check . → 114 files already formatted
- core 77/77 ✅ + scenarios 72/72 ✅

### Phase 0 (§7-8) 완료 체크리스트

- [x] **Sub-phase 1**: `pyproject.toml` + `uv` (5/7)
- [x] **Sub-phase 2**: `pre-commit` + `ruff` (lint+format) (5/7)
- [x] **Sub-phase 3**: SPDX 헤더 일괄 (5/8)
- [x] **Sub-phase 4**: GitHub Actions CI (5/8)
- [x] **Sub-phase 5**: `.devcontainer/` (5/8)
- [ ] **structlog + Sentry** — ROADMAP Phase 0 의 observability layer. Phase 0 후반 또는 Phase 1 초반에 별도 작업.
- [ ] **mypy 도입** — Phase 1 의 "core/* 타입 힌트 완성" 마일스톤과 묶음.

### Phase 1 sub-task 1 (5/8) — 저장소 추상화 강화 + AppService leak 제거

**컨텍스트**: ROADMAP §3 Phase 1 (1) 시작. 데스크톱 앱과 향후 backend (PostgresRepository) 가 **동일한 `core/`** 를 공유하도록 저장소 인터페이스 정리.

| 변경 | 위치 | 효과 |
|---|---|---|
| `SessionRepository(ABC)` 에 `export_session_as_project()` + `import_session_folder()` abstract 메서드 추가 | [core/storage/base.py](../core/storage/base.py) | 모든 backend 가 export/import contract 준수 (NotImplementedError 가능) |
| `CaptureStore(ABC)` 신규 — `resolve_capture_path` / `list_captures_for_session` / `delete_capture` | (위 파일) | Phase 2 의 S3CaptureStore 진입로. 실제 capture 쓰기 경로 마이그레이션은 Phase 2 일괄 |
| `LocalCaptureStore` 신규 — filesystem 기반 구현 | [core/storage/local_capture.py](../core/storage/local_capture.py) | CaptureStore contract 준수 |
| `InMemoryRepository` 신규 — 테스트 가속용 (file IO 없음) | [core/storage/in_memory.py](../core/storage/in_memory.py) | tempdir 기반 테스트 대비 빠름. ROADMAP "테스트 전략" 항목 충족 |
| `LocalJsonRepository` 에 `export_session_as_project` / `import_session_folder` 메서드 추가 (manager 위임) | [core/storage/local_json.py](../core/storage/local_json.py) | 새 abstract 메서드 구현 |
| `AppService` 의 `getattr(self._repo, "manager", None)` **leak 2 곳 제거** — `export_workflow` / `import_workflow` / `reorder_step` 모두 abstraction 만 사용 | [core/app_service.py](../core/app_service.py) | Phase 2 PostgresRepository 가 manager 속성 없이도 작동 |
| `reorder_step` 의 `_renumber_steps` 호출 → 인라인 (3 줄) | (위 파일) | private 메서드 의존 제거 |
| test_78 (InMemoryRepository contract) + test_79 (AppService leak 차단) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**검증**:
- core 79/79 ✅ (test_78 + test_79 신규)
- scenarios 72/72 ✅
- ruff check 0 issue + format 0 diff
- PySide6 port sync 완료 (5 파일)

### Phase 1 sub-task 2 Chunk A (5/8) — UI-Core 분리: ui_v2 정리

**컨텍스트**: ROADMAP §3 Phase 1 (2) KPI: "ui/ 폴더에서 session_manager · workflow_engine · ai_engine 직접 import 0건". 큰 작업이라 2 chunk 분할:
- **Chunk A** (5/8 완료): ui_v2 의 5 import 정리 + AppService 인터페이스 확장
- **Chunk B** (예정): ui/ legacy 의 12+ import 정리 + main_window.py 1649 → 600줄 축소

| 변경 | 위치 | 효과 |
|---|---|---|
| `AppService` 가 `Session/Step/SessionSummary` + `ExecutionKernel/StepResult` re-export | [core/app_service.py](../core/app_service.py) | UI 가 `core.session_manager` / `core.execution_kernel` 직접 import 안 해도 됨 |
| `AppService.create_default(data_dir, settings)` classmethod 추가 | (위 파일) | LocalJsonRepository + AIEngineManager 일괄 생성. UI 가 storage/ai_engine 직접 import 안 함 |
| `AppService.reload_ai(settings)` + `create_kernel()` factory 메서드 | (위 파일) | settings 변경 시 AI 재초기화, 세션별 kernel 생성 모두 facade 경유 |
| ui_v2/main_window_v2.py 의 5 banned import 모두 제거 — 모든 import 가 `core.app_service` 경유 | [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) | KPI 충족 |
| 함수 내부 `from core.session_manager import Step` → 모듈 상단 `from core.app_service import Step` | (위 파일) | local import 도 정리 |
| test_80 (ui_v2 banned import 0건 + AppService re-export + factory 메서드 검증) 추가 | [tests/test_core.py](../tests/test_core.py) | KPI 자동 가드 |

**검증**:
- core 80/80 ✅ (test_80 신규)
- scenarios 72/72 ✅
- ruff check 0 issue + format 0 diff
- PySide6 port sync 완료

### Phase 1 sub-task 5 (5/8) — Agent 브리지 스켈레톤

**컨텍스트**: ROADMAP §3 Phase 1 (5) 의 마지막 결산. agent/ 의 두 항목 평가:

| 항목 | ROADMAP 의도 | 실제 상태 |
|---|---|---|
| `agent/runner.py` — WorkflowEngine 감싸 원격 명령 수신 | no-op 스켈레톤 | ✅ **이미 초과 달성** — 827 line, M2.10 까지 완성. ExecutionRunner 가 `execution.start`/`execution.cancel` WS 프레임 처리, capture 업로드, mid-run cancel 등 모두 동작 |
| `agent/bridge.py` — 로컬 HTTP/WS 브리지 (no-op) | no-op 스켈레톤 | ❌ 미작성 → 5/8 추가 |

**(외 부수적 컴포넌트)**: `agent/agent_main.py` (623), `agent/auth.py` (386 — device flow), `agent/ws_client.py` (319 — cloud → agent WS) 도 이미 운영급 구현 완료.

| 변경 | 위치 |
|---|---|
| `agent/bridge.py` 신규 — `LocalBridge` 클래스 (no-op contract). `register_handler` / `start(port)` / `stop()` / `is_running` / `port` / `list_actions` / `get_handler` | [agent/bridge.py](../agent/bridge.py) |
| 미래 사용 시나리오 명시 — Phase 3 의 `ohdo://session/<id>` URL scheme 처리, desktop UI ↔ agent IPC, 외부 도구 (VS Code 확장 등) | (위 파일 docstring) |
| scenarios test_73 (LocalBridge contract 가드) 추가 — 인스턴스화 + handler 등록/조회 + 잘못된 입력 ValueError + start/stop 토글 | [tests/test_scenarios.py](../tests/test_scenarios.py) |
| pyside6_port sync — agent/ 폴더 전체 복사 (Qt 의존성 없음, cp 가능) | [pyside6_port/agent/](../pyside6_port/agent/) |

**검증**:
- core 80/80 ✅
- scenarios 73/73 ✅ (test_73 신규)
- ruff 0 issue + format 0 diff
- PySide6 port sync 완료

### Phase 1 sub-task 4 (5/8) — 설정 레이어 (Pydantic Settings)

**컨텍스트**: ROADMAP §3 Phase 1 (4) — `config/settings.json` 의 dict 기반 → Pydantic v2 `Settings` 모델 + `.env` / 환경변수 병합. 비파괴 도입 (기존 `_load_settings() -> dict` callers 유지).

| 변경 | 위치 | 효과 |
|---|---|---|
| `pydantic-settings>=2.0.0` 의존성 추가 | [pyproject.toml](../pyproject.toml) | typed Settings + .env 병합 도구 |
| `core/config.py` 신규 — 10 섹션 모델 (AI/Image/Recognition/Execution/VisualFeedback/UI/OutputProject/Logging/Hints/ElementPicker) + `Settings(BaseSettings)` 최상위 | [core/config.py](../core/config.py) | 타입 안전 접근, IDE 자동완성, validation |
| `load_settings(path) -> Settings` + `load_settings_dict(path) -> dict` (legacy 호환) + `save_settings(s, path)` | (위 파일) | 신/구 callers 양쪽 cover |
| `settings_customise_sources` override — env > dotenv > init(JSON) > secrets > defaults 우선순위 | (위 파일) | 사용자가 `.env` / shell 로 settings.json 값 override 가능 (CI/Docker 친화) |
| 모든 섹션 모델에 `extra="allow"` — 미정의 키 보존 (forward compat, settings.json 새 필드 추가 시 모델 갱신 전이라도 무손실) | (위 파일) | breaking change 회피 |
| test_81 (Settings 모델 + JSON load + env override + save 라운드트립 + extra=allow forward compat) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**비파괴 정책**:
- 기존 `_load_settings()` patterns (ui/, ui_v2/) 그대로 작동 — `load_settings_dict()` 가 동일한 dict 반환
- 신규 코드는 `from core.config import load_settings; s = load_settings(); s.execution.step_delay_ms` typed access 권장
- Phase 2 backend 가 같은 `Settings` 모델을 FastAPI 의존성 주입에 활용 가능

**환경변수 override 예**:
- `OHDO_AI__SELECTED=openai_compat` → `s.ai.selected`
- `OHDO_EXECUTION__STEP_DELAY_MS=2000` → `s.execution.step_delay_ms`
- `OHDO_UI__THEME=dark` → `s.ui.theme`

**검증**:
- core 81/81 ✅ (test_81 신규)
- scenarios 73/73 ✅
- ruff 0 issue + format 0 diff
- pydantic-settings 양 venv (legacy + uv-managed) 설치 완료
- PySide6 port sync 완료 (uv.lock 76 packages 재해석)

### Phase 1 sub-task 3 (5/8) — Pydantic 모델 승격 (옵션 B parallel)

**컨텍스트**: ROADMAP §3 Phase 1 (3) — dataclass (Session/Step/Capture 등) → Pydantic v2. 비파괴 도입 정책 채택 (옵션 B):
- 기존 dataclass 유지 — 사용자 JSON 데이터 + 모든 callers 무손상
- 신규 Pydantic 모델은 **API 경계용** (Phase 2 FastAPI `response_model` 즉시 활용 가능)
- `from_dataclass()` / `to_dataclass()` 변환 helper

| 변경 | 위치 | 효과 |
|---|---|---|
| `core/models.py` 신규 — 7 Pydantic 모델 (CaptureModel/PromptLogModel/ExecutionResultModel/ConversationMessageModel/StepModel/SessionModel/SessionSummaryModel) | [core/models.py](../core/models.py) | dataclass 와 동일 필드 + 기본값 + `extra="allow"` (forward compat) |
| `from_dataclass(instance)` / `to_dataclass(model)` 변환 helper | (위 파일) | dataclass ↔ 모델 양방향. `_DATACLASS_TO_MODEL` 매핑 dict |
| 매핑 안 된 타입은 `TypeError` (잘못 호출 시 명시적 fail) | (위 파일) | 안전성 |
| `model_dump()` 결과 = `asdict(dataclass)` 결과 (JSON wire format 동일) | (검증 by test) | Phase 2 backend 의 `response_model` 호환 보장 |
| test_82 (round-trip + JSON 직렬화 + extra=allow + TypeError) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**API 경계 활용 예** (Phase 2 진입 시):
```python
# FastAPI 백엔드
from core.models import SessionModel, StepModel, from_dataclass

@app.get("/sessions/{sid}", response_model=SessionModel)
async def get_session(sid: str):
    session = repo.load_session(sid)  # dataclass
    return from_dataclass(session)    # SessionModel
```

**비파괴 검증**:
- 기존 dataclass 호출 사이트 (수십 개) 전혀 변경 X
- 사용자 data/sessions/ JSON 파일 호환성 유지
- `model_dump()` ↔ `asdict()` 라운드트립 손실 0

**검증**:
- core 82/82 ✅ (test_82 신규)
- scenarios 73/73 ✅
- ruff 0 issue + format 0 diff
- PySide6 port sync 완료

### Phase 1 진행 체크리스트 (ROADMAP §3 Phase 1)

- [x] (1) 저장소 추상화 `core/storage/` — 5/8 완료
- [x] (2) UI-Core 완전 분리 — **Chunk A (5/8 ui_v2) + Chunk B (5/9 ui/ legacy) 모두 완료**
- [x] (3) Pydantic 모델 승격 — 5/8 완료 (parallel 모델 + 변환 helper)
- [x] (4) 설정 레이어 분리 — 5/8 완료
- [x] (5) Agent 브리지 스켈레톤 — 5/8 완료

**Phase 1 진행률: 5/5 (100% 완료)** — Phase 2 진입 직전 [docs/commercial_review.md](commercial_review.md) 재독 필수. 자세한 Chunk B 변경 내역은 §14 참조.

### 다음 작업 후보
- **main_window.py 줄수 축소 (stretch)** — 1304 → 600줄대. handler 추가 분해 (Step 5+). KPI 무관, 별도 결정.
- **structlog + Sentry SDK** (ROADMAP Phase 0 후반) — observability layer
- **§7-10**: AI 자동 에러 복구 — 사용자 보류 중
- **Phase 2 진입** — commercial_review.md 재독 + GO/NO-GO 게이트 통과 후 결정

### ⚠️ Phase 2 (SaaS 백엔드) 진입 직전 필독 문서

[docs/commercial_review.md](commercial_review.md) — 5/8 작성. ohdo 의 상업적 경쟁력 정직 진단 + Computer Use / UiPath / 기타 RPA 와의 비교 + GO/NO-GO 게이트 제안. **Phase 1 완료 직후 / Phase 2 진입 결정 전 반드시 재독.** Phase 1 까지는 어느 시나리오든 가치 있어 진행 OK.

## 14. 5/9 Phase 1 sub-task 2 Chunk B — UI-Core 완전 분리 (ui/ legacy)

**컨텍스트**: ROADMAP §3 Phase 1 (2) KPI: "ui/ 폴더에서 session_manager · workflow_engine · ai_engine 직접 import 0건" 의 Chunk B (ui/ legacy 정리). 5/8 의 Chunk A (ui_v2) 와 합쳐 KPI 100% 충족. 3 sub-step 으로 분할 진행 — AppService 보강 → main_window 정리 → handler/panel 정리.

### Sub-step 1 (5/9) — AppService 인터페이스 보강

| 변경 | 위치 | 효과 |
|---|---|---|
| 클래스 re-export 추가: `AIEngineManager / WorkflowEngine / PromptBuilder / WindowInspector / CodeSandbox` | [core/app_service.py](../core/app_service.py) `__all__` + 모듈 상단 eager import | UI 가 type hint / 인스턴스 보유 / 생성 시 모두 `from core.app_service import` 만 |
| 상수 re-export 추가: `INITIAL_BLOCK_STEP_ID / LIBRARY_BLOCK_STEP_ID` | (위 파일) | block_execution_handler 에서 사용 |
| pure 함수 re-export 추가: `extract_imports / merge_imports / extract_code_delta / extract_import_delta / extract_initial_block / extract_library_block / extract_step_delta_code / format_element_label` | (위 파일) | UI 가 pure 함수 직접 호출하는 사이트 모두 cover |
| `workflow_engine` property + `set_workflow_engine(engine)` setter | (위 파일) | 외부에서 settings (`step_delay_ms` / `visual_feedback_enabled`) 반영 인스턴스 주입 가능 |
| `prompt_builder` property + `set_prompt_builder(builder)` setter + `__init__(prompt_builder=)` 인자 | (위 파일) | 외부 prompts.json 주입 + lazy 생성 fallback |
| test_83 (Chunk B 인터페이스 가드 — 클래스/상수/함수 re-export + property/setter contract) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**검증**: core 83/83 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff + PySide6 sync.

### Sub-step 2 (5/9) — ui/main_window.py banned import 정리

**Option A (보수)** 채택: import 만 정리하고 `self.session_manager / self.ai_engine / self.prompt_builder / self.workflow_engine` alias attributes 보존 (handler / code_viewer 등 산재된 호출 사이트 보호). KPI 는 import 만 측정하므로 충족.

| 변경 | 위치 |
|---|---|
| 모듈 상단 7 banned `from core.* import` (ai_engine / execution_kernel / import_manager / prompt_builder / session_manager / win_inspector / workflow_engine) → `from core.app_service import (...)` 단일 진입점 | [ui/main_window.py:47-66](../ui/main_window.py#L47-L66) |
| 함수 내부 `from core.import_manager import` 2 곳 (line 993 / 1052) 제거 — 모듈 상단에서 이미 import | (위 파일) |
| `__init__` 의 `self.session_manager = SessionManager()` / `self.ai_engine = AIEngineManager(...)` / `self.prompt_builder = PromptBuilder(...)` / `self.workflow_engine = WorkflowEngine(...)` 4개 인스턴스화 → `self.app_service = AppService.create_default(data_dir=..., settings=...)` + `set_workflow_engine(...)` + `set_prompt_builder(...)` 후 alias 4개 (`self.session_manager = self.app_service.repo.manager` 등) | (위 파일 line 100-123) |
| test_84 (main_window 의 banned core import 0건 + `from core.app_service import` 단일 진입점 가드) 추가 | [tests/test_core.py](../tests/test_core.py) |

**검증**: core 84/84 ✅.

### Sub-step 3 (5/9) — handler / chat_panel / ui_inspection_handler 정리

| 변경 | 위치 |
|---|---|
| `ui/ai_call_handler.py` — 모듈 상단 2 banned (`session_manager.Step` + `win_inspector.format_element_label`) + 함수 내부 1 (`import_manager.*` 3 함수) → `from core.app_service import (Step, extract_code_delta, extract_import_delta, extract_imports, format_element_label)` 단일 진입점 | [ui/ai_call_handler.py](../ui/ai_call_handler.py) |
| `ui/block_execution_handler.py` — 모듈 상단 2 banned (`execution_kernel.{INITIAL_BLOCK_STEP_ID, LIBRARY_BLOCK_STEP_ID, ExecutionKernel}` + `workflow_engine.{CodeSandbox, extract_library_block}`) → 단일 진입점 | [ui/block_execution_handler.py](../ui/block_execution_handler.py) |
| `ui/chat_panel.py` + `ui/ui_inspection_handler.py` — `win_inspector.format_element_label` → app_service 경유 | [ui/chat_panel.py](../ui/chat_panel.py), [ui/ui_inspection_handler.py](../ui/ui_inspection_handler.py) |
| test_85 (ui/ 폴더 전체 banned core import 0건 가드) 추가 — test_80 (ui_v2) + test_84 (main_window) 의 영역을 ui/*.py 전체로 확장 | [tests/test_core.py](../tests/test_core.py) |

**검증**: core 85/85 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff (`tests/test_core.py` 두 개 reformat 적용 후) + PySide6 port 7 파일 sync (cp + sed `PyQt6→PySide6, pyqtSignal→Signal`).

### Sub-step 4a (5/9, stretch — partial) — 기본 다크 테마 stylesheet 분리

**컨텍스트**: KPI 와 무관한 main_window.py 줄수 축소 stretch goal 의 첫 sub-step. 가장 risk 낮고 효과 큰 단일 변경.

| 변경 | 위치 |
|---|---|
| `_get_default_dark_theme()` 메서드 (156줄 stylesheet 문자열) → `ui/themes.py` 의 `get_default_dark_theme()` 함수로 추출 | [ui/themes.py](../ui/themes.py) (신규) |
| main_window 의 `_apply_theme` 이 `from .themes import get_default_dark_theme` 후 호출. 메서드 자체 통째 제거 (CLAUDE.md "delete completely" 룰) | [ui/main_window.py:392-403](../ui/main_window.py#L392-L403) |

**검증**: core 85/85 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff (130 files) + PySide6 sync (sed `PyQt6→PySide6, pyqtSignal→Signal`).

**효과**: main_window.py **1321 → 1166 줄 (-155줄)**.

### 보류된 stretch sub-step

- **4b**: 세션 CRUD (8 메서드, ~169줄) → `ui/session_management_handler.py` (예상 1166 → ~997)
- **4c**: Step 편집 (7 메서드, ~170줄) → `ui/step_edit_handler.py` (예상 ~997 → ~827)
- **4d**: UI setup `_setup_*` (5 메서드, ~175줄) → `ui/ui_setup.py` (예상 ~827 → ~652)

KPI 무관 + (c) commercial_review.md 게이트 우선순위로 보류 결정 (5/9 사용자). 4b~d 진행 시 main_window.py 600줄대 stretch goal 도달.

### Phase 1 최종 상태

- ROADMAP §3 Phase 1 의 5/5 sub-task 모두 완료. KPI ("ui/ 폴더에서 banned core 직접 import 0건") 충족. test_80 + test_84 + test_85 가드 3중.
- 예외: `core.environment_scanner` (environment_setup_dialog / settings_dialog 에서 함수 내 import) + `core.adapters.openai_compat_adapter` (settings_dialog) 는 KPI banned 목록 외 → 추후 정리.
- main_window.py 줄수: 1304 → 1166 (Sub-step 4a 적용). 600줄대 stretch goal 은 4b/4c/4d 보류.

## 15. 5/9 시장 결정 글로벌 확장 + 공개 직전 방어 정비

**컨텍스트**: Phase 1 100% 완료 직후 사용자와 commercial_review.md 재독 → 시장 타깃 변경 + 공개 직전 외부 정비 패키지를 한 세션에 묶어 처리.

### Stage 1 — 시장 타깃 글로벌 확장 결정 (사용자 결정 5/9)

- 한국 niche 단독 → **글로벌 + 한국 dual-locale** 양립으로 변경.
- 근거: 글로벌 dev-focused RPA SAM (~50-100M USD/yr) 이 한국 (~5-10M) 의 10배 + Computer Use 와 시간 경쟁.
- 차별성 재포지셔닝: "한국어 UI" 단일 강점 (🟢) → "i18n (영어 + 한국어) dual-locale" 의 하나 (🟡). 진입 장벽 효과 약화 인정 + 글로벌 SAM 진입.

| 갱신 문서 | 항목 |
|---|---|
| [docs/ROADMAP.md](../ROADMAP.md) | §0 타깃 시장 라인, §1 비전 본문 + 라이선스 절 본문, §10 변경 로그 5/9 행 |
| [docs/commercial_review.md](commercial_review.md) | 헤더 5/9 갱신 표시, §3 차별성 표 (한국어 UI → i18n dual-locale, 🟢→🟡), §5 SAM anchor 글로벌 + ARR 추정 상향 (비관 0-15K / 중립 20-80K / 낙관 150-500K), §7 GO/NO-GO 게이트 ("한국어 콘텐츠 5+" → "영어 + 한국어 mix"), §9 변경 로그 |
| [CLAUDE.md](../../CLAUDE.md) | 장기 로드맵 동기화 규칙 절의 타깃 시장 본문 |
| 본 §0 | 마지막 업데이트 라인 + 시장 결정 표시 |

### Stage 2 — 영어 README + 한국어 분리

- [README.md](../../README.md) → 영어로 전면 재작성. 차별성 표 (ohdo vs UiPath/Power Automate vs Computer Use), Windows 전용 명시, commercial_review link 추가.
- [README.ko.md](../../README.ko.md) 신규 — 한국어 버전. 양쪽 상단에서 cross-link.
- pyside6_port/README.md 는 internal (라이선스 비교 baseline) 수준이라 영어 변환 보류.

### Stage 3 — 공개 직전 방어 정비

| 변경 | 위치 | 효과 |
|---|---|---|
| `.gitignore` 강화 — secrets / credentials 패턴 추가 (`.env`, `.env.local`, `.env.*.local`, `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*credentials*`, `*secret*`) | [.gitignore](../../.gitignore) | broad guard |
| `COMMERCIAL.md` 신규 — 오픈코어 의도 + AGPL 적용 경계 (when AGPL OK / when commercial license 필요) + 문의 가이드 | [COMMERCIAL.md](../../COMMERCIAL.md) | dual-licensing 의도 명시. 외부 commercial 문의 진입점 |
| `CONTRIBUTING.md` (영어) + `CONTRIBUTING.ko.md` (한국어) — DCO sign-off 가이드 (`git commit -s`), PR 체크리스트, scope 명시 (Windows-only, no XAML, Phase 2 SaaS 미공개), 환영 영역 (i18n, element picker, 테스트, 문서) | [CONTRIBUTING.md](../../CONTRIBUTING.md), [CONTRIBUTING.ko.md](../../CONTRIBUTING.ko.md) | 외부 기여자 진입점. CLA 보류 (DCO 만으로 작은 OSS 충분, 큰 기여 시 별 협의) |

### 보안 검증 결과

- `git ls-files | grep -iE "tmp/|data/sessions/|\.env|secret|\.key$|\.pem$|conversations"` → tracked sensitive 0건 (`.env.example` template 만).
- `git log --diff-filter=A -- 'tmp/*' 'data/sessions/*' ...` → history commit 0건. **`git filter-repo` 불필요**.

### 최종 상태 (5/9 세션 종료 시점)

- baseline: core 85/85 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff (130 files).
- **공개 가능 상태** (private → public 전환 결정만 사용자에게 남음).
- 시장 검증 GO/NO-GO 게이트 0/4 (private 유지로 측정 불가).

### 사용자 결정: 다음 단계 보류 + Phase 1.8 진입

5/9 세션 종료 결정 — Phase 2 / 공개 / 시장 검증 등 외부 다음 단계는 잠시 보류.
사용자 본인이 ohdo 를 일상 사용하면서 **AI 대화 → Python 자동화 코드 생성 기능의 완성도 향상 루프** 진행 (= 비공식 Phase 1.8).

작업 흐름:
1. 사용자가 자동화 시나리오에서 ohdo 사용
2. 회귀 / 엣지케이스 / 품질 이슈 발견 → Claude 와 함께 root cause 분석 + fix
3. 회귀 가드 추가 (test_core / test_scenarios)
4. baseline 그린 유지

영향 영역 (개선 후보):
- [core/prompt_builder.py](../core/prompt_builder.py) — 프롬프트 동적 구축 (누적 코드, 컨텍스트, 분기)
- [config/prompts.json](../config/prompts.json) — 시스템 프롬프트, 에러 복구 템플릿, jupyter 호환 가이드
- [core/win_inspector.py](../core/win_inspector.py) — element → 코드 변환 (UWP, owner-drawn, 브라우저, 동적 auto_id)
- [core/workflow_engine.py](../core/workflow_engine.py) + [core/import_manager.py](../core/import_manager.py) — step delta + import 추출 + jupyter 호환
- [core/adapters/gemini_cli_adapter.py](../core/adapters/gemini_cli_adapter.py) — AI 어댑터 (응답 corrupt, timeout, 인코딩)
- [ui/element_picker.py](../ui/element_picker.py) — element 검출 + EFP 토글 + F3 wait
- [ui/ai_call_handler.py](../ui/ai_call_handler.py) — AI 호출 path + step_code/generated_code 분리

회귀 위험 baseline: §4 의 contract 들 모두 (특히 §4.2 jupyter 6 함수, §4.5 ForegroundLock, §4.8 코드 편집 4중 안전장치) 회귀 시 즉시 발견.

## 16. 5/9~5/10 Phase 1.8 OpenAI 호환 (DeepSeek) 등록 + 코드 생성 품질 루프

**컨텍스트**: 5/9 §15 종료 시점 사용자 결정 — Phase 2/공개/시장 검증 보류, 본인이 ohdo 일상 사용하면서 AI 대화→Python 자동화 코드 생성 완성도 향상 루프 진행. 검증 시나리오: OpenAI API (DeepSeek 키) 등록 → 메모장 자동화 step 1 (실행) → step 2 (새 탭 추가 클릭) → step 3 (텍스트 입력) → 발견 이슈 fix.

11 unit 누적, baseline 85 → 96 (+11 회귀 가드). PySide6 port 양쪽 sync (core/ 는 cp, ui/ 는 sed PyQt6→PySide6).

### Step A (5/9) — settings dialog 의 Test connection 버튼 (test_86)
| 발견 갭 | DeepSeek 등 OpenAI 호환 LLM 을 등록해도 키 정확성 즉시 검증 불가 — 채팅에서 코드 생성 끝까지 돌려야 401 알 수 있음 (UX 나쁨, 비용 낭비) |
| Fix | [ui/settings_dialog.py:209-302](../ui/settings_dialog.py#L209-L302) 에 `Test connection` 버튼 + `_test_openai_connection` 메서드. dialog 입력값으로 임시 어댑터 → ping 호출 (timeout 15s + max_tokens 32 + temperature 0 + "Reply with OK only.") → ✅/❌ inline label. Save 안 한 입력값으로 즉시 검증 |
| 가드 | test_86 — 메서드 존재 + 위젯 + 콜백 dialog 입력값 사용 + 15s/32 강제 + OpenAICompatAdapter._generate_sync 직접 호출 5중 |

### Step B (5/9) — _open_settings 가 AIEngineManager 재로드 (test_87)
| 발견 갭 | settings dialog 에서 OpenAI 엔진 선택 + Apply → settings.json 저장 + theme/picker 즉시 반영. **AIEngineManager 재로드 누락** → 다음 AI 호출이 init 시점 settings 그대로 (gemini_cli 만 가지고 있어서 OpenAI 호환은 빈 api_key 401) |
| Fix | [ui/main_window.py:1107-1124](../ui/main_window.py#L1107-L1124) `_open_settings` 가 `_save_settings()` 후 `app_service.reload_ai(self.settings)` + `self.ai_engine = self.app_service.ai_manager` 추가. ai_call_handler 가 매번 `mw.ai_engine` lookup 하므로 alias 만 갱신하면 자동 전파 |
| 가드 | test_87 — `_open_settings` 소스에 `reload_ai(self.settings)` + `ai_manager` alias 패턴 |

### B1+B2+B4 (5/9) — 어느 엔진이 호출됐는지 확인 가능 + settings 영구 저장 (test_88)
| 발견 갭 | (B1) `mw.ai_engine.current_engine` 은 없는 속성 (`get_current_name()` 이 정답) — legacy ui 콘솔 패널의 `엔진:` 메타가 항상 빈 칸. (B2) ui_v2 의 `_send_request` worker 에서 step_done 메시지에 어느 엔진이 답했는지 명시 누락. (B4) `switch_ai_engine` (헤더 콤보 / 명령 팔레트 / onboarding 4 호출 사이트) 가 메모리 `_current_name` 만 변경하고 settings.json 영구 저장 X — 사용자가 ui_v2 헤더로 openai_compat 변경했는데 settings.json 의 ai.selected 는 gemini_cli 그대로 → 재시작 시 회귀 |
| Fix | (B1) [ui/ai_call_handler.py:193-195](../ui/ai_call_handler.py#L193-L195) `current_engine` → `get_current_name()`. (B2) [ui_v2/main_window_v2.py:2165-2188](../ui_v2/main_window_v2.py#L2165-L2188) step_done 메시지에 `엔진: {name}` prefix. (B4) ui_v2 에 `_persist_engine_choice(name)` 헬퍼 (settings.ai.selected = name + _save_settings) + 헤더/팔레트/onboarding 모두 호출. legacy main_window `_on_ai_engine_changed` 도 settings persist |
| 가드 | test_88 — 5중 (B1 속성명 + B2 메시지 prefix + B4 4 호출 사이트의 persist 패턴) |

### P4 (5/9) — 콘솔 패널이 settings.ui.console_visible 따름 (test_89)
| 발견 갭 | ui_v2 의 `_console_visible = False` 하드코딩 + `_build_console_panel` 의 `hide()` 하드코딩. 사용자가 Ctrl+\` 모르면 AI 응답 메타 (엔진/토큰/시간) 화면에서 볼 수 없음 + 토글해도 settings.json 영구 저장 X |
| Fix | [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `__init__` 가 `_load_settings()` 로 ui.console_visible 읽고 `_console_visible` 초기화. `_build_console_panel` 이 `setVisible(self._console_visible)`. `_toggle_console` 가 settings.json 영구 저장 |
| 가드 | test_89 — `__init__` settings 로드 + `_build_console_panel` setVisible (hardcoded hide() 0건) + `_toggle_console` 의 _save_settings 3중 |

### P1a (5/9) — 가장 큰 본질 fix: system_context 가 prompt 에 inject (test_90)
| 발견 갭 | **prompt_builder 가 self.system_context 를 보유만 하고 build_step_prompt 의 출력 (parts.join) 에 어디에도 append 하지 않음**. prompts.json 의 12K+ chars 핵심 가이드 (idempotent driver, jupyter mode, UWP wait, pyautogui PRIMARY, title_re, Text→부모 promote 등) 가 어떤 모델에도 도달조차 안 함. 이전엔 inline 가이드만 적용됨. 이게 5/9 step 2/3 가이드 무시 회귀의 진짜 원인 |
| Fix | [core/prompt_builder.py:90](../core/prompt_builder.py#L90) `_build_step_prompt_parts` (private 공통 빌더) 에서 `system_text = self.system_context or ""` 분리. `build_step_prompt` 는 backward compat (system + user 합쳐 단일 string 반환) — 호출자 깨지지 않음 |
| 가드 | test_90 — sentinel 본문 prepend 검증 + 사용자 요청보다 앞 위치 + 빈 system_context fail-safe |

### P1b (5/9) — system role 분리 (test_91)
| 발견 갭 | OpenAI compat 어댑터의 messages = [{role:user}] — system role 미활용. P1a 단일 string prepend 보다 best practice = system role 분리 (모델 attention 강화) |
| Fix | (a) [core/adapters/base_adapter.py](../core/adapters/base_adapter.py) `generate(prompt, images, system=None)` 시그니처 확장. (b) [core/adapters/openai_compat_adapter.py](../core/adapters/openai_compat_adapter.py) `_generate_sync` 가 system 받으면 `messages = [{role:system}, {role:user}]`. (c) [core/adapters/gemini_cli_adapter.py](../core/adapters/gemini_cli_adapter.py) system 받으면 stdin prompt 앞에 prepend (CLI 는 role 분리 path 없음). (d) [core/ai_engine.py](../core/ai_engine.py) 통과. (e) [core/prompt_builder.py](../core/prompt_builder.py) `build_step_prompt_split` 신규 메서드 — `(system_text, user_text)` 튜플 반환. (f) [core/app_service.py:622-634](../core/app_service.py#L622-L634) `generate_step` 가 split 호출 + 어댑터에 system 별도 전달 |
| 가드 | test_91 — split 메서드 + 어댑터 시그니처 + OpenAICompat messages 분리 + AIEngineManager 통과 + AppService split 호출 7중. scenarios mocks (`_FakeAI` / `MockAI` / `FakeAIManager` / `MockPromptBuilder`) 모두 `system=None` 인자 + `build_step_prompt_split` 추가 |

### P3 (5/9) — system_context 가이드 #3 + #5 강화 (test_92)
| Fix | [config/prompts.json](../config/prompts.json) system_context #3 → "**try/except 강제 (예외 없음)**: 외부 자원 다루는 모든 코드 블록 (앱 실행/연결 / 윈도우 wait / UI 조작 / 파일 I/O / 네트워크 / subprocess / 클립보드 / 단축키) 반드시 try/except". #5 → "**import 위치 강제 (Jupyter 호환)**: 모든 import 는 코드의 가장 최상단 (라인 1~N) 에만. try/except/함수/step 본문 안 import 금지" |
| 가드 | test_92 — sentinel 어휘 (`try/except 강제` / `예외 없음` / `import 위치 강제` / `가장 최상단` / `step 본문 안 import 금지`) |

### G1 (5/9) — system_context #17 의 element 자동 주입 X 명시 (test_93)
| 발견 갭 | DeepSeek 가 #17 예제 (`click_target = element` 패턴) 만 복사 → `name 'click_target' is not defined` 즉시 NameError. 기존 #17 예제는 `element` 가 자동 주입된다는 잘못된 가정 — ohdo 의 흐름은 element_context 에 텍스트 메타로만 들어가고 코드는 `win.child_window(...)` 로 직접 찾아야 함 |
| Fix | [config/prompts.json](../config/prompts.json) #17 본문에 "⚠ **변수 자동 주입 X — element 를 코드 안에서 직접 찾으세요**" 명시 + Step 1) `element = win.child_window(auto_id=..., control_type=..., found_index=0)` Step 2) walk-up promote Step 3) pyautogui.click 의 3단계 예제 추가. NameError 회귀 사례 인용 |
| 가드 | test_93 — sentinel 4중 |

### G2 + G5 (5/9) — element_context 템플릿 강제 사용 + library 블럭 essential imports (test_94/95)
| 발견 갭 | (G2) prompt_builder 의 element_context 가이드 "참고하되 ... 수정" 어휘 너무 약함 → DeepSeek 가 [core/win_inspector.py:680-940](../core/win_inspector.py) 의 ready-to-use 코드 템플릿 (`_resolve_element` + `element` + `click_target` + walk-up + pyautogui.click 모두 포함) 을 무시하고 짧은 자체 코드 작성 → element 변수 누락. (G5) `pyautogui` import 누락 — try block 에서 NameError → except 의 fallback `click_input()` 으로 살아남음 (silent fail). 모든 step 에서 pyautogui 호출 silent fail |
| Fix | (G2) [core/prompt_builder.py:297-340](../core/prompt_builder.py#L297-L340) "🚨 **위 ## 선택된 UI 요소 섹션의 ```python 코드 템플릿을 그대로 시작 코드로 사용하세요**" + "**자체적으로 element 변수를 다시 만들지 마세요**" + 회귀 사례 (`name 'click_target' is not defined`) 인용 + "사용자 요청 동작 코드만 템플릿 끝에 추가" 명시. (G5) [core/workflow_engine.py:846+](../core/workflow_engine.py#L846) `extract_library_block` 후 `_ensure_essential_imports` 적용 — 핵심 5개 (`time`, `subprocess`, `ctypes`, `pyautogui`, `pyperclip`) 누락 시 자동 prepend. regex 매칭으로 `import X` / `from X` 양쪽 인식 — 중복 prepend 방지 |
| 가드 | test_94 (G5 — 5개 패키지 prepend / 누락만 / 중복 방지 / from-style 인식) + test_95 (G2 — '그대로 시작 코드로 사용' / 'element 자체 정의 금지' / 회귀 사례 인용). [tests/test_scenarios.py:2506-2515](../tests/test_scenarios.py#L2506-L2515) test_42 의 `gc.startswith` → `in gc` 변경 (G5 의 prepend 로 generated_code 시작이 library 로 변경 — 의도된 동작) |

### G2.5 (5/10) — element_context 템플릿에서 import 라인 제거 (test_96)
| 발견 갭 | G2 효과로 DeepSeek 가 element_context 템플릿을 그대로 사용 → 마커 안에 `import ctypes` / `import pyautogui` 등이 들어감. `extract_imports` (header 영역만 인식) 가 step 1 의 상단 import 만 추출 → step 2/3 의 step_imports = []. P3 #5 (import 위치 강제) 위반 + G5 와 중복 import |
| Fix | [core/win_inspector.py:853-862](../core/win_inspector.py#L853-L862) desktop element 템플릿에서 import 5줄 (`ctypes` / `ctypes.wintypes` / `time` / `pyautogui` / `from pywinauto import Application`) 제거 + 안내 주석. owner-drawn 템플릿도 동일. [core/workflow_engine.py](../core/workflow_engine.py) `_ESSENTIAL_LIBRARY_IMPORTS` 에 `ctypes.wintypes` + `pywinauto.Application` 추가 (5 → 7개). [core/prompt_builder.py](../core/prompt_builder.py) element_context 가이드에 "import 는 코드 안에 작성하지 마세요 — 라이브러리 블럭에 자동 prepend 됨" 안내 한 줄 추가 |
| 가드 | test_96 — desktop / owner-drawn 템플릿 import 라인 0건 + `_ESSENTIAL_LIBRARY_IMPORTS` 보강 (ctypes.wintypes + Application) |

### 검증 결과 (5/10 사용자 'v2-새세션-150708' 메모장테스트 세션)

**🎉 G2.5 효과 확인** — Step 2 의 import 가 정확히 step_imports 영역으로 분리됨:
```
step 2.step_imports: ['import ctypes', 'import ctypes.wintypes', 'import pyautogui']
step 2.step_code: import 라인 0건. element_context 템플릿 거의 그대로 사용 (_resolve_element + element + click_target + walk-up + pyautogui.click + try/except 전체 wrapping)
```

### 잔존 갭 → G7 + 후속 fix 로 1~6 모두 대응 완료 (5/11)

§16 종료 시점에 식별된 6 갭 모두 처리됨. G7 (§17) 의 정적 분석으로 #1~#4, 후속 fix (§18) 로 #5/#6.

| # | 갭 | 대응 상태 |
|---|---|---|
| 1 | Step 3 의 `app`/`win` 변수 재정의 (jupyter mode 호환 위반) | ✅ G7 `redefined_var` 검출 + ⚠ 경고 + 재생성 시 prompt inject + G6 가이드 강화 (§18) |
| 2 | Step 3+4 의 try/except 누락 | ✅ G7 `missing_try` 검출 (risky 호출 화이트리스트) + G6 #3 강화 (§18) |
| 3 | Step 3 의 들여쓰기 깨짐 → SyntaxError 가능 | ✅ G7 `syntax` 검출 (`ast.parse` 실패) |
| 4 | Step 3 의 `import pyperclip` 이 else 블록 안 (P3 #5 위반) | ✅ G7 `import_misplaced` 검출 (module body 직계 아닌 모든 import) |
| 5 | Step 1 의 `Application().connect(timeout=3)` 짧음 — 새 메모장 인스턴스 가능 | ✅ G4 (system_context #14(b) timeout=5 + polling 패턴 + win_inspector inspect_window timeout 5초 — §18) |
| 6 | 자동 실행 옵션 부재 — 코드 생성 후 ▶ Ctrl+R 별도 트리거 필요 | ✅ F1 (settings.execution.auto_run_on_step_create + ui_v2 request_auto_run signal + legacy 자동 실행 trigger — §18) |

### 후속 fix 옵션 — 모두 완료 (5/11, §18)

| 옵션 | 설명 | 분량 | 상태 |
|---|---|---|---|
| ~~**G7**~~ | ~~step 코드 생성 후 ast 정적 분석 + 사용자 경고 + 자동 재생성 옵션~~ | 중간 | **완료 (§17)** |
| ~~**G4**~~ | ~~system_context #14(b) timeout=3s → 5s 권장 또는 polling 추가~~ | 매우 작음 | **완료 (§18)** |
| ~~**G7-E**~~ | ~~legacy BlockCard 재생성 버튼 (E1: validate hook, E2: 다이얼로그 + relay + ai_call_handler 의 previous_warnings path)~~ | 중간 | **완료 (§18)** |
| ~~**G6**~~ | ~~system_context #3 강화 + 새 #20 "이전 step 변수 재사용 — 재정의 금지" 가이드 + 회귀 사례 인용~~ | 작음 | **완료 (§18)** |
| ~~**F2**~~ | ~~step 카드 첫 생성 시 토스트에 실행 힌트 + ui.hint_run_shown 영구 dismiss~~ | 매우 작음 | **완료 (§18)** |
| ~~**G7-UX**~~ | ~~settings dialog 의 auto_regenerate_on_warning 체크박스 노출~~ | 매우 작음 | **완료 (§18)** |
| ~~**F1**~~ | ~~settings.execution.auto_run_on_step_create + ui_v2/legacy 양쪽 trigger~~ | 작음 | **완료 (§18)** |

**다음 세션 출발점**: 일상 사용으로 7 fix 의 효과 측정 → 새 갭 발견 시 후속. handoff §16+§17 잔존 갭 0건.

## 17. 5/10~5/11 Phase 1.8 G7 코드 정적 분석 + 사용자 경고 + 재생성 흐름

**컨텍스트**: §16 종료 시점에 식별된 잔존 갭 #1~#4 (변수 재정의 / try-except 누락 / 들여쓰기 / import 위치) 가 프롬프트 가이드 강화 (G6) 만으로는 100% 보장 불가 (DeepSeek-V3 같은 모델의 가이드 따르기 한계). 사후 정적 분석 + 사용자 경고 + 재생성 옵션으로 대응. 4 unit 누적, baseline 96 → 100 (+4 회귀 가드). PySide6 port 양쪽 sync.

### G7-A (5/10) — 정적 분석 엔진 신규 (test_97)

| 모듈 | [core/code_validator.py](../core/code_validator.py) — 순수 함수, side effect 없음. UI / AI 호출 hook 없음 |
| public API | `validate_step_code(step_code: str, *, prev_step_codes: Iterable[str] = ()) -> ValidationResult` |
| 검사 4종 | (1) `syntax` — `ast.parse` 실패 시 line 정보 포함. 발생 시 나머지 검사 skip. (2) `redefined_var` — 이전 step 들의 module-level 할당 변수와 현재의 교집합. (3) `missing_try` — risky 호출 (Application/connect/pywinauto 메서드/pyautogui.*/pyperclip.*/subprocess.*/selenium find_element 등) 이 try 블록 밖 module-level 또는 top-level 함수 정의 밖. (4) `import_misplaced` — `Import`/`ImportFrom` 가 module body 직계 아닌 모든 위치 (try/def/class/if/for/while/with 안) |
| False positive 방지 정책 | 함수 정의 (`def`/`async def`/`lambda`) 내부의 risky 호출은 검사 제외 (호출자 측 wrap 이면 충분, `_resolve_element` 같은 helper). try.body / except.body / finally.body 모두 protected. module-level Assign / AnnAssign 만 변수 재정의 검사 — for-target / 함수 안 변수 무관 |
| 가드 | test_97 — 9 케이스 (빈 코드 / 정상 코드 / SyntaxError / 변수 재정의 / try 밖 risky / if 안 import / 함수 안 risky 제외 / for-target 제외 / 다중 issue 동시) |

### G7-B (5/11) — `app_service.generate_step` hook + Step.validation_warnings 메타 (test_98)

| Fix | (a) [core/session_manager.py](../core/session_manager.py) `Step` dataclass 에 `validation_warnings: list = field(default_factory=list)` 필드. (b) [core/models.py](../core/models.py) `StepModel` Pydantic 미러도 동일. (c) [core/app_service.py:696-721](../core/app_service.py#L696-L721) `generate_step` 의 Step 생성 직전에 `validate_step_code(delta_body, prev_step_codes=[모든 이전 step 의 step_code])` 호출 → issues 를 `{kind, message, line}` dict 리스트로 변환 후 `Step(validation_warnings=...)` 전달. **차단 X — 실행 그대로 가능**. 정적 분석 실패는 try/except 로 생성 흐름 보호 |
| 가드 | test_98 — Step + StepModel 필드 / 기본값 빈 리스트 / generate_step 소스의 hook 패턴 4종 / try 블록 보호 / dict 변환 형식 / Step 인자 전달 |

### G7-C (5/11) — UI ⚠ 위젯 + tooltip + 상세 다이얼로그 (test_99)

| Fix | (a) [ui/code_viewer.py](../ui/code_viewer.py) `BlockCard.__init__` 에 `validation_warnings: list[dict] \| None = None` 인자. 헤더 status_label 직후에 `QLabel("⚠")` (warnings 있을 때만 — false positive 방지) + tooltip (최대 3건 미리보기 + "외 N건" + "클릭: 상세 보기") + 클릭 → `_show_validation_dialog`. 다이얼로그는 `QMessageBox.warning` + kind 사용자 친화 라벨 매핑 (`syntax`→"문법 오류", `redefined_var`→"변수 재정의", `missing_try`→"try/except 누락", `import_misplaced`→"import 위치 위반"). (b) `_add_step_block` 가 `data.get("validation_warnings")` 전달. (c) [ui/main_window.py](../ui/main_window.py) `_refresh_block_view` 의 `steps_data` 에 `"validation_warnings": step_dict.get("validation_warnings")` 키 추가. (d) [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `StepCardV2` 동일 패턴 + caller 가 `sd.get("validation_warnings")` 전달 |
| 가드 | test_99 — 19 assert (양 카드 시그니처 / ⚠ 위젯 패턴 4종 / _show_validation_dialog 메서드 / kind 라벨 매핑 4종 / 3 caller 의 validation_warnings 전달 패턴) |

### G7-D (5/11) — 재생성 버튼 + prompt warnings inject + settings 옵션 (test_100)

| Fix | (a) [core/prompt_builder.py](../core/prompt_builder.py) `build_step_prompt` / `build_step_prompt_split` / `_build_step_prompt_parts` 시그니처에 `previous_warnings: Optional[list[dict]] = None`. 있으면 user_text 사용자 요청 직후 [1.5] 섹션 "🚨 이전 시도 코드 검사 결과 (반드시 피해야 할 문제)" prepend — 각 issue 의 kind 라벨 / line / message + 4 해결 가이드 (변수 재사용 / try-except 강제 / import 최상단 / 들여쓰기 검증). (b) [core/app_service.py](../core/app_service.py) `generate_step` 시그니처에 `previous_warnings` 인자 + `build_step_prompt_split` 호출 시 전달. (c) [config/default_settings.json](../config/default_settings.json) `execution.auto_regenerate_on_warning: false` 키 (default OFF — 사용자 클릭 우선, UI 토글은 후속 G7-UX). (d) [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `StepCardV2` 새 signal `regenerate_with_warnings_requested(int)`, `_show_validation_dialog` 의 `QMessageBox` 에 "재생성" / "닫기" 버튼 (Retry 시 signal emit), `MainWindowV2._on_regenerate_with_warnings(step_id)` 핸들러 (step lookup → user_request + warnings 추출 → `_send_request(..., previous_warnings=warnings)`), `_send_request` 시그니처에 `previous_warnings` 인자 + `generate_step` 호출 시 전달 |
| 가드 | test_100 — 20 assert (prompt_builder 시그니처 + inject sentinel / None 시 idempotent / app_service 시그니처 + 전달 / default_settings 키 + value / StepCardV2 signal / 다이얼로그 재생성 버튼 + emit / MainWindowV2 connect + 핸들러 + send_request 시그니처) |

**흐름 다이어그램**:
```
AI 가 코드 생성
  → app_service.generate_step 의 hook
  → validate_step_code(delta_body, prev_step_codes=[...])
  → Step.validation_warnings = [{kind, message, line}, ...]
  → 카드 렌더 시 ⚠ 표시 (warnings 있을 때만)
  → 사용자 ⚠ 클릭
  → 상세 다이얼로그 (4 kind 라벨 + line + message)
  → "재생성" 버튼 클릭
  → regenerate_with_warnings_requested(step_id) signal
  → _on_regenerate_with_warnings: user_request + warnings 추출
  → _send_request(..., previous_warnings=warnings)
  → generate_step(previous_warnings=...)
  → build_step_prompt_split(previous_warnings=...)
  → user_text 에 "🚨 이전 시도 코드 검사 결과" inject
  → AI 가 같은 실수 회피해서 재생성
```

### 스코프 제한 (별도 unit 으로 분리)

- **G7-E (legacy `BlockCard` 재생성 버튼)**: legacy 의 _show_validation_dialog 는 정보 표시만 (QMessageBox.warning). 재생성은 ui_v2 에만 — legacy 의 ai_call_handler 경유 path 가 다르고 사용자 메인 환경이 ui_v2 (handoff §16 메모장테스트 v2-새세션). 필요 시 별 unit.
- **G7-UX (settings dialog 토글)**: `auto_regenerate_on_warning` 키만 default_settings.json 에 정의. settings_dialog 의 체크박스 노출은 별도. 현재는 자동 재생성 비활성, 사용자 클릭으로만 동작.
- **F1 / F2 (자동 실행 옵션 / 토스트 힌트)**: G7 흐름과 무관 — handoff 잔존 갭 #6 의 별도 후속.

### 검증 (G7 완료 시점)

baseline 100/100 core + 73/73 scenarios + ruff (lint 0 issue + format 132/132). PySide6 port sync 완료 (core 3 cp + config 1 cp + ui sed 4). 후속 fix 는 §18 참조.

## 18. 5/11 Phase 1.8 후속 fix 모음 (G4 / G7-E / G6 / F2 + G7-UX / F1)

**컨텍스트**: §17 G7 (4 unit) 완료 후 잔존 갭 #5/#6 + handoff §16 의 후속 fix 옵션 6개 (G6/G4/G7-E/F1/F2/G7-UX) 모두 처리. 7 unit 누적, baseline 100 → 106 (+6 회귀 가드, test_101~106). 양 venv 그린. PySide6 port 양쪽 sync.

### G4 (5/11) — `Application().connect()` timeout 보강 (test_101)

| 발견 갭 | handoff §16 잔존 갭 #5 — `timeout=3` 짧음 → 응답 지연 환경에서 false-negative → except 분기 → Popen 으로 새 메모장 인스턴스 매번 추가 |
| Fix | (a) [config/prompts.json](../config/prompts.json) system_context #14(b) 첫 connect 예제 `timeout=3` → `timeout=5` + "⚠ timeout=3 금지" 어휘 + polling 패턴 (20회 × 0.25s) 대안 예제. (b) [core/win_inspector.py:154](../core/win_inspector.py#L154) `inspect_window` 의 `timeout=3` → `timeout=5` |
| 가드 | test_101 — system_context 코드 라인 `timeout=3` 부재 + `timeout=5` 권장 + 'timeout=3 금지' 어휘 + polling sentinel ('for _ in range(20)' + 'time.sleep(0.25)') + win_inspector timeout >= 5 |

### G7-E1 (5/11) — legacy AICallHandler 에 code_validator hook (test_102)

| 발견 갭 | legacy 의 `ai_call_handler.call_ai_thread` 가 `app_service.generate_step` 거치지 않고 직접 `ai_engine.generate` 호출 → G7-B 의 hook 동작 안 함 → legacy 세션의 Step.validation_warnings 가 항상 빈 상태 → 카드 ⚠ 위젯 아예 안 뜸 |
| Fix | [ui/ai_call_handler.py:258~285](../ui/ai_call_handler.py#L258-L285) `on_ai_response` 의 Step 생성 직전에 G7-B 와 동일한 hook (`validate_step_code(delta_body, prev_step_codes=[모든 이전 step 의 step_code])` → dict 변환 → `Step(validation_warnings=...)`). 정적 분석 실패는 try/except 로 보호 |
| 가드 | test_102 — AICallHandler.on_ai_response 소스에 import + validate_step_code 호출 + Step 인자 전달 + prev_step_codes 수집 + try 블록 보호 |

### G7-E2 (5/11) — legacy BlockCard 재생성 버튼 + signal relay (test_103)

| 발견 갭 | G7-D 의 재생성 흐름이 ui_v2 의 StepCardV2 에만 — legacy BlockCard 의 ⚠ 다이얼로그는 정보 표시만. legacy 사용자도 재생성 옵션 필요 |
| Fix | 3단계 signal relay (BlockCard → BlockViewWidget → CodeViewer → MainWindow → AICallHandler): (a) [ui/code_viewer.py](../ui/code_viewer.py) BlockCard 새 signal `regenerate_with_warnings_requested(int)` + `_show_validation_dialog` 의 QMessageBox 에 "재생성" / "닫기" 버튼 (step_id > 0 만), BlockViewWidget + CodeViewer 도 동일 outer signal + relay. (b) [ui/main_window.py](../ui/main_window.py) code_viewer signal 연결 + `_on_regenerate_with_warnings(step_id)` 위임 stub. (c) [ui/ai_call_handler.py](../ui/ai_call_handler.py) `on_regenerate_with_warnings(step_id)` 신규 — step lookup → user_request + warnings 추출 → `call_ai_thread(..., previous_warnings=warnings)`. `call_ai_thread` 시그니처에 `previous_warnings: Optional[list[dict]] = None` + `build_step_prompt` 호출 시 전달 |
| 가드 | test_103 — 3단계 relay 패턴 (signal 양 클래스 + _add_step_block relay + CodeViewer block_view relay) + MainWindow connect + 위임 stub + AICallHandler 메서드 + call_ai_thread 시그니처 + build_step_prompt 전달 |

### G6 (5/11) — system_context 어휘 강화 + 새 #20 가이드 (test_104)

| 발견 갭 | G7 (사후 검출) + G6 (사전 회피) 시너지 — 모델이 처음부터 가이드 따르면 ⚠ 안 뜨고 토큰/시간 절약. 단 system_context 에 "이전 step 변수 재사용" 가이드 명시 없었음 (jupyter mode 호환 핵심) |
| Fix | [config/prompts.json](../config/prompts.json) system_context: (a) #3 (try/except 강제) 어휘 강화 — "🚨 위반 시 외부 자원 silent fallthrough → 후속 step cascade fail. ohdo 의 정적 분석기 (code_validator) 가 ... 검출 시 카드 ⚠ + 재생성 path". (b) #14(b) 변수 명명 규칙 끝에 cross-reference "⚠ 첫 step 에서만 정의, 후속 step 은 재정의 금지 — 가이드 #20 참조". (c) 새 #20 "이전 step 변수 재사용 — 재정의 금지 (Jupyter mode 핵심)" — 3 가지 재정의 문제 + 회귀 사례 (5/10 DeepSeek-V3 메모장테스트 step 3 app/win 재정의) + 올바른 패턴 예제 + 의도된 재정의 예외 (app2/win2) + module-level Assign 만 검사 (for-target 무관) |
| 가드 | test_104 — #3 강화 어휘 4 (silent fallthrough / 정적 분석기 / code_validator / 재생성) + #14(b) cross-ref + #20 본문 4 (제목 / 재정의 금지 / jupyter mode 핵심 / 변수명) + 회귀 사례 인용 + false positive 방지 어휘 (module-level, for x in). system_context 14K → 17K chars (+3K) |

### F2 + G7-UX (5/11) — 실행 힌트 토스트 + settings 체크박스 (test_105)

| 발견 갭 | (F2) 신규 사용자가 step 카드 생성 후 ▶ Ctrl+R / ⏯ 단독 버튼 못 찾음 — 발견성 낮음. (G7-UX) G7-D 의 `auto_regenerate_on_warning` 키만 정의되고 UI 토글 X → 사용자 옵션 발견성 0 |
| Fix | (F2) [config/default_settings.json](../config/default_settings.json) `ui.hint_run_shown: false` 키. [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `_on_step_done` 에 step 첫 성공 생성 시 (step_id > 0 + success + 미표시 플래그) 토스트 "💡 ▶ Ctrl+R 또는 카드의 ⏯ 단독 버튼으로 실행 (다시 안 보임)" 1회 + `hint_run_shown = True` 영구화. (G7-UX) [ui/settings_dialog.py](../ui/settings_dialog.py) 실행 탭에 `auto_regen_cb` QCheckBox + tooltip 2줄 (검사 4종 명시 + 기본 OFF 권장) + load/save 연결 |
| 가드 | test_105 — F2 5 (default 키 + 값 + Ctrl+R / 단독 / 영구화 패턴) + G7-UX 4 (체크박스 + load + save + 한국어 라벨) |

### F1 (5/11) — 코드 생성 직후 자동 실행 (test_106)

| 발견 갭 | handoff §16 잔존 갭 #6 — AI 응답 후 사용자가 ▶ Ctrl+R / ⏯ 단독 버튼 별도로 눌러야 실행. 옵션 도입 시 사용자 입력 → AI → 실행 한 번에 |
| Fix | (a) [config/default_settings.json](../config/default_settings.json) `execution.auto_run_on_step_create: false` (default OFF — 안전). (b) [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `V2Signals` 에 `request_auto_run = pyqtSignal(int)` 신규 (blocks 실행 path step_done 과 분리 — 무한 루프 회피). generate_step worker 의 정상 응답 emit 직후 옵션 체크 + `step.step_id > 0` → `request_auto_run.emit`. signal connect `request_auto_run.connect(self._on_run_single)`. (c) [ui/ai_call_handler.py](../ui/ai_call_handler.py) `on_ai_response` 끝 — 옵션 체크 + `response["success"]` + `step.step_id > 0` → `mw._on_run_single_step(step.step_id)`. 실패 시 console_panel WARNING (step 생성 무효화 X). (d) [ui/settings_dialog.py](../ui/settings_dialog.py) `auto_run_cb` 체크박스 + tooltip 3줄 (동작 + ⚠ 위험 동작 경고 + 기본 OFF 권장) |
| 가드 | test_106 — 옵션 키 + 값 + ui_v2 signal/emit/connect + legacy 옵션 체크/호출/step_id 가드 + settings 체크박스/tooltip 경고 어휘 |

### 검증 결과 (5/11)

baseline 100 → **106** (core 106/106 + scenarios 73/73). ruff lint 0 issue + format 132/132 그린. PySide6 port 양쪽 sync 완료. **handoff §16 잔존 갭 #1~#6 + 후속 fix 옵션 6개 모두 완료**.

### 다음 세션 출발점

- **일상 사용으로 효과 검증**: 7 fix (G7 / G4 / G7-E / G6 / F2 / G7-UX / F1) 가 실제 워크플로우에서 어떤 영향을 주는지 측정.
  - ⚠ 위젯 발생률 (G7 검출 4종 중 어느 kind 가 가장 자주?)
  - 재생성 효과 (warnings 인용 prompt 가 AI 가 같은 실수 반복을 줄이는가?)
  - 자동 실행 (F1) 만족도 — 위험한 자동 실행 사례 vs 편리한 자동 실행 사례
  - G6 가이드 강화 후 model 의 사전 회피율 (⚠ 안 뜨는 비율 증가?)
- 효과 측정 후 새 갭 발견 시 후속 fix 결정
- 또는 다른 우선순위 (Phase 2 commercial_review GO/NO-GO / 영어 README + i18n / Agent 브리지 PoC 등 — handoff §7)

## 19. 5/12 Phase 1.9 C-1 i18n 인프라 + commercial_review 게이트 평가 + PySide6 main 전환 결정

**컨텍스트**: §18 7 unit 완료 + commit `6c7f9c1` 후 일상 사용 검증 대기 상태에서 진입. 이번 세션은 Phase 2 GO/NO-GO 게이트 평가 + Phase 1.9 i18n 인프라 첫 unit + 라이선스 호환성 결정 + 단일 commit (`b11b980`).

### B (5/12) — commercial_review GO/NO-GO 게이트 평가

| 게이트 | 결과 | 비고 |
|---|---|---|
| 1. GitHub Stars 500+ | ❌ 선결과제 미완 | github.com/oddsung/ohdo 404 — 저장소 public 공개 안 됨 |
| 2. 유료 의향 5명+ | ❓ 데이터 필요 | 외부 채널 (Discord/이메일/X DM) 응답 — 사용자 확인 |
| 3. 영어 + 한국어 콘텐츠 mix | 🟡 부분 진행 | README 양쪽 있음 (README.md + README.ko.md) / Show HN·Reddit·dev.to·블로그·유튜브 외부 노출 데이터 필요 |
| 4. Computer Use 우월 X | ❓ 사용자 판단 | 2024-10 출시 + ~1.5년 경과. Anthropic 최근 메이저 업데이트 추적 필요 |

**종합 판단**: 4개 중 ≥3 미충족/평가 불가 → Phase 2 SaaS 백엔드 진입 **NO-GO** 권고. 선결과제: 저장소 public 공개 (게이트 #1 측정 시작점). 옵션 B (Computer Use 어댑터 PoC 1~2주 spike) 또는 옵션 C (포트폴리오 재정의) 도 후보 — commercial_review.md §6/§7 참조.

### C-1 (5/12) — i18n 인프라 (test_107)

| 발견 갭 | 5/9 dual-locale 결정 후 i18n 인프라 미시작. ui/, ui_v2/, core/ 사용자 노출 ~4,800 줄 모두 한국어 literal. QTranslator/gettext/tr() 호출 0건 |
| Fix | (a) [core/i18n.py](../core/i18n.py) — dict 기반 translation dispatcher. API 4 함수 (set_locale/get_locale/tr/reset_cache). fallback locale = `en` (5/9 글로벌 우선 결정). missing key 시 키 자체 반환 + format 스킵 (debug 시 placeholder 그대로 보임). 동시 사용 안 한 locale catalogue 는 lazy 로드 + 메모리 캐시. (b) [core/locale/en.json](../core/locale/en.json) + [core/locale/ko.json](../core/locale/ko.json) — sample 3 키 (app.title, common.ok, common.cancel) |
| 가드 | test_107 — 모듈 API 4 함수 callable + fallback locale = "en" + catalogue 양쪽 존재 + 키 집합 동일 (한쪽 추가 시 다른쪽 누락 방지) + tr 동작 4 케이스 (en/ko/미정의 키/미지원 locale → fallback) |

**prompts.json locale 관리 design 결정**: 옵션 1 (언어별 파일 분리) — `prompts.{ko,en}.json`. 단순, diff 가독성 ↑, 한국어 sentinel test 회귀 보호 (test_104 등). C-4 에서 실제 분리 작업 진행 예정. fallback = en (글로벌 우선). 영어 초안은 Claude 작성 + 사용자 리뷰.

### 5/12 결정 — 최종 PySide6 만 사용 (PyQt6 보관)

**컨텍스트**: 5/2 PySide6 port 추가 (LGPL 라이선스 유연성) 후 양쪽 sync 부담. PyQt6 = GPL → AGPL-3.0 데스크톱 + 상업 SaaS 오픈코어 전략과 라이선스 마찰. PySide6 = LGPL → 호환성 ↑.

**결정**:
- **최종적으로 PySide6 만 사용**, PyQt6 코드는 **삭제 X / 보관**
- 이번 세션부터 PyQt6 쪽 작업 안 함, **PySide6 만 작업**
- 새 세션에서 **Plan 1 (디렉터리 swap + PyQt6 deprecate + PySide6 venv 셋업)** 진행

**이번 세션 PySide6 catch-up**: 5/4~5/11 작업이 PySide6 port 에 코드 sync 됐으나 회귀 가드 11개 (test_97~test_106) 누락 발견 — handoff §18 의 "양쪽 sync 완료" 와 충돌. test_97~test_107 합 12 가드 한 번에 PySide6 catch-up (1035 줄 삽입). PyQt6 직접 import 0건 → sed 변환 불필요, straight copy. PyQt6/PySide6 test 함수 집합 완전 일치 확인.

**검증 한계**: 양 venv (`venv/`, `.venv/`) 모두 PySide6 미설치 → PySide6 port baseline 실행 검증 불가. handoff §3 의 "별도 venv 없음" 정확. 새 세션 venv 셋업 후 확보 예정.

### Commit (5/12)

`b11b980 feat: Phase 1.8 G7 + 후속 fix 7 unit + Phase 1.9 C-1 i18n 인프라`
- 34 files / +4134 / -31
- 7 새 파일: core/i18n.py + core/locale/{en,ko}.json + pyside6_port/core/i18n.py + pyside6_port/core/locale/{en,ko}.json + pyside6_port/docs/handoff.md
- pre-commit hook (end-of-file-fixer) 가 config/default_settings.json 양쪽 newline 자동 fix → re-stage 후 재시도 통과
- `tests/results/latest_result.json` unstaged 유지 (test 결과 캐시, .gitignore 후보 — handoff TODO)

### 다음 세션 출발점 (Plan 1)

**Plan 1 작업 항목 (디렉터리 swap + PyQt6 deprecate + PySide6 venv 셋업)** — 새 세션 시작 시 실행:

1. **디렉터리 swap**:
   - `pyside6_port/` → 메인 위치 (`ui/`, `ui_v2/`, `core/`, `tests/`, `config/`, `docs/` 가 PySide6 기준)
   - 기존 `ui/`, `ui_v2/` (PyQt6) → `legacy_pyqt6/` 로 이동 후 deprecate (삭제 X, 보관)
   - `core/` 는 라이브러리 의존성 없으므로 동일 (PySide6 port 의 core 가 PyQt6 의 복사본)
2. **문서 갱신**:
   - `CLAUDE.md` (root + pyside6_port 양쪽 → 하나로 통합, PySide6 기준)
   - `README.md` + `README.ko.md` — PySide6 기반 명시
   - `docs/ROADMAP.md` — Phase 2 진입 직전 단계, 라이선스 호환성 변경 반영
   - `pyside6_port/docs/handoff.md` 와 `docs/handoff.md` 통합
3. **CI 갱신**:
   - `.github/workflows/ci.yml` — PySide6 dependency 추가, PyQt6 matrix 제거 또는 legacy_pyqt6 한정
4. **venv 셋업**:
   - `.venv` 에 PySide6 추가 (`uv add PySide6`) 또는 별도 `.venv-pyside6/`
   - baseline 실행 검증 (`core 107/107 + scenarios 73/73 그린`)
5. **`tests/results/` gitignore 추가**: 캐시 파일 commit 제외 자동화

**Plan 1 완료 후 C-2 ~ C-6 진입**:
6. C-2 — ui_v2/ 사용자 노출 문자열 추출 + locale catalogue 채움 (~600 lines)
7. C-3 — skip (PyQt6 legacy 미작업)
8. C-4 — prompts.{ko,en}.json 분리 + 영어 초안 작성 + 회귀 가드 갱신 (test_104 등 한국어 sentinel 분리)
9. C-5 — 로그/콘솔 메시지 영어 통일
10. C-6 — README sync 점검 (이미 양쪽 있음, 0 unit)

**B 후속 (사용자 action 필요)**:
11. 저장소 public 공개 (게이트 #1 측정 시작점). README CI 뱃지 동작 확인
12. 외부 콘텐츠 노출 (Show HN / Reddit r/Python / dev.to / 한국 블로그/유튜브)
13. 유료 의향 응답 수집 채널 (Discord/이메일/X DM) 셋업
14. Computer Use 최근 메이저 업데이트 추적
15. 데이터 확보 후 Phase 2 GO/NO-GO 재평가 — commercial_review.md §7 게이트 4개 재검사

## 20. 5/12 Plan 1 완료 — PySide6 (LGPL) 메인 전환

**컨텍스트**: §19 의 5/12 결정 ("최종 PySide6 만 사용, PyQt6 보관") 실행. 새 세션에서 Plan 1 (6 step) 진행. 핵심: 디렉터리 swap (history 보존) + PyQt6 dep 격리 + 문서/CI 갱신 + baseline 회귀 0.

### Plan 1 commit 분할 (총 7 commits)

| # | Commit | 내용 |
|---|---|---|
| C1 | `16d5349 chore: untrack tests/results/latest_result.json` | `git rm --cached` — 이미 `.gitignore` 패턴에 포함 (handoff §19 step 6). |
| C2 | `072dd39 feat(deps): add PySide6, keep PyQt6 (dual import phase)` | swap 직후 import 깨짐 회피용 dual phase. `.venv` 에 PySide6 추가, PyQt6 유지. |
| C3 | `833174a refactor: move PyQt6 sources to legacy_pyqt6/ (history preserved)` | `git mv ui legacy_pyqt6/ui` 등 24 file rename **single source → single destination** (rename detection 명확). 100% similarity. + pyproject.toml `legacy_pyqt6` exclude + `known-first-party` 명시 (ruff source-layout 자동 추론 swap 안정성 ↑). |
| C4 | `f759ebb refactor: promote pyside6_port/ to main location (PySide6 메인 전환)` | `git mv pyside6_port/ui ui` 등 24 file rename + 107 deletion + 2 modification. environment_scanner.py PyQt6→PySide6 string. `tests/test_scenarios.py:2361` sentinel `from PyQt6.QtGui` → `from PySide6.QtGui` (handoff §19 PySide6 catch-up 누락분). ruff format 일괄 — Windows autocrlf 가 swap 후 CRLF 만든 25 files LF 정규화. |
| C5 | `d6642f0 feat(deps): scope PyQt6 to optional extra [legacy-pyqt6]` | `dependencies` 에서 PyQt6 제거, `[project.optional-dependencies] legacy-pyqt6` 추가. `uv sync --extra legacy-pyqt6` 로만 설치. |
| C6 | (이 commit) `docs: rewrite all docs for PySide6 main + add handoff §20` | CLAUDE.md / README*.md / CONTRIBUTING*.md / ROADMAP §10 / pyproject metadata / .pre-commit-config 주석 / .devcontainer / tests/test_runner / ui/main_window / agent/build.spec / requirements.txt 의 PyQt6 mention → PySide6. handoff §0 갱신 + §20 추가. 회고 문서 (triage, feature_catalog, wireframes, saas/*) 보존 (과거 시점 사실). |
| C7 | (다음) CI 갱신 — `.github/workflows/ci.yml` 의 PyQt6 → PySide6, pyside6_port mention 제거. |

### 핵심 함정 + 해결 (다음 swap 시 참고)

1. **git mv rename detection 의 cross-match**: C3+C4 합본 commit 으로 시도하면 두 source (PyQt6 ↔ PySide6 카피) 의 similarity 가 거의 100% — git 이 어느 source 가 어느 destination 으로 갔는지 매칭 결과가 **의도와 반대**로 나옴 (예: `R  pyside6_port/ui/main_window.py -> legacy_pyqt6/ui/main_window.py` — legacy 가 pyside6_port history 를 가져감, 원본 PyQt6 history 끊김). 해결: **분할 commit (C3 단독, C4 단독)** — 각 commit 안에 source 1, destination 1 → 매칭 모호성 0.
2. **`reset --hard HEAD` 의 untracked 빈 디렉터리 잔류**: revert 후 `legacy_pyqt6/ui/`, `legacy_pyqt6/ui_v2/` 가 빈 디렉터리로 남음 (mkdir 로 만들었기에 untracked). 다음 `git mv ui legacy_pyqt6/ui` 가 destination 디렉터리 존재 인식 → `legacy_pyqt6/ui/ui/` 이중 path. 해결: revert 후 `rm -rf legacy_pyqt6/` 로 working tree 청소.
3. **ruff `source-layout` 자동 추론 깨짐**: swap 중간 상태에서 `ui/__init__.py` 가 root 에 일시적으로 없으면 ruff 가 `ui` 모듈을 third-party 로 잘못 분류 → isort 순서 위반 false positive. 해결: pyproject.toml `[tool.ruff.lint.isort]` 에 `known-first-party` 명시.
4. **Windows autocrlf + ruff `line-ending = "lf"` 충돌**: swap 후 working tree 파일이 CRLF — ruff format 이 reformat 요청. 해결: `ruff format .` 실행으로 LF 정규화. 다음 checkout 시 autocrlf 가 다시 CRLF — **후속 작업: `.gitattributes` 도입 (`*.py text eol=lf`) 검토**.
5. **PyQt6 sentinel string 잔재**: `tests/test_scenarios.py:2361` 의 `from PyQt6.QtGui import QSyntaxHighlighter` 가 swap 후 PySide6 의 `QSyntaxHighlighter` 와 binding 충돌 → `issubclass` 검증 fail (test_43). swap 책임 외 sentinel sync 누락. C4 안에 부수 fix 포함.

### 검증 결과 (PySide6 단독 `.venv`)

- core: 107 passed / 0 failed
- scenarios: 73 passed / 0 failed
- ruff check + format: 0 issue
- PyQt6 uninstalled — PySide6 만 import

### 다음 세션 출발점 (C7 + follow-up)

- **C7 완료**: 50b3115 ci: switch CI comments to PySide6, scope legacy_pyqt6 out.
- **follow-up 완료**:
  - `.gitattributes` 추가 (b8ce57f) — §21 참조.
  - C-2 i18n 본격 작업 완료 (§21 참조).
- **잔여**: 저장소 public 공개 (사용자 action), `ui/` v1 i18n (별도 작업).

## 21. 5/12 Phase 1.9 C-2 완료 — ui_v2 i18n + startup locale 감지

**컨텍스트**: §20 Plan 1 (PySide6 메인 전환) 완료 후 진입. C-1 (5/12 오전) 의 i18n 인프라 (core/i18n.py + locale/{en,ko}.json 샘플 3 키) 와 dual-locale 결정 (5/9) 의 마무리 작업. ui_v2 의 사용자 노출 한국어 literal 을 `tr("ns.key")` 호출 + locale catalogue 로 분리.

### C-2 commit 분할 (총 8 commits)

| # | Commit | 내용 | 신규 catalog 키 |
|---|---|---|---|
| pre | `b8ce57f chore: add .gitattributes` | `*.py/.md/...` LF, `*.ps1/.bat/.cmd` CRLF, 바이너리 명시. autocrlf 와 ruff `line-ending=lf` 충돌 항구 해결. renormalize 변경 0 (ruff format 가 이미 정규화). | - |
| C-2a | `4b5e99f feat(i18n): extract ui_v2 user-facing strings (small files)` | onboarding.py (14 키) + command_palette.py (2 키). SCENARIOS class attribute → `_scenarios()` staticmethod (import-time 평가 회피). | 20 |
| C-2b-1 | `20113b4 feat(i18n): extract ui_v2 main_window strings (action bar/step card/chat)` | action_bar (14) + step_card (15) + validation dialog (9) + chat input (7). chat 영역은 처음 분할 안 누락 — 매일 보는 핵심이라 1차 sub-commit 에 포함. | 44 |
| C-2b-2 | `7490d9c feat(i18n): extract ui_v2 tab/sidebar menus + workflow + toasts` | tab/sidebar 컨텍스트 메뉴 (15) + session dialog (5) + workflow export/import (2) + scenarios data (6) + toast format (12). | 38 |
| C-2b-3 | `4502325 feat(i18n): extract ui_v2 remaining strings (empty/dialog/palette/toasts)` | empty state (8) + library/initial card title (2) + run labels (6) + QMessageBox dialog (7) + step_done emit (4) + command palette items + 잔여 toast (24). | 51 |
| C-2c | `e081335 feat(i18n): extract ui_v2 log/console messages + remaining literals` | self._log() 22 호출 + step_done emit 3 + 새 세션 title format + validation tooltip overflow. handoff §19 C-5 "로그/콘솔 영어 통일" 는 dual-locale 으로 확장 처리. | 30 |
| guard | `5d9cb82 test: add test_108 i18n call site / catalogue sync guard` | ui_v2/*.py 안 `tr("ns.key")` 호출 정규식 추출 → en+ko 양쪽 catalog 존재 검증. raw key 화면 노출 사고 방지. | - |
| final | `2d9cece feat(i18n): startup locale auto-detect + settings integration` | main.py 에 `_detect_and_set_locale()` 추가 + main() 시작부 호출 (UI import 전). 우선순위: settings.ui.language → 시스템 locale → "en" fallback. default_settings.json `ui.language` "ko" → "auto". test_109 회귀 가드. | - |

총 신규 catalog 키 **183** (en/ko 양쪽 동일 — test_107 sync 가드).

### 핵심 영향 받은 회귀 가드 (sentinel → tr key 검색 전환)

| Test | 기존 sentinel | 새 sentinel |
|---|---|---|
| test_36 | `OnboardingWizard.SCENARIOS` 직접 참조 | `OnboardingWizard._scenarios()` method 호출 |
| test_100 | `addButton("재생성"` | `addButton(\n            tr("ui_v2.validation.btn_regenerate")` |
| test_678 | `'"⏹ 중지"' in src and '"전송 ▶"' in src` | `'tr("ui_v2.chat.btn_stop")' in src and 'tr("ui_v2.chat.btn_send")' in src` |
| test_743 | `"모두 펼치기" in src and "모두 접기" in src` | `'tr("ui_v2.action_bar.btn_expand_all")' in src and ...` |
| test_1667 | `"워크플로우 가져오기" in src` | `'tr("ui_v2.tab.menu_import_workflow")' in src` |
| test_2336 | `"세션 영구 삭제" in src` | `'tr("ui_v2.tab.menu_delete")' in src` |
| test_2662 | `"💡 템플릿" in src or "템플릿" in src` | `'tr("ui_v2.tab.menu_templates")' in src` |
| test_2750 | `for group in ('"명령"', '"세션"', '"AI 엔진"')` | `for group_key in ('ui_v2.command_palette.group_commands', ...)` |
| test_88 | `"엔진:" in send_src` | `'"ui_v2.step_done.step_generated"' in send_src` (ruff multi-line 분리 대응 — key string 만) |

신규 가드:
- **test_108** — i18n call site / catalogue sync: ui_v2/ 의 모든 `tr("...")` key 가 en+ko 양쪽 catalogue 에 존재 검증.
- **test_109** — startup locale 자동 감지: main._detect_and_set_locale 존재 + main() 호출 sentinel + 함수 안 핵심 패턴.

### 핵심 함정 + 해결 (다음 세션 참고)

1. **Parallel Edit 충돌**: 같은 파일에 동시 Edit tool 호출 시 첫 성공 후 mtime 변경 → 나머지 22개 fail (`File has been modified since read`). 해결: **sequential Edit only** — multi-edit 같은 파일은 한 번에 1개 호출.
2. **ruff format multi-line tr() 분리**: tr() 인자가 많으면 ruff format 가 `tr(\n            "ui_v2..."` 형태로 분리. sentinel 이 `'tr("ui_v2..."'` literal substring 검사면 fail. 해결: **key string 만 검사** (`'"ui_v2..."'` in src).
3. **SCENARIOS class attribute import-time 평가**: tr() 호출이 class attribute 안에 있으면 module import 시 평가 — `set_locale()` 호출 전이라 fallback (en) 결과로 고정. 해결: **method 로 변환** (`@staticmethod _scenarios()`) — 인스턴스 생성 시점에 평가.
4. **cp949 stdout 한글/emoji 출력**: Python -c 또는 print 로 한글/emoji 출력 시 Windows terminal cp949 인코딩 충돌. 해결: `PYTHONIOENCODING=utf-8 .venv\Scripts\python.exe -X utf8 ...` + `sys.stdout.reconfigure(encoding='utf-8')`.
5. **test sentinel = 한국어 literal**: i18n 도입 전 회귀 가드들이 한국어 literal 을 직접 검사 (예: `"⏹ 중지" in src`). i18n 치환 후 source code 에서 사라짐 → 가드 fail. 해결: **tr key 검색으로 갱신** (예: `'tr("ui_v2.chat.btn_stop")' in src`).

### 검증 결과 (PySide6 단독 `.venv`)

- core: **109 passed** / 0 failed (test_108 + test_109 추가)
- scenarios: 73 passed / 0 failed
- ruff check + format: 0 issue
- test_108 측정: ui_v2/*.py 안 tr() 호출 모든 key 가 en+ko catalog 양쪽 존재 (0 missing)

### 다음 세션 출발점 (사용자 결정 대기)

- **GUI 실제 검증 (한국어 ↔ 영어 토글)**: 사용자 직접 — `python main.py --ui v2` 실행. settings.json 의 `ui.language` 를 `"en"` 으로 변경 → 영어 UI 보기 → 다시 `"ko"` 복원.
- **저장소 public 공개**: 사용자 action — commercial_review.md GO/NO-GO 게이트 #1 측정 시작점.
- **ui/ (v1) i18n** (선택): 처음 분할 안에서 C-2 범위 외였지만, dual-locale 완성도 위해 추후 작업 가능. handoff §19 의 C-2 plan 은 ui_v2 만 명시했으므로 별도 sub-task.
- **영어 catalogue 검토**: 영어 초안은 Claude 작성. 자연스러움 다듬기 필요 (특히 "Web search" 같은 일반화된 시나리오 라벨이 한국 사용자의 "네이버 검색" 직역과 다른 의도임).

## 22. 5/12 (저녁~밤) GUI 핵심기능 테스트 세션 — 7 fix (test_110~116)

**컨텍스트**: §21 완료 후 사용자가 ohdo 를 직접 띄워 (`python main.py --ui v2`) cmd 실행 / 메모장 / element picker / step 관리 시나리오를 반복 테스트. 매 보고마다 Claude 가 root cause 분석 → fix → 회귀 가드 추가 루프 진행. **미커밋 — 다음 세션에서 commit 권장** (working tree: `core/app_service.py`, `core/kernel_worker.py`, `core/locale/{en,ko}.json`, `core/prompt_builder.py`, `tests/test_core.py`, `ui_v2/main_window_v2.py`. commit 전 `ruff check` + `ruff format` 한 번 더).

### Fix 목록

| # | Test | 문제 (사용자 보고) | Fix |
|---|---|---|---|
| 1 | test_110 | 실패한 step 이 ✅ 로 오보고 (v2-새세션-153705). subprocess (cmd.exe) 가 trailing newline 없이 fd1 에 출력 → `kernel_worker` 의 `<<<ERROR>>>` 마커가 그 partial line 과 한 라인으로 합쳐짐 → `execution_kernel` 의 `line == "<<<ERROR>>>"` literal 비교 fail → success 유지 | `core/kernel_worker.py` — `RESULT_SUCCESS` / `RESULT_ERROR` / `PONG_RESP` / 빈 코드 success 4곳 모두 `"\n" + MARKER + "\n"` prefix 로 새 라인 보장 |
| 2 | test_111 | AI 가 `subprocess.Popen(['cmd.exe'])` 만 생성 — `kernel_worker` 는 콘솔 없는 piped subprocess 라 자식이 부모 stdio 상속 → CMD 윈도우 미생성, banner 만 파이프로 출력 → `Application().connect(title_re='.*명령 프롬프트')` 영원히 못 찾아 TimeoutError | `core/prompt_builder.py` Windows 가이드 — 콘솔 앱 (cmd/powershell/pwsh/wt) 실행 시 `creationflags=subprocess.CREATE_NEW_CONSOLE` 필수 규칙 추가. GUI 앱 (notepad/chrome) 은 불필요 명시 |
| 3 | test_112 | `AttributeError: 'MainWindowV2' object has no attribute 'settings'` (메모장테스트 step 실행 후). F2 (auto_run hint 토스트) 추가 시 `self.settings` 잘못 사용 — `MainWindowV2` 는 `self.settings` 없음 (항상 `self._load_settings()`). export (line 1588) / F1 (line 2382) 도 같은 버그 복붙 | `ui_v2/main_window_v2.py` 4곳 → `self._load_settings()`. mutate+save 는 `s = self._load_settings(); ...; self._save_settings(s)` |
| 4 | test_113 | 재생성 (G7-D) 이 새 step 추가 — 같은 user_request 두 개 존재. step1 잘못된 코드면 전체 실행 시 step1 실패 → step2 도달 불가, 또는 작업 2번 시도 (메모장테스트). 사용자 직관: ⚠ 재생성 = "이 step 의 문제 해결" → in-place 대체가 맞음 | `core/app_service.py` `generate_step()` 에 `replaces_step_id` 파라미터 — prev_body 계산 시 그 step skip (자기 코드 prev 인식 회피) + `add_step` 대신 `update_step` 분기 (`execution_result=None` reset 포함) + 반환 step.step_id 보존. `ui_v2/main_window_v2.py` `_send_request` + `_on_regenerate_with_warnings` 가 step_id 전달 |
| 5 | test_114 | F3 일시정지 (3초) 후 picker 다시 떠도 main window 가 화면에 보임. `_on_elempick` 가 `self.lower()` 만 — Z-order 만 내려가고 가시 영역 잔존, picker overlay 의 transparent 영역으로 노출 | `ui_v2/main_window_v2.py` — v1 패턴 (`ui_inspection_handler.py:46`) 처럼 `showMinimized()`. picked/cancel 시 `showNormal()` 로 복원 |
| 6 | test_115 | v1 의 step 삭제 기능이 v2 카드에서 누락 (의도 제거 아님 — `wireframes_v2.md` line 110, 123 spec 명시). 또한 ⬆⬇ 버튼이 ✏️ 대비 작고 간격 큼 | `ui_v2/main_window_v2.py` — `StepCardV2.delete_requested = Signal(int)` + 푸터 🗑 버튼 (step_id > 0 만 — Library/Initial 제외) + `MainWindowV2._on_step_delete` (QMessageBox.question confirm → `AppService.delete_step` → 세션 재로드 → `_refresh_step_cards`) + signal 연결. ⬆⬇ → QPushButton + bg_overlay 스타일 통일 (✏️ 와 동일 높이) + footer 기본 spacing (✏️↔🗑 간격과 동일). locale (en+ko) 5쌍 키: `btn_delete` / `btn_delete_tooltip` / `dialog.step_delete_title` / `dialog.step_delete_confirm` / `toast.step_deleted` 외 |
| 7 | test_116 | step 삭제 후 후속 step 의 `generated_code` 에 삭제된 step 코드 잔존 → 전체 실행 시 실행됨. `generated_code` 는 cumulative (library + 이전 step 누적) 인데 `session_manager.delete_step` 은 session.steps 에서 빼고 step_id 만 renumber, chain 정리 안 함. `reorder_step` 은 이미 같은 fix 됨 (5/5) — `delete_step` 만 누락 | `core/app_service.py` `delete_step()` 을 chain 재구성 패턴으로 교체 (reorder_step 동일): ① 삭제 전 모든 step 의 step_code 사전 추출 (`extract_step_delta_code`, chain 정상 시점) + `manually_edited=True` 마킹 ② 대상 step 제거 ③ 새 순서대로 generated_code 재구성 (library + step_code 누적) ④ renumber + save. test_116 은 in-memory session 으로 runtime 검증 (삭제 후 후속 step gen 에 삭제 코드 0회) |

### 검증 결과 (PySide6 단독 `.venv`)
- core: **116 passed** / 0 failed (test_110~116 추가)
- scenarios: 73 passed / 0 failed
- ruff: commit 전 한 번 더 돌릴 것 (이번 세션에서 미실행)

### 다음 세션 출발점

**A. GUI 핵심기능 테스트 계속** (사용자 직접 — Claude 는 결과 paste 받아 분석/fix 담당. 오늘 모델: 이 워크플로우가 잘 작동했음):
- 1순위: 다이얼로그/모달 (메모장 Ctrl+S → 저장 다이얼로그 → 파일명 → 덮어쓰기 확인 Y — system_context #18 가이드 실전 검증) / 한글·CJK 텍스트 입력 (`pyautogui.write` silent skip → `pyperclip`+Ctrl+V 분기, #13) / 다중 윈도우 + found_index (#12)
- 2순위: Excel 셀 자동화 (EFP/owner-drawn, §4.1) / AutoCAD (사용자 도메인 — ohdo 실수익 시나리오, owner-drawn UI 많음)
- 3순위: 클립보드 cross-app 이동 / 우클릭 컨텍스트 메뉴 / 파일 다운로드 + 후처리
- 4순위: UWP 계산기 (`wait('ready')` 환각 빈도, #14c) / 단축키 시퀀스 (`'control'` silent skip 환각, #19)

**B. 재생성/삭제 UX 후속** (선택):
- 재생성/삭제 시 kernel state stale — 기존 step 의 globals 변수 (driver/app 등) 잔존. 큰 영향 시 사용자 수동 kernel restart. 자동 restart 옵션 추가 후보.
- `manually_edited=True` step 도 재생성으로 덮어씀 — 확인 다이얼로그 추가 후보.
- `_on_capture` 의 `self.lower()` 도 element picker 와 동일 UX 이슈 가능 — 사용자 보고 시 `showMinimized()` 적용.

**C. AI 환각 대응** (DeepSeek-chat 모델 한계 — Gemini 는 그나마 잘 함):
- 관찰: title_re 과도한 escape (`r'.*관리자:\ C:\\\\WINDOWS\\\\SYSTEM32\\\\cmd\.exe'`), "이전 스텝에서 import됨" 거짓 단정 → try 안에 import, "지침 숙지...준비됐습니다" 메타-acknowledgment 응답 (메모장테스트 첫 step — 메모장 코드 X, print 한 줄만)
- 후보: 모델별 prompt template 분기 / Gemini 기본 권장 / `test_ai_integration.py` 에 환각 빈도 정량 가드 / AI 메타-acknowledgment 검출 (ai_description 메타 키워드 + generated_code 가 print 한 줄) 후 ⚠ 표시 (false positive 위험 — "Hello World 출력" 같은 진짜 print 요청 구분 필요)

**D. 원래 로드맵 (핵심기능 무관)**:
- 저장소 public 공개 — commercial_review.md GO/NO-GO 게이트 #1 측정 시작점
- ui/ (v1) i18n — dual-locale 완성도 (handoff §19 C-2 plan 은 ui_v2 만 명시 — 별도 sub-task)
- 영어 catalogue 검토 — Claude 초안 자연스러움 다듬기
- handoff §7 우선순위 4~10 (baseline UI 스크린샷 / 와이어프레임 / AI prompt 효과 측정 / Phase 0 본격 진입 / SaaS M3.2+ / AI 자동 에러 복구)

## 9. 자주 하는 실수 / 주의사항

- **`legacy_pyqt6/` 는 freeze 상태**: 5/12 PySide6 메인 전환 이후 PyQt6 코드는 참고용으로 보존. 새 기능 mirror 하지 X. ruff `extend-exclude` 로 lint 대상 제외. 실행 필요 시 `uv sync --extra legacy-pyqt6`.
- **test 메시지에 em-dash 사용**: cp949 인코딩 에러로 test runner 가 ERROR 표시. hyphen 사용. (docstring/markdown 은 OK)
- **delta 추출 fallback**: `.strip()` 사용하면 첫 라인 indent 잘려 `_smart_dedent` 가 못 풀어줌. 사용 금지.
- **wait UI signal**: `valueChanged` 사용하면 매 키 입력마다 emit → 카드 재생성 → 포커스 손실. `editingFinished` 만 사용.
- **개별 step wait 변경 핸들러**: `_refresh_block_view` 호출하면 카드 재생성 → 포커스 손실. session 저장만.
- **handler 분해 시 회귀 테스트**: `inspect.getsource(MainWindow._method)` 로 검사하던 테스트는 메서드가 handler 로 옮겨가면 fail. 검사 대상을 `Handler.method` 로 변경 + `self.xxx` → `mw.xxx` 변환된 패턴으로 assertion 갱신 필수.
- **코드 편집 핸들러는 두 필드 동시 업데이트**: `step_code` 와 `generated_code` 가 desync 되면 `extract_step_delta_code` (실행/화면) 가 stale 한 쪽 우선해 사용자 수정 무시 회귀 발생 (§4.8).
- **subprocess 의 SendInput 으로 ForegroundLock 이전**: pyautogui 같은 input 시뮬레이션 사용 시 권한이 subprocess 로 이동 — `OHDO_PARENT_PID` + `AllowSetForegroundWindow` 패턴 깨면 회귀 (§4.5).
- **i18n tr() 의 parallel Edit 충돌**: 같은 파일에 다발 Edit 호출 시 첫 성공 후 mtime 변경 → 나머지 fail. 한 번에 1개 sequential edit 만 가능 (§21).
- **i18n class attribute import-time 평가**: tr() 가 class attribute 안에 있으면 `set_locale()` 호출 전 평가됨 — method 로 노출 (§21).
- **i18n 회귀 가드 한국어 literal sentinel**: `"⏹ 중지" in src` 같은 sentinel 은 i18n 후 fail. tr key 검색으로 갱신 (§21). 새 i18n 작업 시 영향 받는 sentinel 미리 식별.
- **i18n ruff multi-line 분리**: 인자 많은 tr() 는 multi-line 으로 분리됨. sentinel 은 key string 만 검사 (`'"ui_v2.xxx"'` in src) — 다행히 multi-line 호환.
- **i18n catalog 누락 시 raw key 노출**: tr() 가 missing key 면 key 자체 반환 → 화면에 `ui_v2.xxx.yyy` 그대로 표시. test_108 으로 강제 — 새 tr() 추가 시 catalog 동시 추가.
- **step 삭제/이동 시 generated_code chain 재구성** (§22 #7): 각 step 의 `generated_code` 는 cumulative (library + 이전 step 코드 누적). `session_manager.delete_step`/`move_step` 단독 호출은 step_id 만 renumber 하고 chain 정리 안 함 → 삭제/이동된 step 코드 잔존 → 전체 실행 회귀. `app_service.delete_step` / `reorder_step` 의 사전 step_code 추출 + 새 순서 재구성 path 를 거쳐야 함. UI 는 항상 AppService 경유하므로 OK 지만, 새 step 조작 path 추가 시 이 패턴 필수.
- **ui_v2 MainWindowV2 는 self.settings 없음** (§22 #3): 항상 `self._load_settings()` 로 fresh load. mutate+save 는 `s = self._load_settings(); ...; self._save_settings(s)`. test_112 가 `self.settings` 패턴 0회 강제. (cf. v1 `MainWindow` 은 `self.settings` 보유 — v2 와 다름. SettingsDialog 도 `self.settings` 보유 — 별개)
- **콘솔 앱 launch 시 CREATE_NEW_CONSOLE** (§22 #2): `kernel_worker` 는 콘솔 없는 piped subprocess. AI 생성 코드가 `subprocess.Popen(['cmd.exe'])` 만 호출하면 자식이 부모 stdio 상속 → 윈도우 미생성. `prompt_builder` Windows 가이드에 규칙 박힘 (test_111). GUI 앱 (notepad/chrome) 은 불필요.
- **kernel IPC RESULT 마커는 항상 "\n" prefix** (§22 #1): `kernel_worker` 가 `RESULT_SUCCESS`/`RESULT_ERROR`/`PONG_RESP` 쓸 때 `"\n" + MARKER + "\n"`. subprocess 가 trailing newline 없이 fd1 에 남긴 partial line 과 합쳐지면 `execution_kernel` 의 literal 비교 fail → success/error 오분류. test_110.
- **재생성 (G7-D) 은 in-place 대체** (§22 #4): `generate_step(replaces_step_id=...)` — `add_step` 대신 `update_step`, prev_body 계산 시 그 step skip, step_id 보존. 새 step 추가 X. test_113.
- **v2 element picker 는 showMinimized** (§22 #5): `_on_elempick` 가 `self.showMinimized()` (not `self.lower()`). picked/cancel 시 `showNormal()`. F3 wait 후 main window 가시 회귀 방지. test_114. (cf. `_on_capture` 는 아직 `self.lower()` — 추후 동일 fix 후보)
- **시크릿 placeholder `{{secret:label}}` / element placeholder `{{el:label}}`** (§23): 사용자 메시지에 직접 또는 `@` 자동완성으로 삽입. `{{secret:...}}` 는 prompt_builder 가 그대로 AI 에 전달 + kernel runtime 에 vault 환경변수로 주입. `{{el:...}}` 는 ui_v2 가 전송 직전 `📌 [label]` 자연어 reference 로 사전 치환 → AI 는 placeholder 안 봄. label 패턴: `[a-z0-9_]{1,32}`.
- **`@` 자동완성 trigger 조건** (§23 PR-9): 채팅창에 `@` 가 공백/줄 시작 뒤일 때만 popup. email `user@host` false-positive 회피. popup 에 시크릿 (🔒) + apikey (🔑) + element (📌) 통합 표시.
- **chip 라벨 자동 추론 + 편집** (§23 PR-10c): picker 로 element 잡으면 `core/element_labels.suggest_element_label` 이 HTML/UIA attribute 분석해 의미 라벨 부여 (`type=password` → `pw`, `name=username` → `id`). chip 클릭으로 inline edit. 중복 라벨 거부.

## 10. 사용자에게 빠르게 물어볼 후보

세션 시작 직후 사용자에게 물어볼 만한 질문:
- "다음 작업 후보 (§7) 중 어느 거 진행할까?" (Phase 2.5 Initial 블럭 단독 실행 / AI prompt 효과 측정 / main_window 추가 분해)
- "PySide6 포트 GUI 검증 결과는?"
- "LICENSE 파일 (AGPL-3.0) 추가할까? README 라이선스 섹션도 같이 작성?"

## 23. 5/13~5/14 ADR 0003 Phase 1+2 — 시크릿 처리 + element placeholder (PR-1~10)

**컨텍스트**: 5/13 사용자 질문 — "AI 와 대화로 Python 코드 만들 때 사용자가 웹사이트 ID/PW 나 API 키 같은 민감 정보를 입력하면 그게 그대로 코드에 박혀 보이는 경우 발생. 해결 방법을 여러 가지 제안해 줘." 본 트랙은 그 질문에 대한 다층 방어 (Defense in Depth) 구현. 5/13 ADR + 설계 문서 작성 → Accepted → PR-1~10 순차 구현 → 5/14 완료.

**관련 문서**:
- [ADR 0003 시크릿 처리 정책](saas/decisions/0003-secrets-handling.md)
- [Architecture — Phase 1+2 데이터 흐름·삽입점](saas/architecture/24-secrets-phase-1-2.md)

### Sub-PR 요약

| PR | 작업 | 신규 테스트 |
|---|---|---|
| **PR-1** | A1 detector (`core/secrets_detector.py`) + C1 prompt 가이드 (system_context #21) + C2 정적 분석 (`code_validator.hardcoded_secret` issue kind) | test_117~121 |
| **PR-2** | `core/secrets.py` (`SecretLabel` + `SecretsVault` ABC + `KeyringVault` — OS keyring + `data/vault_index.json` for list()), `core/secrets_redact.py` (placeholder ↔ 평문 변환) | test_122~124 |
| **PR-3** | AppService `secrets_vault` 인자 + 자동 KeyringVault 생성, ExecutionKernel env 주입 (start() 시점), kernel_worker `_get_secret(label)` helper + globals 등록 | test_125~130 |
| **PR-4** | `SecretAdvisoryDialog` (ui_v2) + SettingsDialog 🔒 시크릿 탭 (list/add/delete) + i18n catalog 36 키 + `prepare_outgoing_text` 후크 in `_on_send_message` | test_131 |
| **PR-5** | Detector 보강 — `_QUOTED_LITERAL` 패턴 (따옴표 안 PW-look-alike) + RPA 입력 동사 (`입력`/`write`/`paste` 등) 인접 confidence boost + UI 라벨/식별자 skip list | test_132~133 |
| **PR-6** | Hot secret reload — kernel_worker `<<<SET_SECRETS>>>` IPC 마커 + ExecutionKernel `push_secrets()` (매 execute_block 직전 자동 호출). vault.set 후 즉시 반영 — kernel 재시작 불필요 | test_134~135 |
| **PR-7** | Element-based password-field 감지 — `is_password_field_element` + `detect_with_elements`. HTML `type="password"` / UIA Edit + password-hint automation_id 신호 시 사용자가 PW 키워드 안 써도 advisory 발동 | test_136~137 |
| **PR-8** | Windows Credential Manager import — `core/windows_credentials.py` (`win32cred` wrapper, read-only) + `WindowsCredentialsImportDialog`. 일반 자격 증명 (CRED_TYPE_GENERIC) 만 노출, RDP 등 제외 | test_138 |
| **PR-9** | `@` 자동완성 popup (`SecretInsertPopup`) — 채팅창 `@` + 공백/줄 시작 뒤 trigger, email `user@host` false-positive 회피, `find_at_trigger` helper | test_139~140 |
| **PR-10a** | 🔒 버튼 제거 — `@` 자동완성 만으로 충분 (사용자 피드백) | test_140 갱신 |
| **PR-10b** | `core/element_labels.suggest_element_label` — HTML/UIA attribute 기반 의미 라벨 자동 추론 (`type=password` → `pw`, `userId` → `id`, `userPs` → `pw`) + 중복 시 `_2` suffix | test_141 |
| **PR-10c** | chip 영역 컴포넌트화 — `ui_v2/chip_widgets.py` `ImageChip` + `ElementChip` (stacked widget, inline 라벨 edit) + `_ohdo_label` 키에 라벨 저장 + 중복 라벨 거부 | test_142 |
| **PR-10d** | `@` popup 통합 — `SecretInsertPopup` 에 `elements_provider` 인자, vault (🔒/🔑) + elements (📌) 통합 표시. UserRole 에 `(kind, label)` 튜플 저장, kind 별 placeholder 삽입 (`{{secret:...}}` 또는 `{{el:...}}`) | (test_140 갱신) |
| **PR-10e** | `core/element_placeholders.py` (`{{el:label}}` → `📌 [label]` 자연어 reference 치환, `find_unresolved` 매핑 검사) + `win_inspector.get_element_info_text` header 에 `[📌 label]` suffix. `_on_send_message` 에 미매핑 차단 모달 (i18n) | test_143~144 |

**총 28 신규 테스트** (test_117~144), **10 신규 모듈**:
- `core/secrets.py`, `secrets_detector.py`, `secrets_redact.py`, `windows_credentials.py`, `element_labels.py`, `element_placeholders.py`
- `ui/windows_credentials_import_dialog.py`
- `ui_v2/secret_advisory_dialog.py`, `secret_insert_popup.py`, `chip_widgets.py`

**신규 IPC**: kernel_worker `<<<SET_SECRETS>>>` / `<<<SECRETS_OK>>>` (PR-6 hot reload).

**의존성 추가**: `keyring>=24.0.0` (PR-2). `win32cred` 는 기존 `pywin32` 의 일부 — 추가 없음.

### 핵심 데이터 흐름 (Phase 2 완료 기준)

**시크릿 path**:
```
사용자 입력 → A1 detector (PR-1+5+7) → SecretAdvisoryDialog (PR-4) → vault.set
                                                                    ↓
        AI prompt (placeholder 만) ← prompt_builder ← _send_request (사용자 입력에 placeholder 만 보냄)
                                                                    ↓
        AI 응답 → C2 정적 분석 (PR-1) → Step 저장 (placeholder 만, PR-3)
                                                                    ↓
        kernel.execute_block → push_secrets IPC (PR-6) → env OHDO_SECRET_<label>
                                                                    ↓
        AI 생성 코드 `get_secret('label')` → kernel_worker helper → env 값 반환
```

**Element placeholder path** (PR-10):
```
사용자 picker → chip 영역 (자동 추론 라벨, 편집 가능) → _ohdo_label
                                                            ↓
사용자 채팅에 {{el:label}} 또는 '@' 자동완성 → popup 에서 선택
                                                            ↓
_on_send_message 진입 → find_unresolved → 미매핑 시 차단 + 모달
                                                            ↓
replace_with_references → user_request 내 {{el:label}} → 📌 [label]
                                                            ↓
prompt_builder → element_context 헤더에 [📌 label] suffix → AI
                                                            ↓
AI 가 placeholder 안 보고 평범한 element_context cross-reference 로 코드 생성
```

### 알려진 한계 / Phase 3 후보

1. **세션 마이그레이션 미구현**: 옛 세션 JSON 의 평문 시크릿 자동 detect → 모달 안내. ADR 0003 §4 에 설계 명시되어 있지만 PR 범위 외로 미뤘음.
2. **콘솔 출력 마스킹 미구현**: 사용자 step 코드가 `print(get_secret('xxx'))` 처럼 직접 출력하면 콘솔에 평문 보임. kernel_worker stdout 캡처 단계에서 vault 값 사후 치환 (Phase 3).
3. **Export `.env.example` 분리 미구현**: `app_service.export_workflow` 가 placeholder 그대로 export. `python-dotenv` 기반 `.env.example` + `os.environ` 패턴 변환 (Phase 3).
4. **AI 환각 — try/except 가 RuntimeError 묻음**: PR-3 시도 시 사용자 보고 케이스 — AI 가 `get_secret('password')` 실패한 RuntimeError 를 가장 바깥 try/except 로 잡아 print 만 하고 raise 안 함 → kernel 은 ✅ 보고, 사용자는 콘솔만 보고 confusing. system_context 보강 후보 (re-raise 강제) 또는 PR-7 처럼 정적 가드.
5. **AI api_key vault 마이그레이션**: `settings.json` 평문 잔존 — handoff §6 #5. 같은 `KeyringVault` 의 `apikey` namespace 활용 가능 (이미 가능). UI 마이그레이션 path 미구현.
6. **외부 vault provider** (HashiCorp Vault, 1Password CLI): ADR 0004 후보, SaaS / 팀 시나리오 시.

### 검증 결과

- **core: 144/144 그린** (5/13 핵심 116 + PR-1~10 28 새 테스트 = 144)
- **scenarios: 73/73 그린** (회귀 0)
- **ruff check + format**: All passed
- 실측 (사용자 시스템 — Windows + WinVaultKeyring backend): 22 자격 증명 중 generic 15 enumerate, RDP/도메인 7 자동 필터

### 다음 세션 출발점

**A. 사용자 GUI 검증 (권장 1순위)**: ohdo (`python main.py --ui v2`) 직접 띄워 다음 5 시나리오 실측:
1. 채팅에 평문 PW 입력 → advisory 모달 발동 → 라벨 입력 → vault 등록 → AI 코드에 `get_secret()` 패턴 → 즉시 실행 성공 (PR-6 hot reload 검증)
2. picker 로 password field 선택 → chip 라벨 자동 `pw` → 채팅 `@pw` 입력 → 자동완성 → `{{el:pw}}` 삽입 → 전송 (PR-10 검증)
3. Windows 자격 증명에서 import → Settings → 🔒 시크릿 탭 → 표 표시 → 가져오기 → 채팅 `@` 자동완성에 등장 (PR-8 검증)
4. 미매핑 `@unknown` → 차단 모달 (PR-10e 검증)
5. chip 라벨 클릭으로 inline edit → 라벨 변경 → `@` popup 에 새 라벨로 즉시 반영 (PR-10c 검증)

**B. Phase 3 진행**: 위 한계 1~3 (세션 마이그레이션 / 콘솔 마스킹 / export 분리). 각각 PR-11/12/13 정도.

**C. AI 환각 가드** (한계 4): system_context 보강 또는 정적 검사. 사용자 보고 빈도에 따라 우선순위.

**D. 다른 트랙 복귀**: §22 D 의 저장소 public 공개 준비 / ui/ (v1) i18n / 영어 catalogue 검토 / baseline UI 스크린샷.

## 24. 5/16 ADR 0004 Accepted — 작업 녹화 (Action Recording) 도입 + PR-11 완료

**컨텍스트**: 5/16 사용자 요청 — *"작업 녹화? 작업 자동화? 같은 기능을 만들면 좋을것 같은데 녹화를 시작하고 사용자가 평상시대로 하는 작업을 진행할때마다 클릭 키입력등을 시간순으로 클릭한 요소들을 기록하여 최종적으로 우리가 단계별로 요청하여 생성하는것과 같은 효과를 나타내어 빠르게 자동화 프로그램이 만들어지는 기능 (녹화를 실행하고 기존의 RPA나 자동화 프로그램을 실행하면 자연스럽게 마이그레이션이 될 수 있는)"*. ADR 0003 GUI 검증이 사용자 시간 부족으로 미뤄지면서 다른 트랙으로 전환.

**핵심 발견**: WH_MOUSE_LL / WH_KEYBOARD_LL 후크 코드가 [ui/element_picker.py:2079-2209](../ui/element_picker.py) 에 이미 구현되어 있음 — 녹화 인프라 절반 이상 갖춰진 상태. ohdo 의 win_inspector 가 element 메타 → 코드 생성 로직 보유, ADR 0003 (시크릿 처리) 와 강 통합 시너지 가능 (녹화 중 PW field → 자동 advisory → `get_secret()` 변환). 비개발자/AI 두려운 사용자에게 큰 진입 장벽 감소.

**관련 문서**:
- [ADR 0004 — 작업 녹화 도입](saas/decisions/0004-action-recording.md) (Accepted, 2026-05-16)
- [Architecture — Phase R1+R2 데이터 흐름·삽입점](saas/architecture/25-recording-phase-r1-r2.md) (Accepted)

### 확정 결정 (사용자 승인)

| # | 항목 | 결정 |
|---|---|---|
| 1 | Phase 범위 | R1+R2 묶음 (3주). R3 후순위 |
| 2 | 결과 미리보기 | 항상 강제 (R1). 즉시 commit 모드 R3 후보 |
| 3 | 녹화 핫키 | Ctrl+Shift+R 하드코딩 (R1). 사용자 설정 R2 |
| 4 | 마이그레이션 모드 | R2 (Power Automate / AutoHotkey / pywinauto 따라잡기). R1 은 데스크톱 핵심 |
| 5 | 화면 캡처 | OFF 기본 (사생활). R3 OpenCV fallback 시 옵션 ON 가능 |
| 6 | **메인화면 통합 (사용자 추가 요청)** | D25 빈 상태 화면 (예시 카드 위) 에 "🎬 자동 녹화로 만들기" 강조 카드 + "+ 새 탭" 메뉴에 "녹화로 새 세션" 액션 |
| 7 | **Step 적절한 구분 (사용자 추가 요청)** | 자동 경계 신호 4종: 창 포커스 / F8 marker / 동일 element key group 종료 / idle_boundary_ms (3초) 휴지. user_request 자동 생성 (control_type + name 조합) |
| 8 | **review dialog 편집 강화 (사용자 추가 요청)** | inline 편집 (user_request/code/wait), drag&drop 순서, multi-select bulk action, 인접 step 합치기/분할, 변환 옵션 toggle 즉시 재변환, raw events 디버그 보기 |

### PR 분할 (R1 5개 + R2 3개)

| PR | 작업 | 상태 |
|---|---|---|
| **PR-11** | `core/input_hooks.py` 신규 — multi-callback LL hook manager. element_picker inline hook 은 그대로 둠 (R2/R3 점진 마이그레이션, test_44~48 sentinel 보호) | ✅ **완료** (test_145~148 4 신규) |
| **PR-12** | `core/recorder_models.py` (RawEvent + RecordingSession + TransformOptions Pydantic) + `core/recorder.py` (Recorder lifecycle + InputHookManager 통합 + element_capture_fn callback hook) | ✅ **완료** (test_149~152 4 신규) |
| **PR-13** | `core/recorder_transform.py` — raw events → Step 변환 (노이즈 필터 + 키 그룹핑 + 자동 경계 4 신호 + element_meta → pywinauto/Selenium/pyautogui 코드 + user_request 자동 생성 + ADR 0003 강 통합 PW field → get_secret) | ✅ **완료** (test_153~158 6 신규) |
| **PR-14** | AppService — `start_recording` / `stop_recording` / `commit_recording` + listener pattern (`add_recording_listener` / `remove_recording_listener`) + 이벤트 (`recording.started` / `stopped` / `committed`). EventBus 신규 모듈은 도입 X — 가벼운 callback list 패턴 (PR-15 UI 가 connect 쉽고 향후 EventBus 통합 쉬움) | ✅ **완료** (test_159~161 3 신규) |
| **PR-15** | UI — `ui_v2/recorder_overlay.py` (click-through floating overlay, WA_TransparentForMouseEvents) + `ui_v2/recording_review_dialog.py` (inline 편집 + drag&drop + bulk action + 4 옵션 toggle 즉시 재변환 + raw events 보기) + main_window_v2 통합 (툴바 ⏺ + Ctrl+Shift+R + D25 빈 상태 🎬 카드 + + 새 탭 메뉴) + locale 47 키 (en/ko) | ✅ **완료** (test_162~167 6 신규) |
| **PR-16w (R2)** | `core/input_hooks.py` SetWinEventHook(EVENT_SYSTEM_FOREGROUND, SKIPOWNPROCESS) + WinEventEvent/WinEventCallback API + `core/recorder.py` start/stop 에서 winevent callback 등록·해제 + `_on_winevent_event` 가 window_focus RawEvent 적재 + F8 keydown (VK_F8=0x77) 을 enable_f8_marker 옵션에 따라 marker RawEvent 로 자동 변환 | ✅ **완료** (test_170~173 4 신규) |
| **PR-17 (R2)** | `core/recorder.py` async event queue + drain thread — hook callback 은 RawEvent 생성 + 큐 enqueue 만 (fast return). drain thread 가 element_capture_fn 호출 + session 적재. backpressure (oldest drop + counter) + sentinel join. `core/input_hooks.py` docstring 에 "callback fast return" 원칙 명시 | ✅ **완료** (test_174~177 4 신규 + PR-12/14/16w async 갱신) |
| **PR-18 (R2)** | `core/input_hooks.py` ensure_dpi_awareness (PER_MONITOR_AWARE_V2) + get_dpi_for_point + get_hook_manager 가 매 호출 idempotent 트리거 + `core/recorder.py` drain 가 click 의 monitor_dpi 캡처 + `core/recorder_models.py` RawEvent.monitor_dpi 필드 + `core/recorder_transform.py` fallback 좌표 코드에 비표준 DPI 코멘트. **R2 완료** | ✅ **완료** (test_178~181 4 신규) |

### PR-11 핵심 구현 노트

**`core/input_hooks.py`** (375줄, AGPL-3.0 SPDX):
- `MouseEvent` / `KeyboardEvent` dataclass + `Literal` 타입 (move / lbutton_down/up / rbutton_down/up / mbutton_down/up / wheel / keydown / keyup / syskeydown / syskeyup)
- Win32 상수 (`WH_MOUSE_LL=14`, `WH_KEYBOARD_LL=13`, `WM_*` 12개)
- `InputHookManager` — 단일 instance 가 hook 설치 + multi-callback dispatch
  - `install_mouse_callback(cb) -> int` (등록 ID 반환), `uninstall_mouse_callback(cb_id)`
  - 동일 패턴 keyboard 측
  - `uninstall_all()` 전부 해제
  - 콜백 등록 시 자동 hook 설치, 마지막 해제 시 자동 hook 제거
  - callback 시그니처: `(MouseEvent) -> bool` — True 반환 시 차단 (CallNextHookEx 호출 X), False/None 통과
  - dispatch 시 callback snapshot — 예외 발생해도 다른 callback 영향 X (try/except 격리)
  - non-Windows 환경에서 `_user32 = None` → install/uninstall silent noop, `is_*_hook_installed` 항상 False
- `get_hook_manager()` 모듈 레벨 싱글톤 — recorder + 향후 element_picker 통합 시 공유

**element_picker 비변경 결정 근거**: test_44 sentinel 이 `_install_mouse_hook` source 안에서 `WH_MOUSE_LL`, `WM_LBUTTONDOWN`, `return 1`, `CallNextHookEx` 등 키워드 직접 검사 → wrapper 로 바꾸면 자동 fail. Win32 LL hook 은 같은 thread 에 여러 hook 동시 설치 가능 (call chain) + element_picker 와 recorder lifecycle 동시 활성 X (ADR 0004 명시). PR-11 에서는 두 hook 시스템 병렬 유지, R2/R3 에서 점진 통합.

### 회귀 가드 (test_145~148, 4 신규)

- **test_145**: 모듈 + dataclass + Literal 타입 + Win32 상수 + InputHookManager API + get_hook_manager 싱글톤
- **test_146**: callback 등록 ID 고유성 + 부분 해제 + 잘못된 ID idempotent + uninstall_all
- **test_147**: callback 예외 격리 — 한 callback 예외가 다른 callback dispatch 영향 X
- **test_148**: non-Windows silent noop (`_user32 = None` 강제 path 검증)

### PR-12 핵심 구현 노트

**`core/recorder_models.py`** (Pydantic v2):
- `RawEvent` — LL hook 캡처된 단일 입력. `kind: Literal["click", "key", "scroll", "window_focus", "marker"]` + 종류별 필드 (x/y/button/click_count, vk_code/key/text/modifiers, hwnd/window_title/exe_name, element_meta, screenshot_path, is_password_field, wheel_delta). 모두 Optional default — kind 별 분기.
- `RecordingSession` — 녹화 한 세션. `id` (uuid4) + `started_at` / `stopped_at` + `events: list[RawEvent]` + `target_session_id`. property `is_stopped` / `event_count`.
- `TransformOptions` — PR-13 에서 사용할 변환 옵션 9개. 핵심: `idle_boundary_ms=3000` (사용자 추가 요청 §7 의미 단위 휴지), `integrate_secrets=True` (ADR 0003 강 통합), `group_consecutive_keys=True`, `drop_self_window_clicks=True`.

**`core/recorder.py`** (Recorder lifecycle):
- `Recorder(hook_manager, opts, element_capture_fn=None)` — InputHookManager 주입 + element_capture_fn callback hook (PR-13/PR-15 에서 win_inspector EFP 연결)
- `start(target_session_id) -> RecordingSession` — 새 RecordingSession + mouse/keyboard callback 등록. 이미 녹화 중이면 `RecorderAlreadyStartedError`
- `stop() -> RecordingSession` — callback 해제 + stopped_at 기록. 두 번 stop 도 동일 세션 반환 (멱등)
- `add_marker()` — F8 수동 step 경계. 녹화 안 한 상태면 `RecorderNotStartedError`
- 캡처 동작: `lbutton_down` / `rbutton_down` / `mbutton_down` → click event, `wheel` → scroll event, `keydown` / `syskeydown` → key event. `move` 무시 (PR-12 범위 외 — drag 캡처 R3 후보), `*_up` 무시 (`_down` 만 캡처)
- element_capture_fn 주입 시 click event 에서 호출 → element_meta 채움. callback 예외 시 element_meta None 으로 진행 (event 자체는 정상 추가)
- callback 항상 False 반환 (이벤트 통과 — 녹화 중 사용자 평상시 작업 보장. 차단 X)
- 스레드 안전: hook callback 은 OS hook thread, buffer 접근 시 lock 필수. start/stop 도 lock 으로 보호

### 회귀 가드 (test_149~152, PR-12 4 신규)

- **test_149**: RawEvent + RecordingSession + TransformOptions 필드 구조 + 사용자 추가 §7 키 (`idle_boundary_ms=3000`, `integrate_secrets=True`)
- **test_150**: start/stop/marker 상태 전이 + `RecorderAlreadyStartedError` / `RecorderNotStartedError` + stop 멱등 + hook callback 등록/해제 카운트 + 재진입 시 새 세션 id
- **test_151**: mouse/keyboard event buffer 누적 — click/scroll/key 종류별 + lbutton_up/move 무시 + 시간순 정렬
- **test_152**: element_capture_fn 호출 (click 시), callback 예외 격리, wheel/key 는 미호출

### PR-13 핵심 구현 노트

**`core/recorder_transform.py`** (raw events → Step):
- `transform(session, opts=None, self_window_titles=None) -> list[Step]` 메인 entry
- **노이즈 필터** (`_filter_noise`): `drop_self_window_clicks` (`self_window_titles` 리스트에 매칭되는 window_title 가진 click drop) + `drop_empty_space_clicks` (element_meta None click drop)
- **자동 경계 4 신호** (`_split_into_batches`):
  - F8 marker → batch 분리 + marker 자체 drop
  - window_focus → batch 분리 (R2 캡처 활성 후 동작)
  - `idle_boundary_ms` 휴지 → 새 batch (기본 3000ms)
  - 이전 key + 현재 click → 새 batch (key group 종료)
  - 이전 click + 현재 click + 다른 element → 새 batch (같은 element 면 double click 같은 batch)
- **Step 생성** (`_batch_to_step`):
  - click → `_emit_click` (브라우저 `css_selector`/`xpath` → Selenium, 데스크톱 → pywinauto `child_window().click_input()`, owner-drawn (meta None) → `pyautogui.click(x, y)`)
  - key → `_emit_key_group` 으로 묶음. `_VK_CHAR_MAP` (0x30-0x39, 0x41-0x5A, SPACE) → 텍스트 누적, `_VK_SPECIAL_KEYS` (Enter/Tab/Backspace/Esc/F2~F9) → `pyautogui.press()` 별도
  - scroll → `pyautogui.scroll(wheel_delta, x, y)`
- **user_request 자동 생성** (사용자 추가 §7): 각 action 의 description ("Button '확인' left 클릭", "Edit '사용자 ID' 클릭 후 텍스트 입력 'abc'") 을 ` 후 ` 로 join
- **ADR 0003 강 통합** (`integrate_secrets=True`): click 의 element_meta 가 `is_password_field=True` 또는 `control_type=Edit + automation_id 에 'password' 포함` 이면, 그 다음 key 그룹은 `pyautogui.write(get_secret('label'))` 으로 변환. label 은 `_ohdo_label` 우선, 없으면 `'password'`. **평문 PW 가 generated_code 에 단 한 번도 박히지 않음** — ADR 0003 보안 보장이 녹화 path 에서도 자동 적용.

**Step 출력 필드**:
- `step_id` = 1, 2, 3... (transform 내부에서 reassign; AppService 의 add_step 가 최종 할당)
- `user_request` = 자동 description (편집 가능)
- `generated_code` / `step_code` = 동일 코드 (delta 분리는 PR-14 에서)
- `conversation` = `[{role: "system", content: "[recording] 작업 녹화로 자동 생성된 step"}, {role: "user", content: user_request}]`

**PR-13 의 코드 생성 minimal — review dialog (PR-15) 에서 편집**: 정교한 코드는 PR-15 의 AI 후처리 (R3 후보) 또는 win_inspector helper 통합으로 미룸.

### 회귀 가드 (test_153~158, PR-13 6 신규)

- **test_153**: 단일 click + element_meta → pywinauto 코드 + user_request 자동 생성
- **test_154**: 노이즈 필터 (`drop_self_window_clicks` "ohdo" 매칭 + `drop_empty_space_clicks=True` element_meta None click drop)
- **test_155**: 연속 키 5개 (HELLO) → `pyautogui.write('hello')` 1개로 그룹핑
- **test_156**: 자동 경계 4 신호 — idle_boundary_ms 5초 휴지 → 2 step + key→click 전환 → 2 step + F8 marker → 2 step (marker 자체 drop)
- **test_157**: ADR 0003 강 통합 — PW field click 후 'secret' 키 시퀀스 → `get_secret('login_pw')` 변환 + 평문 'secret' 코드에 안 박힘. integrate_secrets=False 시 평문 (디버그 모드)
- **test_158**: 브라우저 element (css_selector) → Selenium `find_element(By.CSS_SELECTOR).click()` + element_meta None → `pyautogui.click(x, y, button='right')` fallback

### PR-14 핵심 구현 노트

**`core/app_service.py`** 추가 (단일 instance per AppService — Recorder 자체가 lock 으로 동시 두 녹화 거부):

```python
# 인스턴스 변수 (__init__):
self._recorder: Optional["Recorder"] = None
self._recording_listeners: list[Callable[[str, dict], None]] = []

# Listener 패턴 (EventBus 모듈 신규 도입 X — minimal change):
def add_recording_listener(callback) -> None: ...
def remove_recording_listener(callback) -> None: ...
def _emit_recording_event(event_name, payload) -> None: ...

@property
def is_recording -> bool
@property
def recording_event_count -> int

# Lifecycle 메서드:
def start_recording(target_session_id=None, element_capture_fn=None) -> str
def stop_recording(self_window_titles=None) -> list[Step]
def commit_recording(edited_steps, target_session_id=None, new_session_title=None) -> Session
```

**이벤트 종류** (callback 시그니처: `(event_name: str, payload: dict)`):
- `recording.started` — payload `{recording_session_id, target_session_id}`
- `recording.stopped` — payload `{recording_session_id, raw_event_count, transformed_step_count}`
- `recording.committed` — payload `{recording_session_id, target_session_id, step_count}`

**lifecycle 흐름**:
1. `start_recording` — `get_hook_manager()` + `Recorder` 신규 인스턴스 + `recorder.start()` → "started" emit, recording_session_id 반환
2. (UI 가 element_capture_fn 주입 — PR-15 의 WindowInspector EFP 연결)
3. `stop_recording` — `recorder.stop()` + `transform()` → "stopped" emit, Step 리스트 반환 (아직 commit X)
4. (UI 가 review dialog 로 사용자 편집)
5. `commit_recording(edited_steps)` — target_session_id None 이면 create_session 자동 ("Recording YYYYMMDD-HHMMSS" 또는 new_session_title), 각 step → repo.add_step → "committed" emit + Recorder 인스턴스 정리

**listener 격리**: callback 예외 시 다른 listener dispatch 영향 X (try/except).

**EventBus 모듈 도입 보류**: ohdo 에는 EventBus 가 없음. 가벼운 callback list 로 시작 — PR-15 UI 가 connect 쉽고, Phase 2 SaaS 진입 시 EventBus 통합도 쉬움. architecture 25 의 "EventBus 신규 이벤트" 는 listener pattern 으로 대체.

### 회귀 가드 (test_159~161, PR-14 3 신규)

- **test_159**: 전체 lifecycle (initial state → listener 등록 → start → event 누적 → stop → commit → listener 해제 후 dispatch X) — InMemoryRepository 사용 통합 검증
- **test_160**: 중복 start 거부 (`RecorderAlreadyStartedError`)
- **test_161**: target_session_id 분기 (지정 → 그 세션, None → 새 세션 자동 + new_session_title 적용)

### PR-15 핵심 구현 노트

**`ui_v2/recorder_overlay.py`** (RecorderOverlay):
- `Qt.FramelessWindowHint | WindowStaysOnTopHint | Tool` + `WA_ShowWithoutActivating`
- 전체 위젯 `WA_TransparentForMouseEvents=True` (click-through) — 자식 [중지] 버튼만 명시적으로 `WA_TransparentForMouseEvents=False` 로 mouse 받음 (Win32 LL hook 기반 녹화는 부모 click-through 와 무관하게 동작 — overlay 는 단순 시각 표시)
- 표시: 빨간 ⏺ + 경과시간 (mm:ss) + event count + [■ 중지]
- `start()`: 우상단으로 자동 배치 (작업표시줄 여백) + 0.5초 QTimer 갱신 시작
- `stop_and_hide()`: timer 정지 + 숨김
- 콜백 주입: `get_event_count` (AppService.recording_event_count) + `on_stop` (UI 측 stop 처리)
- callback 예외 격리 (overlay 마비 방지)

**`ui_v2/recording_review_dialog.py`** (RecordingReviewDialog) — 사용자 추가 §8 6 기능:
- 헤더: 단계 수 + raw event 수 요약
- **변환 옵션 4 토글** (즉시 재변환): `group_consecutive_keys` / `drop_empty_space_clicks` / `auto_window_focus_boundary` / `integrate_secrets`. raw recording_session 보존 → toggle 시 `recorder_transform.transform()` 다시 호출 → step 리스트 재구성
- **step 카드 리스트** (QListWidget + `InternalMove` drag&drop + `ExtendedSelection` multi-select)
  - 각 카드: 제목 (double-click 으로 inline 편집 via QInputDialog) + wait spinbox (0~60000ms) + code preview (3줄) + 버튼 6개 (💻 코드 편집 / ✂ 분할 / 🔗 위와 합치기 / ⬆ ⬇ / 🗑 삭제)
  - drag&drop 후 `id(step)` 기반 재배열 (widget detach 회피)
  - rowsMoved 재진입 가드 (`blockSignals` + `_refresh_list` 내부)
- **bulk action**: 우클릭 컨텍스트 → 선택 삭제 / 선택 합치기 / 전체 선택 / 선택 해제
- **분할**: 코드 줄을 절반으로 나눠 새 step 삽입; **합치기**: 이전 step 의 generated_code 에 누적 + user_request join (" 후 ")
- **코드 편집**: 별도 QDialog (QPlainTextEdit + OK/Cancel) — 큰 영역 편집
- **raw events 보기**: 별도 dialog (read-only QPlainTextEdit) — `RawEvent.model_dump(mode="json", exclude_none=True)` 각 라인 JSON
- accept 시 `edited_steps` 가 채워짐; cancel 시 빈 리스트

**`ui_v2/main_window_v2.py` 통합**:
- 액션바 ⏺ 버튼 (`_record_btn`, 빨간 글씨) + Ctrl+Shift+R `QShortcut` — 둘 다 `_on_toggle_recording` 진입
- `_on_toggle_recording`: 녹화 중이면 `_do_stop_recording`, 아니면 `_do_start_recording(target=current_session_id)`
- `_do_start_recording`: `app_service.start_recording(target_session_id)` → 버튼 스타일 toggled (배경 빨강) → `RecorderOverlay` 생성 + start → `self.showMinimized()` → 토스트
- `_do_stop_recording`: `stop_recording(self_window_titles=["ohdo"])` → overlay teardown → `showNormal` + `activateWindow` → 변환 step 0 개면 commit empty + 경고 토스트 / 1+ 개면 review dialog
- `_show_review_dialog`: `RecordingReviewDialog.exec()` → Accepted 면 `commit_recording(edited_steps, target_session_id)` + 세션 열기 + 토스트, Rejected 면 commit empty 로 recorder 정리 + cancel 토스트
- **D25 빈 상태 통합**: `_show_empty_state` 가 `show_recording_card: bool = False` 인자 추가 → 세션 빈 상태 호출에서 `True` → 예시 카드 위에 "🎬 자동 녹화로 만들기" 강조 카드 (빨간 테두리 + 큰 버튼) 노출
- **+ 새 탭 메뉴**: `_on_plus_tab` 메뉴에 "🎬 녹화로 새 세션 시작" 액션 추가 → `_on_new_session_with_recording` (빈 세션 + 즉시 녹화)
- toolbar 버튼 + 핫키 + D25 카드 + + 새 탭 → 4 진입점이 모두 같은 lifecycle (`_on_toggle_recording` / `_do_start_recording`) 로 수렴

**locale 47 키 추가** (`core/locale/{en,ko}.json` 양쪽 동일 set):
- `ui_v2.recording.action_bar.*` (버튼/툴팁), `ui_v2.recording.tab_menu.new_recording`
- `ui_v2.recording.empty.card_*` (빈 상태 카드 제목/설명/버튼)
- `ui_v2.recording.overlay.*` (라벨/중지 버튼)
- `ui_v2.recording.review.*` (다이얼로그/옵션/버튼/컨텍스트 ~30 키)
- `ui_v2.recording.toast.*` (started/stopped/committed/empty_steps/error/cancel/commit_failed)

### 회귀 가드 (test_162~167, PR-15 6 신규)

- **test_162**: 툴바 ⏺ 버튼 (`_record_btn`) + Ctrl+Shift+R `QShortcut` + `_on_toggle_recording` 핸들러 + `_do_start_recording` / `_do_stop_recording` 헬퍼 + tr 키 사용 (action_bar.btn / tooltip_start / tooltip_stop)
- **test_163**: RecorderOverlay 의 Qt 플래그 sentinel — FramelessWindowHint / WindowStaysOnTopHint / Tool / WA_ShowWithoutActivating / WA_TransparentForMouseEvents (True 부모 + False 자식) / start / stop_and_hide / get_event_count + on_stop 인자
- **test_164**: locale 47 키 catalog 검증 — en/ko 양쪽 30+ 키, key set 동일, 필수 키 (action_bar.btn / overlay.label_recording / review.title / empty.card_title / tab_menu.new_recording / toast.started/committed) 노출
- **test_165**: ADR 0003 시너지 sentinel — recorder_transform 의 `integrate_secrets` / `is_password_field` / `get_secret(` path 살아있음 + review dialog 의 `opt_secrets` 토글 tr 키 노출
- **test_166**: D25 빈 상태 카드 sentinel — `_show_empty_state` 가 `show_recording_card` 인자 받음 + 세션 빈 상태 호출에서 `show_recording_card=True` + 카드 tr 키 (empty.card_title / desc / btn) + + 새 탭 메뉴의 `tab_menu.new_recording` + `_on_new_session_with_recording` 핸들러
- **test_167**: review dialog 편집 기능 sentinel — 13 메서드 (`_on_step_wait_changed` / `_on_edit_code` / `_on_item_double_clicked` / `_on_option_toggled` / `_on_split` / `_on_merge_prev` / `_on_move` / `_on_delete` / `_on_rows_moved` / `_bulk_delete` / `_bulk_merge` / `_on_context_menu` / `_on_view_raw_events`) + Qt 모드 sentinel (InternalMove / ExtendedSelection / transform / TransformOptions / blockSignals) + tr 키 6개

### PR-16a 핵심 구현 노트 (5/16 — R1 완료 후 사용자 즉시 요청)

**배경**: 사용자가 "녹화 시 element 정보를 element_picker 수준으로 수집하고, 종료 후 한번에 step 별 자동화 코드 생성" 을 요청. 첫 갭 분석에서 발견 — PR-14 의 `element_capture_fn` 인자는 설계상 element_picker 수준 메타를 받게 되어 있지만, PR-15 의 `_do_start_recording` 이 callback 을 안 넘기고 있어서 모든 click 의 `element_meta=None`. recorder_transform 은 좌표 fallback (`pyautogui.click(x, y)`) 만 생성. PR-16a 가 이 갭을 메움.

**`core/element_inspect.py`** (신규, ~190줄, AGPL-3.0 SPDX):
- `capture_element_at(x, y) -> Optional[dict]` — best-effort UIA EFP 캡처
- `IUIAutomation::ElementFromPoint` (element_picker 의 `_detect_via_efp` 와 동일 path) → UIAWrapper 래핑 → 필드 추출
- 채우는 필드: `control_type`, `name`, `automation_id`, `class_name`, `window_title` (top-level), `hwnd`, `process_id`, `exe_name` (basename only — 보안), `rect`, `is_password_field`
- `is_password_field` 감지 — UIA `CurrentIsPassword` property (가장 정확) + heuristic fallback (automation_id/class 에 'password'/'pwd')
- 모든 예외 격리 — 실패 시 None 반환 → recorder_transform 이 자동으로 좌표 fallback
- non-Windows 환경 silent fallback (`sys.platform` 분기 + 지연 import)
- UI overlay / signal / hierarchy 의존 X — LL hook thread 에서 직접 호출 가능 (스레드 안전)
- 브라우저 element (css_selector / xpath / tag_name) 는 R3 / PR-17 (async CDP) 에서 추가. PR-16a 는 desktop subset 만

**`ui_v2/main_window_v2.py` 변경 (단 4줄)**:
- `_do_start_recording` 안에서 `from core.element_inspect import capture_element_at` 지연 import
- `app_service.start_recording(target_session_id=..., element_capture_fn=capture_element_at)` 로 callback 주입
- 다른 lifecycle path 무변경 — Recorder + AppService 가 이미 element_capture_fn 받게 설계되어 있어서 PR-16a 는 단순 wire-up

**예상 비용**: LL hook callback thread 에서 EFP 호출 → 평균 50~200ms (target element 의 a11y 트리 활성도에 따라). Windows LL hook 의 ~300ms 타임아웃에 닿을 가능성 있음 — 그 경우 Windows 가 hook 을 skip 하거나 자동 비활성화 (회복 가능). 진짜 안정성 보장은 PR-17 (async EFP + event queue) 의 몫이지만 PR-16a 의 sync 호출도 일반 사용에서는 충분히 빠름

**ADR 0003 시너지**: `is_password_field=True` 가 element_meta 에 채워지면 recorder_transform 의 `integrate_secrets=True` path 가 자동 발화 → 다음 키 그룹이 `pyautogui.write(get_secret('label'))` 로 변환. 평문 PW 가 generated_code 에 단 한 번도 박히지 않는 보안 약속 PR-16a 부터 실제로 동작 (이전엔 element_meta=None 으로 인해 detection 자체가 안 됨)

### 회귀 가드 (test_168~169, PR-16a 2 신규)

- **test_168**: `core.element_inspect` 모듈 contract — `capture_element_at` callable + (x, y) 시그니처 + 필수 10 필드 sentinel (control_type / name / automation_id / class_name / window_title / hwnd / process_id / exe_name / rect / is_password_field) + non-Windows 분기 + UIA `CurrentIsPassword` path
- **test_169**: `MainWindowV2._do_start_recording` 의 element_capture_fn 주입 sentinel — `from core.element_inspect import capture_element_at` import + `element_capture_fn=capture_element_at` keyword 호출

### PR-16w 핵심 구현 노트 (5/18 — R2 첫 PR; PR-16a 와 이름 충돌 회피로 -w 접미사)

**배경**: PR-13 에서 `auto_window_focus_boundary` / `enable_f8_marker` TransformOptions 와 `_split_into_batches` 의 window_focus / marker 처리 로직이 구현되어 있었지만, 실제 캡처 path 가 없어서 dead code 였음 (RawEvent 의 `window_focus` / `marker` kind 가 외부에서 들어올 일 없었음). PR-16w 가 캡처 path 를 활성화하여 end-to-end 작동.

**`core/input_hooks.py` 변경**:
- Win32 상수 추가: `EVENT_SYSTEM_FOREGROUND=0x3`, `WINEVENT_OUTOFCONTEXT=0x0`, `WINEVENT_SKIPOWNPROCESS=0x2`, `OBJID_WINDOW=0`
- `WinEventEvent` dataclass 신규 + `WinEventType = Literal["foreground"]` + `WinEventCallback = Callable[[WinEventEvent], None]` (반환값 없음 — WinEvent 는 OS 알림 전용, 차단 불가)
- `InputHookManager` 확장:
  - `_winevent_callbacks: dict[int, WinEventCallback]`, `_winevent_hook`, `_winevent_proc_ref`
  - `install_winevent_callback(cb) -> int` / `uninstall_winevent_callback(cb_id)` / `is_winevent_hook_installed` / `winevent_callback_count`
  - `_install_winevent_hook_locked` → `SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, proc, 0, 0, OUTOFCONTEXT | SKIPOWNPROCESS)` — SKIPOWNPROCESS 로 ohdo 자체 창 전환 (showMinimized / overlay 등) 자동 제외
  - `_uninstall_winevent_hook_locked` → `UnhookWinEvent` (NOT `UnhookWindowsHookEx` — 다른 API)
  - `_winevent_dispatch` → `OBJID_WINDOW (0)` 만 처리 (컨트롤 레벨 idObject 무시) + `GetWindowTextW(256)` 로 window_title 채움 + callback 예외 격리
- `uninstall_all` 도 winevent 정리

**`core/recorder.py` 변경**:
- `VK_F8 = 0x77` 상수 모듈 레벨 노출
- `Recorder.__init__` 에 `_winevent_cb_id: Optional[int]` 추가
- `start()` 가 mouse/keyboard 외에 winevent callback 추가 등록, `stop()` 이 해제
- `_on_winevent_event(WinEventEvent)` → `_append_winevent_event` → `RawEvent(kind="window_focus", hwnd=..., window_title=...)` 추가
- `_append_keyboard_event` 분기 추가: `opts.enable_f8_marker and vk_code == VK_F8` 이면 `RawEvent(kind="marker")` (vk_code 미채움 — clean marker), 그 외엔 기존 key event 유지. enable_f8_marker=False 시 F8 도 일반 key event (디버그/사용자 선호용)

**OUTOFCONTEXT dispatch 의존**: WinEvent OUTOFCONTEXT 콜백은 SetWinEventHook 을 호출한 스레드에 SendMessage 로 dispatch — Qt 메인 이벤트 루프가 메시지 펌프 역할. recorder 사용은 main_window_v2 에서 시작되므로 자동 작동. 테스트는 `_on_winevent_event` 를 직접 invoke 하여 OS 의존성 우회.

**recorder_transform 무변경**: `_split_into_batches` 의 `window_focus` / `marker` 처리는 PR-13 에서 이미 구현됨. PR-16w 는 capture path 만 활성화 — 변환 로직은 그대로.

### 회귀 가드 (test_170~173, PR-16w 4 신규)

- **test_170**: `input_hooks` WinEvent 모듈 contract — Win32 상수 값 / WinEventEvent 필드 / InputHookManager API (install/uninstall_winevent_callback/properties) / SKIPOWNPROCESS 플래그 sentinel / UnhookWinEvent (NOT UnhookWindowsHookEx) sentinel / get_hook_manager 싱글톤 동일 property 노출
- **test_171**: Recorder window_focus 캡처 — start 시 winevent_callback_count==1 / `_on_winevent_event(WinEventEvent("foreground", hwnd=42, title="Notepad"))` → 첫 RawEvent kind="window_focus" + hwnd/window_title 보존 / 'foreground' 외 type 무시 / stop 시 callback 해제 / 재진입 재등록
- **test_172**: F8 marker 매핑 — `VK_F8=0x77` 상수 + enable_f8_marker=True default 시 F8 keydown → marker RawEvent (vk_code=None, clean) + 다른 키 (0x41 'A') 는 key event 유지 + enable_f8_marker=False 시 F8 도 일반 key event
- **test_173**: end-to-end transform — window_focus event 가 PR-13 의 `_split_into_batches` 의 `auto_window_focus_boundary` 분기에서 step 경계 신호로 작동 + 옵션 OFF 시 1 step 으로 합침 + window_focus 자체는 generated_code 에 안 박힘

### PR-17 핵심 구현 노트 (5/19 — R2 두번째 PR — 마이그레이션 모드)

**배경**: PR-12~16w 까지 LL hook callback 안에서 element_capture_fn (EFP — UIA, 평균 50~200ms) 을 동기 호출했음. 한 가지 입력만 캡처할 땐 안전하지만, 빠른 자동화 스크립트 (Power Automate Desktop, AutoHotkey, pywinauto 등) 가 ~10ms 간격으로 SendInput 을 쏘면 hook callback 처리 시간이 누적되어 Windows ~300ms 임계치를 넘기고, OS 가 자동으로 hook 을 skip / disable 시킬 위험이 있었음. 마이그레이션 모드 (기존 자동화 → ohdo 녹화) 의 핵심 시나리오라 우선 처리.

**해결**: producer-consumer 분리. LL hook thread 는 **enqueue 만**, drain thread 는 **무거운 호출 + 적재**.

**`core/recorder.py` 변경**:
- `import queue`, `import time` + `from threading import Event, Thread` 추가
- 상수: `DEFAULT_QUEUE_MAXSIZE = 10000` (≈30+분 정상 입력), `_DRAIN_JOIN_TIMEOUT_SEC = 5.0`, `_DRAIN_POLL_TIMEOUT_SEC = 0.1`
- `Recorder.__init__` 인자에 `queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE` 추가
- 인스턴스 변수: `_raw_queue: Optional[queue.Queue]`, `_drain_thread: Optional[Thread]`, `_drain_stop_event: Event`, `_dropped_event_count: int`
- 신규 property: `dropped_event_count` (backpressure drop 누적), `queue_size` (현재 대기 수)
- 신규 메서드: `wait_for_event_count(expected, timeout=1.0)` — 테스트·모니터링용 동기 barrier (5ms polling)
- `start()`: 매번 새 `queue.Queue(maxsize=queue_maxsize)` 생성 + daemon thread `ohdo-recorder-drain` 시작 (재진입 안전)
- `stop()`: (1) hook 해제 → 새 enqueue 차단, (2) sentinel `None` put, (3) drain thread join (5s timeout) → 정상 시 큐 자연 드레인 + event loss 0, (4) lock 안에서 thread/queue cleanup + stopped_at 기록. join 실패 시 `_drain_stop_event.set()` 로 강제 종료 (안전망)
- hook callback 3종 (`_on_mouse_event` / `_on_keyboard_event` / `_on_winevent_event`) 재구조:
  - `_build_*_raw(event)` helper 가 RawEvent 생성 (sub-ms, element_meta=None 으로 click 도 만들어 둠)
  - `_enqueue_raw_event(raw)` 가 큐에 put_nowait. `queue.Full` 시 `get_nowait()` 로 oldest drop + counter 증가 + 첫·100번째마다 logger.warning. 재시도 후 또 full 이면 그냥 drop
  - keyboard 의 F8 marker 분기는 hook 스레드에서 즉시 결정 (외부 호출 없으므로 빠름)
- `_drain_loop()`: while `_drain_stop_event` not set, `q.get(timeout=_DRAIN_POLL_TIMEOUT_SEC)` — 큐 비어있으면 polling. sentinel `None` 받으면 종료. click + `element_capture_fn` 있으면 EFP 호출 + `raw.element_meta` 채움. lock 안에서 `self._session.events.append(raw)`

**`core/input_hooks.py` 변경**:
- `InputHookManager` docstring 에 "콜백 처리 시간 원칙 (R2 PR-17 마이그레이션 모드 전제)" 섹션 추가 — Windows LL hook ~300ms 임계치 + 무거운 호출 비동기 분리 권장 명시. recorder 가 이 원칙의 구현체임을 명시
- API 자체 무변경 (호환성 유지)

**기존 테스트 async 계약 갱신** (PR-12 부터 동기 가정으로 작성됨):
- test_151 (PR-12 buffer capture): 각 `_on_mouse_event` 후 `wait_for_event_count(N)` + 무시 케이스 (lbutton_up, move) 는 `time.sleep(0.05)` 후 count 불변 확인
- test_152 (PR-12 element capture): drain 대기 후 `capture_calls` + `element_meta` 검증. wheel/key 미호출 확인은 4 events 도달 후 추가 50ms 대기로 capture 호출 가능성 제거
- test_159 (PR-14 lifecycle): mouse hook 후 `recorder.wait_for_event_count(1)` 추가
- test_171 (PR-16w window_focus): drain 대기 + foreground 외 type 무시는 50ms sleep + count 불변 확인
- test_172 (PR-16w F8 marker): 모든 keydown 후 wait_for_event_count

**Pydantic RawEvent 가변성**: `RawEvent.model_config = {"extra": "allow"}` 가 이미 있어서 `element_meta` 후속 mutation (drain 안에서) 가능. 모델 자체 immutability 부여하지 않은 결정 유지.

### 회귀 가드 (test_174~177, PR-17 4 신규)

- **test_174**: queue/drain pipeline contract — `DEFAULT_QUEUE_MAXSIZE` 상수 + start 전 `queue_size==0`/`dropped_event_count==0` 안전성 + start 후 drain thread alive + `_raw_queue` 생성 + hook → drain → session 적재 + stop 후 cleanup
- **test_175**: hook callback fast return — slow `element_capture_fn` (200ms sleep) 주입해도 `_on_mouse_event` 호출 시간 <50ms (실측 ~0.1ms) + drain 가 slow capture 후 element_meta 채움 검증
- **test_176**: backpressure overflow — `queue_maxsize=3` + blocking capture 로 큐 차단 + 8 events 주입 → `dropped_event_count >= 1` + `queue_size <= 3` + 차단 해제 후 event_count < 8 (일부 drop 확정)
- **test_177**: graceful drain on stop — slow capture (50ms × 5 events) + stop 호출 → 모든 5 event 처리 + capture 5 호출 + dropped=0 (event loss 0)

### PR-18 핵심 구현 노트 (5/19 — R2 마지막 PR — DPI/멀티모니터 안정화)

**배경**: Windows 의 per-monitor DPI 환경 (100/125/150/175/200%) 에서 process awareness 가 미설정이면 LL hook 좌표가 virtualized (DPI-scaled) 로 들어옴 → 실제 픽셀과 불일치 → pywinauto/pyautogui 클릭 위치 오차. 또한 멀티모니터에서 모니터마다 DPI 가 다르면 같은 가상 좌표가 모니터 별로 다른 물리 픽셀에 매핑됨. 녹화·재생 환경 DPI 가 다를 때도 좌표 fallback 의 정확도 저하 → 사용자 진단 가능하게 메타 기록.

**`core/input_hooks.py` 변경**:
- Win32 상수 추가: `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4` (Win10 1703+), `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3`, `PROCESS_PER_MONITOR_DPI_AWARE = 2`, `MDT_EFFECTIVE_DPI = 0`, `DEFAULT_DPI = 96`. `DpiAwarenessMode = Literal["per_monitor_v2", "per_monitor_v1", "system", "unaware", "unsupported", "error"]`.
- `ensure_dpi_awareness() -> DpiAwarenessMode`: idempotent — `_dpi_awareness_mode` 모듈 캐시. Win10 1703+ 의 `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` 우선, 실패 시 Win8.1+ 의 `shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)` fallback. 이미 다른 모드면 GetProcessDpiAwareness 로 현재 모드 라벨 반환 (Qt 가 먼저 설정한 system aware 등). 예외 격리.
- `get_dpi_for_point(x, y) -> int`: `MonitorFromPoint(POINT(x, y), MONITOR_DEFAULTTONEAREST)` → `GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI)`. 호출 실패 / non-Windows 시 `DEFAULT_DPI` (96) 반환.
- `reset_dpi_awareness_cache()`: 테스트용 cache 초기화. 프로덕션 호출 X.
- `get_hook_manager()`: 매 호출 시 `ensure_dpi_awareness()` 트리거 (idempotent cache hit sub-µs). singleton 분기 안에 두면 cache reset 후 재호출 시 작동 X — 분기 밖으로 이동.

**`core/recorder_models.py` 변경**:
- `RawEvent.monitor_dpi: Optional[int] = None` 필드 신규. drain thread 가 click event 처리 시 채움. 기본 None (backwards compat — 이전 녹화 세션 JSON 로드 안전).

**`core/recorder.py` 변경**:
- `from core.input_hooks import ... get_dpi_for_point` 추가
- `_drain_loop` 의 click event enrichment 블록 확장: `element_capture_fn` 호출 후 `raw.monitor_dpi = get_dpi_for_point(cx, cy)` (try/except 격리). 키/스크롤 event 는 채우지 않음.
- docstring 에 "R2 PR-18 — DPI/멀티모니터 안정화" 섹션 추가.

**`core/recorder_transform.py` 변경**:
- `_emit_click` 의 fallback path (`element_meta is None`, `pyautogui.click(x, y)`): `monitor_dpi != 96` 일 때 trailing 코멘트 `# captured at DPI=144 (150%)` 첨부. 표준 96 / None / pywinauto·Selenium path 는 변경 X.

**i18n 결정**: PR-18 은 background mechanics (DPI 처리는 사용자에게 코드 코멘트로만 노출) — 새 i18n catalog 키 미발생. PR-15 의 47 키가 R1+R2 사용자 노출 UI 를 모두 커버. 향후 "DPI mismatch 진단 banner" 같은 explicit UI 추가 시 그 PR 에서 새 키 추가.

### 회귀 가드 (test_178~181, PR-18 4 신규)

- **test_178**: `core.input_hooks` DPI 모듈 contract — Win32 상수 값 + `ensure_dpi_awareness` / `get_dpi_for_point` / `reset_dpi_awareness_cache` 노출 + ensure 가 정의된 mode 반환 + idempotent 캐시 + get_dpi_for_point 가 정수 (>=96) 반환
- **test_179**: `get_hook_manager` 가 ensure_dpi_awareness 자동 호출 — source sentinel + cache reset 후 재호출 시 `_dpi_awareness_mode` 재결정
- **test_180**: `RawEvent.monitor_dpi` 필드 — 기본 None / 명시값 보존 + drain 가 실 Recorder lifecycle 안에서 monitor_dpi 채움 (>=96 검증)
- **test_181**: transform DPI 코멘트 — monitor_dpi=144 (150%) → `# captured at DPI=144 (150%)` 첨부 + 96 (표준) / None / pywinauto path 는 코멘트 미부착

### 검증 결과 (PR-11 ~ PR-18 = R2 완료)

- **core: 181/181 그린** (144 + 4 PR-11 + 4 PR-12 + 6 PR-13 + 3 PR-14 + 6 PR-15 + 2 PR-16a + 4 PR-16w + 4 PR-17 + 4 PR-18)
- **scenarios: 73/73 그린** (회귀 0)
- **element_picker baseline (test_42~48): 그린 유지**
- ruff check + format All passed (84 files)
- **R2 완료 조건**: PR-16w + PR-17 + PR-18 모두 완료. R1+R2 묶음 (3주 일정) 종료.

### 다음 세션 출발점 (R2 종료 후 — 2026-05-19 사용자 확정 진행 순서)

**확정 순서** (사용자 결정, 2026-05-19):
1. **Now → 1~2주**: 사용자 GUI 실측 검증 (옵션 A) — recorder R1+R2 + 기존 워크플로우 PySide6 v2 직접 사용. notepad / 계산기 / 브라우저 / pywinauto 스크립트 시나리오 반복. 발견 fix 는 PR-19+ 분기.
2. **실측 중 ~ 후**: AppService API surface 보강 (실측에서 부족한 메서드 자연 노출 — 예: `pause_recording`, live event WebSocket subscription, `merge_steps`). API 안정화 후 TS 클라이언트 작성 시점.
3. **~2~3주 뒤**: TS UI 트랙 시작.
   - **PR-19** `core/api_server.py` 신규 — FastAPI 라우터 + AppService 위임 (REST + WebSocket for live events). 별도 Python process spawn 가능. 시작 시 브라우저 자동 오픈 (Electron/Tauri 묶음은 후순위).
   - **PR-20** `web_ui/` 신규 — Vite + React + TypeScript. 첫 화면: 채팅 + 코드 뷰 (가장 가치 큰 부분). PySide6 와 병행 운영.
   - **PR-21+**: 점진 기능 이식 (settings → 세션 목록 → 블럭 뷰 → ...). recorder overlay/review 는 Win32 의존도 높아 후순위.
   - **핵심 원칙**: recorder/element_picker/win_inspector 는 **Python 으로 유지** (ROADMAP Phase 2 SaaS 정합 + Win32 바인딩 성숙도). TS 는 UI 레이어만 — 풀 재작성 X.
   - **국제화 재사용**: PySide6 의 `core/locale/{en,ko}.json` 그대로 i18next/react-intl 로 재사용 (catalog 포맷 호환).

**R3 후순위 (TS UI 트랙 진행 중 병행 가능)**:
- **PR-16b** AI 후처리: 녹화 종료 시 raw events + element_meta + screenshot → AI 프롬프트 → step 별 generated_code 매핑 + review dialog "AI 재생성" 버튼. 비용 tradeoff (녹화 30초당 AI 호출 1번, 토큰 ~5K). PR-13 deterministic 과 공존
- 브라우저 CDP 후킹: Chrome 자동 attach (Selenium 코드 정확도 향상)
- screenshot OpenCV fallback: element 못 잡힌 케이스 재생 시 이미지 매칭
- Power Automate Desktop import (.pad → Step 리스트)
- DPI mismatch 진단 banner UI (PR-18 의 monitor_dpi 메타 활용)
- `test_scenarios.py` — pywinauto 마이그레이션 시나리오 (1초당 10 events, drop 율 ≤ 5%, PR-17 후속 미해소)

## 25. 2026-05-20~23 사용자 GUI 실측 1차 — 녹화 lifecycle 6 fix

**컨텍스트**: ADR 0004 R1+R2 (PR-11~18) 완료 후 사용자가 `.venv\Scripts\python.exe main.py --ui v2` 직접 띄워 녹화 시나리오 실측. notepad/계산기/Excel/브라우저/시작메뉴 등 다양한 시나리오로 녹화 + 실행 + UX 검증. Claude 가 결과 분석 + fix + 회귀 가드. 진행 흐름은 5/12 GUI 테스트 세션 (handoff §22) 과 동일 패턴.

### 발견 + Fix 6개

| # | 증상 | 원인 | Fix | 테스트 |
|---|---|---|---|---|
| F-1 | 녹화된 step 실행 시 `NameError: name 'pywinauto' is not defined` | recorder_transform 이 `pywinauto.Application(...)` (fully qualified) 형태로 생성하는데, `extract_library_block` 의 essential imports 는 `from pywinauto import Application` 만 prepend → namespace 미스매치 | `_pywinauto_click_code` 가 `Application(...)` 으로 생성 | test_182 |
| F-2 | overlay [중지] 버튼 영역에 마우스 진입 시 마우스 컨트롤 체감 지연 (모든 OS 영역으로 확산) | (a) LL hook `_mouse_hook_dispatch` 가 WM_MOUSEMOVE 마다 Python entry + GIL 획득 (200Hz × Python 진입) (b) Qt nested click-through (root WA_TransparentForMouseEvents=True + 자식 False) hit-test 부하 (c) Qt WA_ShowWithoutActivating 만으로 부족 — OS activate/deactivate 잡음 | (a) input_hooks 가 WM_MOUSEMOVE 즉시 CallNextHookEx fast-path (b) overlay root 도 mouse 받도록 변경 (nested 구조 제거) — 사용자가 Ctrl+Shift+R 핫키로 stop 가능하므로 [중지] hover 불필요 (c) Win32 `WS_EX_NOACTIVATE` 명시 적용 (SetWindowLongPtrW) | test_183, test_184, test_163 갱신 |
| F-3 | Ctrl+Shift+R 핫키로 녹화 stop 안 됨 (main window minimize 상태) | Qt QShortcut 이 focus 못 받음 | recorder LL keyboard hook 에서 직접 감지 (`_build_keyboard_raw` 가 `VK_R` + Ctrl + Shift 동시 눌림 시 `stop_hotkey_callback` 호출). LL hook thread → main Qt thread dispatch 는 `QTimer.singleShot(0, _do_stop_recording)` thread-safe wrapper. `AppService.start_recording` 가 callback 전달 | test_185 |
| F-4 | 사용자가 새 세션 만들고 녹화 commit 했는데 별도 "Recording YYYYMMDD-HHMMSS" 세션이 생성됨 (target 무시) | `_teardown_recording_ui` 가 `self._recording_target_session_id = None` reset 을 `_show_review_dialog` 호출 *전* 에 발화 → review dialog 의 `commit_recording(target_session_id=...)` 시점에 None → 새 세션 자동 생성 | `_do_stop_recording` 이 stop 시작 시 `target_id = self._recording_target_session_id` local 보존 + `_show_review_dialog(target_session_id=target_id)` 인자 전달 | test_186 |
| F-5 | commit 후 가운데 영역이 빈 상태 카드 유지 (좌측 세션 카운트는 갱신됐는데 step 카드 안 보임) | commit 후 `_open_session_tab(session.session_id)` 가 이미 활성 탭 → `setCurrentIndex` 동일 인덱스 → `currentChanged` 미발화 → `_switch_session` 안 불려 `self.current_session` stale (commit 이전 빈 세션 객체) | accept path 에 명시: `self.current_session = self.app_service.get_session(session.session_id)` + `self._refresh_step_cards()` | test_186 step (4) |
| F-6 (관찰) | 동일 element 두 번 클릭이 별개 batch 로 분리되어 동일 generated_code 인 step 2개 생성 → jupyter delta empty → step 2 실질 no-op | recorder_transform 의 `_split_into_batches` 가 idle_boundary_ms / window_focus 등 다른 신호로 batch 분리. 사용자 의도 (의도적 두 번 클릭) 손실 | **미해결** — 다음 세션에서 동일 코드 step dedup 또는 jupyter delta 의 동일코드 처리 정책 결정 필요 | — |

### 코드 변경 요약

- **`core/input_hooks.py`**: `_mouse_hook_dispatch` 가 `wParam == WM_MOUSEMOVE` 시 callback dispatch 전부 skip하고 CallNextHookEx 즉시 반환 (Python entry / MouseEvent 생성 / GIL 비용 제거 — 200Hz × Python entry × Qt main thread GIL 경쟁 해소)
- **`core/recorder.py`**: `VK_R` / `VK_CONTROL` / `VK_SHIFT` 상수 + `_is_modifier_pressed` (Win32 GetAsyncKeyState helper) + `Recorder.__init__(stop_hotkey_callback=...)` 인자 + `_build_keyboard_raw` 가 R + Ctrl + Shift 감지 시 callback 호출 (raw event 안 만듦)
- **`core/recorder_transform.py`**: `_pywinauto_click_code` 가 `Application(...)` (unqualified) 생성 (essential imports `from pywinauto import Application` 매치)
- **`core/app_service.py`**: `start_recording(stop_hotkey_callback=...)` 인자 + Recorder 에 전달
- **`ui_v2/recorder_overlay.py`**: root `WA_TransparentForMouseEvents=False` (nested 구조 제거) + setMouseTracking(False) 명시 + `_apply_no_activate()` Win32 SetWindowLongPtrW 로 `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` 비트 적용
- **`ui_v2/main_window_v2.py`**:
  - `_do_start_recording` 이 `stop_hotkey_callback=lambda: QTimer.singleShot(0, self._do_stop_recording)` 주입 (LL hook thread → Qt thread thread-safe dispatch)
  - `_do_stop_recording` 이 stop 시작 시 `target_id = self._recording_target_session_id` local 보존 + `_show_review_dialog(target_session_id=target_id)` 인자 전달
  - `_show_review_dialog(initial_steps, target_session_id=None)`: 시그니처 갱신 + 모든 commit_recording 호출이 local target 사용 + accept path 가 `self.current_session = self.app_service.get_session(session.session_id)` reload + `_refresh_step_cards()` 명시 호출

### 회귀 가드 (test_182~186, 5 신규 + test_163 갱신)

- **test_182**: recorder_transform 이 `Application(...)` (unqualified) 생성 + essential imports 매치 (fully qualified `pywinauto.Application` 금지)
- **test_183**: `_mouse_hook_dispatch` WM_MOUSEMOVE fast-path (MouseEvent 생성보다 먼저 분기)
- **test_184**: RecorderOverlay 의 `_WS_EX_NOACTIVATE`/`_GWL_EXSTYLE` 상수 + `_apply_no_activate` 메서드 (SetWindowLongPtrW + WS_EX_NOACTIVATE + non-Windows noop) + start() 가 호출 + setMouseTracking(False) 명시
- **test_185**: Ctrl+Shift+R 글로벌 stop hotkey — VK_R/VK_CONTROL/VK_SHIFT 상수 + `_is_modifier_pressed` (GetAsyncKeyState + 0x8000) + Recorder.__init__ stop_hotkey_callback 인자 + `_build_keyboard_raw` 가 modifier+R 감지 + AppService.start_recording 가 callback 전달 + main_window_v2 가 QTimer.singleShot thread-safe wrapper 주입
- **test_186**: target_session_id 보존 — `_do_stop_recording` 가 target_id local 보존 (teardown 호출 *전* 위치) + `_show_review_dialog` 시그니처에 target_session_id 인자 + commit_recording 호출이 인자 사용 + accept path 가 current_session reload + `_refresh_step_cards` 명시 호출
- **test_163 갱신**: 이전 `WA_TransparentForMouseEvents=True` (root) sentinel → `False` (root 가 mouse 받음 — 2026-05-20 fix). 잔재 금지 가드 추가

### 검증 결과

- **core 186/186** (181 + 5 GUI 실측 fix) + scenarios 73/73 그린
- ruff check + format All passed (84 files)
- element_picker baseline (test_42~48) 그린 유지

### 다음 세션 주제 (사용자 명시 2026-05-23)

**"녹화로 사용자의 패턴을 파이썬 코드로 만드는 과정 개선"** — recorder_transform 의 deterministic 코드 생성 품질 향상.

가능한 작업 영역 (실측 + 사용자 협의 후 우선순위 결정):

1. **F-6 동일 코드 step dedup** (1차 후속) — recorder_transform 의 `transform()` 마지막에 인접 동일 generated_code step 합치기. 또는 jupyter delta 가 empty 인 step 을 "이전 step 재실행" 으로 처리. 사용자 의도 (두 번 클릭) 보존 정책 결정 필요
2. **한글/CJK 입력** (handoff §22 기존 후보) — recorder 가 `pyautogui.write('dkssudgktpdy')` 처럼 영문 layout 키 그대로 캡처. 사용자 의도 "안녕하세요" 보존을 위해 IME 인지 + clipboard paste (pyperclip) fallback
3. **win_inspector helper 통합** (architecture 25 §"PR-13" 노트) — 현재 recorder_transform 이 자체 코드 생성. win_inspector 의 element → code 로직 재사용으로 정교화 (예: control_type 별 specialized 코드, owner-drawn 좌표 fallback 개선)
4. **브라우저 element 코드 정교화** — 현재 `find_element(By.CSS_SELECTOR, ...).click()` 단순. wait/explicit timeout/CDP attach 검토 (R3 일부 당김)
5. **동적 selector 정교화** — `auto_id` 가 동적/숫자/uuid 인 경우 안정적 fallback (handoff §3 win_inspector 의 동적 auto_id 경고 패턴 재사용)
6. **클릭 후 wait 자동 삽입** — 사용자가 "Step 클릭 후 다음 step 까지의 텀" 을 보존하도록 step.wait_after_ms 자동 채움 (현재 ms 단위 정보는 있는데 wait 으로 변환 안 됨)
7. **review dialog 의 코드 편집 보강** — 사용자가 review 단계에서 직접 코드 수정/구조 변경하기 쉽게 UX 개선

권장 시작 영역: **F-6 동일 코드 step dedup** + **3 win_inspector 통합** — 가장 작은 변경으로 가장 큰 효과 (확실한 회귀 가드 작성 가능). 그 다음 정성적 개선들.

→ **2026-05-23 진행 결정 (사용자 align)**: 위 7개 영역을 PR 단위로 끊어 진행 — PR-19a (win_inspector 통합) → PR-19b (F-6 dedup) → PR-19c (idle gap → wait_after_ms). 각 PR 마다 사용자 GUI 실측 검증 후 다음으로. PR-19a 완료 — 자세한 §26.

## 26. 2026-05-23 PR-19a — recorder_transform 코드 품질 1차 (pywinauto_codegen 추출)

**컨텍스트**: §25 의 다음 세션 주제 "녹화 → Python 코드 생성 과정 개선" 1차 진입. 7개 후보 중 사용자 align (2026-05-23) 으로 **win_inspector 통합 → F-6 dedup → idle wait** 순서, 각 PR 마다 GUI 실측 검증. PR-19a 는 가장 큰 회귀 차단 효과 + 후속 PR 의 베이스 (`pywinauto_codegen.py` helper 모듈) 갖춤.

### 문제 — recorder_transform 의 6줄 minimal 코드 회귀

- 이전 `core/recorder_transform.py::_pywinauto_click_code` 가 단 3줄 emit:
  ```python
  app = Application(backend="uia").connect(title_re='.*<full_window_title>.*')
  win = app.top_window()
  win.child_window(...).click_input()
  ```
- **문제 1 (메모장 등 동적 title)**: `window_title` 전체를 `title_re=".*{title}.*"` 에 hardcode → "*hello world - 메모장" 같은 title 이면 재실행 시 "*다른 메모 - 메모장" 매칭 실패.
- **문제 2 (DPI 미설정)**: pywinauto ↔ pyautogui 좌표 불일치. picker (uia) 로 잡은 좌표 = logical, pyautogui = physical (DPI 인식 안 되어 있으면).
- **문제 3 (selector 단일 시도)**: control_type 잘못 분류된 경우 (Text 라벨 vs Button) 전체 fail.
- **문제 4 (창 활성화 누락)**: minimized 창에 직접 click_input 시 hit-test 실패.
- **문제 5 (leaf 캡처)**: picker 가 Text/Image 같은 leaf 잡은 경우 click 무반응 (UWP/XAML 메뉴 등 사용자 보고 5/5).
- **win_inspector 에는 이미 다 해결되어 있음** — `_get_desktop_element_info_text` 가 program_name `.*메모장` 매칭 + DPI Awareness + selector fallback chain + 창 활성화 + walk_up to clickable parent + pyautogui PRIMARY click 까지 robust 코드 emit. 하지만 markdown (AI 프롬프트 컨텍스트) 안에 갇혀 있어 recorder 가 재사용 못 함.

### 해결 — pure helper 추출 + 단일 source of truth

**신규 모듈 `core/pywinauto_codegen.py`** (336줄, pure helper). 단일 entry point:

```python
def build_pywinauto_click_code(meta: dict, button: str = "left") -> str:
    """element 메타 → 실행 가능한 pywinauto + pyautogui click 코드 (str)."""
```

emit 되는 코드 구조 (~70줄/click):

1. **DPI Awareness** — `SetProcessDpiAwarenessContext` PER_MONITOR_AWARE_V2 우선, shcore.SetProcessDpiAwareness fallback. `pyautogui.FAILSAFE = False`.
2. **Application.connect** — 비브라우저는 `window_title.split(" - ")[-1]` (program_name) 만 `re.escape` → `title_re=".*<프로그램명>"` (메모장처럼 동적 title 안전). 브라우저 (`is_browser_process=True`) 는 full title hardcode + `found_index=0`.
3. **Element selector** — 우선순위: (1) name+auto_id(non-dynamic)+ctrl_type 결합, (2) name+ctrl_type, (3) auto_id+ctrl_type, (4) class_name+ctrl_type, ..., (8) ctrl_type only.
4. **Selector fallback chain** (`_resolve_element()`) — primary fail 시 (a) title only, (b) title_re 정규식, (c) ctrl_type only 순으로 시도.
5. **창 활성화** — `IsIconic` → SW_RESTORE (minimized 일 때만, maximized 보존) / SW_SHOW, `BringWindowToTop`, `SetForegroundWindow`, `time.sleep(0.5)`.
6. **walk_up to clickable parent** — `_clickable_types = {'Button', 'MenuItem', ...}` set, 6단계 limit, 부모가 win.handle 이면 stop.
7. **Dynamic rect → center 좌표** — 창 활성화 후 최신 좌표 사용.
8. **pyautogui PRIMARY + element fallback** — `pyautogui.click(center_x, center_y[, button='right'])` 우선 (UWP/XAML/Win32 좌표 hit-test 가 가장 안정), 실패 시 `click_target.click_input()` / `right_click_input()` 폴백.

### 코드 변경

- **`core/pywinauto_codegen.py`** (신규, 336줄) — helper + 내부 sub-builders (`_build_element_selector`, `_build_connect_lines`, `_build_fallback_lambdas`).
- **`core/recorder_transform.py::_pywinauto_click_code`** — 22줄 → 11줄. helper 호출 위임 + docstring 에 PR-19a 변경 설명.
- **`core/win_inspector.py`** — **변경 없음** (의도적 분리, PR-19a' 로). 단순 helper 호출로 교체 시 inline AI-targeted commentary (DPI 설명, ★ 강조, 사용자 보고 5/5 회고, WindowFromPoint 디버그 체크, print() 출력) 손실 → AI 코드 생성 품질 회귀 risk. sentinel test_189 로 일관성만 보장.

### 회귀 가드 (test_187/188/189, 3 신규)

- **test_187 `pywinauto_codegen_helper_core_patterns`** (11 step) — helper 자체 검증:
  1. 메모장 케이스 `title_re='.*메모장'` (full title hardcode X)
  2. 브라우저 케이스 full title + `found_index=0`
  3. DPI Awareness 코드 포함
  4. `Application(...)` unqualified (`pywinauto.Application` 금지, test_182 회귀 가드 통합)
  5. `_resolve_element` fallback chain
  6. 창 활성화 3 신호 (`BringWindowToTop`, `SetForegroundWindow`, `IsIconic`)
  7. walk_up (`_clickable_types`, `_cur.parent()`)
  8. pyautogui PRIMARY + click_input fallback (try/except 이중)
  9. right button → `right_click_input` + `button='right'` 인자
  10. name+auto_id(non-dynamic) 결합 selector (recorder baseline)
  11. 동적 (숫자만) auto_id 는 primary selector 에서 제외
- **test_188 `recorder_transform_delegates_to_pywinauto_codegen`** — recorder 가 helper 위임:
  1. `from core.pywinauto_codegen import build_pywinauto_click_code` import 명시
  2. `_pywinauto_click_code` source 가 `build_pywinauto_click_code(` 호출
  3. end-to-end `transform()` 결과에 helper 핵심 패턴 7개 (DPI / title_re / `_resolve_element` / BringWindowToTop / `_clickable_types` / pyautogui PRIMARY / click_input fallback) + "untitled" 같은 동적 부분 hardcode 회귀 가드
- **test_189 `win_inspector_pywinauto_codegen_sentinel_consistency`** — divergence 방지 sentinel:
  - `win_inspector._get_desktop_element_info_text` source + helper output 양쪽 모두에 7개 공통 패턴 (DPI 2개, `_resolve_element`, `_clickable_types`, `BringWindowToTop`, `SetForegroundWindow`, pyautogui PRIMARY) 존재 검증
  - 양쪽 모두 fully qualified `pywinauto.Application` emit 안 함 (anti-pattern)
  - win_inspector 가 PR-19a' 에서 helper 호출로 교체되면 이 sentinel 은 자동 만족

### 검증 결과

- **core 189/189** (186 + 3 PR-19a) + scenarios 73/73 그린
- ruff check + format All passed (56 files)
- 기존 test_153/158/182 (recorder_transform 기존 contract) + test_15 (win_inspector 데스크톱 코드 생성) 모두 그린 유지

### 사용자 GUI 실측 검증 가이드

`.venv\Scripts\python.exe main.py --ui v2` 띄워 다음 시나리오 녹화 + step 실행:

1. **메모장 동적 title 케이스** — 메모장에 "테스트 1" 입력 후 녹화 시작 → 메뉴 "파일" 클릭 → 녹화 stop → review 통해 commit → 같은 메모장 (또는 새 메모장 "다른 내용") 에서 step 실행 → "파일" 메뉴 열림 확인 (이전엔 full title hardcode 로 실패했어야 함).
2. **계산기 / 시작메뉴** — UWP 앱 단순 시나리오. walk_up + pyautogui PRIMARY 가 정상 동작 확인.
3. **권한 차이 앱 (관리자 권한 cmd)** — pyautogui PRIMARY 가 UIPI 우회. click_input fallback 도 동작 확인 (옵션).
4. **브라우저 (Chrome)** — `is_browser_process` 가 채워지지 않으므로 (element_inspect 가 캡처 안 함) 비브라우저 path 로 떨어짐. full Chrome title 이 program_name `Chrome` 으로 줄어들어 매칭됨. (R3 / 후속 PR 에서 element_inspect 보강 필요)

### 다음 세션 (사용자 검증 후)

**PR-19b — F-6 동일 element 두 번 클릭 dedup**: `_split_into_batches` 가 이미 동일 element 인접 click 을 같은 batch 로 유지. `_emit_click` 이 batch 안 n번 동일 element click 감지 시 `click_input(double=True)` 또는 `pyautogui.doubleClick` 생성. RawEvent 의 `click_count` 필드 활용 (이미 정의됨, LL hook 캡처 검증 필요).

**PR-19c — idle gap → step.wait_after_ms 충전** (옵션): `_split_into_batches` 가 `idle_boundary_ms` 로 batch 분리 시, previous step 의 `wait_after_ms` 에 gap 충전 → 사용자 의도 (step 간 호흡) 보존.

## 27. 2026-05-23~24 PR-19d → PR-19g — 사용자 GUI 실측 반복으로 녹화 코드 품질 종합 fix (test_190~194)

**컨텍스트**: §26 PR-19a 완료 후 사용자가 실측 (메모장 등에서 click/key 녹화 + 실행) 반복하며 발견한 5 가지 별개 문제 + 1 quality 기능. 매 fix 마다 사용자가 GUI 에서 재현 → 다음 PR. 최종적으로 v2-새세션-005917 의 다음 녹화에서 **"텍스트 입력 + 단축키 + 마우스 클릭 모두 정상 동작"** 사용자 확인.

### PR-19d (option 3 옵션) — Step.element_meta 보존 + AI 재생성 path adapter

**컨텍스트**: PR-19a 완료 후 사용자가 "녹화로 deterministic 코드 생성 vs AI 통해 step 별 코드 생성, 어느 게 더 robust 한가" 가설 제기. 옵션 3 (하이브리드) 실증 위해 녹화 step 의 element 정보를 AI 재생성 path 에 전달할 수 있어야 함.

**문제**: 녹화 step 의 element 정보는 generated_code 안에 hardcode 만 됨 — 구조화된 형태로 Step 객체에 안 남음. ohdo 기존 step regenerate path (`_on_regenerate` → `_send_request(..., elements=None)`) 는 `self._pending_elements` (F3 picker 결과) 만 사용. 녹화 step 에서는 비어 있음 → AI 는 `user_request` 텍스트만 받음 → selector / window 정보 0.

**Fix**:
- `Step.element_meta: Optional[dict] = None` 필드 추가 (`core/session_manager.py`). 백워드 호환 — 녹화 안 거친 step 은 None.
- `recorder_transform._batch_to_step` 가 batch 의 첫 click element_meta 를 Step.element_meta 에 보존.
- ui_v2 module helper 2개 추가 (`main_window_v2.py` 모듈 상단):
  - `_lookup_step_element_meta(session, step_id) -> Optional[dict]` — dict / dataclass Step 양쪽 처리.
  - `_recorder_meta_to_picker_dict(meta) -> dict` — recorder element_inspect 필드 (`window_title`, rect list, exe_name) → win_inspector picker 형식 (`parent_window_title`, rect dict, `is_browser` exe 추론, default backend) 변환.
- `_on_regenerate` 가 pending elements 비었을 때 step.element_meta lookup → adapter 통과 → `_send_request(elements=[picker_dict])` 전달. AI 가 element_context 받음.

**검증**: 코드 path + adapter end-to-end 동작 확인 (recorder dict → picker → win_inspector markdown 에 selector 정보 포함). **단, 실제 AI 호출 통한 옵션 3 비교 실증은 사용자 미테스트 — 후속 (B 단계)**.

### PR-19e — `_safe_str_literal` escape + process_id 우선 connect chain (test_192)

**컨텍스트**: 사용자 실측 v2-새세션-000727 → 6/6 모두 fail. 두 가지 별개 버그.

**문제 1 — SyntaxError**: Win11 메모장 Document 본문이 element name 으로 잡힘 (`"1111\r2222\r3333\r"`). `_build_element_selector` 가 raw f-string interpolation 으로 박음 → `compile()` 단계에서 `SyntaxError: unterminated string literal`.

**문제 2 — ElementNotFoundError**: `Application.connect(title_re='.*데스크톱 1', ...)` 가 매칭 실패. "데스크톱 1" 은 Win11 메모장의 **탭 이름** (XAML 중간 노드) 이지 진짜 top-level window title 이 아님. element_inspect 의 `_resolve_top_window_title` 이 탭 노드에서 멈춤.

**Fix**:
- `_safe_str_literal(s)` helper (`json.dumps(s, ensure_ascii=False)`) — double quote 형식 + 모든 control char (CR/LF/tab/backslash/quote) 안전 escape + unicode literal 유지. 기존 test sentinel `title="검색"` 호환.
- `_build_element_selector` / `_build_fallback_lambdas` / `_build_title_connect_pair` 의 모든 user-data string 이 이 helper 통과.
- `_build_connect_block(process_id=...)` 새 함수 (이전 `_build_connect_lines` tuple 반환을 `list[str]` 반환으로 교체). process_id 있으면 `_connect_app()` 함수 emit — process 우선 (timeout=2s, 짧게 시도 → fail fast) + title fallback (timeout=10s) chain. process_id 없으면 기존 단일 connect line 유지 (회귀 안 함).

### PR-19f — modifier 키 인식 (Ctrl+A 등 hotkey) + Session.recording_meta (test_193)

**컨텍스트**: 사용자 실측 v2-새세션-003052 — "메모장에 단축키 (Ctrl+A) 도 입력하고 일반 텍스트도 입력하고 마우스도 클릭했는데 단축키와 마우스 클릭은 실행되지 않고 문자 입력만 실행". 또한 사용자 요청 — 녹화 metadata 를 세션에 보존해 사후 분석 가능하게.

**문제 — Critical**: `_build_keyboard_raw` 가 keydown 마다 `RawEvent(vk_code=...)` 만 생성. modifier 자체 키 (Ctrl, vk=0x11) 는 `_VK_CHAR_MAP` 에 없어 silent skip + 후속 A 키 (vk=0x41) 가 char 'a' 로 변환 → `pyautogui.write('a')` emit (Ctrl 정보 손실). 결과: Ctrl+A 가 글자 'a' 입력으로 변질.

**Fix — Critical**:
- `core/recorder.py` 에 `VK_MENU`/`VK_LWIN`/`VK_RWIN` 상수 + `_MODIFIER_CHECKS` 리스트 + `_capture_modifier_state()` helper (`GetAsyncKeyState` 로 Ctrl/Shift/Alt/Win 현재 상태 list 반환).
- `_build_keyboard_raw` 가 매 keydown 시 호출해 `RawEvent.modifiers` 채움.
- `core/recorder_transform.py` 에 `_MODIFIER_VK_CODES` frozenset (11 vk, L/R variants 포함) + `_VK_SPECIAL_KEYS` 확장 (방향키 / del / home / end / pgup / pgdn).
- `_emit_key_group` 가 (a) modifier 자체 키 skip, (b) modifier 있는 char/special → `pyautogui.hotkey('ctrl', 'a')` / `hotkey('ctrl', 'shift', 'tab')` 변환, (c) modifier 없는 키는 기존 text/special 로직 보존.

**Fix — Quality (recording_meta)**:
- `Session.recording_meta: list = field(default_factory=list)` 필드 추가.
- `app_service.commit_recording` 이 commit 시점 (Recorder cleanup 전) 에 metadata entry 만들어 append:
  - `recording_session_id`, `started_at`, `stopped_at`, `duration_sec`, `raw_event_count`, `transformed_step_count`, `dropped_event_count`, `committed_at`, `committed_step_ids`
- 같은 세션에 여러 번 commit 시 list 에 append (각 commit 별 entry).

### PR-19g — UWP `Light Dismiss` / `PopupRoot` noise filter (test_194)

**컨텍스트**: 사용자 실측 v2-새세션-005917 — "단축키와 텍스트는 잘 되었는데 마우스 컨트롤 단계에서 메모장이 닫혔다". Step 2 실행 후 메모장 종료 → Step 3~7 모두 `Application.connect` 실패 (process 없음).

**문제**: Step 2 element_meta = `{name="닫기", automation_id="Light Dismiss", class_name="PopupRoot"}` — UWP/WinUI 의 **invisible popup overlay click-receptor**. Win11 메모장 등 UWP 앱은 popup (메뉴/dialog/toast) 떠 있을 때 popup 영역 밖에 전체화면 invisible click receptor 를 깔아둠 — 사용자가 popup 외부 클릭 시 popup 닫기 ("light dismiss") 용도. EFP (element_inspect.capture_element_at) 가 이 invisible element 를 잡으면 `name="닫기"` 라벨이 부여됨. 재실행 시 selector fallback chain 의 `title="닫기"` 매칭이 메모장의 진짜 X 닫기 버튼 / 메뉴를 찾아 클릭 → 메모장 종료 → 후속 step connect 실패.

**Fix**:
- `core/recorder_transform.py` 에 `_is_uwp_popup_dismiss_overlay(meta)` helper — `automation_id == "light dismiss"` 또는 `class_name == "popuproot"` (case insensitive) 감지.
- `_filter_noise` 가 click event 의 element_meta 가 이 시그니처면 silent drop + info log (몇 개 drop 됐는지).
- **안전**: 시그니처 정확 매칭만 — 일반 "닫기" Button (다른 class_name) 은 그대로 통과. 회귀 안전망 test_194 (4) 가 보장.

### 검증 결과

- **core 194/194** (189 + PR-19d~g +5: test_190 input_hooks argtypes / test_191 element_meta regenerate / test_192 escape+process / test_193 modifier+recording_meta / test_194 popup filter) + scenarios 73/73 그린
- ruff check + format All passed (43 files)
- 사용자 GUI 실측 통과 (다음 녹화 후 텍스트/단축키/클릭 모두 정상 동작)

### 추가 발견 — input_hooks ctypes argtypes 버그 (test_190, PR-19a 진단 중 발견)

PR-19a~g 의 modifier/popup fix 진행 중 사용자가 보고: "녹화 중 click/key 가 씹힘". 진단 과정에 옵션 A (WinEvent disable) + 옵션 B (drain EFP disable) 모두 무효 → stderr 에서 발견:

```
ctypes.ArgumentError: argument 4: OverflowError: int too long to convert
File "input_hooks.py", line 381, in _mouse_hook_dispatch
    return self._user32.CallNextHookEx(None, nCode, wParam, lParam)
```

**원인**: `CallNextHookEx` 의 `argtypes` 미설정 → ctypes 가 default `c_int` (32-bit) 로 lParam 마샬링 시도. x64 LL hook 의 lParam = MSLLHOOKSTRUCT 포인터 = 64-bit 주소 (예: `0x0000024BB9D1D300`) → 32-bit 초과 OverflowError → 매 mouse/keyboard event 마다 예외 + stderr write 비용 누적 → 사용자 체감 input 씹힘 + 더블 클릭 필요.

**Fix** (PR-19f 이전 별도 commit):
- `InputHookManager._configure_user32_signatures()` 새 메서드 — __init__ 에서 호출.
- `CallNextHookEx` / `SetWindowsHookExW` / `UnhookWindowsHookEx` / `SetWinEventHook` / `UnhookWinEvent` / `GetWindowTextW` 의 argtypes/restype 명시 (Windows 타입: WPARAM=size_t, LPARAM=ssize_t, LRESULT=ssize_t, HHOOK=void_p).
- test_190 sentinel 가드.

### 다음 세션 출발점 (2026-05-24 작업 종료 시점 정리)

**완료 상태**:
- PR-19a~g 모두 commit `d94a04c`. core 194/194 + scenarios 73/73 그린.
- 사용자 GUI 실측 통과: 텍스트 + 단축키 + 마우스 클릭 모두 정상 동작 (v2-새세션-005917 다음 녹화에서 확인).
- 옵션 3 실증 진행 중 (PR-19d AI 재생성 path) — 사용자가 "재생성 잘 되고 있다" 보고만 받음, **결과 비교 미완료**.

**미해결 / 진행 중**:

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 결과 분석** | 사용자가 GUI 에서 AI 재생성 (deterministic step → 새 AI step) 실행 결과 확보. session.json 의 두 step 의 generated_code 비교. 평가 포인트: AI 가 element_meta 활용했나, semantic 추가 가치 있나, 코드 품질 더 좋은가, 한글 IME 같은 deterministic 한계 해결하나. 결과로 옵션 3 영구 채택 / 거부 / prompt 보강 결정 |
| **P2** | **PR-19h** — destructive action 의심 step UX | review dialog 의 step 카드에 ⚠️ badge — "닫기"/"종료"/"X" 라벨 + window 닫기 가능성 있는 element 에 사용자 confirm. PR-19g 의 Light Dismiss filter 외 다른 의도 안 한 element 잡힐 케이스 대비 |
| **P3** | **PR-19b** — F-6 동일 element 두 번 클릭 dedup | handoff §25 F-6 미해결. `_split_into_batches` 가 이미 동일 element 인접 click 같은 batch 로 유지. `_emit_click` 이 batch 안 n번 동일 element click 감지 시 `click_input(double=True)` 또는 `pyautogui.doubleClick` 생성. RawEvent.`click_count` 필드 활용 (이미 정의됨, LL hook 캡처 검증 필요) |
| **P4** | **PR-19c** — idle gap → step.wait_after_ms 충전 | `_split_into_batches` 가 `idle_boundary_ms` 로 batch 분리 시, previous step 의 `wait_after_ms` 에 gap 충전 → 사용자 의도 (step 간 호흡) 보존 |
| **P5** | **PR-19i** — raw events JSONL 저장 | PR-19f Quality 에서 분리. `data/sessions/<id>/raw_events.jsonl` 에 raw events 보존 → 사후 재변환 / 디버깅 가능. 사이즈/IO 신중 디자인 필요 |
| **P6** | **CJK / 한글 IME 입력** | handoff §25 다음 세션 후보 #2. recorder 가 `pyautogui.write('dkssudgktpdy')` 처럼 영문 layout 키 그대로 캡처. 사용자 의도 "안녕하세요" 보존 위해 IME 인지 + clipboard paste (pyperclip) fallback. P1 결과로 AI 가 이걸 자동 해결한다면 우선순위 낮아짐 |

**새 세션 진입 시 첫 단계**:
1. 이 §27 + §25 + §26 읽기 (녹화 코드 품질 작업 history)
2. **사용자에게 P1 결과 보여달라고 요청** — `data/sessions/v2-새세션-XXXX/session.json` 안 AI 재생성 step (commit 후 옆에 추가됨) + 원본 deterministic step 비교
3. P1 결과 분석 → 옵션 3 채택 여부 결정 → 그에 따라 P2~P6 우선순위 재조정

**진행 중인 hybrid mode 확인용**:
- 녹화 step 의 `Step.element_meta` 가 채워져 있어야 PR-19d adapter 가 picker 형식으로 변환해서 AI 에게 selector / window 정보 전달. element_meta 비어 있는 step 은 AI 가 user_request 텍스트만 받음 — 그 경우 결과 약함은 prompt 부족이 원인.
- 옵션 3 평가 시 위 차이 (element_meta 있음/없음) 고려 필요.

## 28. 2026-05-24 PR-19j + PR-19b — P1 분석 부산물 (regenerate in-place fix) + 빠른 double-click 감지

**컨텍스트**: §27 의 다음 세션 출발점 P1 (옵션 3 실증 결과 분석) 진행 중 발견 + P3 (PR-19b F-6 dedup 본문) 처리.

### P1 분석 결과 — 사용자 실측 보류

`data/sessions/111e5306-77ff-45fa-8f9f-ac476047870b/session.json` (2026-05-24 01:58, 7 step) 분석:

- Step 1: Document 클릭 (녹화)
- Step 2: keyboard (Ctrl+A → backspace → "111\n222\n333\n")
- **Step 3 & 4**: MenuItem '보기' — 천천히 두 번 click (별개 batch — F-6 사례)
- **Step 5 & 6**: Button '시작' — 천천히 두 번 click (별개 batch — F-6 사례)
- **Step 7**: "MenuItem '보기' left 클릭" — AI 가 새 step 으로 추가 (`element_meta=None`, `replaces_step_id=None`, code_len=6756 vs step 3 의 2662)

**Step 3 (deterministic) vs Step 7 (AI) 핵심 비교**:
- AI 가 win_inspector markdown 의 helper 템플릿을 본질적으로 그대로 emit (DPI/connect/resolve chain/walk_up/pyautogui PRIMARY 모두 동일 구조)
- AI 의 손실: `process=12676` 우선 connect chain (element_meta 없으니까)
- AI 의 추가가치: `print()` 디버그, `WindowFromPoint` 좌표 검증, namespace `_resolve_element_7`, 한글 주석

**결정적 — 옵션 3 path 가 트리거 안 됐을 가능성**:
- Step 7 의 `replaces_step_id=None` → 사용자가 (a) send-message 로 같은 텍스트 재전송 했거나 (b) 재생성 버튼 눌렀지만 버그로 새 step 으로 떨어짐
- → 옵션 3 의 진짜 실증 데이터 아님 → 사용자 GUI 재실측 필요 — 단 시간 비용 큼 → 일단 보류

### PR-19j — `_on_regenerate` 의 `replaces_step_id` 누락 fix (test_195)

**문제**: [ui_v2/main_window_v2.py:3290](../ui_v2/main_window_v2.py#L3290) 의 `_on_regenerate` (D17 일반 재생성) 가 `_send_request` 호출 시 `replaces_step_id` 전달 안 함. `_on_regenerate_with_warnings` (G7-D path, test #113) 는 정상 전달. **handoff §22 #4 "재생성 = in-place 대체" 정책 위반** — 사용자가 재생성 누르면 새 step 으로 추가됨 (5/12 메모장 테스트의 회귀 패턴 재발).

**Fix**: `replaces_step_id=step_id` 인자 추가 (5줄). 양쪽 path 일관성 회복.

**가드**: test_195 `regenerate_inplace_replaces_step_id` — `_on_regenerate` source sentinel + `_on_regenerate_with_warnings` 일관성.

### PR-19b — 빠른 double-click 감지 + `pyautogui.doubleClick` emit (test_196)

**컨텍스트**: handoff §27 P3. RawEvent.`click_count` 필드는 정의만 있고 (`recorder_models.py:45`) recorder.py / recorder_transform.py 어디서도 미사용 (dead field). LL hook 캡처 대신 **transform layer 에서 ts delta 기반 감지** 로 단순화.

**시나리오 범위**:
- **빠른 double-click** (예: 파일/폴더 더블 클릭, 시간 차 < 500ms) — PR-19b 가 처리: `pyautogui.doubleClick` emit
- **천천히 두 번 별개 click** (handoff §25 F-6, 시간 차 > 500ms) — PR-19b 가 처리 X. 별개 batch + 별개 step 유지. jupyter delta empty no-op 회귀는 §25 F-6 그대로 **미해결** (사용자의 "의도적 두 번 click" 의미 손실 risk 때문에 단순 dedup 못 함 — 후속 정책 결정 필요)

**핵심 변경** ([core/recorder_transform.py](../core/recorder_transform.py)):
- `_DOUBLE_CLICK_THRESHOLD_MS = 500` 상수 (Windows GetDoubleClickTime default)
- `_same_click_target(a, b)` helper — element_meta 있으면 `_same_element`, 둘 다 None 이면 좌표 ±5px 일치
- `_merge_consecutive_clicks(batch)` — 같은 batch 안 같은 button + 같은 target + < 500ms 인접 click → `click_count` 누적 단일 RawEvent (`model_copy`)
- `_batch_to_step` 시작 시 `batch = _merge_consecutive_clicks(batch)` 적용
- `_emit_click` 가 `ev.click_count >= 2` (left/middle 만 — right 는 제외) 면 doubleClick 변환 호출 + desc_parts 에 "더블 클릭" 표기
- `_split_into_batches` 의 click→click 경계 판단도 `_same_click_target` 활용 — 좌표 fallback 의 same-position 도 같은 batch (이전엔 None→None 이면 별개 batch 로 떨어짐)

**`_pywinauto_click_code` / `_browser_click_code` 시그니처 확장** — `double: bool = False` 인자 추가:
- pywinauto path: `pyautogui.doubleClick(center_x, center_y, button='left|middle')` + `click_target.click_input(double=True)` fallback
- browser path: `ActionChains(driver).double_click(_el).perform()` (browser path 는 element_inspect 미캡처로 dead path 에 가깝지만 syntactic 정합성 유지)
- right button + double=True → silent ignore (single right-click emit) — right double-click 은 일반적 사용 X

**[core/pywinauto_codegen.py](../core/pywinauto_codegen.py) 의 `build_pywinauto_click_code(meta, button, double=False)`**:
- `pyautogui_click_fn = "doubleClick" if is_double else "click"`
- `element_click_args = "double=True" if is_double else ""`
- 주석 라벨 "더블 클릭" / "클릭" 분기

### 검증 결과

- **core 196/196** (194 + PR-19j +1 + PR-19b +1) + scenarios 73/73 그린
- ruff check + format All passed (touched files)

### 다음 세션 출발점 (2026-05-24 두 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | PR-19j 후 재생성 path 가 in-place 동작. 사용자가 GUI 에서 step 카드 재생성 → 같은 step_id 의 generated_code 갱신 → element_meta 활용 (process_id 우선 connect 등) 확인. 한글 IME / unstable selector 같이 옵션 3 가치 명확한 시나리오로 비교 권장. **사용자 실측 보류 중** — 다음 세션에서 시간 확보 시 재시도 |
| **P2** | **PR-19h** — destructive action 의심 step UX | (미진행) review dialog 의 step 카드에 ⚠️ badge — "닫기"/"종료"/"X" 라벨 + window 닫기 가능성 있는 element 에 사용자 confirm. PR-19g 의 Light Dismiss filter 외 다른 의도 안 한 element 잡힐 케이스 대비 |
| ~~P3~~ | ~~PR-19b — F-6 빠른 double-click~~ | **완료 (PR-19b, test_196)**. **남은 부분**: 천천히 두 번 click → 별개 step → jupyter delta empty no-op 회귀 (handoff §25 F-6 본 문제). dedup vs 의도 보존 정책 결정 후속 |
| **P4** | **PR-19c** — idle gap → step.wait_after_ms 충전 | `_split_into_batches` 가 `idle_boundary_ms` 로 batch 분리 시, previous step 의 `wait_after_ms` 에 gap 충전 → 사용자 의도 (step 간 호흡) 보존 |
| **P5** | **PR-19i** — raw events JSONL 저장 | PR-19f Quality 에서 분리. `data/sessions/<id>/raw_events.jsonl` 에 raw events 보존 → 사후 재변환 / 디버깅 가능. 사이즈/IO 신중 디자인 필요 |
| **P6** | **CJK / 한글 IME 입력** | recorder 가 `pyautogui.write('dkssudgktpdy')` 처럼 영문 layout 키 그대로 캡처. 사용자 의도 "안녕하세요" 보존 위해 IME 인지 + clipboard paste (pyperclip) fallback. P1 결과로 AI 가 이걸 자동 해결한다면 우선순위 낮아짐 |
| **P7** | **F-6 잔여** — 별개 batch 동일 step | 천천히 두 번 click → 별개 batch + 별개 step → jupyter delta empty no-op. dedup (의도 손실 risk) vs jupyter "empty delta 면 prev step 재실행" 정책 결정 필요 |

**새 세션 진입 시**:
1. §28 + §27 + §25 읽기 (녹화 코드 품질 작업 history + 최신 결정)
2. P2 (PR-19h destructive UX) 또는 P4 (PR-19c idle wait) 또는 사용자 GUI 실측 시간 확보 시 P1 재시도
3. P4 와 P7 은 모두 `_split_into_batches` 영역 — 같이 진행 검토

## 29. 2026-05-24 PR-19c — idle gap → wait_after_ms 충전 (test_197)

**컨텍스트**: handoff §28 P4 — 사용자 실측 보류 중 P4 진행. `_split_into_batches` 가 `idle_boundary_ms` (기본 3000ms) 초과 휴지로 batch 분리할 때 gap 값을 직전 step 의 `wait_after_ms` 로 충전 → 재생 시 사용자가 의도한 step 간 호흡 보존.

### 핵심 구현

**[core/recorder_transform.py](../core/recorder_transform.py)**:
- `_split_into_batches` signature 변경: `list[list[RawEvent]]` → `tuple[list[list[RawEvent]], list[int]]`. 두번째 element `idle_gaps_ms` 는 각 batch 진입 직전의 idle gap (ms). 첫 batch + non-idle 분리 사유 (marker/window_focus/key→click/click→다른 element) 는 0.
- 내부 helper `_close_current(idle_gap_for_next)` — 현재 batch 를 닫으면서 다음 batch 의 진입 gap 을 pending 으로 저장. pydantic immutable RawEvent 영향 X.
- `transform()` 가 idle_gaps_ms[i] > 0 이면 step_per_batch[i-1].wait_after_ms = gap 으로 충전. 직전 batch 가 step 생성 안 한 경우 (modifier-only batch) gap 손실 — 코너 케이스 무시.
- gap 값은 전체 gap (idle_boundary_ms 차감 X) — `Step.wait_after_ms` 가 양수면 `step_delay_ms` 를 override 하는 정책이므로 이중 카운트 없음.

### 회귀 가드 (test_197, 1 신규)

- `_split_into_batches` signature: `(batches, idle_gaps_ms)` tuple 반환 + 동일 길이 list + `idle_gaps_ms[0] == 0`
- idle split (5300ms gap) → 직전 step.wait_after_ms ≈ 5300, 마지막 step.wait_after_ms = None
- non-idle 분리 4 시나리오 모두 wait_after_ms = None 충전 X:
  - key→click 분리
  - click→다른 element 분리
  - F8 marker 분리
  - 단일 batch (분리 자체 없음)

### 검증 결과

- **core 197/197** (196 + PR-19c +1 = test_197) + scenarios 73/73 그린
- ruff check + format All passed (touched files)

### 다음 세션 출발점 (2026-05-24 세 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | 사용자 GUI 실측 시간 확보 후 진행 |
| **P2** | **PR-19h** — destructive action 의심 step UX | review dialog 의 step 카드에 ⚠️ badge ("닫기"/"종료"/"X" 라벨 + window 닫기 가능 element confirm). PR-19g 의 Light Dismiss filter 외 다른 의도 안 한 element 잡힐 케이스 대비 |
| ~~P4~~ | ~~PR-19c — idle gap → wait_after_ms 충전~~ | **완료 (PR-19c, test_197)** |
| **P5** | **PR-19i** — raw events JSONL 저장 | `data/sessions/<id>/raw_events.jsonl` 에 raw events 보존 → 사후 재변환 / 디버깅. 사이즈/IO 신중 디자인 필요 |
| **P6** | **CJK / 한글 IME 입력** | recorder 가 `pyautogui.write('dkssudgktpdy')` 처럼 영문 layout 키 그대로 캡처. IME 인지 + clipboard paste (pyperclip) fallback. P1 결과로 AI 가 자동 해결한다면 우선순위 낮아짐 |
| **P7** | **F-6 잔여** — 별개 batch 동일 step | 천천히 두 번 click → 별개 batch + 별개 step → jupyter delta empty no-op. dedup (의도 손실 risk) vs jupyter "empty delta 면 prev step 재실행" 정책 결정 필요 (사용자 결정 대기) |

**새 세션 진입 시**:
1. §29 + §28 + §27 + §25 읽기 (녹화 코드 품질 작업 history + 최신 결정)
2. P2 (PR-19h destructive UX) 또는 P5 (PR-19i raw events JSONL) 진행 추천 — P1/P7 은 사용자 결정/시간 필요
3. PR-19c 의 wait_after_ms 충전 동작은 사용자 실측 시 step 간 호흡이 자연스러워졌는지 확인 가치

## 30. 2026-05-24 PR-19h — destructive action ⚠️ badge + commit confirm (test_198)

**컨텍스트**: handoff §28 P2 — PR-19g 의 Light Dismiss / PopupRoot filter 외 다른 의도 안 한 close/cancel/delete click 잡힐 케이스 대비. review dialog 의 step 카드에 ⚠️ badge 표시 + commit 전 사용자 confirm.

### 핵심 구현

**[core/recorder_transform.py](../core/recorder_transform.py) — 새 pure helper**:
- `_DESTRUCTIVE_NAME_SUBSTRINGS` — 한/영 키워드 (닫기/종료/취소/삭제/지우기/제거/끝내기/나가기 + close/exit/quit/cancel/delete/remove). 부분 일치 (case-insensitive).
- `_DESTRUCTIVE_NAME_EXACT` — `("x", "×", "✕")`. 정확 일치 (case-insensitive) — "Xerox" 같은 X-시작 name false-positive 차단.
- `_DESTRUCTIVE_CONTROL_TYPES` — `{button, menuitem, hyperlink}`. Edit/TextBox 같은 데이터 입력 element 의 같은 라벨 false-positive 차단.
- `is_destructive_step(step) -> Optional[str]` — 사유 문자열 반환 또는 None. 차단 X — UI 권고만.

**[ui_v2/recording_review_dialog.py](../ui_v2/recording_review_dialog.py)**:
- `_StepCardItemWidget.__init__` — title 옆 ⚠️ badge label 추가 (sentinel `is_destructive_step` 반환값 기반). tooltip 에 사유 표시.
- `_on_accept` — destructive step 목록 모아 `QMessageBox.warning` Yes/No confirm. default `No`. Yes 시만 `accept()` — 사용자 의도면 진행.
- import line 갱신: `from core.recorder_transform import is_destructive_step, transform` (PR-15 sentinel 가드는 `"from core.recorder_transform import"` 분리 검증으로 갱신 — `transform(` 호출 sentinel 별도 유지).

**[core/locale/ko.json](../core/locale/ko.json) + [core/locale/en.json](../core/locale/en.json)** — 3 신규 키:
- `destructive_badge_tooltip` — `"⚠️ {reason}"` (사유 표시)
- `destructive_confirm_title` — `"주의 — 창 닫기/삭제 가능 동작 포함"`
- `destructive_confirm_body` — `"다음 단계가 창을 닫거나 데이터를 삭제할 수 있습니다:\n\n{details}\n\n그대로 세션에 추가하시겠습니까?"`

### 회귀 가드 (test_198, 1 신규 + PR-15 sentinel 갱신)

13 단계:
1. `_DESTRUCTIVE_NAME_SUBSTRINGS` 핵심 한/영 키워드 8개 포함
2. `_DESTRUCTIVE_CONTROL_TYPES` = button/menuitem/hyperlink
3. Button "닫기" → 사유 반환
4. Button "Cancel"/"CANCEL" (case 무관) → 사유 반환
5. Button "확인" → None (false-positive 차단)
6. MenuItem "파일 종료" → 사유 반환
7. Edit "Close" → None (control_type 화이트리스트)
8. Button "X" 정확 일치 + "×" → 사유 반환
9. Button "Xerox" → None (정확 일치만 — 부분 매칭 false-positive 차단)
10. element_meta=None / 빈 name → None
11. `_StepCardItemWidget.__init__` source 가 `is_destructive_step` + `destructive_badge_tooltip` 사용
12. `_on_accept` source 가 confirm 흐름 (`is_destructive_step` + `destructive_confirm_title/body` + `StandardButton.Yes`) 포함
13. i18n ko/en 양쪽 모두 3 신규 키 존재

PR-15 sentinel 갱신: `"from core.recorder_transform import transform"` (정확) → `"from core.recorder_transform import"` (느슨) — 멀티 심볼 import 대응.

### 검증 결과

- **core 198/198** (197 + PR-19h +1 = test_198) + scenarios 73/73 그린
- ruff check + format All passed

### 다음 세션 출발점 (2026-05-24 네 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | 사용자 GUI 실측 시간 확보 후 진행 |
| ~~P2~~ | ~~PR-19h destructive UX badge + confirm~~ | **완료 (PR-19h, test_198)** |
| ~~P4~~ | ~~PR-19c idle gap → wait_after_ms~~ | **완료 (PR-19c, test_197)** |
| **P5** | **PR-19i** — raw events JSONL 저장 | `data/sessions/<id>/raw_events.jsonl` 에 raw events 보존 → 사후 재변환 / 디버깅. 사이즈/IO 신중 디자인 필요 |
| **P6** | **CJK / 한글 IME 입력** | recorder 가 `pyautogui.write('dkssudgktpdy')` 처럼 영문 layout 키 그대로 캡처. IME 인지 + clipboard paste (pyperclip) fallback. P1 결과로 AI 가 자동 해결한다면 우선순위 낮아짐 |
| **P7** | **F-6 잔여** — 별개 batch 동일 step | 천천히 두 번 click → 별개 batch + 별개 step → jupyter delta empty no-op. dedup vs 의도 보존 정책 결정 필요 (사용자 결정 대기) |
| **P8** | **PR-19h follow-up** — generated_code 패턴 매칭 | 현재 PR-19h 는 element_meta 의 name 만 검사. `os.remove` / `shutil.rmtree` / `subprocess.run(['rm', ...])` / `os.system('rd /s')` 등 generated_code 분석은 후속. 사용자 의도 안 한 destructive 코드가 element 없이 직접 들어간 케이스 (수동 편집 / AI hallucination) 대응 |

**새 세션 진입 시**:
1. §30 + §29 + §28 + §27 + §25 읽기
2. P5 (PR-19i raw events JSONL) 진행 추천 — 디자인 작업 (저장 형식, 로테이션, 사이즈 캡, opt-in/out)
3. P6 (CJK IME) 는 recorder.py 의 hook callback 수정 필요 — pyperclip 의존성 추가 검토
4. PR-19h 사용자 실측 시 destructive false-positive / false-negative 케이스 수집 가치 (badge 사유 메시지 개선 + 키워드 추가/제거 근거)

## 31. 2026-05-24 PR-19i — raw events JSONL 저장 (test_199)

**컨텍스트**: handoff §30 P5 — 작업 녹화 raw events 를 commit 시점에 세션 부속 artifact 로 영속화. 사후 재변환 (옵션 토글 비교) / 디버깅 / 사용자 의도 안 한 click 분석에 활용. PR-19f 의 `recording_meta` 와 짝.

### 핵심 구현

**[core/storage/base.py](../core/storage/base.py) — SessionRepository ABC 새 abstract 메서드**:
- `save_recording_raw_events(session_id, recording_session_id, events: list[dict]) -> Optional[str]` — 백엔드 추상화 유지 (filesystem leak X). None 반환은 미지원, caller graceful skip.
- 데스크톱: relative filename 반환. 미래 backend (Postgres/S3) 는 URL 또는 storage key 반환 가능.

**[core/storage/local_json.py](../core/storage/local_json.py)**:
- `data/sessions/<id>/raw_events_<rec_id>.jsonl` 에 UTF-8 한 줄당 한 RawEvent JSON (`json.dumps(ensure_ascii=False)` — 한글 그대로 보존). 세션 dir 없으면 None graceful.
- filename 형식: `raw_events_<rec_id>.jsonl` (같은 ohdo session 에 여러 녹화 commit 가능 — rec_id 로 충돌 회피).

**[core/storage/in_memory.py](../core/storage/in_memory.py)**:
- None 반환 (no-op) — InMemoryRepository 는 file IO 가 본 의도 아님. 파일 저장 검증 필요 시 LocalJsonRepository + `tempfile.TemporaryDirectory()` 사용 (test_199 패턴).

**[core/app_service.py](../core/app_service.py) `commit_recording`**:
- PR-19f 의 `rec_meta` 빌드 직후, save_session 직전에 `self._repo.save_recording_raw_events(...)` 호출.
- 성공 시 `rec_meta["raw_events_path"] = filename`. 실패해도 commit 자체는 성공 (try-except + logging).
- 직렬화: `[ev.model_dump(mode="json", exclude_none=True) for ev in rs.events]` — datetime ISO 8601 자동 변환 + None 필드 생략.

### 회귀 가드 (test_199, 1 신규)

4 단계:
1. SessionRepository abstract 메서드 존재 (`__isabstractmethod__` 확인)
2. LocalJsonRepository + tempdir end-to-end: commit 후 JSONL 파일 존재 + 2 RawEvent → 2 줄 + 한글 (`"확인"`) + raw fields (vk_code 등) 보존 + recording_meta[-1]["raw_events_path"] 정확
3. InMemoryRepository: 직접 호출 → None + commit end-to-end → recording_meta 에 raw_events_path 키 없음
4. LocalJsonRepository graceful: 세션 dir 없을 때 None 반환

### 검증 결과

- **core 199/199** (198 + PR-19i +1 = test_199) + scenarios 73/73 그린
- ruff check + format All passed

### 다음 세션 출발점 (2026-05-24 다섯 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | 사용자 GUI 실측 시간 확보 후 진행. 이제 raw_events JSONL 보존됨 → 사후 분석 / 옵션 비교 / element_meta 영향 평가에 활용 |
| ~~P5~~ | ~~PR-19i raw events JSONL 저장~~ | **완료 (PR-19i, test_199)** |
| **P6** | **CJK / 한글 IME 입력** | recorder 가 `pyautogui.write('dkssudgktpdy')` 처럼 영문 layout 키 그대로 캡처. IME 인지 + clipboard paste (pyperclip) fallback. P1 결과로 AI 가 자동 해결한다면 우선순위 낮아짐 |
| **P7** | **F-6 잔여** — 별개 batch 동일 step | 천천히 두 번 click → 별개 batch + 별개 step → jupyter delta empty no-op. dedup vs 의도 보존 정책 결정 필요 (사용자 결정 대기) |
| **P8** | **PR-19h follow-up** — generated_code 패턴 매칭 | os.remove / shutil.rmtree / subprocess(['rm']) / os.system('rd /s') 등 코드 분석으로 element_meta 없는 destructive 코드 (수동 편집 / AI hallucination) 대응 |
| **P9** | **PR-19i follow-up** — raw events 사후 재변환 UI | 보존된 JSONL → review dialog 재진입 (옵션 다르게 토글하며 비교). 또는 CLI helper `python -m ohdo.recording.replay <session_id>` |

**새 세션 진입 시**:
1. §31 + §30 + §29 + §28 읽기
2. P6 (CJK IME) 또는 P8 (PR-19h follow-up code 분석) 진행 추천
3. PR-19i 사용자 실측 시 `data/sessions/<id>/raw_events_*.jsonl` 파일 생성 확인 → P9 follow-up (replay UI/CLI) 디자인 근거
4. raw_events JSONL 파일 사이즈 모니터링 — 장시간 녹화 시 MB 단위 가능 → 향후 opt-out 토글 또는 gzip 검토

## 32. 2026-05-24 PR-19k — 한글/CJK IME 입력 감지 + pyperclip placeholder (test_200)

**컨텍스트**: handoff §31 P6 — recorder 의 LL keyboard hook 은 raw VK code 만 보므로 한글 IME mode 가 켜진 상태에서 사용자가 친 'dkssudgktpdy' (안녕하세요의 영문 layout) 가 OS IME 로 어떤 한글로 조합됐는지 모름. 캡처된 영문 키를 그대로 `pyautogui.write(...)` 로 재생하면 한글 입력이 영문으로 박힘. fix: per-key IME open 상태 캡처 + transform 에서 IME mode 면 pyperclip placeholder 로 변환.

### 핵심 구현

**[core/recorder_models.py](../core/recorder_models.py)**:
- `RawEvent.ime_open: bool = False` 새 필드. drain thread 가 채움. False 가 안전 default (현재 동작 유지).

**[core/recorder.py](../core/recorder.py) `_capture_ime_open()`**:
- Windows: `ImmGetContext(GetForegroundWindow()) → ImmGetOpenStatus`. 실패 / non-Windows / hwnd=0 / NULL IMC / 예외 시 False.
- `_build_keyboard_raw` 가 `_capture_modifier_state()` 옆에 `_capture_ime_open()` 호출 → `ime_open=` 전달.

**[core/recorder_transform.py](../core/recorder_transform.py)**:
- `_emit_key_group` 에 `text_any_ime: bool` accumulator 추가. char push 시 `ev.ime_open` 이면 set. flush 후 reset.
- `_emit_text(..., any_ime=False)` signature 확장. 우선순위:
  1. `is_password + integrate_secrets` → `get_secret(...)` (secret path — IME 보다 우선; password 필드는 보통 IME 비활성, 둘 다 마킹 시 secret 의도일 가능성 + 사용자가 review dialog 에서 secret 라벨로 확인 가능)
  2. `any_ime=True` → IME path:
     ```python
     # ⚠️ 한글/CJK IME 입력 감지 — 영문 layout 키: 'dkssud'. 실제 입력 텍스트로 교체 후 실행하세요.
     pyperclip.copy('<여기에 실제 텍스트 입력>')
     pyautogui.hotkey('ctrl', 'v')
     ```
  3. 기본 → `pyautogui.write({text!r})` (기존 동작)

**의존성**: `pyperclip` 은 이미 `_ESSENTIAL_LIBRARY_IMPORTS` (workflow_engine.py:887) 에 포함 → import 자동.

### 회귀 가드 (test_200, 1 신규)

7 단계:
1. `RawEvent.ime_open` default False
2. `_capture_ime_open()` 존재 — non-Windows False / Windows bool 반환 (분기)
3. `_build_keyboard_raw` source 가 `ime_open=_capture_ime_open()` 전달
4. 모든 text 키 ime_open=True → pyperclip + Ctrl+V + 영문 키 코멘트, `pyautogui.write` X
5. 모든 키 ime_open=False → 기존 `pyautogui.write('hi')` 유지 (회귀 가드)
6. 일부 키만 ime_open=True → any_ime=True (보수적 IME path)
7. password 필드 + ime_open=True → `get_secret(...)` secret path 우선

### 검증 결과

- **core 200/200** (199 + PR-19k +1 = test_200) + scenarios 73/73 그린
- ruff check + format All passed

### 다음 세션 출발점 (2026-05-24 여섯 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | 사용자 GUI 실측 시간 확보 후 진행. raw_events JSONL 보존됨 → 사후 분석에 활용. IME 입력은 PR-19k 의 placeholder + raw_events 의 ime_open 필드 활용 가능 |
| ~~P6~~ | ~~CJK / 한글 IME 입력~~ | **완료 (PR-19k, test_200)** — placeholder MVP. 실제 텍스트 자동 캡처는 P10 (후속) |
| **P7** | **F-6 잔여** — 별개 batch 동일 step | 천천히 두 번 click → 별개 batch + 별개 step → jupyter delta empty no-op. dedup vs 의도 보존 정책 결정 필요 (사용자 결정 대기) |
| **P8** | **PR-19h follow-up** — generated_code 패턴 매칭 | os.remove / shutil.rmtree / subprocess(['rm']) / os.system('rd /s') 등 코드 분석으로 element_meta 없는 destructive 코드 (수동 편집 / AI hallucination) 대응 |
| **P9** | **PR-19i follow-up** — raw events 사후 재변환 UI | 보존된 JSONL → review dialog 재진입 (옵션 다르게 토글하며 비교) 또는 CLI helper |
| **P10** | **PR-19k follow-up** — IME 실제 텍스트 자동 캡처 | placeholder 대신 UIA ValuePattern 으로 key group 끝난 후 element value read → clipboard 내용 자동 채움. 또는 WM_IME_COMPOSITION/UIA TextChangedEvent 활용. 사용자 실측으로 placeholder UX 충분한지 먼저 확인 |

**새 세션 진입 시**:
1. §32 + §31 + §30 + §29 + §28 읽기
2. P8 (PR-19h follow-up code 분석) 진행 추천 — 자체 완결 + 사용자 결정 X
3. PR-19k 사용자 실측 시: 한글 입력 step 이 pyperclip placeholder 로 떨어지는지, raw_events JSONL 의 ime_open 필드 채워지는지 확인 → P10 follow-up 결정 근거

## 33. 2026-05-24 PR-19l — generated_code destructive 패턴 매칭 (test_201)

**컨텍스트**: handoff §32 P8 — PR-19h 본문은 `element_meta` 의 control_type + name 만 검사. element_meta 없는 destructive 코드 (수동 편집 / AI hallucination / 좌표 fallback click) 는 검출 못 함. fix: `is_destructive_step` 가 element + code 둘 다 검사하고, 매칭 시 사유 결합 반환.

### 핵심 구현

**[core/recorder_transform.py](../core/recorder_transform.py)**:
- `_DESTRUCTIVE_CODE_PATTERNS` — `(re.Pattern, 사유)` 튜플 리스트 (모듈 레벨 compile, 한 번만). 13 패턴:
  - 파일/폴더 삭제: `os.remove`, `os.unlink`, `os.rmdir`, `shutil.rmtree`, `Path.unlink()`, `Path.rmdir()`
  - HTTP: `requests.delete(`
  - 프로세스: `.kill()`, `.terminate()`, `taskkill` (case 무관)
  - Shell: `'rm -rf'`, `'rd /s'`, `'del /switch'`
- `_check_destructive_element(meta)` — 기존 PR-19h 로직 그대로 helper 로 분리 (단일 책임).
- `_check_destructive_code(code)` — 줄 단위 순회, `#` 코멘트 줄 skip (false-positive 차단), 첫 매칭 사유 반환.
- `is_destructive_step(step)` — 둘 다 시도 + 매칭 시 `"{element}; {code}"` 결합 반환.

### 회귀 가드 (test_201, 1 신규)

12 단계:
1. `_DESTRUCTIVE_CODE_PATTERNS` 모음에 7 핵심 키워드 (os.remove, shutil.rmtree, requests.delete, .kill(), taskkill, rm -rf, rd /s) 포함
2. `os.remove('a.txt')` → 사유 반환
3. `shutil.rmtree(...)` → 사유 반환
4. `requests.delete(url)` → 사유 반환
5. `.kill()` / `.terminate()` → 사유 반환
6. `TaskKill` (mixed case) → 사유 반환
7. shell `'rm -rf '` / `'rd /s'` / `'del /q'` → 사유 반환
8. `Path('a.txt').unlink()` → 사유 반환
9. 안전 코드 4종 (pyautogui.click, pyperclip.copy, pyautogui.write 한글, plain expr) → None
10. `# os.remove(...)` 코멘트 → None (skip)
11. element=Cancel + code=os.remove → `"'Cancel' 에 'cancel' 포함 ...; os.remove() — 파일 삭제"` 결합
12. element 안전 + code 안전 → None (PR-19h 회귀 가드)

### 검증 결과

- **core 201/201** (200 + PR-19l +1 = test_201) + scenarios 73/73 그린
- ruff check + format All passed (E402 fix — `import re` 파일 상단으로 이동)

### 다음 세션 출발점 (2026-05-24 일곱 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | 사용자 GUI 실측 시간 확보 후 진행 |
| **P7** | **F-6 잔여** — 별개 batch 동일 step | dedup vs 의도 보존 정책 결정 필요 (사용자 결정 대기) |
| ~~P8~~ | ~~PR-19h follow-up generated_code 패턴~~ | **완료 (PR-19l, test_201)** |
| **P9** | **PR-19i follow-up** — raw events 사후 재변환 UI | 보존된 JSONL → review dialog 재진입 또는 CLI helper |
| **P10** | **PR-19k follow-up** — IME 실제 텍스트 자동 캡처 | UIA ValuePattern 으로 element value read → clipboard 자동 채움 |

**사용자 결정 / 실측 필요 항목만 남음** — 자체 완결 가능한 후속 작업은 P9 (UI/CLI replay) 정도. P10 은 사용자 실측으로 placeholder 충분한지 먼저 확인 후 우선순위 재평가 권장.

**새 세션 진입 시**:
1. §33 + §32 + §31 + §30 읽기
2. P1 (사용자 GUI 실측) 진행 가능한지 우선 확인 — 누적된 PR-19a~l (12 PR) + 5 신규 테스트 (test_197~201) 의 종합 효과를 사용자가 직접 검증할 시점
3. P9 (raw events replay UI/CLI) 디자인 작업 — JSONL 파일 → review dialog 재진입 path 또는 별도 CLI command. 후방 호환 신중

## 34. 2026-05-24 PR-19m — raw events JSONL 사후 재변환 helper + CLI (test_202)

**컨텍스트**: handoff §33 P9 — PR-19i 가 commit_recording 시점에 보존한 `data/sessions/<id>/raw_events_<rec_id>.jsonl` 파일을 다시 transform 으로 흘림. 옵션 비교 / 디버깅 / 잘못 commit 된 세션 복구 / 미래 UI replay 백엔드.

### 핵심 구현

**[core/recording_replay.py](../core/recording_replay.py) — 신규 모듈**:
- `load_raw_events_from_jsonl(jsonl_path) -> list[RawEvent]` — pydantic `model_validate_json` 으로 한 줄당 한 RawEvent 라운드트립. 빈 줄 skip. UI 재사용 가능 (review dialog 가 "Load from JSONL" 추가 시 이 helper 만 호출).
- `replay_jsonl(jsonl_path, opts=None, self_window_titles=None) -> list[Step]` — load + transform. `RecordingSession.id` 는 파일명 (`raw_events_<id>.jsonl`) 에서 추출, `started_at/stopped_at` 은 첫/마지막 event ts 추정 (transform 이 metadata 보지 않음 — 정확도 무관).
- `main(argv=None) -> int` — CLI entry. `argparse` 로 옵션 파싱:
  - `--idle-boundary-ms N` (default 3000)
  - `--no-group-keys` / `--drop-empty`
  - `--out path.json` — step list JSON 저장; 없으면 stdout 요약
- Exit code: 0 성공 / 1 파일 없음 / 2 파싱·변환 실패

**CLI 사용 예**:
```bash
python -m core.recording_replay data/sessions/abc/raw_events_xyz.jsonl
python -m core.recording_replay <path> --idle-boundary-ms 5000 --drop-empty --out steps.json
```

### 회귀 가드 (test_202, 1 신규)

7 단계:
1. `load_raw_events_from_jsonl` 라운드트립 — 한글 element_meta + ts + `ime_open` + `modifiers` 모두 보존
2. `replay_jsonl` end-to-end — JSONL → Step 리스트 (step 존재)
3. `opts` 토글로 결과 차이 — 같은 element 5300ms gap → default(3000ms)=2 steps vs idle=10000ms=1 step
4. `main()` CLI — 파일 없음 → exit 1 + stderr 에러 메시지
5. `main()` CLI — `--out` 지정 → JSON 파일 생성 + step count print
6. `main()` CLI — `--out` 미지정 → stdout 요약 (`[01] <user_request>` 형식)
7. 빈 JSONL → 빈 리스트 graceful

### 검증 결과

- **core 202/202** (201 + PR-19m +1 = test_202) + scenarios 73/73 그린
- ruff check + format All passed

### 다음 세션 출발점 (2026-05-24 여덟 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | 사용자 GUI 실측 필요 |
| **P7** | **F-6 잔여** — 별개 batch 동일 step | 사용자 정책 결정 필요 (dedup vs 의도 보존) |
| ~~P9~~ | ~~PR-19i follow-up replay helper + CLI~~ | **완료 (PR-19m, test_202)** |
| **P10** | **PR-19k follow-up** — IME 실제 텍스트 자동 캡처 | UIA ValuePattern + element value pre/post diff. 사용자 실측으로 placeholder UX 충분한지 우선 확인 권장 |
| **P11** | **PR-19m follow-up** — review dialog "Load from JSONL" UI | `RecordingReviewDialog` 에 "📂 JSONL 불러오기" 버튼 추가 — `load_raw_events_from_jsonl` 호출 → 새 RecordingSession 으로 dialog 재초기화. 사용자가 옵션 토글하며 비교 가능 |

**자체 완결 후속 작업은 거의 소진** — 남은 항목 모두 사용자 결정 / 실측 / 추가 디자인 필요.

**새 세션 진입 시**:
1. §34 + §33 + §32 + §31 + §30 읽기
2. **사용자 GUI 실측 진행 권장** — 누적된 PR-19a~m (13 PR) + 6 신규 테스트 (test_197~202) 효과를 사용자가 직접 검증해야 P10/P11 우선순위 평가 가능
3. P11 (UI "Load from JSONL") 는 디자인은 단순하지만 사용자 가치 검증이 필요 — 실측 보류 중에는 우선순위 낮음
4. P10 (IME 실제 텍스트 자동 캡처) 는 placeholder 한계 사용자 체감 후 디자인 결정 권장

## 36. 2026-05-29 CLI AI 일반화 — Gemini → Agy rename + 제네릭 CliAIAdapter + preset UI (test_204)

**컨텍스트**: 사용자 보고 — Google 이 `gemini` CLI 를 `agy` 로 rename. 동시에 사용자 요청으로 CLI AI 어댑터를 일반화 — Settings 에서 Agy / Claude Code / Codex 등 다양한 CLI AI 도구를 preset 으로 선택 가능하게.

### 핵심 변경

**[core/adapters/cli_ai_adapter.py](../core/adapters/cli_ai_adapter.py)** — 신규 generic 어댑터:
- `CLI_AI_PRESETS: dict[str, dict]` — 3 preset 등록:
  - `agy`: command=`agy`, model=`agy-3.1-pro`, model_arg=`-m`, prompt_arg=`-p`, supports_images=True
  - `claude_code`: command=`claude`, model=`claude-opus-4-7`, model_arg=`--model`
  - `codex`: command=`codex`, model=`gpt-5-codex`, model_arg=`--model`, prompt_arg=None
- `class CliAIAdapter(BaseAIAdapter)` — config-driven, preset 또는 custom command 지원.
- `migrate_ai_settings(ai_settings)` — 구 `gemini_cli` → `cli_ai` + command `gemini` → `agy` 자동 변환.
- **Back-compat 정책**: `preset` 키 명시 없으면 raw config 유지 (이전 `GeminiCLIAdapter({"command": "gemini"})` 호출 패턴 그대로 보존, model 없으면 `-m` 미추가).

**[core/adapters/gemini_cli_adapter.py](../core/adapters/gemini_cli_adapter.py)** — shim 으로 축소:
- `from .cli_ai_adapter import CliAIAdapter as GeminiCLIAdapter` — alias 만 re-export.
- 기존 `from core.adapters.gemini_cli_adapter import GeminiCLIAdapter` import 경로 그대로 동작.

**[core/ai_engine.py](../core/ai_engine.py)**:
- `ADAPTER_REGISTRY` 에 `"cli_ai": CliAIAdapter` 신규 + `"gemini_cli": GeminiCLIAdapter` (alias) 유지.
- 초기화 시 `migrate_ai_settings()` 자동 호출 — 구 settings.json 호환.
- default selected = `"cli_ai"` (이전 `"gemini_cli"`).

**[core/environment_scanner.py](../core/environment_scanner.py)**:
- `check_cli_ai(command="agy")` 신규 (default `"gemini"` → `"agy"`).
- `check_gemini_cli = check_cli_ai` back-compat alias.
- `full_scan()` 결과 dict 에 `"cli_ai"` 키 신규 + `"gemini_cli"` 키도 동일 값 alias.

**[ui/settings_dialog.py](../ui/settings_dialog.py) `_create_ai_tab`**:
- 진입 시점에 `migrate_ai_settings()` 호출 — legacy settings 자동 정규화.
- "CLI AI 도구" QGroupBox 신규 — preset dropdown (`agy` / `claude_code` / `codex` / `(custom)`) + editable command + editable model + timeout + max_retries + "Test connection" 버튼.
- `_on_cli_preset_changed` — preset 선택 시 command + model 자동 채움 (custom 은 제외).
- `_test_cli_command` — `<command> --version` 호출 (timeout 5s) 로 가용성 진단.
- `get_settings()` — `cli_ai` 섹션 저장 (구 `gemini_cli` 대신).
- 기존 OpenAI 호환 섹션 변경 없음.

**[ui_v2/onboarding.py](../ui_v2/onboarding.py)**:
- 엔진 선택 라디오에 `cli_ai` 신규 항목 + `gemini_cli` (legacy) 유지.

**[core/locale/{ko,en}.json](../core/locale/)**:
- `ui_v2.onboarding.engine_cli_ai` 신규 키 — "CLI AI 도구 (Agy / Claude Code / Codex 등)".
- `engine_gemini_cli` 라벨 갱신: "(legacy — agy 로 자동 마이그레이션됨)".

**[config/{default_,}settings.json](../config/)**:
- `ai.selected` = `"cli_ai"` (이전 `"gemini_cli"`).
- `ai.available_engines.cli_ai` 신규: `preset="agy"`, `command="agy"`, `model="agy-3.1-pro"`, `model_arg="-m"`, `prompt_arg="-p"`, timeout 180, max_retries 3.

### 회귀 가드 (test_204, 1 신규 + 기존 4 갱신)

**test_204 12 단계**:
1. CLI_AI_PRESETS 핵심 3 preset (agy / claude_code / codex) 존재
2. 각 preset 의 필수 필드 (command + display_name + model)
3. `CliAIAdapter(preset="agy")` → command="agy" + agy- model 자동
4. `CliAIAdapter(preset="claude_code")` → command="claude" + claude- model
5. `CliAIAdapter(preset="codex")` → command="codex"
6. preset 미명시 + model 미지정 → `-m` 미추가 (back-compat — 구 GeminiCLIAdapter 호환)
7. preset 미명시 + model 명시 → `-m <model>` 추가
8. `GeminiCLIAdapter is CliAIAdapter` (alias 확인)
9. `migrate_ai_settings` — legacy → 정규화 + 원본 비변형
10. `AIEngineManager.ADAPTER_REGISTRY` 에 `cli_ai` + `gemini_cli` + `openai_compat` 모두
11. `AIEngineManager(legacy settings)` → `selected="cli_ai"` 자동
12. SettingsDialog source 에 CLI AI preset dropdown 핵심 sentinel

**기존 테스트 갱신**:
- test_13: legacy `gemini_cli` settings → migration 후 `cli_ai`/`agy` 검증
- test_31: `check_gemini_cli()` default command 가 `agy` 로 변경
- test_71: source sentinel `gemini_exec` → `cli_exec`, settings.json key `gemini_cli` → `cli_ai`, model prefix `agy-` / `gemini-` 둘 다 허용
- scenarios test_20: AIEngineManager legacy settings → `cli_ai` 정규화 반영

### 검증 결과

- **core 204/204** (203 + test_204 +1) + scenarios 73/73 + recording_fixtures 2/2 모두 그린
- ruff check + format All passed (auto-fix 1건)
- 모든 기존 import 경로 (`from core.adapters.gemini_cli_adapter import GeminiCLIAdapter`) 동작
- 구 settings.json (`selected="gemini_cli"`, `command="gemini"`) 로드 시 자동 마이그레이션 — 사용자 작업 0

### 다음 세션 출발점 (2026-05-29 첫 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | 옵션 3 실증 재시도 | 사용자 GUI 실측 필요 |
| **P7** | F-6 잔여 | 사용자 정책 결정 필요 |
| **P10** | IME 실제 텍스트 자동 캡처 | placeholder UX 검증 후 |
| **P11** | review dialog "Load from JSONL" UI | 사용자 가치 검증 후 |
| **NEW P12** | **사용자가 새 preset (예: Aider, GitHub Copilot CLI) 요청 시** | `CLI_AI_PRESETS` 에 entry 추가 — 어댑터 코드 수정 불필요 |

**사용자 측 확인 권장**:
1. Settings → AI 엔진 탭 → "CLI AI 도구" 그룹 → preset 드롭다운에서 agy / claude_code / codex 전환 시 command + model 자동 채움 동작
2. "Test connection" 버튼으로 `agy --version` 호출 성공 확인
3. 기존 사용자: 첫 실행 시 settings.json 자동 마이그레이션됨 (별도 작업 X)

**새 세션 진입 시**:
1. §36 + §35 + §34 읽기
2. 사용자 실측 결과 따라 P1 / P10 / P11 우선순위 결정
3. 새 CLI AI preset 추가 요청 시 `CLI_AI_PRESETS` 에 entry 추가만 하면 됨

## 37. 2026-05-29 TS UI v3 트랙 전환 결정 — Electron + React + TS + Tailwind + Zustand (`desktop_v3/`)

**컨텍스트**: handoff §24 의 "TS UI 트랙 ~2~3주 뒤 시작" 계획을 사용자 결정으로 **즉시 시작**. 단기 GUI 실측 지연 누적 + Discord-like UX 요구 충족. 기존 PySide6 v1/v2 는 **불변** 유지 — 위험 완화 우선.

### 사용자 확정 (2026-05-29)

| 결정 항목 | 값 |
|---|---|
| 디렉터리 전략 | **Option 1: 같은 repo `desktop_v3/` 추가** (별도 repo X) |
| 데스크톱 셸 | **Electron 38+** (Discord 매칭) |
| 언어 | **TypeScript 5+** |
| UI 라이브러리 | **React 19+** |
| 스타일링 | **TailwindCSS + shadcn/ui** (Radix 기반) |
| 상태 관리 | **Zustand** (가벼움) + **TanStack Query** (API state) |
| 빌드 | **Vite 6+** + **electron-vite** |
| Python bridge | **FastAPI** (`api_server/server.py` 신규) + uvicorn |
| 통신 | REST (CRUD) + WebSocket (실시간 이벤트/스트리밍) |
| 참조 UX | **Discord 데스크톱 앱** — 다크 테마, 3-column 레이아웃, 컴팩트 밀도, 부드러운 애니메이션, 단축키 풍부 |

### 핵심 원칙 (불변)

1. **Python core 변경 없음** — `core/` (recorder / element_picker / win_inspector / CliAIAdapter) 그대로 유지. v3 는 FastAPI 로 호출만.
2. **PySide6 v1+v2 살아있음** — `main.py --ui v2` 항상 launchable. 회귀 비교 가능.
3. **공유 자산 재사용** — `data/sessions/`, `config/settings.json`, `core/locale/{en,ko}.json` 모두 그대로.
4. **i18n 카탈로그 재사용** — i18next 가 기존 `{en,ko}.json` 직접 로드 (포맷 호환).

### 구조 (계획)

```
ohdo/
├── core/                  # Python — 변경 없음
├── ui/                    # PySide6 v1 — 변경 없음
├── ui_v2/                 # PySide6 v2 — 변경 없음
├── main.py                # PySide6 launcher — 변경 없음
│
├── api_server/            # 신규 — FastAPI bridge to core/
│   ├── __init__.py
│   ├── server.py          # uvicorn entry
│   └── routes/            # sessions / steps / ai / recording / picker / execution / settings
│
└── desktop_v3/            # 신규 — Electron + React + TS
    ├── main/              # Electron main process (Node.js)
    │   ├── index.ts       # Python server spawn
    │   └── ipc.ts
    ├── preload/           # IPC bridge (security)
    │   └── index.ts
    ├── renderer/          # React UI (브라우저 process)
    │   ├── src/
    │   │   ├── App.tsx
    │   │   ├── components/  # shadcn/ui + Discord-like
    │   │   ├── store/       # Zustand
    │   │   ├── api/         # HTTP/WS clients (fetch + ws)
    │   │   └── i18n/        # i18next + core/locale 로딩
    │   └── index.html
    ├── package.json
    ├── tsconfig.json
    └── vite.config.ts
```

### 통신 디자인

```
Electron Renderer (React+TS)  ──HTTP/WS──>  Python FastAPI (localhost:8765)
                                                    │
                                                    └──> AppService (기존) ──> core/* (기존)

Electron Main (Node)  ──subprocess──>  python -m api_server  (자식 lifecycle 동기화)
```

- **REST**: sessions/steps CRUD, settings, environment check
- **WebSocket**: 실시간 이벤트 (recording events, execution logs, AI streaming)
- **보안**: localhost 만 listen, 앱 시작 시 토큰 생성 + Electron preload 에 주입

### 단계별 plan (5단계, 총 6~8주)

| Phase | 기간 | 내용 | 검증 포인트 |
|---|---|---|---|
| **A. 셋업** | 1-2일 | desktop_v3/ 보일러플레이트 + api_server/ 최소 (`GET /health`, `GET /sessions`) + Electron 이 Python spawn + Hello World UI | Python 응답이 React 화면에 표시 |
| **B. 핵심 화면 MVP** | 1-2주 | Discord-like 3-column 레이아웃 + 채팅 패널 (AI 스트리밍) + Monaco 코드 뷰어 + 다크 테마 | agy/openai_compat 로 코드 생성 → 화면 표시 |
| **C. 통합 기능** | 2-3주 | 녹화 lifecycle (recorder API + WS) + element picker (Python 트리거) + 세션/step CRUD + 실행 (live log WS) | v2 의 핵심 시나리오 v3 에서 재현 가능 |
| **D. Polish + Discord 감각** | 1-2주 | i18n + 단축키 + 애니메이션 + 상태바 + 토스트 + 테마 토글 | v2 보다 좋다는 사용자 체감 |
| **E. 배포 + v2 deprecate 검토** | 1주 | electron-builder + .exe/.dmg/AppImage + CI 빌드 + v2 deprecated 마킹 (코드는 보존) | 실측 안정 확인 |

### 위험 완화 장치

- Python core 직접 수정 금지 — api_server/ 에서만 호출. test_core 회귀 가드 유지.
- Electron 빌드 환경: electron-vite + electron-builder (성숙).
- node_modules: `.gitignore` + CI 캐시 + lockfile 만 커밋.
- Python API 와 PySide6 동시 띄움 방지: 단일 instance 락 (data dir 충돌 방지).
- 회귀 시 v2 로 복귀: `python main.py --ui v2` 한 줄.

### 다음 세션 출발점

**Phase A 셋업부터 시작**. 첫 작업:
1. `desktop_v3/` Electron + Vite + React + TS 보일러플레이트 생성
2. `api_server/server.py` 최소 FastAPI (`GET /health`, `GET /sessions`)
3. `pyproject.toml` 에 fastapi + uvicorn 추가
4. Electron main 이 Python subprocess spawn (생애주기 동기화)
5. React 가 `fetch('http://localhost:8765/sessions')` 호출 → 세션 목록 표시
6. **회귀 가드**: `main.py --ui v2` 여전히 동작 (test 추가)

**Open questions (Phase A 진입 시 결정)**:
- electron-vite 템플릿: `create-electron-vite` 사용? 아니면 직접 셋업?
- shadcn/ui 컴포넌트 우선 선정 — Button / Input / Dialog / Tabs / Toast / DropdownMenu / ScrollArea
- API 토큰 생성/저장 방식 — Electron app 시작 시 random + preload IPC 로 주입
- Python subprocess 종료: Electron `before-quit` 이벤트에서 SIGTERM, 5s 후 SIGKILL
- 포트 충돌 처리: 8765 점유 시 8766/8767 fallback

**미해결 — 사용자 실측 시 자연 발견 예정** (TS UI 트랙과 병행 진행 가능):
- agy CLI 한글 prose garbling (cosmetic — 코드는 정상)
- 누적된 PR-19a~m 의 종합 GUI 동작 검증
- recording_fixtures 사용자 시나리오 5개 수집

## 72. 2026-05-31 picker 요소 셀렉터 결정적 강제 (탭닫기 오클릭 진짜 해결, core 0줄)

**컨텍스트**: §71 후속. 사용자 정당한 반론 — "엔진 교체 필수 아닐 것, v2 에서 검증된 작업, step2(+)와
step4(x)는 같은 작업". 재조사로 **엔진 무능 아님** 확정 + 결정적 fix.

### 진짜 근본원인 = 프롬프트 신호-잡음 (엔진 아님)
- **동일 세션 대조**: STEP2("+"클릭, **성공**) 생성코드 = `child_window(auto_id="AddButton", control_type="Button")`
  — AI 가 픽 요소를 **정확히 사용**. STEP4("x"닫기, **실패**) = `control_type="Document"` — 텍스트영역 클릭.
  → 엔진은 픽 요소를 쓸 능력이 있음(step2 증명). 차이는 프롬프트.
- **신호-잡음 계측**: STEP4 프롬프트에 "Document" **31회** vs "CloseButton" **1회**. 직전 STEP3 이
  텍스트입력하려 Document 를 클릭했고, STEP1~3 이 모두 `manually_edited=True` 라 "반드시 유지" 강조 +
  누적코드에 Document 클릭이 도배 → AI 가 압도적 다수(Document)를 따라감. step2 는 직전이 "메모장 실행"
  뿐이라 노이즈 0 → 픽 요소 사용 성공. **클릭 step 쌓일수록 악화** = v3/v2 공통 prompt_builder 구조 문제.
- run-time 은 §71 처럼 마커추출로 valid 코드 실행하나, 그 코드가 Document 를 찍어 탭이 안 닫힘.

### fix = 결정적 셀렉터 강제 (사용자 선택, api_server only, core 0줄)
picker 는 정확한 요소(auto_id=CloseButton)를 이미 안다 → AI 가 재작성해 잡음에 휩쓸리게 두지 말고
**생성 후 그 step 의 element 셀렉터를 픽 요소로 교정**.
- **`api_server/selector_enforce.py`** (신규): `parse_picked_selector(element_context)` (auto_id 우선,
  숫자=동적ID는 title 폴백) + `enforce_picked_selector(generated_code, step_id, element_context)` —
  대상 step **마커 영역** 내 `element = win.child_window(...)` kwargs 를 픽 요소 auto_id/title+control_type
  으로 치환(마커/주석 보존, 이미 타겟/요소호출없음/식별자없음/치환후 compile 실패 시 무변경 = best-effort).
- **`routes/generate.py`**: WS 생성 성공 후 `_enforce_step_selector` 호출 → generated_code 교정 +
  step_code(델타) 마커 재추출 → update_step → 교정된 step 으로 done. (타 step 영역 불간섭 — 실측:
  step2 AddButton/step3 Document 그대로, step4 만 CloseButton.)

### 검증
- **test_232** +1 (core **227/227**): 파싱(auto_id/동적ID폴백/None) + 교정+compile + Document 제거 +
  idempotent + guard(이미타겟/_resolve_element/식별자없음 무변경). 실측: 세션 STEP4 generated_code 에
  적용→CloseButton 타겟+compile, step2/3 불변. scenarios 73/73 + recording_fixtures 2/2 + ruff 그린.
  core/PySide6/ui_v2 0줄, 프론트 무변경.
- **사용자: Python 브리지 재시작 후 STEP4 재생성**(또는 새 닫기 step). 그러면 picker 요소(CloseButton)를
  찍어 탭이 닫힘. (기존 저장된 step4 는 재생성해야 교정 적용 — enforcement 는 생성 시점 동작.) §71 delta
  fix 도 함께 적용됨.

## 71. 2026-05-31 step delta 추출 dangling-block 버그 fix (core) + 탭닫기 미동작 = AI 타겟팅

**컨텍스트**: 세션 ba7f4dc8(메모장 새탭→입력→탭닫기"x"). 전체 실행 시 마지막 탭닫기만 안 됨.
조사로 **두 개의 별개 사안** 확정. **사용자 승인 하에 core 수정**(첫 core 변경 — 불변원칙 예외 1회).

### (1) core 버그 fix — extract_code_delta dangling block (실제 수정함)
- **버그**: `core/import_manager.py` `extract_code_delta` 의 SequenceMatcher fallback 후처리가
  "prev 와 동일한 라인 제거" 시 **제어 헤더(if/for/else)는 남기고 그 본문 라인은 제거**.
  연속 클릭 step 의 walk-up promote / `pyautogui.click` 본문이 직전 step 과 줄 단위로 동일 →
  본문만 통째 제거되어 **헤더만 남은 dangling block → SyntaxError**. (STAGE 계측: SequenceMatcher
  diff 엔 본문 있음 → prev_set 제거 단계가 21줄 드롭 확정.) 저장된 step_code 가 깨짐.
- **fix**: 제거 로직을 **block-aware** 로 — 유지된 제어 헤더의 indent 스택을 추적해, 그 블록
  **본문**(더 깊은 indent)은 prev 중복이어도 보존. 블록 **밖**(module-level) 중복만 stale 단편 제거.
- **검증**: 이 세션 STEP4 델타 재추출 → 컴파일 OK. **test_231** +1(core **226/226**) + scenarios 73 +
  recording_fixtures 2 + ruff 그린. (v2 공유 — 전 스위트 무회귀 확인.)

### (2) "탭닫기 미동작"의 실제 run-time 원인 = AI 타겟팅 (core fix 와 별개, 미해결)
- **(1)은 run-time 원인이 아님**: run-time `execute_session_blocks` → `extract_step_delta_code` 는
  **마커 추출 우선 + `_is_compilable` 검증** 이라, 깨진 저장 step_code 를 우회해 generated_code(정상)
  에서 valid 델타를 뽑는다(실측 확인: 마커 후보 컴파일 OK). 그래서 STEP4 는 valid 코드로 **실행은 됨**.
- **그런데 그 valid 코드가 "x"(탭닫기)가 아니라 `control_type="Document"`(텍스트영역)을 클릭** →
  탭이 안 닫힘. 프롬프트 로그(20260531_144556_step4) 실측: AI 에 `## 선택된 UI 요소` (이름="탭 닫기",
  **auto_id="CloseButton"**) + §68 anti-pattern 지시까지 **완벽히 전달됐는데도** AI(agy/Gemini)가 전부
  무시하고 Document 클릭 코드를 생성. = **엔진 프롬프트 준수 한계**(§68 지시도 실패). 우리 쪽 데이터/
  코드 버그 아님. **해결 후보**: 엔진 교체(OpenAI-compat 등 지시 잘 따르는 모델) / 사용자 수동 셀렉터
  편집(auto_id="CloseButton") / 픽 요소를 AI 없이 결정적 코드 생성(설계 변경). **사용자 결정 필요.**

### 사용자 조치
- core 변경이므로 **Python 브리지 재시작** 필요(델타 fix 는 신규 생성/삭제·재정렬 chain 재구성/마커
  부재 fallback 에 적용 — 기존 저장 step_code 는 재생성 시 교정). **탭닫기 자체는 (2) 때문에 재생성해도
  AI 가 또 Document 를 찍으면 안 닫힘** → 엔진/수동편집 논의.

## 70. 2026-05-31 캡처에 picker 붉은 오버레이 찍힘 — grab 직전 오버레이 숨김

**컨텍스트**: §69 후 이미지 표시 정상. 그러나 캡처된 "+" 이미지에 **picker 의 붉은 하이라이트
오버레이 색이 가미돼 찍힘**(빨간 테두리). 원인(§66 타이밍): `_capture_element_image` 가 mss 로
요소 rect 를 grab 할 때, Electron 붉은 박스 오버레이가 **아직 떠 있음** — 오버레이는 /pick/click
응답이 렌더러에 도달한 뒤 `stopPickOverlay` 로 닫히는데, grab 은 그 응답 생성 전(라우트 핸들러)에
일어남. → grab 프레임에 빨간 박스 포함.

### fix (api_server only, core 0줄)
- **`pick_pump.py`**: `pick_on_click` finally 의 `_overlay_hwnd = None` 클리어 **제거**(반환 직후
  라우트가 그 HWND 를 써야 함 — 다음 pick 의 set_overlay_hwnd 가 덮어씀) + **`get_overlay_hwnd()`** 추가.
- **`routes/pick.py` `_hide_pick_overlay()`**: grab 직전 오버레이 HWND 로 `ShowWindow(SW_HIDE)`
  (§49 처럼 cross-process 동작, x64 HWND 절단 방지 argtypes) → DWM 재합성 0.12s 대기 → grab.
  **복원 안 함**(렌더러가 곧 닫음 — 복원 시 붉은 박스 깜빡임만). 오버레이 미등록(HWND None)이면
  그대로 grab(graceful). `_capture_element_image` 가 grab 전에 호출.

### 검증
- **test_230**(+1, core **225/225**): get_overlay_hwnd set/get 라운드트립 + 미등록 시
  _hide_pick_overlay graceful False(실 창 미접촉, 비-Windows 안전). 실제 숨김+grab 은 GUI 의존이라
  미테스트. scenarios 73/73 + recording_fixtures 2/2 + ruff 그린. core/PySide6/ui_v2 0줄. 프론트 무변경.
- **사용자: Python 브리지 재시작 필요**(api_server 변경 — 렌더러 재빌드 불필요). 재픽 → 캡처에 빨간
  테두리 없이 "+"만 깨끗이 찍히는지 확인. (안 되면 0.12s 재합성 대기 상향 또는 렌더러측 숨김 대안.)

## 69. 2026-05-31 캡처 이미지 "깨진 표시" = CSP img-src 에 blob: 누락 (한 줄 fix)

**컨텍스트**: §68 재빌드 후 사용자 실측 — 썸네일 박스는 고정 크기로 정상이나 **이미지가 "깨진
이미지" 아이콘**(브라우저 broken-image placeholder)으로 표시. 즉 `<img>` 는 렌더되나 src 로드 실패.

**근본 원인**: `desktop_v3/src/renderer/index.html` 의 CSP `img-src 'self' data:;` 에 **`blob:` 누락**.
CaptureThumb 는 인증 fetch→`URL.createObjectURL`(=`blob:` URL)로 이미지를 로드하는데, CSP img-src
가 blob: 을 막아 `<img src="blob:...">` 차단 → broken-image. (`connect-src` 는 bridge 허용이라
fetch 자체는 성공 — JSON·이미지 fetch 동일, 그래서 데이터는 잘 받아옴. `worker-src`/`script-src` 는
blob: 허용했지만 img-src 만 누락 — §66 이미지 기능 추가 시 CSP 미갱신.) **서빙 엔드포인트/CORS/
파일 모두 정상 검증됨**(TestClient: 200 image/png 318B, Origin 시 ACAO `*`) — 순수 CSP 문제.

**fix**: index.html CSP `img-src 'self' data:` → **`img-src 'self' data: blob:`** (한 줄). CaptureThumb
코드(object URL)는 정상이라 무수정. 빌드 출력 out/renderer/index.html 에 반영 확인.

**검증**: electron-vite build 그린, 번들 CSP 에 blob: 포함 확인. core 224/224 불변(HTML 변경뿐).
core/PySide6/ui_v2 0줄. **사용자: 재빌드/새로고침 후 썸네일에 실제 "+" 이미지 표시 확인**(P1 오클릭은
§68 의 AI 준수 이슈로 별개 — 재생성 시 셀렉터 확인 필요).

## 68. 2026-05-31 캡처 썸네일 고정크기 + 셀렉터 단순화 방지 지시 (검은 세로줄 + 오클릭 후속)

**컨텍스트**: §67 재빌드 후 사용자 실측(세션 ba7f4dc8, 메모장 "+" pick→"클릭하기"). §67 Fix #1
검증됨(step.captures 에 경로 저장됨 = race 해소). 남은 2건:

### P2 — 캡처 이미지가 "검은 세로줄"로만 표시 (CaptureThumb CSS 버그)
- 원인: `CaptureThumb` 컨테이너가 높이(h-20)만 고정·**너비 미고정** + img `max-h-20 max-w-full`
  (object-contain 무효 — 컨테이너가 img 자연크기로 줄어듦). 작은 "+"(~56×42) → 좁은 박스 →
  bg-black/30 만 보여 검은 세로줄. (사용자가 §66 때 요청한 "표시 영역 일정"도 미충족.)
- fix(ChatPanel `CaptureThumb`): 컨테이너 **`h-20 w-28` 고정** + img `h-full w-full object-contain p-1`
  → 이미지 크기와 무관히 일정한 박스, 작은 "+"도 업스케일되어 보임. 카드 높이 안정.

### P1 — 클릭이 "+"(새 탭)가 아닌 엉뚱한 Button (AI 셀렉터 단순화)
- **§66/§67 버그 아님**: 프롬프트 로그(tmp/conversations/...step2_ba7f4dc8.md) 실측 — §67 풍부한
  element_context 가 정상 주입됨(`## 선택된 UI 요소`, 타입 Button, 이름 "새 탭 추가",
  **Automation ID AddButton**, rect (1602,425) 56×42) + `_resolve_element` 템플릿(title="새 탭 추가"
  셀렉터 cascade)까지 제공. **그런데 AI(agy/Gemini)가 그 템플릿을 무시**하고 시스템 가이드의
  generic 예시(`win.child_window(control_type="Button", found_index=0)`)로 단순화 → **같은 타입의
  첫 Button** 이 잡혀 오클릭. 즉 데이터 흐름은 맞고 **AI 프롬프트 준수(adherence) 문제**.
  근본은 프롬프트 충돌(system_context 의 generic `control_type+found_index` 예시 vs element_context
  의 specific title 템플릿 — AI 가 generic 선택). 깊은 해결은 `config/prompts.json`/`prompt_builder`
  (core+v2 공유) 라 **불변 원칙(core 0줄) 상 사용자 결정 필요**.
- **v3-only 완화(이번, core 0줄)**: `routes/pick.py _build_element_context` 가 element_context
  말미(프롬프트 recency 위치)에 강한 anti-pattern 지시 추가 — "`_resolve_element` 의 title/auto_id
  셀렉터를 그대로 쓰고 `control_type+found_index=0` 로 단순화 말 것(첫 요소 오클릭)". best-effort
  (AI 가 따를지는 비결정적) — 확실한 해결은 prompts.json 측.

### 검증
- **test_229 확장**(core **224/224** 유지): _build_element_context 에 anti-pattern 지시(found_index/
  단순화하지) 포함 가드 추가. scenarios 73/73 + recording_fixtures 2/2 + tsc/build/ruff 그린. core/PySide6/ui_v2 0줄.
- **사용자 조치**: 재빌드/재시작 후 "+" 재픽→재생성. ① 썸네일이 일정 박스에 "+"로 보이는지 ②
  생성 코드가 `child_window(auto_id="AddButton"...)` 또는 `title="새 탭 추가"` 로 "+"를 타겟하는지.
  **②가 여전히 generic 이면** = AI 준수 한계 → prompts.json 강화(v2 영향) 또는 엔진 교체를 사용자와 논의.

## 67. 2026-05-31 pick race fix + 풍부한 element_context (요소 이미지 미표시 + 엉뚱 클릭 근본 수정)

**컨텍스트**: 사용자 실측(세션 5c3361ad) — 메모장 "+"(새 탭) 버튼을 picker 로 고르고 "클릭하기"
생성 시 ① 선택 "+" 이미지가 step 카드에 안 보이고 ② AI 가 "+"를 무시하고 control_type="Document"
(텍스트영역)를 클릭하는 코드 생성. **워크플로우(4 에이전트: 2 finder + 2 적대 검증)로 단일 근본
원인 규명** — 실 프롬프트 로그(tmp/conversations/...step2...md)에서 element_context 가 null 이었음 실측 확정.

### 근본 원인 = 단일 race (두 증상 모두 설명)
`ChatPanel.send()` 가 `genMut.mutate(req)` **직후 같은 tick 에 `clearPending()`/`clearImages()` 동기
호출**. 그러나 React Query v5 는 mutationFn 을 **다음 microtask** 에 실행(내부 `await onMutate?.()`
가 undefined 라도 yield). → mutationFn 이 `usePickStore.getState().pending` 을 읽을 땐 **이미 null**.
- 증상②: pendingEl=null → element_context=null 전송 → core prompt_builder `if element_context:` skip
  → AI 가 선택 요소 정보 0 → prompts.json 가이드 #17 의 폴백 예시(`child_window(control_type="Document")`)
  를 거의 verbatim 복제.
- 증상①: elementImage=pendingEl?.imagePath=undefined → onDone attach 가드 false → attachStepCapture
  미호출 → step.captures=[]. (이미지는 pick 단계에서 이미 디스크 저장 — 캡처≠링크, 모순 아님.)
- 빌드 stale 아님(번들 내용으로 검증). 같은 race 가 카메라 images 경로에도 잠재했음.

### Fix #1 — race 제거 (desktop_v3, 두 증상 즉시 해결)
- **ChatPanel**: `send()` 가 mutate **호출 시점에** `pending`+`images` 스냅샷을 떠 `genMut.mutate({req,
  pendingEl, images})` 인자로 동기 전달 후 clear. mutationFn 시그니처 `(req)`→`({req,pendingEl,images})`,
  내부 getState() lazy read 제거(인자 사용). microtask 지연과 무관하게 정확한 pending 전달.

### Fix #2 — 풍부한 element_context (v2 동등, "+" 클릭 신뢰성, core 0줄)
- 근본 원인과 별개로 v3 는 element_context 로 **한 줄 라벨**(format_element_label)만 보냈음 → 프롬프트
  가이드 #17 이 "그대로 시작 코드로 쓰라"는 **"## 선택된 UI 요소" 섹션/코드 템플릿이 v3 프롬프트에
  부재**(v2 는 get_element_info_text 사용). 라벨이 닿아도 타겟팅이 구조적으로 약함.
- **routes/pick.py `_build_element_context(element)`**: core 공개 `WindowInspector.get_element_info_text`
  재사용(core 0줄)으로 그 구조화 섹션 생성. `capture_element_at` 의 rect=`[l,t,r,b]` 리스트를
  `{left,top,width,height}` dict 로 정규화(get_element_info_text 가 dict 기대 — §49 fix1 함정). **guard**:
  실패 시 None → 한 줄 라벨로 폴백(최악도 Fix #1 동작). `/pick/click` 성공 시 `element_context` 반환.
- **desktop_v3**: PickResult.element_context / PendingElement.elementContext(라벨은 칩용 유지) /
  pickStore 보관 / ws.ts `element_context: pending.elementContext ?? pending.label`.

### 검증
- **test_229**(+1, core **224/224**): `_build_element_context` 가 rect-리스트에 crash 없이 "## 선택된 UI
  요소" 섹션 + control_type/name/auto_id 생성, rect 없음/빈 dict graceful, core 공개 메서드 가드.
  (test_228=§66 유지.) scenarios 73/73 + recording_fixtures 2/2 + tsc/build/ruff 그린. core/PySide6/ui_v2 0줄.
- **사용자 조치 필요**: 앱 **재빌드/재시작**(특히 Python 브리지 — §67 백엔드는 브리지 재시작 필요) 후,
  기존 깨진 step2 는 **재생성(또는 삭제 후 재픽)** 해야 올바른 코드+이미지가 나옴(기존 step 의 잘못된
  코드는 자동 교정 안 됨). 재현 확인: "+" pick → "클릭하기" → step 카드에 "+" 이미지 표시 +
  생성 코드가 Button(name/auto_id) 타겟(Document 아님).

## 66. 2026-05-31 step 카드 UX — AI설명 숨김 + 단색 아이콘 + 선택 요소 스크린샷 표시

**컨텍스트**: 사용자 보고 3건. 좌측 레일 폭 축소(커밋 ff0db59, §-less)에 이어 step 카드.

### (1) AI 설명 기본 숨김 + (3) 사용자/AI 아이콘 단색화 — 커밋 e4dc28f
- `ChatPanel.StepCard`: `ai_description` 은 기본 숨김 → **step 선택(active) 시에만** 표시
  (코드는 선택 시 CodePane 에 이미 보임). 👤/🤖 컬러 이모지 → lucide `User`/`Bot` 단색
  아이콘(`text-discord-muted`)으로 Library/Initial 블록 카드(`Library`/`Cog`)와 통일.

### (2) 선택 요소 스크린샷 캡처 + step 표시 — 이 커밋
**중요 사실관계**: 요소 선택(pick)은 원래 **이미지를 캡처 안 함** — control_type/name/rect 등
**텍스트 메타만** 잡아 `element_context` 로 AI 에 전달. 이미지를 만드는 건 §60 카메라(영역 캡처)
뿐인데 그것도 `step.captures` 에 경로만 저장되고 **서빙 엔드포인트가 없어** 화면 표시 불가였음.
사용자 선택(옵션 A): **pick 시 요소 rect 를 스크린샷으로 잘라 표시**. core 0줄(공개 API 재사용).

설계 — **표시 전용(AI 무전송)**: pick 의 element_context(텍스트)는 그대로 두고, 스크린샷은
generate 의 `images` 채널(→AI 멀티모달)을 **타지 않고** 생성 후 step.captures 에만 붙인다.
(images 로 보내면 매 pick 마다 AI 토큰/비용 증가 — 사용자는 표시만 원함.)

- **api_server (core 0줄)**:
  - `deps.session_captures_dir(service, sid)` 공용 헬퍼(공개 `get_captures_dir` 위임).
  - `routes/pick.py`: `/pick/click` 가 `PickClickRequest{session_id?}` 수용 → 클릭 후
    (메인 minimize 라 대상 가시) 요소 `rect` 를 `capture_pump.capture_region` 으로 grab →
    세션 captures 저장 → 응답 `image`(절대경로). best-effort(실패해도 pick 성공).
  - `routes/sessions.py`: **`GET /sessions/{id}/captures/{filename}`** FileResponse 서빙
    (traversal 가드, 인증 헤더 유지 위해 프론트는 fetch→blob).
  - `routes/steps.py`: **`POST /sessions/{id}/steps/{step_id}/capture {path}`** → step.captures
    병합(중복 무시) `update_step` 위임. AI 무전송.
- **desktop_v3**: `client.ts`(PickResult.image / PendingElement.imagePath / Step.captures /
  `pickElementOnClick(sessionId)` / `attachStepCapture` / `fetchCaptureObjectUrl`=인증 fetch→objectURL).
  `pickStore.startPick(sessionId)` → pending.imagePath. `ChatPanel`: genMut `onDone` 에서 생성된
  step 에 attach(표시 전용) → invalidate 로 captures 반영. **`CaptureThumb`**(고정 높이 `h-20`
  컨테이너 + `object-contain` → 이미지 크기 무관 표시 영역 일정, step 카드 높이 안정) 를 STEP
  헤더와 사용자 요청 사이에 렌더. `CommandPalette` pick 도 selectedSessionId 전달.
  - **부수효과(긍정)**: §60 카메라 영역 캡처 이미지도 이제 step 카드에 표시됨(같은 captures 경로).

### 검증
- **test_228**(+1, core **223/223**): 서빙 GET + attach POST 라우트 + PickClickRequest/
  AttachCaptureRequest 스키마 + session_captures_dir + 세션생성→더미png 서빙 라운드트립 +
  traversal 400/없는파일 404 + attach 병합(중복무시) + 없는 step/세션 404. (실 grab 은 디스플레이
  의존이라 미호출.) scenarios 73/73 + recording_fixtures 2/2. tsc/build/ruff 그린. core/PySide6/ui_v2 0줄.
- **사용자 GUI 실측 필요**: 요소 pick → 클릭 → 자연어 전송 → 생성된 step 카드에 요소 스크린샷이
  고정 영역으로 표시(크기 다른 요소도 카드 높이 일정), 카메라 캡처도 동일 표시, AI 설명은 선택 시만,
  아이콘 단색. 멀티모니터/고DPI 에서 rect grab 정확도.

## 65. 2026-05-31 설정 다이얼로그 한글화 (config 키 라벨 i18n)

**컨텍스트**: 사용자 보고 — "한글인데 설정 메뉴에 한글화 안 된 항목이 많다". 원인: §56 이 설정
화면을 전체 config 섹션으로 확장하며 제네릭 에디터가 **`default_settings.json` 의 영문 원본 키**
(`image`/`recognition`/`execution`/... + `capture_quality`/`step_delay_ms`/`sandbox_mode`/…)를
mono 폰트로 **그대로 라벨에 출력**했음. 정적 라벨(title/save 등)만 `t()` 였고 동적 키는 미번역.

### 수정 (desktop_v3 전용, core 0줄)
- **i18n 카탈로그**: ko.ts/en.ts 에 `settingsKeys` 네임스페이스 신규 — 섹션 10개 + 엔진 이름
  (cli_ai/openai_compat) + 전 필드(ai/image/recognition/execution/visual_feedback/ui/
  output_project/logging/element_picker/hints) 키 → 사람이 읽는 라벨 맵. ko/en 동일 키
  (tsc 가 `Catalog`=typeof ko 로 parity 강제).
- **`SettingsDialog.tsx`**: `labelFor(k)=t(\`settingsKeys.${k}\`,{defaultValue:k})` (미등록 키는
  원본 키로 graceful 폴백). `Field`/`ArrayField` 에 `label` prop 추가(표시는 라벨, **원본 키는
  `title` tooltip 으로 보존** — 설정이 config 파일/v2 와 공유라 키 식별성 유지). `GenericFields`
  가 `labelFor` 전파, `ConfigSection` 은 `title`=라벨/`rawKey`=tooltip, 엔진 셀렉트 옵션·엔진설정
  헤더도 `labelFor`. 값(value, 예: theme=dark)은 실제 저장값이라 그대로(라벨만 번역).
- 비-문자열 배열 값은 여전히 `JSON.stringify` mono 표시(라벨 아님, 의도).

### 검증
- tsc EXIT 0(ko/en parity 포함) + electron-vite build EXIT 0. core/PySide6/ui_v2 **0줄**.
- **사용자 GUI 실측**: 설정 → 고급 섹션 펼치면 항목들이 한글 라벨, 항목 hover 시 원본 키 tooltip,
  영어 전환 시 영문 라벨, 미등록 키(있다면)는 원본 키 노출.

## 64. 2026-05-31 Phase E 배포 freeze 실측 / de-risk (개발 환경 실빌드)

**컨텍스트**: P1+ 패리티 백로그 소진(§63) 후 사용자 선택 = 배포 freeze 준비. §46 은 설정/문서만
하고 "freeze 는 사용자 머신"으로 미뤘는데, freeze 자체는 GUI 불필요한 CLI 작업이라 이 개발
환경(Windows)에서 **실제로 빌드·부팅·동봉까지 돌려 막힘을 미리 제거**. core/PySide6/ui_v2 **0줄**.

### 발견·수정한 막힘 (실빌드로 드러난 것)
1. **PyInstaller 미선언** → 문서의 `uv run pyinstaller` 가 애초에 실패(program not found).
   `pyproject.toml [project.optional-dependencies].build = ["pyinstaller>=6.0"]` 추가 + `uv.lock` 갱신.
2. **spec 의 죽은 hidden import**: `"pywinpty"` 는 PyPI **배포명**이라 import 모듈이 없음
   (freeze 시 `ERROR: Hidden import 'pywinpty' not found`). import 모듈명은 `winpty`(이미 목록에 있음,
   `core/adapters/cli_ai_adapter.py` 가 lazy import) → `pywinpty` 제거 + 주석.
3. **§63 의 기커밋 tsc 버그**: `ChatPanel.tsx` 가 recordStore 의 옛 메서드 `stopCommit` 을 구조분해
   (§63 이 `stopReview` 로 rename 하며 호출 인자/CommandPalette 는 고쳤지만 ChatPanel 구조분해 키 누락).
   `npm run build`(electron-vite=esbuild)는 타입을 stripping 해서 통과 → §63 "tsc 그린"이 오claim.
   `tsc --noEmit` 로 잡아 `stopReview: stopRec` 로 수정(런타임 시 녹화중단 버튼이 undefined 호출로 throw 할 버그).
4. **packaged data-dir 가 번들 내부**: frozen 기본 data 경로 = `Path(__file__).parent.parent/data`
   = `resources/pybridge/_internal/data` (실측으로 거기 생성 확인). 앱 업데이트 시 세션 소실 +
   perMachine 설치 시 쓰기 불가 위험. → **Electron `bridgeCommand` packaged 분기가 `--data-dir
   <userData>/data` 전달**(`app.getPath("userData")`, `%APPDATA%/ohdo/data`). 브리지는 `--data-dir`
   이미 지원(§37) → **TS 만 수정, core 0줄**. dev 는 미지정(프로젝트 루트 data/, PySide6 공유).
5. **package-lock 미동기화**: §46 이 `electron-builder` 를 package.json 에 넣고 `npm install` 을
   안 돌려 lockfile 에 의존성 트리가 없었음 → `npm install` 로 동기화(+4595/-252, 커밋).

### 실제로 검증한 것 (이 환경)
- **freeze**: `uv run --extra build pyinstaller desktop_v3/build/ohdo-bridge.spec --noconfirm` → exit 0,
  `dist/ohdo-bridge/ohdo-bridge.exe`(18.8MB) + `_internal/`. warn 파일의 "missing module" 은 전부
  표준 노이즈(`collections.abc`/`comtypes.test.*`/`trio` 미사용 백엔드/numpy lazy attr) — 실 의존성
  (winpty/keyring/fastapi/uvicorn/pywinauto/uiautomation/comtypes/cv2/pandas/PIL/mss) 전부 동봉 확인.
  `config/`+`core/locale/` datas 도 `_internal/` 에 정상 동봉.
- **frozen 부팅**: `ohdo-bridge.exe --port 9123` → `OHDO_API_READY` 마커 + uvicorn startup,
  `/health` 200, `/sessions`(토큰) 200·(무토큰) 401, `/environment` 200(**core 스캐너가 frozen 에서
  실동작**, python_path=frozen exe). create_app→deps→AppService.create_default→config 로딩 OK.
- **동봉 패키징**: 브리지를 `desktop_v3/build/pybridge/` 복사 후 `electron-builder --win --dir` →
  exit 0, `release/win-unpacked/ohdo.exe`(201MB) + `resources/pybridge/ohdo-bridge.exe`(18MB) 동봉 확인
  (extraResources 매핑 정상). winCodeSign 캐시의 macOS dylib **symlink 생성 에러**가 로그에 뜨지만
  비-치명(재시도로 exit 0) — 코드 서명 안 하므로 무관. NSIS 빌드가 막히면 Windows 개발자 모드 ON.
- tsc EXIT 0 + electron-vite build EXIT 0 + **core 222/222** + scenarios 73/73 + recording_fixtures 2/2 + ruff 그린.

### 문서
- **`docs/BUILD.md`** (신규): 0 사전준비(`.venv` 강조 — `venv/` 는 구버전 잔재라 브리지 의존성 결손) →
  1 freeze + 단독 스모크테스트 → 2 복사 → 3 NSIS/dir 빌드 → 4 GUI 실측 체크리스트 → 5 한계
  (코드서명/자동업데이트/config 영속성) → 6 트러블슈팅(winCodeSign/hidden import/포트). README 에 빌드 섹션 + 포인터.

### 남은 / 후속 (사용자 머신 필요)
- **NSIS 설치본 실측**: `npm run dist` → `ohdo-0.1.0-setup.exe` 설치/실행/브리지 spawn/세션
  `%APPDATA%/ohdo/data` 저장/종료 시 브리지 동반종료 확인. + §58~§63 기능 실측(`pending_gui_verification`).
- **config 영속성**: 세션은 userData 로 뺐지만 `config/`(settings/prompts)는 여전히 번들 내부 읽기 →
  설정 다이얼로그 변경이 업데이트 시 초기화. 브리지 `--config-dir` + first-run 복사 후속 필요.
- **코드 서명 / 자동 업데이트** 미구성(SmartScreen 경고).

## 63. 2026-05-31 v3 패리티 백로그 P1 — 녹화 review 다이얼로그 (#22)

**컨텍스트**: 마지막 P1+ 백로그 #22. v3 는 녹화 종료(stop)가 즉시 commit 이었는데, v2 는
stop → RecordingReviewDialog 로 변환된 step 을 검토/편집 후 commit. 이를 v3 로 이식.

### 설계 (core 0줄 — 기존 분리 API 조합)
- core 는 이미 **stop_recording**(후크 해제 + raw→step 변환된 step 반환) /
  **commit_recording(edited_steps, target_session_id)**(세션 append+save) 로 2분리. 기존
  `RecordingController.stop("commit")` 은 stop_recording 결과를 받아 곧장 commit_recording 했을 뿐
  → review 는 **stop_recording(변환)까지만** 하고 commit 보류하면 됨. core 수정 불필요.
- LL 후크 해제(stop_recording)는 펌프 전용 스레드에서만 안전(§42) → preview 도 컨트롤러
  스레드 경유(stop 의 finally 에서 commit/preview 둘 다 stop_recording → `_steps` 보존).
  commit_recording 은 순수 데이터라 commit_steps 가 요청 스레드 직접 실행.

### 백엔드 (api_server, core 0줄)
- **`recording_pump.py`**: `stop(mode)` 가 "preview" 수용. `_run` finally 의 stop 분기를
  `if self._mode in ("commit", "preview")` 로 — 둘 다 변환 step 을 `_steps` 에 보존(preview 는
  commit 안 함, recorder 인스턴스 유지). `commit_steps(session_id, steps)`(commit_recording 직접) 신규.
- **`routes/recording.py`**: `POST /sessions/{id}/recording/stop_preview`→`{steps}`(녹화 중 아님 409)
  + `POST /sessions/{id}/recording/commit {steps}`(없는 세션 404, 빈 목록=모두 버림, commit 시
  drop_kernel). `CommitStepsRequest`. Step 재구성은 `Step.__dataclass_fields__` 로 알려진 키만
  (UI 전용/미지 키 무시, element_meta round-trip).

### 프론트 (desktop_v3)
- **client.ts**: `recordingStopPreview`/`recordingCommit`. **recordStore**: stopCommit → **stopReview**
  (stop_preview → 메인 복원 → step>0 이면 reviewOpen, 0이면 toast) + **commitReview**(편집 step 커밋
  + 세션 invalidate) + **discardReview**(버림). review 상태(reviewOpen/reviewSessionId/previewSteps).
- **`components/RecordingReviewDialog.tsx`** (신규): previewSteps 로컬 사본 편집 — step별 설명(input)/
  코드(textarea) 편집 + 삭제 + ↑↓ 순서변경, "버리기"/"N개 추가" 확정. App 에 전역 렌더.
- **ChatPanel/CommandPalette**: 녹화 중단 버튼 → stopReview(onDone 콜백 제거 — 다이얼로그가 invalidate).
- **i18n**: en/ko `review.*`.

### 검증
- **test_227** (+1, core **222/222**): stop_preview/commit 라우트 노출 + RecordingController
  메서드(stop/commit_steps) + core 분리 API(stop_recording/commit_recording)
  가드 + Step 재구성(미지 키 무시 + element_meta round-trip) + 없는 세션 commit 404 / 녹화 중 아님
  stop_preview 409. **실제 녹화는 LL 후크라 미테스트.** scenarios 73/73 + recording_fixtures 2/2.
  tsc/build/ruff 그린. core/PySide6/ui_v2/main.py **0줄**.
- **사용자 GUI 실측 필요**: 녹화 → 동작 → 종료 시 즉시 commit 안 되고 review 다이얼로그 → step
  편집/삭제/순서변경 → "추가" 시 세션 반영, "버리기" 시 미저장, 캡처 0건이면 다이얼로그 대신 toast.

### P1+ 백로그 완료
- §47 표의 P1+ 전부 소진: #10~#20(§47~§57) + #13(§60) + #19(§58) + #21(§61/§62) + #22(§63).
  남은 건 사용자 GUI 실측 후 발견되는 버그 / 신규 지정 작업.

## 62. 2026-05-31 v3 패리티 백로그 P1 — 시크릿 @자동완성 + 평문 감지 #21b

**컨텍스트**: §61(#21a CRUD)에 이어 #21b. v2 의 `secret_insert_popup`(@ 자동완성) +
`secret_advisory_dialog`(전송 전 평문 감지→마스킹 권고)의 v3 등가. core 0줄
(`secrets_detector.detect`/vault 목록 재사용 + placeholder 는 core 가 generate 시 해결).

### 백엔드 (api_server)
- **`routes/secrets.py` 에 `POST /secrets/scan` 추가**: `secrets_detector.detect(text)` 위임 →
  매치별 `{start,end,kind,confidence,suggested_label,preview}` 반환. **값(value)은 절대 미노출** —
  preview 는 앞 2자 + `•` 마스킹(최대 32자). vault 무관(감지는 항상). 감지 실패는 빈 결과 graceful.

### 프론트 (desktop_v3)
- **`components/SecretAutocomplete.tsx`** (신규): 기존 Textarea 를 감싼 입력창. `findAtTrigger`
  (커서 직전 `@<prefix>`, `@` 앞은 공백/시작 + 뒤는 `[a-z0-9_]*`)로 토큰 감지 → `/secrets` 라벨
  드롭다운(prefix 필터, ↑↓ 이동, Enter/Tab 선택, Esc 닫기, 마우스다운 선택). 선택 시 `@prefix` →
  `{{secret:label}}` 치환 + 커서 이동. Enter(자동완성 닫힘 상태)=전송, Shift+Enter=줄바꿈 유지.
- **ChatPanel**: Textarea → SecretAutocomplete 교체(Textarea import 제거). `submit` 을 async 로:
  전송 전 `scanSecrets(req)` → 매치 있으면 `secrets.plaintextWarn` confirm(취소 시 미전송 → @등록
  유도). 감지 실패는 무시하고 전송(보조 안전장치). 자동완성으로 이미 placeholder 면 detect 무경고.
- **client.ts**: `scanSecrets(text)` + `SecretScanMatch` 타입. **i18n**: en/ko `secrets.plaintextWarn`.

### 검증
- **test_226 확장**(core **221/221** 유지): #21a CRUD 에 더해 (6) `/secrets/scan` 라우트 노출 +
  평문 감지 1건+ + **응답에 원본 시크릿 값 미노출 가드** + match 에 value 필드 없음 + 평문 없는
  문장 200. scenarios 73/73 + recording_fixtures 2/2. tsc/build/ruff 그린. core/PySide6/ui_v2 0줄.
- **사용자 GUI 실측 필요**: 입력창에 `@` → 라벨 드롭다운(등록된 시크릿) → 선택 시 placeholder 삽입,
  ↑↓/Enter/Tab/Esc 동작, 평문 비밀 입력 후 전송 시 경고 confirm(취소→미전송), placeholder 는 무경고,
  실제 generate 시 `get_secret` 으로 해결되는지.

### #21 완료 / 남은
- #21a(§61) + #21b(§62) 로 시크릿 볼트 완료. **남은 P1+: #22 녹화 review 다이얼로그.**

## 61. 2026-05-31 v3 패리티 백로그 P1 — 시크릿 볼트 #21a (CRUD)

**컨텍스트**: 백로그 #21(시크릿 볼트, 큼). 큼 → **#21a CRUD + #21b @자동완성** 2조각 분할.
이번엔 #21a. core ADR0003 시크릿 인프라(서브에이전트 조사로 확인)는 이미 완비:
- `core/secrets.py` `SecretsVault`(추상)+`KeyringVault`(OS keyring) — set/get/delete/list,
  `SecretLabel(label,namespace)` label 패턴 `^[a-z0-9_]{1,32}$`, namespace `secret|apikey`.
- `AppService.secrets_vault` 프로퍼티로 노출(create_default 가 KeyringVault 자동 생성, 실패 시 None).
- 실행 주입은 이미 배선: `deps.get_kernel` → `kernel.push_secrets()` → kernel_worker `get_secret()`
  helper 가 `OHDO_SECRET_<label>` env 로 읽음. → **#21a 는 CRUD 브리지+UI 만, core 0줄.**

### 보안 설계
- **값은 절대 renderer 로 안 보냄**: list 는 label 만, set 응답에 값 미포함, get 엔드포인트 자체
  없음(코드에서 `get_secret('label')` 로만 참조). keyring 에만 평문 저장.
- namespace 는 `secret`(사용자 비밀)만. `apikey`(AI 키)는 설정 다이얼로그(§47)가 별도 관리.
- vault 미가용(keyring 미설치/headless) → `available:false` graceful(등록·삭제 503).

### 백엔드 (api_server, core 0줄)
- **`routes/secrets.py`** (신규): `GET /secrets`→`{available,labels}`, `POST /secrets {label,value}`
  (label 패턴 위반 400 / 빈 값 400 / vault 미가용 503), `DELETE /secrets/{label}`(미존재는 404 아닌
  success=false). `SecretLabel` 로 검증, `AppService.secrets_vault` 위임. server.py include_router.

### 프론트 (desktop_v3)
- **`components/SecretsDialog.tsx`** (신규): 등록 폼(label 입력+실시간 패턴검증, value는 type=password
  마스킹) + 목록(label + `get_secret('label')` 힌트 + 삭제, 값 표시 없음) + 미가용 안내.
- **client.ts**: fetchSecrets/setSecret/deleteSecret. **uiStore**: secretsOpen/setSecretsOpen.
- **ServerRail**: 환경점검과 설정 사이에 KeyRound 버튼. **CommandPalette**: "시크릿 볼트" 명령.
- **i18n**: en/ko `secrets.*` + `palette.secrets`.

### 검증
- **test_226** (+1, core **221/221**): 라우트 3개 노출 + AppService.secrets_vault 속성 + SecretLabel
  패턴 ValueError + GET available/labels + 잘못된 label 400|503 + **가용 시 set→list→delete 라운드트립
  + 응답에 시크릿 값 미포함 가드**(없으면 503 경로). scenarios 73/73 + recording_fixtures 2/2 유지.
  tsc/build(3106)/ruff 그린. core/PySide6/ui_v2/main.py **0줄**.
- **사용자 GUI 실측 필요**: 레일 KeyRound·팔레트로 다이얼로그 → label/값 등록(keyring 저장) → 목록
  표시(값 X) → 코드에서 `get_secret('label')` 실행 시 주입 동작 → 삭제. keyring 미설치 시 안내.

### 남은
- **#21b @자동완성**: ChatPanel 입력창 `@` → 시크릿 라벨 자동완성 + 전송 시 평문 감지 마스킹
  (secrets_detector.detect). **#22 녹화 review**.

## 60. 2026-05-31 v3 패리티 백로그 P1 — 첨부 이미지 (스크린 영역 캡처) (#13)

**컨텍스트**: 남은 P1+ 백로그(§47 표) 순서대로 — #13 부터. v2 는 `ui/screen_capture.py`
(전체화면 오버레이 + mss grab + PIL) 로 영역을 캡처해 AI 호출 시 `generate(images=)` 첨부.
v3 엔 캡처 백엔드도 오버레이도 없었음(picker 만 있었음).

### 설계 (core 0줄)
- **core 이미 지원**: `AppService.generate_step(images=[...])` 가 `step.captures` 저장 + 멀티모달
  프롬프트(`image_paths`)까지 처리(line 891/970/1056). → 갭은 ① 영역 캡처 백엔드 ② v3 generate
  경로(WS/POST) images 배선 ③ Electron 드래그 오버레이 뿐.
- **드래그 오버레이는 picker 와 별개**: picker(§49)는 클릭통과(WS_EX_TRANSPARENT)+hover 폴링이라
  드래그 사각형을 못 받음 → 클릭통과 **아닌** 별도 `capture_overlay`(자체 mousedown→move→up
  사각형 + Esc 취소) 신규. 전역 후크/펌프 불필요(좌표를 프런트가 확정해 보냄).

### 백엔드 (api_server, core 0줄)
- **`api_server/capture_pump.py`** (신규): `capture_region(captures_dir,l,t,w,h)` — mss grab →
  PIL `region_<ts>.png` 저장 → 경로 반환. mss/PIL import 함수 내부(비-Windows 안전), 빈 영역 거부.
- **`routes/capture.py`** (신규): `POST /capture/region` → 공개 `get_captures_dir`(via
  `service._repo.manager`) → capture_pump 위임. 없는 세션 404 / 파일저장소 아님 501 / grab 실패 500.
- **images 배선**: `deps.GenerateRequest.images` + `routes/sessions.py`(POST) & `routes/generate.py`
  (WS) 둘 다 `generate_step(images=...)` 전달.

### 프론트 (desktop_v3)
- **`capture_overlay.html`+`.ts`** (신규): 드래그 사각형 + mouseup→`ohdoCapture.done`, Esc/소영역
  cancel. electron.vite 3번째 엔트리.
- **main**: `createCaptureOverlay`(클릭통과 아님) + `capture:start` IPC(메인 minimize → 오버레이 →
  done/cancel 수신 → `overlayCssRectToPhysical`(DIP→물리, `dipToScreenPoint`) → resolve). `virtualBounds`
  picker 와 공용 추출.
- **preload/env.d.ts**: `captureRegion()` + `ohdoCapture`(done/cancel) 오버레이 브리지.
- **`store/captureStore.ts`** (신규): `startCapture` → `/capture/region` → `images[]` 누적.
- **client.ts** `captureRegion`, **ws.ts** generateStream images 인자, **ChatPanel** 카메라 버튼 +
  파랑 이미지 chip(w×h+제거) + 제출 시 images 전달·전송후 clear. i18n `chat.captureTitle`+`capture.*`.

### 검증
- **test_225** (+1, core **220/220**): /capture/region 라우트 + GenerateRequest.images + capture_pump
  import-safe + 빈영역 거부 + core generate_step images 파라미터(core 0줄) + 없는세션 404 / 누락 422.
  실제 grab 은 디스플레이 의존이라 미호출. scenarios 73/73 + recording_fixtures 2/2 유지. tsc/build
  (3105, capture_overlay 엔트리 emit)/ruff 그린. core/PySide6/ui_v2/main.py 0줄.
- **사용자 GUI 실측 필요**: 카메라 버튼 → 메인 minimize + 드래그 오버레이 → 영역 드래그 → 칩 w×h
  (멀티모니터/고DPI 정확도), 제거, 자연어와 함께 전송 시 멀티모달 인식 + step.captures 저장, Esc 취소.

## 59. 2026-05-30 좌측 서버 레일 회수 — 전역 네비/유틸 바 (#2, 워크스페이스 #1 예약)

**컨텍스트**: 사용자 지적 — "왼쪽 상단 oh 로고 세로영역이 비효율적 공간으로 보인다. 나중에
어떤 용도인가?" 조사 결과 그 영역은 §37 의 Discord-like 레이아웃을 복제하며 따라온 **서버
레일**이지만 ohdo 엔 아직 '서버/워크스페이스' 개념이 없어 **로고 자리표시자로 방치**돼 있었음
(코드/handoff/ROADMAP 어디에도 후속 용도 기록 없음). 사용자 결정: **현 단계는 #2(네비/유틸
회수), 워크스페이스 기능이 실제 들어올 때 #1(프로젝트 전환기)로 승격** — 로드맵 §226 "워크스페이스"
개념과 정합.

### 설계 (왜 레일을 없애지 않나)
- 레일을 제거하고 로고를 사이드바 헤더로 옮기는 #4(공간 회수)도 후보였으나, 나중에 #1 승격 시
  Discord 레이아웃을 다시 세워야 하므로 **레일은 유지하되 실제 역할을 부여**하는 #2 채택.
- 현재 사이드바 푸터에 좁게(h-6 w-6) 밀집했던 전역 유틸 5개(도움말/환경/설정/언어/테마)를
  레일 하단으로 이전 — 레일이 "전역", 사이드바가 "세션 범위"로 의미가 분리됨.

### 구현 (순수 프론트, core/api_server 0줄)
- **`components/ServerRail.tsx`** (신규): App.tsx 인라인 `ServerRail`(로고만)에서 승격.
  - 상단 로고(oh) = **홈**: `selectSession(null)` → 활성 세션 해제 → EmptyState. hover 시
    rounded 전환(Discord 감성).
  - 하단 유틸 그룹(`mt-auto`): 도움말(setOnboardingOpen)/환경점검(setEnvOpen)/설정(setSettingsOpen)/
    언어(setLang)/테마(themeStore.toggle). 모두 기존 uiStore 플래그·themeStore·i18n 재사용.
- **`App.tsx`**: 인라인 ServerRail 함수 제거 + `import { ServerRail }`.
- **`SessionSidebar.tsx`**: 푸터의 유틸 버튼 5개 제거 → HealthDot 만. 미사용해진 import
  (Activity/HelpCircle/Languages/Moon/Settings/Sun, useThemeStore, currentLang/setLang) +
  지역변수(theme/toggleTheme/lang/i18n/setOnboardingOpen) 정리. 설정/환경 다이얼로그는 store
  구동이라 사이드바에 그대로 렌더(레일 버튼이 같은 플래그를 토글).
- **i18n**: en/ko `sidebar.home` 추가.

### 검증
- tsc EXIT 0 + electron-vite build(3100 modules) 통과. core **219/219** 유지(Python 무관).
  api_server/PySide6/ui_v2/main.py 0줄.
- **사용자 GUI 실측 필요**: 레일 하단 5개 아이콘 동작(설정/환경/도움말 다이얼로그, 언어·테마 토글),
  로고 클릭 시 홈(EmptyState)으로, 사이드바 푸터가 브리지 상태만 남았는지, 라이트/다크 양쪽 색.

### 다음(예약) — 워크스페이스 #1 승격 시
- 로고 아래에 워크스페이스/프로젝트 아이콘 목록 추가(세션을 프로젝트로 묶어 전환). ROADMAP §226
  "사용자/워크스페이스" 도입과 함께. 그때 이 레일이 Discord 서버 레일과 동일 역할이 됨.

## 58. 2026-05-30 v3 패리티 백로그 P1 — 온보딩 위저드 (#19)

**컨텍스트**: 남은 P1+ 백로그(§47 표) 중 사용자 선택. 순수 UI(백엔드 0줄, 위험 낮고
첫 실행 경험 개선). 처음 ohdo 를 켠 사용자가 환경/AI 엔진을 안내받고 바로 첫 세션을
만들 수 있게 4단계 위저드 제공.

### 설계 (순수 프론트 — 기존 엔드포인트만 재사용)
- 신규 백엔드 없음. 환경점검은 §54 의 `GET /environment`, AI엔진은 §53 의 `GET /ai/engines`·
  `POST /ai/engine`, 세션 생성은 `POST /sessions` 를 그대로 호출 → **core/api_server 0줄**.
- 첫 실행 감지: `localStorage["ohdo.onboarded"] !== "1"` 이면 자동 오픈. 완료/건너뛰기/X 모두
  `markOnboarded()` 로 플래그 세팅 → 1회만 자동. (테마 `ohdo.theme`·언어 `ohdo.lang` 와 동일 패턴.)

### 구현
- **`components/OnboardingWizard.tsx`** (신규): 4단계 모달 위저드.
  - step0 환영 + 언어 선택(LangPicker, setLang ko/en 즉시·영속).
  - step1 환경 점검(EnvStep — fetchEnvironment 쿼리, Python/CLI AI/패키지 요약, 로딩/실패 처리,
    `staleTime: Infinity` 로 무거운 스캔 자동 refetch 금지).
  - step2 AI 엔진 선택(EngineStep — fetchAiEngines 목록 버튼, 클릭 시 switchAiEngine + toast +
    aiEngines/settings invalidate, 엔진 0개면 안내).
  - step3 완료 + "첫 세션 만들기"(createSession → selectSession → markOnboarded → 닫기).
  - 푸터: 단계 표시 + 이전/건너뛰기/다음, 마지막은 "시작하기". 기존 Button/모달 셸 패턴 재사용.
- **`store/uiStore.ts`**: `onboardingOpen` + `setOnboardingOpen` 추가(settings/env 와 동일 패턴).
- **`App.tsx`**: 첫 실행 useEffect(shouldShowOnboarding→setOnboardingOpen) + `<OnboardingWizard/>`
  렌더(onboardingOpen 일 때, CommandPalette 옆).
- **`SessionSidebar.tsx`**: 푸터에 HelpCircle(?) 버튼 → setOnboardingOpen(true) (재오픈 경로).
- **`CommandPalette.tsx`**: "시작 안내 보기" 명령 추가(HelpCircle, setOnboardingOpen).
- **i18n**: en/ko `onboarding.*` 카탈로그(제목/단계/버튼/4단계 본문) + `palette.onboarding` +
  `sidebar.help`. Catalog 타입 파리티 컴파일 강제.

### 검증
- tsc EXIT 0 + electron-vite build(3100 modules) 통과. desktop_v3 표준 검증 = typecheck+build
  (프로젝트에 lint 스크립트 없음). **순수 프론트 — Python/core 무변경**(core 219/219 유지,
  api_server 0줄). PySide6/ui_v2/main.py 0줄. TestClient 검증 대상 신규 엔드포인트 없음
  (기존 /environment·/ai/*·/sessions 재사용, 각각 §54/§53/기존 테스트가 커버).
- **사용자 GUI 실측 필요**: 첫 실행 시 자동 오픈(이후 미오픈), 4단계 이동/언어전환/환경표시/
  엔진선택/첫 세션 생성, 사이드바 ? · 팔레트로 재오픈, 건너뛰기·X 동작. (재실측하려면 DevTools 에서
  `localStorage.removeItem("ohdo.onboarded")` 후 새로고침.)

### 남은 P1+ 백로그 (§47 표)
- #13 첨부 이미지(B, 캡처 백엔드 필요), #21 시크릿 볼트(ADR0003, 큼), #22 녹화 review(큼).

## 57. 2026-05-30 v3 패리티 백로그 P1 — 멀티 세션 탭 (#17)

**컨텍스트**: §56 에 이어 P1 #17. 단일 세션만 보이던 v3 에 v2 처럼 여러 세션을 탭으로 열어두고
전환. 순수 프론트(백엔드/core 무관).

### 구현
- **uiStore**: `openTabs: string[]` 추가. `selectSession(id)` 가 탭에 없으면 끝에 추가 + 활성화
  (null 이면 활성만 해제, 탭 유지). `closeTab(id)` — 활성 탭이면 인접 탭(같은 위치 우선)으로
  전환, 비활성 탭이면 활성 유지. 마지막 탭 닫으면 selectedSessionId=null → EmptyState.
- **TabBar** (신규): `openTabs` 렌더, 활성 강조, 제목은 sessions 쿼리에서 조회, 탭별 X 닫기
  (활성은 항상, 비활성은 hover 시). 가로 overflow 스크롤.
- **App.tsx**: 사이드바 오른쪽 영역을 flex-col 로 래핑 — 상단 TabBar + 하단 (ChatPanel+CodePane)
  row. 세션 선택돼야 본문, 아니면 EmptyState.
- **SessionSidebar**: 세션 삭제 onSuccess 가 `select(null)` 대신 `closeTab(id)` 호출 — 삭제된
  세션의 탭 제거 + 활성이었으면 인접 탭으로(없으면 빈 화면). i18n `tab.close`.
- 생성/복제/가져오기/사이드바 클릭은 모두 selectSession 경유라 자동으로 탭에 추가됨.

### 검증
- tsc EXIT 0 + electron-vite build 통과. **순수 프론트 — Python/core 무변경**(core 219/219 유지,
  api_server 0줄). PySide6/ui_v2 0줄.
- **사용자 GUI 실측 필요**: 여러 세션 클릭 → 탭 누적, 탭 전환, X 로 닫기(활성 닫으면 인접 전환),
  삭제 시 탭 정리, 마지막 탭 닫으면 빈 화면.

### 남은 P1+ 백로그 (§47 표)
- #13 첨부 이미지(B, 캡처 백엔드 필요), #19 온보딩, #21 시크릿 볼트(ADR0003), #22 녹화 review.

## 56. 2026-05-30 v3 패리티 백로그 P1 — 설정 화면 확장 (#20)

**컨텍스트**: §47 에서 settings GET/PUT 백엔드 + AI 엔진 편집 UI 는 구현됐으나, SettingsDialog
가 **AI 엔진 섹션만** 노출 → 나머지 설정(실행 지연/스크린샷/OCR/로깅 등)은 v3 에서 못 만짐.
백엔드는 이미 전체 설정을 read/write 하므로(test_218) **순수 프론트로 다이얼로그만 확장**.

### 구현 (SettingsDialog 확장)
- **ConfigSection** (접이식, 기본 접힘): ai 를 제외한 모든 top-level dict 섹션을 자동 렌더
  (image/recognition/execution/visual_feedback/ui/output_project/logging/element_picker/hints).
- **GenericFields** (path 기반): 섹션 내부 값을 타입별 렌더 — bool/number/string 은 기존 `Field`
  (api_key 류 마스킹 유지), 문자열 배열은 **ArrayField**(쉼표 편집, 예 recognition.preferred_methods),
  중첩 dict 는 재귀(라벨+들여쓰기).
- **setByPath**: `['execution','step_delay_ms']` 같은 경로로 draft 를 안전하게 깊은 갱신.
  저장은 기존대로 전체 draft 를 PUT /settings (reload_ai 포함). i18n `settings.advanced`.

### 검증
- tsc EXIT 0 + electron-vite build 통과. **순수 프론트 — Python/core 무변경**(core 219/219 유지,
  api_server 0줄). 백엔드는 §47 의 GET/PUT /settings + test_218 이 이미 커버.
- **사용자 GUI 실측 필요**: 설정 다이얼로그 → "고급(전체 섹션)" 아래 각 섹션 펼쳐 값 편집 → 저장 →
  v2 와 공유되는 settings.json 반영, 재시작/재초기화 동작. 배열 필드 쉼표 편집.

### 남은 P1+ 백로그 (§47 표)
- #13 첨부 이미지(B, 캡처 백엔드 필요), #17 멀티탭, #19 온보딩, #21 시크릿 볼트, #22 녹화 review.

## 55. 2026-05-30 v3 패리티 백로그 P1 — 프로젝트 내보내기/가져오기 (#15)

**컨텍스트**: §54 에 이어 P1 #15. core `export_workflow`/`import_workflow` 존재(type A) —
엔드포인트 + Electron 네이티브 폴더 다이얼로그만 신설. core 0줄.

### 백엔드 (routes/sessions.py + deps Export/ImportRequest)
- `POST /sessions/{id}/export {output_dir}` → `export_workflow(id, target, settings)`. target =
  `output_dir/<안전한 세션제목>` (`_safe_dirname` 으로 파일명 불가 문자 치환, 중복 시 `_2.._N`
  suffix 로 clobber 회피). settings.json 의 output_project 설정 적용. 결과 = main.py/requirements/
  README/run.bat/session.json/captures/scripts. 없는 세션 404, output_dir 비-디렉터리 400, 백엔드
  미지원 501.
- `POST /sessions/import {source_dir, new_title?}` → `import_workflow`. `session.json` 없으면 400,
  새 UUID 로 복사돼 충돌 없음. 백엔드 미지원 501. (라우트 `/sessions/import` 는 정적 경로라
  `/sessions/{id}/...` 와 충돌 없음.)

### Electron (네이티브 폴더 선택 + Explorer 열기)
- main: `fs:pick-directory` (dialog.showOpenDialog openDirectory → 경로|null) + `fs:reveal`
  (shell.showItemInFolder). preload `pickDirectory()`/`revealPath(p)`. env.d.ts OhdoBridge 타입.

### 프론트
- client `exportSession(id, dir)`/`importSession(dir)`.
- SessionSidebar: 헤더에 import(Upload) 버튼(+ 옆), 각 세션 행에 export(Download) 버튼.
  export = pickDirectory → exportSession → toast + revealPath(생성 폴더). import = pickDirectory →
  importSession → 새 세션 선택. busyId 에 export 포함.
- CommandPalette: "현재 세션 내보내기"(선택 시) + "프로젝트 가져오기"(항상) 명령.
- i18n `session.export*/import*` + `palette.exportSession/importProject`.

### 검증
- test_224 (+1, core **219/219**): 라우트 노출 + AppService 위임 + **export→import 라운드트립**
  (export 폴더에 session.json/main.py 생성 → import 새 session_id + steps 보존) + 에러 경로
  (없는 output_dir 400 / session.json 없는 import 400). 격리 tempfile. ruff/tsc/build 그린.
  core/PySide6/ui_v2/main.py 0줄.
- **사용자 GUI 실측 필요**: export 버튼 → 폴더 선택 → Explorer 에 결과 폴더 열림(main.py 등),
  import 버튼 → export 폴더 선택 → 새 세션 생성·선택. 네이티브 다이얼로그(dev/packaged 양쪽).

### 남은 P1+ 백로그 (§47 표)
- #13 첨부 이미지(B, 캡처 백엔드 필요), #17 멀티탭, #19 온보딩, #20 설정 확장,
  #21 시크릿 볼트, #22 녹화 review.

## 54. 2026-05-30 v3 패리티 백로그 P1 — 환경 점검 (#18)

**컨텍스트**: §53 에 이어 P1 #18. 읽기 전용이라 GUI/파일 다이얼로그 의존 없이 깔끔. core 의
환경 스캐너는 AppService 에 노출돼있지 않아 **공개 get_scanner() 를 직접 호출**(core 0줄 — 읽기만).

### 구현
- **`api_server/routes/environment.py`** (신규): `GET /environment` → `get_scanner().full_scan()`
  결과 그대로 (success/system_info/python_path/python_version/available_pythons/packages
  (required·optional·all_required_installed)/cli_ai/scan_time). full_scan 은 subprocess 다수
  (패키지 import 확인 + CLI `--version`)라 수초 소요 → FastAPI sync 라 threadpool 실행(이벤트
  루프 비차단), 프런트 on-demand. server.py include_router.
- **프론트**: client `fetchEnvironment` + 타입(EnvironmentInfo/PackageStatus/CliAiStatus).
  `components/EnvironmentDialog.tsx` — 시스템/ CLI AI/ 패키지(필수·선택, 버전·누락 배지) 섹션,
  staleTime Infinity + 재검사 버튼(무거운 스캔 자동 refetch 금지), 로딩 스피너.
  uiStore `envOpen`/`setEnvOpen`(설정과 동일 패턴). SessionSidebar 푸터 Activity 버튼 +
  CommandPalette "환경 점검" 명령. i18n `env.*` + `palette.environment`.

### 검증
- test_223 (+1, core **218/218**): 라우트 노출 + EnvironmentScanner 공개 API(full_scan) +
  가벼운 get_system_info(subprocess 없음, os/python_version 키). **full_scan 자체는 subprocess
  다수라 테스트 미호출**(느림/플래키 회피). ruff/tsc/build 그린. core/PySide6/ui_v2 0줄.
- **사용자 GUI 실측 필요**: 사이드바 Activity·팔레트로 다이얼로그 열기 → 수초 후 Python/패키지/
  CLI AI 상태 표시, 재검사 버튼. (cli_ai 는 default 'agy' 명령 기준 — 설정 엔진 명령과 다를 수 있음.)

### 남은 P1+ 백로그 (§47 표)
- #13 첨부 이미지(B, 캡처 백엔드 필요), #15 내보내기/가져오기(A, Electron 파일 다이얼로그 필요),
  #17 멀티탭, #19 온보딩, #20 설정 확장, #21 시크릿 볼트, #22 녹화 review.

## 53. 2026-05-30 v3 패리티 백로그 P1 — AI 엔진 퀵스위치 (#14)

**컨텍스트**: §52 에 이어 P1 #14. 설정 다이얼로그(전체 편집) 없이 헤더에서 AI 엔진을 빠르게
전환. core/AppService 의 기존 메서드만 호출 — core 0줄.

### 설계 (런타임 전환 + settings.json 영속)
- core `AppService.switch_ai_engine` 은 **런타임 `_current_name` 만** 변경(영속 X). 단독 사용 시
  설정 다이얼로그(GET /settings 의 `ai.selected`)와 불일치 + 재시작 시 원복.
- → 퀵스위치 엔드포인트가 switch 후 **settings.json 의 `ai.selected` 도 갱신**(best-effort)해
  두 UI 일관 + 재시작 유지. v2 와 같은 파일 공유라 v2 에도 반영. reload_ai 풀 재초기화는 불필요
  (switch_engine 이 런타임 즉시 반영).

### 구현
- **`api_server/routes/ai.py`** (신규): `GET /ai/engines` → `{engines: list_ai_engines(),
  current: get_ai_engine_name()}` (AI 미구성 시 빈 목록+None). `POST /ai/engine {name}` →
  `switch_ai_engine`(RuntimeError→503 미구성 / ValueError→400 미존재) + settings.json `ai.selected`
  병합 저장(실패해도 런타임 전환은 유효 → persist_error 동봉). deps `SwitchEngineRequest`.
  server.py `include_router(ai.router)`.
- **프론트**: client `fetchAiEngines`/`switchAiEngine`. `components/EngineSwitcher.tsx` — 헤더
  드롭다운(display_name, 미가용 표시), 전환 시 toast + ["aiEngines"]/["settings"] invalidate.
  ChatPanel 헤더 좌측에 배치(녹화 중엔 혼잡 줄이려 숨김). i18n `engine.*`.

### 검증
- test_222 (+1, core **217/217**): 라우트 노출 + AppService 위임 메서드 + GET 동작 + 빈 이름 400 +
  알 수 없는 엔진 400/503. **POST 성공 경로는 실 config/settings.json 변조하므로 미테스트**
  (persist 이전 실패 경로만 — 테스트가 repo 설정 안 건드림 확인). ruff/tsc/build 그린. core/PySide6 0줄.
- **사용자 GUI 실측 필요**: 헤더 드롭다운으로 엔진 전환 → toast → 설정 다이얼로그에도 같은 엔진
  반영, 재시작 후 유지, 실제 생성 시 전환된 엔진 사용.

### 남은 P1+ 백로그 (§47 표)
- #13 첨부 이미지(B, 캡처 백엔드 필요), #15 내보내기/가져오기, #17 멀티탭, #18 env scanner,
  #19 온보딩, #20 설정 확장, #21 시크릿 볼트, #22 녹화 review.

## 52. 2026-05-30 v3 패리티 백로그 P1 — 세션 복제 (#12)

**컨텍스트**: §50 에서 "core 에 duplicate_session 없음 → §47 의 'A' 분류 부정확"으로 기록했던
항목. 사용자 "다음 진행" 으로 착수. **core 0줄 유지 위해 api_server 가 공개 API 조합으로 구현**.

### 설계 (왜 api_server 에서)
core/AppService 에 복제 메서드가 없고, core 는 불변 원칙. 세션 데이터 모델(`session.steps` =
dict 리스트, `create_session`/`save_session` 공개)만으로 충분히 복제 가능 → 신규 메서드 없이
api_server 라우트에서 조합.

### 구현
- **백엔드** `routes/sessions.py` `POST /sessions/{id}/duplicate` (+ deps `DuplicateSessionRequest`
  optional title): `get_session(원본)` → `create_session(title|fallback, project_type, description)`
  → `dup.steps = deepcopy(src.steps)` + `dup.workflow_metadata = deepcopy(...)` → `save_session`.
  title 미지정 시 `"<원본> (copy)"` fallback(프론트가 locale 별 제목 전달). 없는 세션 404.
- **`_copy_session_assets`** (sessions.py 헬퍼): `service._repo.manager.sessions_dir` 로 원본의
  `captures/`·`scripts/` 폴더를 복제본 폴더로 **best-effort** shutil.copytree(실패 무시 — 데이터
  복제는 save_session 으로 이미 완료, 첨부 이미지가 원본 폴더에만 남아 원본 삭제 시 깨지는 것 보강).
  파일 기반 저장소가 아니면(`manager` 없음) 조용히 skip.
- **프론트**: client `duplicateSession(id, title?)`. SessionSidebar 행에 Copy 버튼 + duplicateMut
  (성공 시 새 세션 선택). CommandPalette 에 "현재 세션 복제" 명령. i18n `session.duplicate/
  duplicated/duplicateFailed/copySuffix` + `palette.duplicateSession`.

### 검증
- test_221 (+1, core **216/216**): 라우트 노출 + 원본 step 1개 준비 → duplicate 200 → 새 session_id
  + `(copy)` fallback + steps/generated_code 보존 + **독립성**(원본에 step 추가해도 복제본 불변) + 404.
  격리된 tempfile data_dir 사용(실데이터 무오염). ruff/tsc/build 그린. core/PySide6/ui_v2 0줄.
- **사용자 GUI 실측 필요**: 사이드바 복제 버튼·팔레트 명령으로 새 세션 생성, steps/코드 그대로,
  캡처 이미지(있으면) 표시.

### 남은 P1+ 백로그 (§47 표)
- #13 첨부 이미지(B, 캡처 백엔드 필요), #14 AI 엔진/모델 퀵스위치(설정화면 일부 커버),
  #15 내보내기/가져오기, #17 멀티탭, #18 env scanner, #19 온보딩, #20 설정 확장,
  #21 시크릿 볼트, #22 녹화 review.

## 51. 2026-05-30 v3 패리티 백로그 P1 — 커맨드 팔레트 (Ctrl+K)

**컨텍스트**: §50 에 이어 P1 백로그 #16. 사용자 선택: 순수 UI(백엔드 불필요, 위험 낮고
UX 체감 큼). 기존 스토어/액션 재사용으로 core/api_server **0줄**.

### 구현
- **`components/CommandPalette.tsx`** (신규): Ctrl+K 로 여는 검색형 명령 목록.
  - 입력 + 필터(label 부분일치) + ↑↓ 이동 + Enter 실행 + Esc 닫기(stopPropagation 으로
    전역 Esc=cancelPick 차단) + 클릭/마우스호버 선택.
  - **컨텍스트별 명령 구성**: 새 세션(항상) / 전체 실행·중단(세션 선택+녹화중 아님) /
    녹화 시작·중단(세션 선택+실행중 아님) / 요소 선택(세션 선택+녹화중 아님) / 설정 열기 /
    테마 전환 / 언어 전환(KO·EN) / 다른 세션으로 이동(목록). 실행 시 `close()` 먼저 → 동작.
- **`hooks/useShortcuts.ts`**: `onCommandPalette` 추가 — Ctrl/Cmd+K 는 **입력 포커스와 무관**하게
  동작(Escape 처리 직후, inEditable 가드 이전에 가로채 preventDefault+토글). 나머지(R/N)는 종전대로
  편집 중 무시.
- **`store/uiStore.ts`**: `paletteOpen`/`togglePalette`/`setPaletteOpen` + `settingsOpen`/
  `setSettingsOpen` 추가. 설정 다이얼로그 open 상태를 SessionSidebar 로컬 useState 에서 store 로
  **lift** — 팔레트의 "설정 열기"와 사이드바 기어가 공용으로 토글.
- **`App.tsx`**: useShortcuts onCommandPalette→togglePalette, `<CommandPalette/>` 렌더.
- **`SessionSidebar.tsx`**: 로컬 settingsOpen → store 사용(동작 동일).
- **i18n**: en/ko `palette.*` 카탈로그(placeholder/empty/명령 라벨 11종). Catalog 타입 파리티 강제.

### 검증
- tsc EXIT 0 + electron-vite build(3096 modules) 통과. **순수 프론트 — Python/core 무변경**
  (core 215/215 유지, api_server 0줄). PySide6/ui_v2/main.py 0줄.
- **사용자 GUI 실측 필요**: Ctrl+K 토글(입력 중 포함), 검색·↑↓·Enter, 각 명령 동작
  (특히 녹화·요소선택은 메인 minimize/overlay 연계), Esc 가 팔레트만 닫고 picker 취소와 안 충돌.

### 남은 P1+ 백로그 (§47 표)
- #12 세션 복제(core 에 duplicate_session 없음 — 신규 로직 필요), #13 첨부 이미지(B),
  #14 AI 엔진/모델 퀵스위치(설정화면이 일부 커버), #15·#17~#22.

## 50. 2026-05-30 v3 패리티 백로그 P1 잇기 — 코드 복사 + Library/Initial 블록 카드

**컨텍스트**: §47 패리티 백로그의 (A)유형 P0 + 설정화면은 §47 에서 완료. 이번엔 P1 중 가장
명확한 추가형(core 0줄, 기존 메서드/엔드포인트만 신설) 2개를 잇기. 사용자 결정: 트랙 #2(패리티).

### 구현 (#10 코드 복사 버튼 — UI, 매우쉬움)
- **CodeViewer 헤더에 Copy 버튼**: `navigator.clipboard.writeText(editing ? draft : code)` → 토스트.
  `!!code` 일 때 항상 노출(블록 read-only 포함). 편집 컨트롤과 동일 우측 영역으로 묶음.
  순수 프론트(백엔드/엔드포인트 무관). i18n: `code.copy/copied/copyFailed`.

### 구현 (#11 Library/Initial 블록 카드 — A유형, 쉬움)
- **백엔드**: `GET /sessions/{id}/blocks` (routes/sessions.py) → `{library_code, initial_code}`.
  `AppService.get_library_block_code` / `get_initial_block_code` 위임(둘 다 기존 façade — core 0줄).
  없는 세션 404. Library=imports+헬퍼 집계, Initial=모듈 레벨 setup (v2 블록 카드와 동일 추출).
- **client.ts**: `fetchBlocks(sessionId)` + `SessionBlocks` 타입.
- **uiStore**: `selectedBlock: "library"|"initial"|null` 추가. step/block 선택 **상호 배타**
  (selectStep→block null, selectBlock→step null, selectSession→둘 다 null).
- **ChatPanel**: step 목록 위에 `BlockCard` 2개 (Library/Cog 아이콘). 각 블록 코드가
  **비어있지 않을 때만** 노출(step 0개면 숨김). blocks 쿼리 키 = `["blocks", id, session.updated_at]`
  → step 변경 시 updated_at 갱신으로 자동 refetch(invalidate 사이트 안 건드림). CodePane 과 동일 키 dedup.
- **CodePane(App.tsx)**: selectedBlock 우선 → 해당 코드를 `stepId=null` 로 CodeViewer 에 넘겨
  read-only 강제(CodeViewer canEdit = stepId!=null && code). title = LIBRARY/INITIAL.

### 검증
- core **215/215** (test_220 +1 — blocks 라우트 노출 + AppService 위임 메서드 가드 + 없는 세션 404).
- tsc EXIT 0 + electron-vite build 통과. ruff All passed. core/PySide6/ui_v2/main.py **0줄**.
- **사용자 GUI 실측 필요**: Copy 버튼 동작(클립보드 권한), Library/Initial 카드 표시·선택·read-only 코드,
  step 추가/재생성 후 블록 카드 자동 갱신.

### 남은 P1+ 백로그 (§47 표)
- #12 세션 복제(core 에 duplicate_session **없음** → §47 의 'A' 분류는 부정확, 신규 로직 필요),
  #13 첨부 이미지(B), #14 AI 엔진/모델 전환 UI(설정화면이 이미 engine select+save 로 커버 — 전용
  퀵스위치는 선택), #15~#22 (내보내기/커맨드팔레트/멀티탭/시크릿볼트/녹화 review 등).

## 49. 2026-05-30 element picker 풀 복원 — 투명 오버레이 + 실시간 하이라이트

**컨텍스트**: §48 절충안(클릭 시 캡처, 하이라이트 없음) 실측 후 사용자 결정: **(c) v2 처럼 풀 복원**(Electron 투명 오버레이 + 실시간 붉은 박스).

### 동작
1. picker 버튼 → main 이 **메인 윈도우 minimize** + **가상 데스크톱 전체를 덮는 투명 오버레이 창** 생성.
2. 오버레이는 ~30fps 로 `GET /pick/hover` 폴링(IPC 경유) → 커서 아래 element 에 **붉은 박스** 그림.
3. 사용자가 대상을 **클릭** → 전역 LL 후크(pick_pump)가 좌표 캡처(클릭 삼킴) → 오버레이 닫고 메인 윈도우 restore → element 첨부.
4. **Esc** → LL 키보드 후크가 취소.

### 핵심 기술 포인트
- **WS_EX_TRANSPARENT 로 오버레이 hit-test 제외**: Electron `setIgnoreMouseEvents(true)` 가 Windows 에서 WS_EX_TRANSPARENT 설정 → UIA `ElementFromPoint` 가 투명 오버레이를 건너뛰고 그 아래 **대상 앱 element** 반환(v2 가 풀던 문제를 동일 원리로). 클릭통과라 대상 앱이 클릭 받고 LL 후크가 캡처.
- **LL 후크 타임아웃 회피(§42)**: 무거운 UIA EFP 는 후크 proc 이 아니라 **펌프 루프**에서 ~50ms throttle. 후크 proc 은 클릭/ESC 만(즉시 반환). `/pick/hover` 는 펌프가 저장한 `_hover_rect` 만 읽음(동시성 안전 — UIA 단일 스레드).
- **멀티모니터/고DPI 좌표 변환**: Python 은 물리 픽셀 rect 반환 → main 이 `screen.screenToDipPoint` 로 두 모서리를 DIP 변환 → 오버레이 창 origin 빼서 로컬 CSS px. 모니터별 scaleFactor 달라도 정확.

### 변경 파일
- **api_server**: pick_pump.py(`_hover_rect` + 펌프 루프 샘플링 + `get_hover_rect`, timeout 20→60s) / routes/pick.py(`GET /pick/hover`). core 0줄.
- **desktop_v3**: electron.vite.config(overlay 멀티 엔트리) + overlay.html/overlay.ts(투명 오버레이 렌더러, vanilla) + preload(ohdoPick.hover + start/stopPickOverlay) + main/index.ts(createPickOverlay/closePickOverlay + physicalRectToOverlayCss + pick IPC + main minimize/restore) + pickStore(오버레이 흐름) + vite-env.d.ts(타입).

### 검증 / 미검증
- tsc+build 그린(overlay.html 엔트리 out/renderer/ 확인). test_219 에 /pick/hover + get_hover_rect 가드. core 214/214, ruff. core/PySide6 0줄.
- **사용자 실측 필요**: WS_EX_TRANSPARENT 로 EFP 가 오버레이를 실제로 건너뛰는지, DPI 변환 정확도, 멀티모니터, 하이라이트 부드러움(throttle ~50ms 캡처+30fps 폴링). 문제 시 fallback: EFP 직전 오버레이 hide 토글 또는 폴링 주기 조정.

### 후속 fix (사용자 실측 루프, 2026-05-30)
- **fix1 (7c134a2) — hover 박스 미표시**: `capture_element_at` 의 rect 는 `[l,t,r,b]` **리스트**인데 main physicalRectToOverlayCss 가 `rect.left` 키로 접근 → NaN → 미표시. 펌프 루프에서 `{left,top,right,bottom}` dict 로 정규화. **결과: 일반 창에서 붉은 박스 정상 표시 (사용자 확인).**
- **fix2 (7d11d76) + fix3 (b5abb1c) — 작업표시줄 위 z-order**: Electron setAlwaysOnTop/moveTop 은 작업표시줄(Shell_TrayWnd) 특수 topmost 못 이김 → Python ctypes `SetWindowPos(HWND_TOPMOST)` 로 전환(오버레이 HWND 를 POST /pick/overlay 로 등록 → pick_pump 펌프 루프가 200ms 재적용). fix3 에서 SetWindowPos.argtypes/restype 명시(미지정 시 x64 HWND 32-bit 절단으로 조용히 실패 — v2 _ensure_user32_argtypes 와 동일). Electron moveTop 타이머 제거.
  - **⚠️ 미해결**: fix3(argtypes 보강)으로 v2 와 동일 호출이 됐는데도 **사용자 실측상 작업표시줄 위 element 의 붉은 박스가 여전히 작업표시줄 뒤로 가려짐**. 일반 창은 OK. 사용자 지시로 **보류**. 다음 후보: (a) 오버레이를 작업표시줄 영역만 별도 layered child 로, (b) hover rect 가 작업표시줄 영역과 겹칠 때 박스를 별도 topmost 미니 창으로, (c) Shell_TrayWnd 위 z-order 는 OS 정책상 일반 앱 불가 가능성 → DPI/좌표 문제인지 재확인(작업표시줄 자체가 고정 위치라 rect 변환 오차 의심).
- **fix4 (b5abb1c) — 녹화 시 메인 최소화**: record:minimize/restore IPC + preload minimizeForRecord/restoreFromRecord + recordStore start 시 최소화 / stopCommit·cancel 시 복원 (picker 와 동일 UX). 사용자 요청.
- **fix6 (627d1e7) — picker 마우스 끊김 + F3 일시정지**: (1) 마우스 느려짐 1차 진단 = LL 후크 스레드에서 UIA EFP 를 직접 호출 → UIA 를 별도 워커 스레드로 분리(§42/PR-17 drain 패턴), 후크 스레드는 펌프만. (2) F3 일시정지(v2 동등) — paused 중 클릭 통과(메뉴 펼침)+하이라이트 끔, /pick/hover 가 paused 반환→오버레이 배너 전환. is_paused().
- **fix7 (79e57c8) — picker 마우스 완전 정지(GIL) 해결**: fix6 워커 분리 후 사용자 실측 = 포인터 **전혀** 안 움직임. 진짜 원인: 워커가 EFP(COM)를 50ms 간격 거의 연속 호출 → **EFP 가 GIL 점유** → LL 마우스 후크 콜백(Python)이 GIL 굶음 → 시스템 전역 마우스 멈춤(키보드는 빈도 낮아 정상). 해결: **hover EFP 디바운스** — 커서 이동 중엔 EFP 스킵(sleep 으로 GIL 양보→후크 부드러움), 멈춘 새 위치에서만 1회 EFP→박스. **핵심 교훈: LL 후크 활성 중엔 어느 스레드든 UIA/COM 을 고빈도로 돌리면 GIL 경쟁으로 마우스 멈춤. 디바운스(정지 시 1회)가 정석.**
- **fix8 (8f3a1c2) — 마우스 완전 정지 회귀 해결(단일 스레드 복귀)**: fix6 의 워커 스레드가 진짜 원인. WH_MOUSE_LL 후크 콜백이 후크 스레드에서 GIL 을 얻어야 하는데 워커가 EFP(COM)로 GIL 점유 → 후크 굶음 → 마우스 완전 정지. 워커 제거하고 7c134a2 의 단일 스레드 구조(후크+펌프+EFP 한 스레드)로 복귀 + 이동 중 EFP 스킵 디바운스 유지. **GIL 교훈 확정: 같은 프로세스 안에서 LL 후크와 UIA/COM 을 다른 스레드로 나눠도 GIL 때문에 소용없음 — 단일 스레드 + 디바운스가 정답.** core 214/214.
- **fix9 (진짜 원인, CallNextHookEx argtypes) — 마우스 정지 해결**: 사용자 터미널 로그로 확정 — _mouse_proc 의 CallNextHookEx 가 매 이동마다 ArgumentError(arg4 OverflowError: int too long)로 죽음. lParam(MSLLHOOKSTRUCT 포인터=x64 64-bit)을 argtypes 미지정 탓에 ctypes 가 32-bit int 로 좁히려다 실패 → 다음 후크로 마우스 이벤트 전달 안 됨 → 포인터 정지. **fix6~8 의 워커/GIL 진단은 전부 오진**. CallNextHookEx argtypes(HHOOK,int,WPARAM,LPARAM)/restype(LRESULT) 명시로 해결. SetWindowPos(fix3)와 동일 함정 — LL 후크 콜백에서 user32 함수 호출 시 argtypes 필수. core 214/214.
- **fix5 (bc9be03 + ec7ca6d) — 코드 실행 후 메인 윈도우 앞으로**: 실행된 코드가 대상 앱(메모장 등)을 띄워 포커스를 가져가므로 useExecution onDone/onError 에서 window:focus IPC 호출 → 메인 복원·focus(alwaysOnTop 잠깐 토글로 Windows foreground 제약 우회). bc9be03 은 IPC/preload/타입만, ec7ca6d 가 호출부 연결(anchor 불일치로 1차 누락).

## 48. 2026-05-30 element picker 절충안 — 클릭 시 캡처 (LL 후크, 하이라이트 없음)

**컨텍스트**: 사용자 질문 "v2 의 오버레이+붉은박스+클릭선택 picker 가 왜 v3 에서 3초 카운트다운으로 바뀌었나". 조사 결과: v2 picker 는 PySide6 QWidget(2321줄, 전체화면 투명 오버레이 + 실시간 EFP 하이라이트 + LL 클릭후크)이라 headless 브리지/Electron 으로 그대로 이식 불가 → Phase B(§40)에서 사용자가 "카운트다운 캡처"를 선택했던 것. 사용자 결정: **절충안(클릭 시 캡처, LL 후크만, 하이라이트 없음)으로 최소 개선 후 결과 보고 재결정**.

### 구현
- **`api_server/pick_pump.py`** (신규): `pick_on_click(timeout)` — 전역 WH_MOUSE_LL (+ WH_KEYBOARD_LL ESC) 설치 후 요청 스레드에서 직접 PeekMessage 펌프(§42 제약: 설치 스레드 펌프 필수). 첫 좌클릭 좌표 기록 + `return 1` 로 클릭 삼킴(대상 앱 미활성) → `capture_element_at` 동일 검출. `cancel_pick()`/`is_active()` + 모듈 lock(동시 1건). Windows ctypes 는 함수 내부 → 비-Windows import 안전.
- **`routes/pick.py`**: `POST /pick/click` (블록형 클릭 캡처) + `POST /pick/cancel`. 기존 `POST /pick`(즉시) 하위호환 유지.
- **desktop_v3**: pickStore 재작성(startPick() 인자 제거 + cancelPick), PickOverlay 상단 배너 힌트(카운트다운/하이라이트 제거, pointer-events-none), App onEscape→cancelPick, client.ts pickElementOnClick/cancelPick, i18n 힌트 갱신.

### 검증 / 한계
- test_219 (라우트 + pick_pump import 안전). core 214/214, ruff/tsc/build 그린. core 0줄. (커밋 2cb27f9 백엔드 + 570dccc 프론트 + e370891 tsc fix)
- **미해결(설계상, 실측 후 재결정)**: Electron 메인 윈도우가 안 숨으므로 대상 앱이 가려지면 클릭이 어려울 수 있음(전역 후크라 보이는 부분 클릭은 잡힘). 하이라이트 없음 = 클릭 전 어떤 요소가 잡힐지 미리보기 불가. 후속 선택지: (a) 그대로 / (b) 윈도우 자동 minimize / (c) Electron 투명 오버레이 + 실시간 하이라이트(풀 복원).

## 47. 2026-05-29 v3 ↔ v2 기능 패리티 백로그 + (A)유형 일괄 구현 착수

**컨텍스트**: 사용자 질문 "v2 기능/설정이 v3에 적용 안 된 건지 계획이 없는 건지 검토".
서브에이전트 3개로 v2(ui_v2/) / v3(desktop_v3/) / 브리지(api_server+AppService) 교차 조사.

### 격차의 두 층위
- **(A) 브리지 미노출**: `core/AppService` 에 메서드는 이미 있는데 `api_server` 가 엔드포인트를
  안 깐 것. 엔드포인트 + UI 만 붙이면 됨. **api_server 는 신규코드라 core 0줄 불변 원칙 유지.**
- **(B) 백엔드도 없음 / 순수 UI**: 새 설계 필요 (설정 read/write API, 시크릿 볼트 UI, 녹화 review 등).

### 패리티 백로그 (우선순위 = 체감/위험 종합)

| # | 기능 | v2 | v3 | 유형 | 난이도 | 우선 |
|--|------|----|----|------|--------|------|
| 1 | "from 실행" 버튼 | O | ws 만 | UI | 매우쉬움 | P0 |
| 2 | 검증경고 상세 보기 | O | 개수만 | UI | 매우쉬움 | P0 |
| 3 | required_packages 표시 | O | 미표시 | UI | 매우쉬움 | P0 |
| 4 | step 삭제 | O | X | A | 쉬움 | P0 |
| 5 | step 이동(up/down) | O | X | A | 쉬움 | P0 |
| 6 | step 삽입 | O | X | A | 쉬움 | P0 |
| 7 | step 재생성(regenerate) | O | X | A | 쉬움 | P0 |
| 8 | 세션 삭제 | O | X | A | 쉬움 | P0 |
| 9 | 세션 이름변경 | O | X | A | 쉬움 | P0 |
| 10 | 코드 복사 버튼 | O | X | UI | 매우쉬움 | P1 |
| 11 | Library/Initial 블록 카드 | O | X | A | 쉬움 | P1 |
| 12 | 세션 복제 | O | X | A | 쉬움 | P1 |
| 13 | 첨부 이미지(스크린 캡처) | O | picker만 | B | 중간 | P1 |
| 14 | AI 엔진/모델 전환 UI | O | X | A* | 중간 | P1 |
| 15 | 프로젝트 내보내기/가져오기 | O | X | A | 중간 | P2 |
| 16 | 커맨드 팔레트(Ctrl+K) | O | X | B | 중간 | P2 |
| 17 | 멀티 세션 탭 | O | 단일 | B | 중간 | P2 |
| 18 | 환경 점검(env scanner) | O | X | A | 중간 | P2 |
| 19 | 온보딩 위저드 | O | X | B | 중간 | P3 |
| 20 | **설정 화면 전체** | O(분산) | 테마/언어만 | B | 큼 | P1 |
| 21 | **시크릿 볼트(@자동완성/마스킹)** | O ADR0003 | X | B | 큼 | P2 |
| 22 | **녹화 review 다이얼로그** | O | stop=즉시 commit | B | 큼 | P2 |

`A*` = AppService 에 `list_ai_engines()`/`switch_ai_engine()` 는 있으나 런타임 전환 시
세션별 영향/재초기화 고려 필요.

### 설정 관점 (가장 큰 구멍)
v2 가 다루는 `config/default_settings.json` 섹션(ai/image/recognition/execution/ui/
output_project/logging/element_picker) 중 **v3 에서 만질 수 있는 건 테마/언어 2개뿐**.
나머지는 브리지에 settings read/write 엔드포인트가 없어 파일 직접 수정 + 재시작만 가능.

### 진행 순서 (사용자 결정)
1. (이 문서) 백로그 문서화
2. **(A)유형 일괄 구현** = 백로그 #1,2,3,4,5,6,7,8,9 (P0) → handoff 후속 절
3. **설정 화면** = 백로그 #20, 브리지 settings GET/PUT 부터 → handoff 후속 절

### 구현 완료 (동일 세션)
- **(A)유형 일괄** (커밋 9e30aff 백엔드/4d8f9da 프론트/ce1f9e3 README): 브리지 6개 엔드포인트 (DELETE/PATCH sessions, DELETE/move/insert/regenerate steps) + StepCard 액션 툴바 (run/from/regenerate/up/down/insert/delete + 선택 시 경고상세/required_packages) + SessionRow rename/delete. 모두 기존 AppService 메서드 위임 (core 0줄). 재생성은 generate_step replaces_step_id 활용(in-place).
- **설정 화면** (커밋 e29eef3 백엔드/0a2c0c2 UI): GET/PUT /settings (config/settings.json read/write, default 병합, 저장 시 reload_ai 즉시 반영, v2 와 파일 공유) + 사이드바 기어 → SettingsDialog (엔진 선택 + config 제네릭 편집, api_key 마스킹).
- 검증: core 213/213 (test_217 패리티 라우트 + test_218 settings), ruff/tsc/build 그린. 남은 백로그: P1+ (#10~22 — 설정 확장/시크릿 볼트/녹화 review/멀티탭 등).

## 46. 2026-05-29 Phase E — electron-builder 배포 셋업 (Python freeze 동봉, 설정+문서)

**컨텍스트**: 사용자 순서 #3 (마지막). 사용자 결정: **설정/문서만, freeze 는 사용자 머신**.

### 동봉 모델
설치본 = Electron 앱 + frozen Python 브리지. Python 미설치 PC 대응 위해 `api_server`+`core` 를
PyInstaller onedir 로 freeze → electron-builder `extraResources` 로 동봉 (`resources/pybridge/`).

### 변경
- **`desktop_v3/src/main/index.ts`**: `pythonExecutable()` -> **`bridgeCommand(port)`** 로 교체.
  분기: packaged(`app.isPackaged`) -> `resources/pybridge/ohdo-bridge.exe --port` / dev -> `.venv python -m api_server` / `OHDO_PYTHON` env override. 빌드 5.25->6.92kB.
- **`desktop_v3/package.json`**: `electron-builder` devDep + `dist`/`dist:dir` 스크립트 + `build` 블록 (appId ai.ohdo.desktop, win nsis x64, extraResources build/pybridge->pybridge, nsis allowToChangeInstallationDirectory).
- **`desktop_v3/build/bridge_entry.py`**: PyInstaller entry (api_server.__main__.main 호출).
- **`desktop_v3/build/ohdo-bridge.spec`**: onedir spec. hiddenimports (uvicorn/websockets/pywinauto/uiautomation/comtypes/win32*/pywinpty/pyautogui/mss/PIL/cv2/keyring/pydantic 등) + collect_submodules(comtypes) + datas(config/, core/locale/) + excludes(PySide6/PyQt6/tkinter). name=ohdo-bridge (main 이 기대하는 exe 이름), console=True (READY 마커 stdout).
- **`.gitignore`**: release/ + build/pybridge/ + dist|build/ohdo-bridge/ ignore. 단 `desktop_v3/build/{bridge_entry.py,ohdo-bridge.spec}` 는 negation 으로 커밋 (최상단 `build/` 광범위 ignore 예외).

### 빌드 절차 (사용자 Windows 머신, README 배포 섹션에 상세)
1. 루트에서 `uv run pyinstaller desktop_v3/build/ohdo-bridge.spec --noconfirm` -> `dist/ohdo-bridge/`.
2. `dist/ohdo-bridge` -> `desktop_v3/build/pybridge/` 복사.
3. `cd desktop_v3 && npm run dist` -> `release/ohdo-<ver>-setup.exe`.

### 미검증 (사용자 실측 필요)
- 이 개발 환경은 GUI/설치 테스트 머신이 아님 -> freeze 실행/hidden-import 완전성/설치본 동작 미검증.
- PyInstaller hidden-import 누락 시 frozen exe ImportError -> `ohdo-bridge.exe --port 9000` 직접 실행해 콘솔 확인 후 spec 보강. 코드 서명/자동 업데이트 미구성 (후속).
- tsc EXIT 0 + electron-vite build 통과 (main 분기 컴파일 확인). core 211 불변.

### 다음
사용자 순서 #1(스트리밍)·#2(i18n+애니메이션)·#3(배포) 3개 트랙 모두 셋업 완료. 남은 것은 사용자 GUI/설치 실측 + (보류했던) 녹화 review, 코드 서명 등.

## 45. 2026-05-29 Phase D — i18n (react-i18next) + 핵심 애니메이션 (desktop_v3 전용)

**컨텍스트**: 사용자 순서 #2. 사용자 결정: i18next + **신규 desktop_v3 카탈로그** (core/locale 키는 PySide6 기준이라 재사용률 낮음) + **핵심 트랜지션만**.

### i18n
- `i18next` + `react-i18next` 도입. `i18n/index.ts` — init + 언어 결정 (localStorage `ohdo.lang` -> navigator.language -> en) + `setLang`/`currentLang`.
- `i18n/locales/{ko,en}.ts` — desktop_v3 전용 카탈로그 (TS 객체, `Catalog` 타입으로 en==ko 키 파리티 컴파일 타임 강제). main.tsx 에서 App 보다 먼저 import.
- UI 한국어 전부 t()/i18n.t 전환: 컴포넌트(App/SessionSidebar/PickOverlay/LogConsole/CodeViewer/ChatPanel/Toaster)는 `useTranslation`, 비컴포넌트(recordStore/pickStore/useExecution/client.ts/ws.ts)는 `i18n.t`. 남은 한국어는 주석뿐 (UI literal 0).
- **언어 토글**: 사이드바 footer Languages 아이콘 (테마 토글 옆). ko<->en 즉시 + 영속.

### 애니메이션 (tailwindcss-animate, §40 에서 이미 설치)
- PickOverlay `fade-in`, Toaster `slide-in-from-bottom`, LogConsole 펼침 `slide-in`. Framer Motion 미도입 (번들 절약).

### 검증
- tsc EXIT 0 + build 통과. core 211 불변 (Python 무관).
- 커밋 8ab7231 (17 files). ws.ts i18n + 문서는 후속 커밋.

### 다음 세션 출발점
1. (사용자) GUI 실측: 언어 토글 ko<->en / 시스템 locale 자동 / 애니메이션 체감.
2. 다음: **Phase E** electron-builder 배포 (Python 동봉).

## 44. 2026-05-29 AI 생성 진행상황 스트리밍 (WS /ws/generate, core 무수정) — test_211

**컨텍스트**: 동기 요청+로딩(스피너) 이던 AI 생성을 "살아있는" 피드백으로 개선. 사용자
결정: **진행상황 스트리밍 (core 0줄 수정)**.

### 설계 제약 (왜 토큰 스트리밍이 아닌가)
- core `BaseAIAdapter.generate()` 는 완성된 `AIResponse` 만 반환 — 토큰 스트리밍 인터페이스 없음.
- agy CLI 는 PTY 캡처라 CLI 종료 후에야 전체 출력 → 토큰 단위 스트리밍 구조적 불가.
- 진짜 토큰 스트리밍은 core/adapters 수정 필요 → §37~§43 의 "core 0줄 수정" 원칙 위배.
- → **타협**: 토큰 대신 `generate_step` 이 이미 emit 하는 `on_progress` 콜백
  ("프롬프트 구성 중…", "AI 호출 중 (프롬프트 N자)…")을 실시간 WS 전송. 모든 엔진 동일.

### 구현
- **`api_server/routes/generate.py`** (신규): `WS /ws/generate?token=&session_id=`. 첫 클라이언트
  메시지 = `{user_request, element_context?, is_browser_element?}` (요청이 길 수 있어 query 대신).
  서버가 `generate_step(..., on_progress=lambda m: emit(progress))` 를 task 로 실행 + queue 소비
  루프(execution WS 와 동일 패턴)로 WS 전송. 메시지: `progress` / `done`(success/step/session/
  description 또는 error) / `error`. AI 미구성·없는 세션 → error+close.
- server.py `include_router(generate.router)` 추가.
- **프런트**: `api/ws.ts` `generateStream(sessionId, req, pending, handlers)` (콜백형).
  ChatPanel genMut.mutationFn 을 POST(`generateStep`) → `generateStream` 을 Promise 로 감싼 형태로
  전환. `progress` state 를 로딩 영역에 라이브 표시. onSettled 로 clear. POST `/sessions/{id}/generate`
  는 그대로 유지 (제거 안 함 — 폴백/다른 용도).

### 검증
- WS 라우트 노출 + 없는 세션 error (TestClient). core 211/211 (test_211 +1) + ruff All passed.
- typecheck EXIT 0 + build 통과. core/PySide6 0줄 수정.

### 다음 세션 출발점
1. **사용자 GUI 실측**: 자연어 요청 → 로딩 영역에 "프롬프트 구성 중…" → "AI 호출 중 N자…" 순차 표시.
   (토큰 단위는 아님 — 진행 단계 표시.)
2. 다음: **Phase D** (i18n core/locale 재사용 + 애니메이션) → **Phase E** (electron-builder 배포).

## 43. 2026-05-29 api_server 리팩토링 — routes/ 모듈 분리 (기능 변화 0)

**컨텍스트**: §38~§42 누적으로 server.py 가 568줄로 비대 (create_app 단일 클로저에 13개
엔드포인트 + 헬퍼 전부). 이후 작업 기반 견고화를 위해 도메인별 분리. **엔드포인트/동작
100% 동일** — 순수 구조 리팩토링.

### 분리 결과
- **`api_server/deps.py`** (155줄, 신규) — 공용 헬퍼/스키마: `get_app_service(app)`,
  `require_token(request, ...)`, `get_kernel`/`drop_kernel`, `get_recording_controller`,
  `to_dict`/`step_result_dict`/`load_json`, 스키마(`CreateSessionRequest`/`GenerateRequest`/
  `UpdateStepRequest`), 경로 상수(`DEFAULT_DATA_DIR`/`CONFIG_DIR`). 상태는 `app.state` 경유.
- **`api_server/routes/`** (신규) — `health.py` / `sessions.py` (목록·상세·생성·generate) /
  `steps.py` (PUT 편집) / `pick.py` / `recording.py` (5개) / `execution.py` (WS). 각 `APIRouter`,
  `request.app.state` / `ws.app.state` 로 상태 접근 (클로저 → 표준 DI 패턴 전환).
- **`server.py`** 568→**55줄** — CORS + app.state 셋업 + `include_router` 6개만. 스키마 3종은
  `from api_server.deps import ...` 로 **하위호환 re-export** (test_209 의 `from api_server.server
  import GenerateRequest` 유지) + `__all__` 명시.

### 검증
- 라우트 parity: 13개 (GET /health·/sessions·/sessions/{id}, POST /sessions·generate·/pick·
  recording start/marker(GET status)/stop_commit/cancel, PUT steps, WS /ws/execute) — 분리 전후 동일.
- E2E (TestClient): health ok / 401 / 5 sessions / 7 steps / 404 / 녹화 가드 409·cancel /
  create / ws bad-session error — 모두 분리 전과 동일.
- core 210/210 (test_207~210 개별 통과) + ruff All passed. core/PySide6 0줄 수정.

### 다음 세션 출발점
1. (사용자 보류) 녹화 등 반복 실측 — 시간 내서 집중 테스트 예정.
2. 후보: AI 응답 스트리밍 (WS/SSE) / Phase D (i18n + 애니메이션) / Phase E (electron-builder 배포).

## 42. 2026-05-29 녹화 실제 캡처 fix — Windows 메시지 펌프 스레드 (RecordingController)

**컨텍스트**: §41 녹화를 사용자 실측 → "버튼 상태/녹화중 표시는 뜨는데 마우스·키보드
입력이 실제로 녹화 안 됨". 근본 원인: **§41 의 가정이 틀렸다.**

### 근본 원인
- `core/input_hooks.py` 는 LL 훅(WH_MOUSE_LL/WH_KEYBOARD_LL)을 `SetWindowsHookExW(..., 0)`
  으로 **호출 스레드**에 설치하고, **그 스레드에서 Windows 메시지 펌프가 돌아야** 훅 콜백이
  발화한다. **자체 펌프 스레드는 없다** (§41 오기재). 소스에도 host message loop 전제 주석.
- PySide 앱은 Qt 이벤트 루프가 펌프 → 동작. FastAPI 브리지는 uvicorn(asyncio)만 있고 메시지
  펌프가 없음 → 훅은 설치되나 콜백 0회 → 입력 0 캡처.

### fix — `api_server/recording_pump.py` (신규, core 무수정)
- `RecordingController` 가 **녹화 전용 데몬 스레드**를 소유. 그 스레드에서:
  1. `CoInitializeEx(APARTMENTTHREADED)` (UIA element 캡처 COM)
  2. `service.start_recording(target, element_capture_fn=capture_element_at)` — **이 스레드에 훅 설치**
  3. `PeekMessageW` 펌프 루프 (5ms) — **LL 훅 콜백이 비로소 발화**
  4. stop 신호 시 `stop_recording` — **같은 스레드에서 UnhookWindowsHookEx** (Windows 제약)
- Windows 는 SetWindowsHookEx / 펌프 / UnhookWindowsHookEx 가 동일 스레드일 것을 요구 →
  start~stop 전체를 이 스레드가 소유. commit(파일 I/O)은 엔드포인트 스레드.
- server.py: `app.state.recording_controller` + `_get_recording_controller()` lazy. 5개
  엔드포인트(start/status/marker/stop_commit/cancel)를 컨트롤러 경유로 재배선. marker 는
  `recorder.add_marker()` 가 lock 으로 thread-safe → 엔드포인트 스레드에서 직접 호출 OK.

### 검증 (E2E 실측)
- **엔드포인트 E2E**: start=200 → 키 6회 합성 입력 → `event_count=6` (이전 0 = 버그 재현·해결)
  → marker → 추가 입력 → stop_commit → **step_count=2** (marker 가 step 분리). ✅
- (주의) recorder 는 mouse **move 미기록**(click/scroll/키 입력만). 사용자 GUI 실측 시 클릭·타이핑 필요.
- core 210/210 + ruff All passed. 실제 캡처는 합성 입력이라 자동 스위트 미포함 (환경 의존).

### 다음 세션 출발점
1. **사용자 GUI 재실측**: 녹화 → 메모장 등에서 **클릭/타이핑** → 헤더 이벤트 수 증가 → 종료 → step 추가.
   (마우스 *이동*만으론 카운트 안 올라감 — 클릭/키 입력 필요.)
2. 녹화 review/편집 (stop→preview→edit→commit 분리), api_server routes/ 분리, AI 스트리밍, Phase D/E.

## 41. 2026-05-29 TS UI v3 #3 잔여 — 작업 녹화 lifecycle + Monaco 로컬 번들 fix (test_210)

> **정정 (§42)**: 아래 "InputHookManager 의 **자체 메시지 펌프 스레드**" 서술은 오기재.
> 실제로는 펌프가 없어 브리지에서 입력이 캡처되지 않았고, §42 의 RecordingController
> (전용 펌프 스레드)로 해결함.

**컨텍스트**: handoff §40 에서 미룬 녹화(recording) lifecycle 구현 + 사용자 실측 Monaco
"Loading" 멈춤 fix. 원칙 그대로 **core/ + PySide6 0줄 수정**.

### 녹화 lifecycle (REST + status polling)
- recorder 가 글로벌 WH_MOUSE_LL/WH_KEYBOARD_LL 훅을 설치하고 `InputHookManager` 의
  **자체 메시지 펌프 스레드**에서 콜백을 받으므로 FastAPI 브리지 프로세스에서도 동작.
- 이벤트가 서버에 누적되므로 WS 스트리밍 대신 **REST + status polling** (단순/견고):
  - `POST /sessions/{id}/recording/start` — `start_recording(target=id)`. 이미 녹화 중 409 / 없는 세션 404 / non-Windows 501.
  - `GET /recording/status` — `{is_recording, event_count}`. 프런트 1s polling.
  - `POST /recording/marker` — `recorder.add_marker()` (**인자 없음** — 현재 시점 경계). 미녹화 409.
  - `POST /sessions/{id}/recording/stop_commit {self_window_titles?}` — `stop_recording`(transform) + `commit_recording` → step 추가. 기본 self_window_titles=["ohdo"]. kernel 폐기.
  - `POST /recording/cancel` — stop + 결과 폐기.
  - **주의 (실측 버그 fix)**: AppService `is_recording` / `recording_event_count` 는 `@property` —
    `()` 붙이면 `TypeError: 'bool' object is not callable`. server.py 에서 괄호 없이 접근.
  - marker/cancel 은 AppService 가 공개 안 해 `service._recorder` 직접 접근 (읽기 — core 무수정).
- 프런트: `store/recordStore.ts` (start/marker/stopCommit/cancel + 1s polling), ChatPanel 헤더
  "녹화" 버튼 (항상) → 녹화 중엔 🔴녹화중·이벤트수 + 구분점(Flag) + 종료 + 취소. commit 후 세션 invalidate.

### Monaco "Loading" fix (§40 #2 후속 — 사용자 실측)
- 증상: step 클릭 시 코드뷰어 "Loading..." 멈춤. 원인: `@monaco-editor/react` 가 jsdelivr CDN
  에서 로드 → 렌더러 CSP 차단. fix: `monacoSetup.ts` `loader.config({ monaco })` 로 **로컬 번들** +
  `editor.worker?worker`, `main.tsx` 먼저 import, CSP 에 `worker-src/script-src 'self' blob:`.
  사용자 확인: "코드 이쁘게 잘 뜬다. IDE 처럼". 빌드에 monaco 언어별 청크 + 8MB main (디스크 로드).

### 검증 (모두 그린)
- **core 210/210** (209 + test_210) + scenarios 73 + recording_fixtures 2.
- 녹화 가드 실측 (TestClient): idle status 200 / 미녹화 marker·stop_commit 409 / cancel idle / 없는 세션 start 404.
  (실제 훅 설치 start→stop 은 글로벌 입력 훅이라 자동 테스트 제외 — 사용자 GUI 실측.)
- desktop_v3 typecheck EXIT 0 + build 통과. ruff All passed.

### 다음 세션 출발점
1. **사용자 GUI 실측**: 녹화 버튼 → 다른 앱(메모장 등) 조작 → 종료 → step 추가 확인. 구분점/취소 동작.
2. **녹화 review/편집** — 현재 stop_commit 이 transform 결과를 바로 commit (review dialog 없음).
   필요 시 stop → preview(steps) → 편집 → commit 분리 (v2 RecordingReviewDialog 대응).
3. **api_server `routes/` 분리** (server.py ~480줄) + AI 스트리밍 (WS/SSE) + Phase D(i18n/애니메이션)/E(배포).

## 40. 2026-05-29 TS UI v3 Phase B 확장 — 실행 WS + 코드 편집 + picker + polish (test_208/209)

**컨텍스트**: handoff §39 (Phase B 1차) 에 이어 사용자 요청 순서대로 4개 기능 구현.
원칙 그대로 **core/ + PySide6 0줄 수정**, api_server + desktop_v3 만 확장.

### #1 step 실행 + live 로그 (WebSocket)
- `api_server/server.py`: **`WS /ws/execute`** — `run_blocks` 를 executor 스레드에서 돌리고
  on_step_start/on_step_complete/on_log 콜백을 `loop.call_soon_threadsafe` 로 asyncio 큐에 넣어
  WS 로 스트리밍. 메시지 타입: `log` / `step_done` / `done` / `error`. 클라이언트 `stop` 수신 시
  `stop_blocks()` + kernel 폐기. mode = `all`/`from`/`single` (+step_id) — ui_v2 `_on_run_*` 매핑.
- 세션별 ExecutionKernel 캐시 (`app.state.kernels`) + lazy start + push_secrets (ui_v2 패턴).
- 프런트: `api/ws.ts` (토큰은 쿼리 파라미터 — 브라우저 WS 헤더 제약), `store/execStore.ts`,
  `hooks/useExecution.ts`, `components/LogConsole.tsx` (하단 접이식 터미널, 테마 무관 고정 다크).
  ChatPanel 헤더 "전체 실행"/"중단" + step 카드 hover ▶.

### #2 코드 편집·저장
- `api_server/server.py`: **`PUT /sessions/{id}/steps/{step_id}`** — `update_step` 위임.
  `generated_code` + `step_code` 동시 갱신 + `manually_edited=True` (실행이 편집본 반영) + 캐시 kernel 폐기.
- 프런트: `CodeViewer.tsx` Monaco read-only ↔ 편집 토글 + 저장(PUT)/취소. step 전환 시 편집 리셋.
- **후속 fix (사용자 실측)**: step 클릭 시 코드뷰어가 "Loading..." 에서 멈춤 — `@monaco-editor/react`
  가 기본 CDN(jsdelivr)에서 에디터를 받는데 렌더러 CSP(connect-src 'self'+localhost)가 차단.
  해결: `src/renderer/src/monacoSetup.ts` 에서 `loader.config({ monaco })` 로 **로컬 번들** 주입 +
  `editor.worker?worker` 등록, `main.tsx` 에서 App 보다 먼저 import. CSP 에 `worker-src 'self' blob:`
  + `script-src 'self' blob:` 추가. `monaco-editor` 직접 dep 등록. 빌드 2391 모듈(번들 ~5MB, 디스크 로드).

### #3 element picker (카운트다운 캡처 — 사용자 결정)
- `api_server/server.py`: **`POST /pick`** — `GetCursorPos` + `capture_element_at(x,y)` +
  `format_element_label` → element_context 문자열 반환 (Windows 전용, 그 외 501).
  `GenerateRequest` 에 `element_context` + `is_browser_element` 추가 → generate_step 전달.
- 프런트: `store/pickStore.ts` (3초 카운트다운 + cancel 토큰), `components/PickOverlay.tsx`
  (pointer-events-none 풀스크린 — 대상 앱 hover 가능), ChatPanel "요소 선택" 버튼 + 첨부 칩.
  **녹화 lifecycle 은 다음으로 미룸 (사용자 결정).**

### #4 polish
- **토스트**: `store/toastStore.ts` + `components/Toaster.tsx` (외부 의존 없이 zustand). save/generate/run/new-session 연결.
- **단축키**: `hooks/useShortcuts.ts` — Ctrl/Cmd+R 실행/중단, Ctrl/Cmd+N 새 세션, Esc picker 취소.
- **테마 토글**: `store/themeStore.ts` (dark/light, localStorage). Discord 표면색을 CSS 변수
  (RGB 채널 → 투명도 modifier 유지) 로 전환, `:root`=light / `.dark`=dark. 사이드바 footer 토글.

### 검증 (모두 그린)
- **core 209/209** (207 + test_208 + test_209) + scenarios 73 + recording_fixtures 2.
- WS 실측 (TestClient): 없는 세션 → error / 실제 single-step → `log…→step_done→done`.
- PUT step round-trip + 없는 step 404. /pick 200 + 키.
- desktop_v3 typecheck EXIT 0 + build 통과 (renderer ~856kB, 1846 모듈).
- ruff All checks passed. `uv sync` — websockets + httpx 추가.

### 다음 세션 출발점
1. **사용자 GUI 실측**: 실행(▶/전체 실행) → 콘솔 live 로그 / step 코드 편집·저장 / 요소 선택(3초) →
   다음 요청에 첨부 / 토스트·단축키·테마 토글 동작 확인.
2. **#3 잔여**: 녹화(recording) lifecycle — recorder 가 Windows 입력 훅 (자체 pump 스레드) 설치.
   WS `/ws/record` (start/stop/pause/marker + 이벤트 스트림) + commit → step 추가. AppService
   `start_recording`/`stop_recording`/`commit_recording` + `add_recording_listener` 재사용.
3. **api_server `routes/` 분리** (server.py 비대) + AI 스트리밍 (WS/SSE) 결정.

## 39. 2026-05-29 TS UI v3 Phase B 1차 증분 — AI 코드 생성 루프 + shadcn/ui + Monaco (test_207)

**컨텍스트**: handoff §38 (Phase A) 에 이어 Phase B 핵심 화면 MVP 의 **첫 의미 있는 증분**.
§37 검증 목표 "agy/openai_compat 로 코드 생성 -> 화면 표시" 를 달성. 사용자 결정:
풀 AI 생성 루프 + Monaco + shadcn/ui, **동기 요청 + 로딩** 방식 (agy CLI 는 PTY 캡처라
네이티브 토큰 스트리밍이 까다로움 — §36 / WS 스트리밍은 Phase B 후반/C 로 연기).

### 백엔드 (api_server) — core/ 무수정, 호출만
- `server.py` v0.1 -> **v0.2**:
  - `GET /sessions/{id}` — 세션 상세 (steps 직렬화 포함).
  - `POST /sessions` — 새 세션 생성 (`CreateSessionRequest`).
  - `POST /sessions/{id}/generate` — 자연어 -> `AppService.generate_step` (async) -> step 추가 + 갱신 세션 반환. AI 미구성 503 / 세션 없음 404 / AI 실패 시 `{success:false, error}`.
  - `get_app_service()` 가 `config/settings.json` (AI) + `config/prompts.json` (PromptBuilder) 로드 -> `create_default(settings)` + `reload_ai` + `set_prompt_builder`. (ui_v2 와 동일 패턴이나 ui_v2 import 는 PySide6 를 끌어오므로 core 만으로 재구성.)

### 프런트 (desktop_v3)
- **shadcn/ui** 도입: `components.json` + `lib/utils.ts` (cn) + `ui/{button,textarea,scroll-area}.tsx` (Radix Slot/ScrollArea + cva). Tailwind 에 CSS 변수 토큰 (Discord 다크 팔레트 매핑).
- **Monaco** (`@monaco-editor/react`): `CodeViewer.tsx` — step 코드 읽기 전용 표시 (vs-dark, python). Phase C 에서 편집+저장.
- **3-column 레이아웃**: `ServerRail` + `SessionSidebar` (목록 + `+` 새 세션 + 브리지 상태) + `ChatPanel` (steps 카드 + 자연어 입력 -> generate, 로딩 스피너, Enter 전송) + `CodePane` (선택 step Monaco). Zustand `uiStore` (selectedSessionId/selectedStepId), TanStack Query (`sessions`/`session/{id}`/`health` + mutation invalidate).
- 의존성 추가: `@monaco-editor/react`, `@radix-ui/react-{slot,scroll-area}`, `class-variance-authority`, `clsx`, `tailwind-merge`, `tailwindcss-animate`, `lucide-react`.

### 검증 (모두 그린)
- **core 207/207** (206 + test_207) + scenarios 73 + recording_fixtures 2.
- **api_server 실측**: /health v0.2.0, /sessions(5), /sessions/{id} (title+steps), 404, POST /sessions (생성) 모두 정상.
- **desktop_v3**: typecheck EXIT 0 + build 통과 (renderer 834kB, Monaco 포함 1839 모듈).
- **ruff** All checks passed.
- test_207: 신규 라우트 노출 + POST 메서드 + (TestClient 가능 시) 세션 상세 직렬화 + 404 + create round-trip.

### 위험 완화 확인
- `core/`, `ui/`, `ui_v2/`, `main.py` **0줄 수정** (git status invariant).
- AI 생성은 기존 `AppService.generate_step` 그대로 재사용 — v2 와 동일 코드 경로.

### 다음 세션 출발점
1. **사용자 GUI 실측** (필수): `cd desktop_v3 && npm run dev` -> 세션 선택/생성 -> 자연어 요청 -> 로딩 후 step 카드 + Monaco 코드 표시 확인. agy CLI 10~30초 소요 정상. 실패 시 채팅 하단 에러 배너 + `[py:err]` 콘솔.
2. **Phase B 잔여**: step 실행 (run) + live 로그 (WS) / 코드 편집+저장 (update_step) / element picker 트리거 / 녹화 lifecycle. 토스트/단축키/테마 토글.
3. **api_server 확장**: `routes/` 분리 + WebSocket (execution logs / AI streaming).
4. **미결정**: AI 스트리밍 WS vs SSE / 코드 편집 저장 시점(자동 vs 명시) / Monaco vs CodeMirror 최종.

## 38. 2026-05-29 TS UI v3 Phase A 셋업 완료 — api_server (FastAPI) + desktop_v3 (Electron+React) 보일러플레이트 (test_206)

**컨텍스트**: handoff §37 결정에 따라 TS UI v3 트랙 Phase A (셋업) 를 구현. Python core /
PySide6 v1+v2 **무수정** 원칙 준수 — 신규 디렉터리 2개만 추가.

### 신규 구조

- `api_server/` — FastAPI bridge (core/ 호출 전용, PySide6 비의존). `python -m api_server`.
  - `server.py` — `create_app(token, data_dir)`: GET /health (무인증) + GET /sessions (Bearer 토큰).
  - `__main__.py` — 포트 bind (요청 포트부터 +1 최대 10회 fallback) + stdout READY 마커 + uvicorn.
  - `__init__.py` — create_app re-export.
- `desktop_v3/` — Electron 38 + React 19 + TS 5 + Vite 6 + electron-vite + Tailwind + Zustand + TanStack Query.
  - `src/main/index.ts` — Python spawn + 포트/토큰/lifecycle + BrowserWindow.
  - `src/preload/index.ts` — contextBridge `window.ohdo.getApiInfo()`.
  - `src/renderer/src/{App.tsx, api/client.ts, store/uiStore.ts, env.d.ts, index.css, main.tsx}`.

### Open questions 결정 (handoff §37 끝 — 이번 세션 확정)

| 질문 | 결정 | 근거 |
|---|---|---|
| electron-vite 템플릿 vs 직접 | **직접 hand-author** | `create-electron-vite` 헤드리스 비대화형 불가. 직접이 완전 제어 |
| shadcn/ui 우선 컴포넌트 | **Phase B 로 연기** | Phase A 는 파이프라인 증명만. Tailwind 만 셋업 |
| API 토큰 | main 이 `randomBytes(32).hex` 생성 —> `OHDO_API_TOKEN` env 로 Python 주입 —> preload `getApiInfo()` 로 renderer 전달 | argv 노출 회피 |
| subprocess 종료 | `before-quit` + `window-all-closed` —> SIGTERM —> 5s 후 SIGKILL | §37 명시 |
| 포트 충돌 | main 이 빈 포트 probe (선호 8765, 점유 시 OS 임의) —> `--port` 전달. Python 이 실제 bind 포트를 stdout `OHDO_API_READY {json}` 로 보고 | Python 이 권위적 결정 |

### 통신 계약 (다음 세션 필독)

1. Electron main 이 빈 포트 + random 토큰 준비 —> `python -m api_server --port <p>` spawn (cwd=루트, `OHDO_API_TOKEN` env).
2. Python 이 소켓 bind —> uvicorn 에 전달 —> stdout 에 정확히 한 줄 `OHDO_API_READY {"port": <int>, "token": "<str>"}`.
3. main 이 그 줄 파싱 —> `{baseUrl, token}` 확정 —> `ipcMain.handle("ohdo:get-api-info")`.
4. renderer `api/client.ts` 가 `window.ohdo.getApiInfo()` 로 받아 `Authorization: Bearer <token>` 헤더로 fetch.
- `/health` 만 무인증 (부팅 readiness 폴링). override env: `OHDO_PYTHON`, `OHDO_PROJECT_ROOT`. 기본 Python: `..\.venv\Scripts\python.exe`.

### 검증 결과 (모두 그린)

- **core 206/206** (205 + test_206 신규) + scenarios 73/73 + recording_fixtures 2/2.
- **api_server 단독 실측** (spawn —> READY —> fetch): /health ok, /sessions 5건, 토큰 없으면 401, Bearer 토큰 200.
- **desktop_v3**: `npm install` (208 pkg) + `npm run typecheck` (tsc EXIT 0) + `npm run build` (main 5.25kB / preload 0.28kB / renderer 640kB) 통과.
- **ruff** check All passed. `uv sync` — fastapi 0.136.3 + uvicorn 0.48.0 설치.

### test_206 (회귀 가드) 6 단계
1. `api_server.create_app` 존재 + 호출 가능 (QApplication 불필요)
2. /health + /sessions 라우트 노출
3. 토큰이 `app.state.api_token` 반영
4. **격리 가드** — 서브프로세스에서 `import api_server` 후 `'PySide6' not in sys.modules`
5. `main.py` 소스에 `--ui` 분기 + `MainWindowV2` import 유지
6. `ui_v2.MainWindowV2` export 유지

### 위험 완화 확인
- `core/`, `ui/`, `ui_v2/`, `main.py` **0줄 수정** (git status 로 확인 — M 은 .gitignore/ROADMAP/pyproject/test_core/uv.lock 뿐).
- `python main.py --ui v2` 회귀 가드 test_206 자동화.
- node_modules/out/dist 는 `.gitignore`, `desktop_v3/package-lock.json` 만 커밋.

### 다음 세션 출발점 — Phase B (핵심 화면 MVP)
1. **GUI 실측 먼저** (사용자): `cd desktop_v3 && npm run dev` —> Electron 창에 세션 목록이 Python 브리지에서 떠야 함. 미동작 시 `[py]`/`[py:err]` 콘솔 로그 확인.
2. **Phase B**: Discord-like 3-column + 채팅 패널 (AI 스트리밍 WS) + Monaco 코드 뷰어 + shadcn/ui + 다크 테마.
3. **api_server 확장**: `routes/` 분리 (sessions/steps/ai/recording/picker/execution/settings) + WebSocket (recording events / execution logs / AI streaming). 현재는 server.py 단일 파일.

## 35. 2026-05-24 GUI 실측 자동화 인프라 1순위 — JSONL 픽스처 회귀 스위트

**컨텍스트**: 사용자 시간 제약 (직접 GUI 실측 어려움) 해결. PR-19i + PR-19m 활용 — **사용자 1회 실측 = 영구 회귀 테스트로 재활용**. 신규 transform 변경 시마다 자동으로 사용자 시나리오 검증.

### 핵심 인프라

**[tests/fixtures/recordings/](../tests/fixtures/recordings/)** — 픽스처 저장소:
- `<name>.jsonl` — raw events (PR-19i 가 commit 시 생성한 파일 그대로 복사)
- `<name>.expected.json` — sidecar assertions (loose, transform 변경 robust):
  ```json
  {
    "description": "...",
    "min_steps": 1, "max_steps": 10,
    "must_contain_in_any_code": ["pyautogui.write", ...],
    "must_have_destructive": true|false,
    "must_have_ime": true|false,
    "must_have_idle_gap": true|false
  }
  ```

**Synthetic 픽스처 2개 (사용자 입력 없이 통과 보장)**:
- `synthetic_smoke.jsonl` — 최소 (Edit click + 'hi' 입력) — pipeline 동작 확인
- `synthetic_comprehensive.jsonl` — Edit click + 한글 IME 'dks' + 6s idle gap + '닫기' Button destructive — PR-19c/h/k 동시 검증

**[tests/test_recording_fixtures.py](../tests/test_recording_fixtures.py)** — 신규 suite (`suite="recording_fixtures"`):
- `test_01_fixtures_smoke` — 모든 `.jsonl` glob → `replay_jsonl` 성공 + ≥1 step + 각 step `generated_code` non-empty
- `test_02_fixtures_assertions` — 각 sidecar 의 assertions 검증 (min/max_steps, must_contain, must_have_destructive/ime/idle_gap)

**[tests/test_runner.py](../tests/test_runner.py)** — `recording_fixtures` suite 등록 (argparse choices + suites_to_run 분기).

### 사용자 픽스처 추가 흐름 (시간 1분)

1. ohdo 에서 시나리오 녹화 → commit_recording → `data/sessions/<session_id>/raw_events_<rec_id>.jsonl` 자동 생성됨
2. 파일을 `tests/fixtures/recordings/<scenario_name>.jsonl` 로 복사
3. 같은 폴더에 `<scenario_name>.expected.json` sidecar 작성 (위 schema)
4. `python -m tests.test_runner --suite recording_fixtures` 실행 → 통과 확인

이후 transform / recorder 변경할 때마다 자동 회귀. **사용자 추가 시간 0**.

### 권장 첫 픽스처 시나리오 (사용자 1회 실측, 각 30초~1분)

- **메모장 기본 입력 + Ctrl+S** — `pyautogui.write` + `hotkey('ctrl', 's')` 검증
- **메모장 X 버튼** — `must_have_destructive: true` (PR-19h)
- **한글 IME 입력** — `must_have_ime: true` (PR-19k)
- **파일 더블 클릭** — `must_contain_in_any_code: ["pyautogui.doubleClick"]` (PR-19b)
- **5초+ 휴지 시나리오** — `must_have_idle_gap: true` (PR-19c)

### 검증 결과

- **recording_fixtures 2/2** + core 203/203 + scenarios 73/73 그린
- ruff All passed (I001 import order auto-fix 1건)

### 다음 세션 출발점 (2026-05-24 아홉 번째 작업 종료)

| 우선순위 | 항목 | 상태 |
|---|---|---|
| **P1** | **옵션 3 실증 재시도** | 사용자 실측 시 raw_events JSONL 자동 보존 → **fixture 로 복사하면 영구 회귀** (시간 0) |
| **P7** | F-6 잔여 — dedup vs 의도 보존 정책 | 사용자 결정 필요 |
| ~~P9~~ | ~~replay helper + CLI~~ | 완료 (PR-19m, test_202) |
| **P10** | IME 실제 텍스트 자동 캡처 | placeholder UX 검증 후 결정 |
| **P11** | review dialog "📂 JSONL 불러오기" UI | replay CLI 가치 확인 후 |
| **NEW** | **사용자 픽스처 5개 수집** | 위 권장 시나리오 5개 — 사용자 5분 투자, 영구 회귀 확보 |

**새 세션 진입 시**:
1. §35 + §34 + §33 읽기
2. 사용자에게 권장 시나리오 5개 녹화 요청 → `data/sessions/.../raw_events_*.jsonl` 파일 5개 받기
3. fixture 복사 + sidecar 작성 (Claude 가 자동 — 사용자 손 X) → 즉시 회귀 자산화
4. 이후 transform 변경 시마다 `recording_fixtures` suite 통과 = 사용자 의도 보존 검증
