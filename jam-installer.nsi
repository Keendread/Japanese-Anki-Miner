; NSIS Installer Script for JAM (Japanese Anki Miner)
; Build with: makensis jam-installer.nsi
; Download NSIS: https://nsis.sourceforge.io/

; Include modern UI
!include "MUI2.nsh"
!include "x64.nsh"

; ============================================================================
; GENERAL SETTINGS
; ============================================================================

Name "JAM - Japanese Anki Miner"
OutFile "dist\JAM-Installer.exe"
InstallDir "$PROGRAMFILES64\JAM"
InstallDirRegKey HKCU "Software\JAM" "InstallDir"

RequestExecutionLevel user
ShowInstDetails show
ShowUninstDetails show

; ============================================================================
; UI SETTINGS
; ============================================================================

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ============================================================================
; INSTALLATION SECTION
; ============================================================================

Section "JAM Application"
    SetOutPath "$INSTDIR"
    
    ; Copy JAM executable and dependencies
    File /r "dist\JAM\*.*"
    
    ; Create Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\JAM"
    CreateShortcut "$SMPROGRAMS\JAM\JAM.lnk" "$INSTDIR\JAM.exe" "" "$INSTDIR\JAM.exe" 0
    CreateShortcut "$SMPROGRAMS\JAM\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
    
    ; Create Desktop shortcut (optional)
    CreateShortcut "$DESKTOP\JAM.lnk" "$INSTDIR\JAM.exe" "" "$INSTDIR\JAM.exe" 0
    
    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    
    ; Register in Windows (for Add/Remove Programs)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JAM" "DisplayName" "JAM - Japanese Anki Miner"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JAM" "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JAM" "InstallDir" "$INSTDIR"
    
    ; Save install directory
    WriteRegStr HKCU "Software\JAM" "InstallDir" "$INSTDIR"
    
    DetailPrint "✓ JAM installed successfully!"
SectionEnd

; ============================================================================
; UNINSTALL SECTION
; ============================================================================

Section "Uninstall"
    ; Remove shortcuts
    RMDir /r "$SMPROGRAMS\JAM"
    Delete "$DESKTOP\JAM.lnk"
    
    ; Remove application files
    RMDir /r "$INSTDIR"
    
    ; Remove registry
    DeleteRegKey HKCU "Software\JAM"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JAM"
    
    DetailPrint "✓ JAM uninstalled successfully!"
SectionEnd

; ============================================================================
; INSTALLER FINISHED
; ============================================================================

Function .onInstSuccess
    MessageBox MB_OK "JAM has been installed!$\n$\nYou can launch it from:$\n- Start Menu > JAM$\n- Desktop shortcut$\n- Or right-click the shortcut to pin to taskbar"
FunctionEnd
