; =====================================================================
;  SoloTalk Zhongkao - Inno Setup installer script
;  Run after build_nuitka.bat produces build\main.dist
;  Keep this ASCII-safe for the exe paths; Chinese display text only in
;  the [Setup]/AppName etc. values. File MUST be UTF-8 with BOM so Inno
;  renders Chinese correctly.
; =====================================================================

#define MyAppName "SoloTalk 江门中考版"
#define MyAppVersion "0.5"
#define MyAppPublisher "SoloTalk"
#define MyAppExeName "SoloTalkZhongKao.exe"

; 应用目录可由构建方覆盖：Nuitka 作业默认用 build\main.dist，
; PyInstaller 作业调用 ISCC 时用 /DSrcDir=<路径> 覆盖（见 #ifndef 守卫）
#ifndef SrcDir
  #define SrcDir "build\main.dist"
#endif

[Setup]
AppId={{B7D9E3A1-5C42-4F2E-84C0-3D9A21E8F0B4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer
OutputBaseFilename={#MyAppName}-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
DisableDirPage=auto
DisableProgramGroupPage=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\tts_cache"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent