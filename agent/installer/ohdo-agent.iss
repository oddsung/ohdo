; Inno Setup 6+ 스크립트 — ohdo Agent 인스톨러
;
; 컴파일:
;     1) https://jrsoftware.org/isinfo.php 에서 Inno Setup 6 설치
;     2) PowerShell: & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\ohdo-agent.iss
;
; 전제: `pyinstaller build.spec` 이 먼저 실행되어 dist\ohdo-agent\ 가 존재해야 함.

#define MyAppName "ohdo Agent"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "ohdo.ai"
#define MyAppURL "https://ohdo.ai"
#define MyAppExeName "ohdo-agent.exe"
#define BuildDir "..\dist\ohdo-agent"

[Setup]
AppId={{8F3C2F8B-5A47-4F2F-9A31-OHDO00000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\ohdo\agent
DefaultGroupName=ohdo
DisableDirPage=no
DisableProgramGroupPage=yes
OutputBaseFilename=ohdo-agent-setup-{#MyAppVersion}
OutputDir=..\dist-installer
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; 비관리자 설치 허용 — 트레이 앱은 사용자 세션에서 돌면 충분
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "startmenuicon"; Description: "시작 메뉴에 바로가기 만들기"; GroupDescription: "추가 아이콘:"; Flags: unchecked
Name: "autostart"; Description: "Windows 시작 시 자동 실행"; GroupDescription: "시작 프로그램:"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ohdo Agent"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\ohdo Agent 제거"; Filename: "{uninstallexe}"; Tasks: startmenuicon

[Registry]
; 자동 실행 (사용자별)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "ohdo-agent"; ValueData: """{app}\{#MyAppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "지금 ohdo Agent 실행"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 로그/캐시는 {userappdata}\ohdo 에 저장되며 제거 시 보존한다.
; 필요 시 사용자에게 옵션으로 삭제 UI 를 제공하는 것은 M1+ 에서.
Type: filesandordirs; Name: "{app}"
