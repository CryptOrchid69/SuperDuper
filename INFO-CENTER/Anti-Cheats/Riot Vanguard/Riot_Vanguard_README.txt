Riot Vanguard README

Purpose

This document is written for legitimate players, server owners, modders, and developers who want to understand fair play protection at a safe conceptual level. It does not include bypass steps, exploit details, cheat code, evasion procedures, or instructions for defeating protection.

Riot Vanguard is Riot Games custom anti cheat system used for Riot competitive titles such as VALORANT and League of Legends on PC. It is designed to protect competitive integrity in games where a small unfair advantage can ruin ranked play.

General design

Vanguard uses a client application, a kernel mode driver, server side validation, Riot account enforcement, telemetry analysis, and active security research. The system checks whether the machine is in a trusted state before allowing protected play. It can also stop the game from launching if required security conditions are not met.

Boot level protection

Vanguard is known for loading a driver early in the Windows boot process. The purpose is to reduce the chance that a cheat can start first, hide itself, and then manipulate the game before the anti cheat is active. This design is powerful, but it is also why Vanguard receives attention from players who are concerned about privacy and system control.

What it watches at a safe level

Vanguard focuses on cheat related manipulation of Riot games. It can check for suspicious drivers, unauthorized memory access, game process tampering, debugging indicators, hardware assisted cheating patterns, abnormal input behavior, and system states that weaken trust. It also uses server side data to detect behavior that does not match normal human play.

Hardware and firmware trust

Modern high end cheats may use external hardware or firmware level tricks. Vanguard has increasingly relied on platform security signals such as Secure Boot, TPM, IOMMU protection, and motherboard firmware requirements in certain contexts. These checks try to make it harder for cheat devices to hide outside the normal operating system.

Server side analysis

Riot combines client security with gameplay analytics. A player may be investigated because of impossible aim patterns, abnormal reaction timing, unusual account behavior, suspicious device history, or reports that match technical telemetry. Human review and automated detection can work together.

Enforcement

Vanguard can block launch, require system setting changes, remove a player from a match, ban accounts, and apply stronger action against repeat or hardware linked cheating. Riot often updates Vanguard because cheat development changes quickly.

Player advice

Keep Windows security features enabled, update motherboard firmware only from the official manufacturer, avoid cheat tools and unknown drivers, and use official Riot support for errors. Do not follow internet guides that tell you to weaken security settings just to run suspicious tools.

[PRODUCT OVERVIEW]
* Developer: Riot Games Inc.
* Architecture: Native Kernel-Level (Ring 0 Boot Driver) + User-Mode Client
* Platform Support: Windows 10 & Windows 11 (64-bit native only)
* Core Philosophy: "Deep Prevention and Immediate Termination." Operates as a 
  highly restrictive security wrapper that launches at system boot time to 
  isolate memory space before any potential exploit drivers can initialize.

-------------------------------------------------------------------------------
1. TECHNICAL ARCHITECTURE & SYSTEMS OPERATION
-------------------------------------------------------------------------------
* System Boot Integration: Vanguard runs as a boot-start driver. It initiates at 
  the earliest phase of the operating system boot process (Ring 0) to ensure a 
  secure baseline before user-mode software can execute.
* Core System Process Components: Splits its operations across two distinct layers:
  - Kernel Driver: `vgk.sys` located within `C:\Windows\System32\drivers`
  - User-Mode Client: `vgc.exe` running out of `C:\Program Files\Riot Vanguard`
* Active Services Profile: Registers the `vgc` service in Windows (`Riot Vanguard 
  Notification Icon`). Disabling this service blocks access to Riot games.
* Lifecycle Boundary: The kernel driver (`vgk.sys`) runs constantly in the background 
  from system boot. The user-mode client (`vgc.exe`) can be manually closed via the 
  system tray, but playing Vanguard-secured titles requires a full hardware reboot 
  to restore system verification hooks.

-------------------------------------------------------------------------------
2. SECURITY ASSURANCE & ANTI-EXPLOITATION MATRIX
-------------------------------------------------------------------------------
* Driver Signature Enforcement (DSE): Strictly blocks vulnerable or unpatched 
  third-party hardware drivers (BYOVD exploits) that could allow malicious code 
  to manipulate kernel-level game structures.
* Hardware Biometric Tracking: Creates unique, persistent HWID (Hardware Identifier) 
  profiles based on underlying BIOS metadata. This prevents banned players from 
  using alternate accounts on the same machine.
* Vanishing Act (Instant Drop): Instantly shuts down live multiplayer matches 
  the exact millisecond a cheater is flagged by server-side verification logic, 
  restoring rating points to unaffected players.
* Deep Virtualization Block: Utilizes hardware-assisted virtualization hooks. 
  Actively flags or terminates the client if it detects isolated hypervisors, 
  sandboxes, or unverified hardware configurations trying to obscure memory.

-------------------------------------------------------------------------------
3. WINDOWS 11 HARDWARE MANDATES & COMPATIBILITY BOUNDARIES
-------------------------------------------------------------------------------
To counter advanced hardware exploits, Vanguard enforces rigid BIOS and system 
security profiles:
* UEFI Secure Boot & TPM 2.0: Absolute hard requirement under Windows 11. The anti-cheat 
  will refuse to let the game launch if the system detects these settings are bypassed 
  or disabled in the BIOS.
* Linux, Wine, & Mac Total Exclusion: Vanguard completely blocks execution under Linux, 
  Valve Proton, Wine, or macOS. Because alternative operating systems cannot replicate 
  Riot's exact kernel verification requirements, these platforms are entirely locked out.
* Peripheral Software Mutual Exclusion: Aggressively blacklists or prevents startup 
  when drawing conflicts occur with specific third-party software, such as custom hardware 
  monitors, unverified overlay managers, or macro remappers.

-------------------------------------------------------------------------------
4. NOTABLE TITLES ENFORCING RIOT VANGUARD
-------------------------------------------------------------------------------
Vanguard protects Riot Games' premier competitive and tactical titles:
* VALORANT (Default launcher environment since 2020)
* League of Legends (Infrastructure migrated globally in Spring 2024)
* Teamfight Tactics (TFT - Deployed alongside League's desktop client migration)

-------------------------------------------------------------------------------
5. DISPOSAL, RESUBMISSION, & MANUAL SERVICE PURGING
-------------------------------------------------------------------------------
If a Vanguard patch loop fails, or if a persistent "Vanguard Not Initialized" error 
occurs, follow this comprehensive manual cleaning guide:

STEP A: Use the Official Uninstallation Engine
1. Close all active Riot client processes.
2. Open Windows Apps & Features (`Settings -> Apps -> Installed Apps`).
3. Locate "Riot Vanguard" in the list, click the options icon, and select "Uninstall".

STEP B: High-Privilege PowerShell Clean
1. If the standard uninstaller hangs, right-click the Windows Start Menu and select 
   "Terminal (Admin)" or "PowerShell (Admin)".
2. Run the following command lines to manually delete the underlying services:
   sc stop vgc
   sc stop vgk
   sc delete vgc
   sc delete vgk

STEP C: Purge Remaining File Artifacts
1. Reboot the PC to unlock any remaining driver files in memory.
2. Open Windows Explorer and navigate to: `C:\Program Files`
3. Delete the `Riot Vanguard` directory entirely.
4. Navigate to `C:\Windows\System32\drivers` and permanently delete `vgk.sys`.
===============================================================================