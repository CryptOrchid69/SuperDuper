FACEIT Anti Cheat README

Purpose

This document is written for legitimate players, server owners, modders, and developers who want to understand fair play protection at a safe conceptual level. It does not include bypass steps, exploit details, cheat code, evasion procedures, or instructions for defeating protection.

FACEIT Anti Cheat protects competitive matches on the FACEIT platform, especially high trust Counter Strike competition. It is designed to create a stronger trust boundary than ordinary public matchmaking.

General design

FACEIT Anti Cheat uses three broad parts. A desktop application must be running for protected matches. A kernel mode driver loads on the PC. A server side component verifies that the player is running the required protection while connected to a protected match.

Why the platform requires it

Competitive platform cheating has high stakes because ranked ladders, prizes, and reputation can be affected. FACEIT uses stronger checks than many normal matchmaking systems because players voluntarily enter a more controlled competitive environment.

Client checks

At a safe level, FACEIT Anti Cheat can check whether the game process is being manipulated, whether suspicious software or drivers are present, whether the protection driver is loaded, and whether the client is communicating correctly with FACEIT servers. It may also detect prohibited debugging, injection, and tampering patterns.

Server verification

The server side SDK helps confirm that the anti cheat is active during a match. If the client stops reporting correctly, the player can be removed or prevented from joining. This makes it harder for a player to start clean and then turn off protection mid match.

Trust and enforcement

FACEIT can use technical signals, match data, reports, account history, and manual review. Enforcement may include blocked queue entry, match removal, platform bans, tournament bans, or broader account restrictions.

Compatibility

Because FACEIT uses a kernel driver and strict platform rules, it may conflict with some drivers, virtualization tools, debugging tools, overlays, and system security configurations. Requirements can change as the cheating threat changes.

Player advice

Launch FACEIT Anti Cheat before joining protected matches, keep Windows updated, avoid suspicious tools, and read official FACEIT support pages for current requirements. Do not run cheat development tools or memory editors on the same machine used for FACEIT competition.

[PRODUCT OVERVIEW]
* Developer: FACEIT Ltd (EFG - ESL FACEIT Group)
* Architecture: Aggressive Kernel-Level (Ring 0) Driver + Server Heuristics + AI
* Environment Support: Windows 10 & Windows 11 (64-bit Only)
* Core Mission: Elite competitive matchmaking defense focusing on strict memory 
  isolation, hardware exploit blocking, and behavioral evaluation.

-------------------------------------------------------------------------------
1. TECHNICAL ARCHITECTURE & OS REQUIREMENT MATRICES
-------------------------------------------------------------------------------
* Root Privilege Isolation: Deploys a rigorous Ring 0 kernel-mode system driver 
  tasked with vetting all active memory calls and process handles on the OS.
* Registered Windows Frameworks: Configures persistent local client elements:
  - System Driver: `faceit.sys` located within `C:\Windows\System32\drivers`
  - Control Service: `FACEITService` (Must remain toggled to Manual startup type)
* Windows Lifecycle Sunsetting: In strict alignment with Microsoft's product cycle, 
  FACEIT has scheduled the absolute end-of-support for Windows 10 for October 
  14th, 2026. Moving forward, Windows 11 is mandated to prevent vulnerabilities 
  prevalent in legacy OS environments.
* System Tray Deactivation: Features a system tray icon allowing players to manually 
  "disable driver" states without uninstalling. Re-enabling the driver to queue 
  for matches requires a mandatory hardware reboot.

-------------------------------------------------------------------------------
2. HARDWARE-LEVEL ENFORCEMENT & HARDENING RULES
-------------------------------------------------------------------------------
To isolate and block DMA (Direct Memory Access) hardware cards and complex cheats, 
FACEIT mandates deep hardware and BIOS security layers:
* TPM 2.0 & Secure Boot: Mandatory baseline execution parameters. Enforces absolute 
  Driver Signature Enforcement (DSE) to block "BYOVD" (Bring Your Own Vulnerable 
  Driver) kernel injection exploits.
* IOMMU RAM Firewalling: Formally required across various player tiers to completely 
  isolate memory pools, establishing a physical barrier against DMA hardware sniffers.
* Virtualization-Based Security (VBS): Required in tandem with IOMMU to wrap core 
  OS kernels in virtualized sandboxes, blocking sub-kernel hypervisor cheats.
* Identity Verification & Re-Checks: Pairs hardware biometric matching with automated 
  selfie re-checks, binding severe cheating infractions directly to the player's 
  legal identity to permanently stop smurfing and account selling.

-------------------------------------------------------------------------------
3. COMPATIBILITY BOUNDARIES & BEHAVIORAL AI ENGINE
-------------------------------------------------------------------------------
* Google Deep Learning Integration: Employs an expansive server-side behavioral AI 
  system trained in partnership with Google engineers. While the client-side kernel 
  blocks local code injection, the AI model profiles telemetry for impossible 
  input mechanics, targeting stealthy machine-learning aimbots and spinbots.
* Platform Exclusion: Absolute restriction on Linux, Valve Proton, Wine, and macOS 
  systems. Because these alternative platforms inherently compromise the required 
  low-level hardware verification hooks, they are entirely locked out.
* BYOVD Driver Blacklisting: Proactively blocks unpatched third-party hardware 
  drivers (such as legacy NVMe controllers, tablet drivers, or obsolete device software) 
  susceptible to privilege escalation exploits.

-------------------------------------------------------------------------------
4. PRIMARY ECOSYSTEM DEPLOYMENT
-------------------------------------------------------------------------------
FACEIT anti-cheat serves as the primary security layer for premium competitive scenes:
* Counter-Strike 2 (CS2 - Premier competitive hubs, Majors, and Challenger leagues)
* Team Fortress 2 (TF2 - Custom competitive implementations)
* PUBG: Battlegrounds (Tournament and league execution layers)

-------------------------------------------------------------------------------
5. MAINTENANCE & MANUAL SERVICE PURGING
-------------------------------------------------------------------------------
Corrupted BIOS states, old drivers, or registry locks can result in "The service 
cannot be started" or "Incompatible driver detected" exceptions. Follow these 
manual cleanup steps:

STEP A: Purge Stalled System Drivers
1. Open Windows Device Manager (`devmgmt.msc`).
2. Expand the `Storage Controllers` or peripheral device trees to isolate outdated 
   vulnerable drivers (e.g., standard Samsung NVMe or old SATA controllers).
3. Right-click the affected item, choose "Update Driver", and manually force the 
   system to use Microsoft's "Standard Controller" alternatives to lift the block.

STEP B: Terminal Unregistration
1. Press the Windows Key, type "cmd", and select "Run as Administrator".
2. Execute the following terminal strings to wipe the operating service entries:
   sc stop FACEITService
   sc delete FACEITService

STEP C: File System Extraction
1. Restart the computer to release active process handles from memory.
2. Navigate to `C:\Program Files` and permanently delete the `FACEIT AC` folder.
3. Open `C:\Windows\System32\drivers` and shift-delete `faceit.sys` to clear 
   the leftover driver payload.