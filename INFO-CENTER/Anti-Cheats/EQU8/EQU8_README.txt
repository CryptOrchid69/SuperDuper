EQU8 README

Purpose

This document is written for legitimate players, server owners, modders, and developers who want to understand fair play protection at a safe conceptual level. It does not include bypass steps, exploit details, cheat code, evasion procedures, or instructions for defeating protection.

EQU8 is a client focused anti cheat solution for online PC games. It is intended to help studios protect multiplayer matches from hackers, cheat tools, and unfair software while also giving developers information about player security events.

General design

EQU8 is integrated into the game client and startup process. When a protected game starts, EQU8 checks whether its components can load, whether the game environment looks trusted, and whether suspicious programs or tampering behavior are present.

Client focus

A client focused system watches what happens around the player game process. At a safe level, this can include process interaction, memory tampering, unauthorized modules, suspicious drivers, known cheat signatures, automation tools, and attempts to interfere with the anti cheat service itself.

Developer information

EQU8 is described as providing protection and analysis. This means a developer may receive reports about cheat categories, suspicious events, and player side errors. Those reports can help the studio tune rules, investigate incidents, and improve compatibility.

Why lightweight matters

Some studios want anti cheat protection without building a large internal security team. A lightweight third party anti cheat can provide a ready made base layer. The tradeoff is that the studio must still handle community policy, appeals, and game specific exploit fixes.

Compatibility

Like other security tools, EQU8 may conflict with debugging tools, overlays, virtualization, unusual drivers, macro utilities, and antivirus products. Compatibility may differ from one protected game to another.

Enforcement

EQU8 can support blocked launch, match kicks, suspicious account flags, or publisher bans. The game studio normally decides the final enforcement policy.

Player advice

Keep the game updated, remove cheat related tools, avoid memory editors, avoid suspicious driver packages, and use the official game support path for errors. Never download replacement anti cheat files from unofficial websites.

[PRODUCT OVERVIEW]
* Developer: Int3 Software (Acquired / Partnered with AccelByte) [accelbyte.io]
* Architecture: Hybrid (Dynamic User-Mode Agent + On-Demand Kernel Driver)
* Key Philosophy: Client-centric, lightweight security boundary emphasizing 
  session integrity, low system overhead, and direct telemetry correlation over 
  persistent background monitoring.

-------------------------------------------------------------------------------
1. TECHNICAL ARCHITECTURE & SYSTEMS OPERATION
-------------------------------------------------------------------------------
* On-Demand Execution: EQU8 operates strictly on a game-bound lifecycle. 
  It loads exclusively when the host game initiates and completely ceases all 
  system tasks and background execution the moment the game exits.
* Modular Service Numbering: Uses a dynamic suffixing scheme based on build 
  versions (e.g., EQU8_39, EQU8_13). It temporarily registers 
  two core system mechanisms during a live gameplay session:
  - Launcher Service: Named `EQU8_[Version]` (e.g., `EQU8_36`)
  - Kernel Helper Driver: Named `EQU8_HELPER_[Version].sys`
* Process Footprint: Launches an obfuscated user-mode manager alongside the game 
  binary, typically tracked as `agent.x64.equ8.exe` or `anticheat.x64.equ8.exe`.

-------------------------------------------------------------------------------
2. SECURITY ASSURANCE & MITIGATION CAPABILITIES
-------------------------------------------------------------------------------
* System Callbacks: The kernel driver (`EQU8_HELPER_*.sys`) sets up strict process 
  creation routines and pre-operation handle callbacks via the Windows kernel. 
  This intercepts unauthorized external memory manipulation.
* Injection Blockade: Actively monitors for dynamic analysis events, intercepting 
  cases where unauthorized Dynamic Link Libraries (DLLs) are forced into the game 
  or external debuggers try to attach to the application threads.
* File Shrouding & Configs: Leverages locally encrypted rule layers (such as 
  `equ8.cfg` and `equ8_con.json`) to establish file system validation parameters.
* AccelByte Telemetry Sync: Feeds real-time execution anomalies directly into backend 
  cloud infrastructure. Rather than evaluating cheating in a complete silo, 
  it cross-references hardware fingerprints, OS profiles, and account traits to flag 
  malicious recurring actors.

-------------------------------------------------------------------------------
3. COMPATIBILITY & SYSTEM REPERCUSSIONS
-------------------------------------------------------------------------------
* Engine Agility: Deployed as a lightweight wrapper heavily favored by automated 
  Steam deployments and modular engine architectures (such as Unity and Unreal Engine).
* Windows Testing Block: EQU8 strictly blocks execution if the host OS is booted in 
  "Windows Test Mode" (Testsigning mode), as this environment allows unverified, 
  user-made kernel drivers to compromise memory safeguards.
* Mutual Exclusion Blocks: Because it registers low-level IRP handlers during game 
  launches, it frequently collides with highly aggressive persistent anti-cheats. 
  Active execution environments like Riot Vanguard or active debugging instances of 
  Cheat Engine often trigger immediate validation failures.

-------------------------------------------------------------------------------
4. NOTABLE TITLES ENFORCING EQU8 ANTI-CHEAT
-------------------------------------------------------------------------------
EQU8 has historically protected various competitive multiplayer and aim-training titles:
* Splitgate
* Totally Accurate Battlegrounds (TABG)
* KovaaK's (Aim Trainer)
* Diabotical (Legacy implementations)
* Dual Universe

-------------------------------------------------------------------------------
5. DISPOSAL, REPAIR & RESIDUAL MANUAL CLEANUP
-------------------------------------------------------------------------------
If an integrated build fails to fully drop its temporary service configuration, 
or if signature errors ("Access is Denied 0005") halt game initialization, follow 
this manual clearance protocol:

STEP A: Purge Active Windows Service Registry
1. Press the Windows Key, type "cmd", and select "Run as Administrator".
2. Run the following terminal commands to strip stalled build services (replace 
   the number suffix with the exact version code your error prompt displays):
   sc stop EQU8_36
   sc delete EQU8_36
   sc stop EQU8_39
   sc delete EQU8_39

STEP B: Rebuild Client JSON Infrastructure
1. Navigate directly to your game's local installation files via Steam.
2. Search the root directory and delete `equ8_con.json` along with `equ8-launcher.exe`.
3. Open Steam, right-click the game -> Properties -> Installed Files -> Click 
   "Verify integrity of game files" to force a clean, uncorrupted re-download.

STEP C: Strip Residual Kernel Drivers
1. Reboot the PC to ensure any open thread locks on driver objects are cleared.
2. Open Windows Explorer and navigate to: `C:\Windows\System32\drivers`
3. Locate any files explicitly prefixed with `EQU8_HELPER_` (e.g., `EQU8_HELPER_36.sys`) 
   and delete them permanently