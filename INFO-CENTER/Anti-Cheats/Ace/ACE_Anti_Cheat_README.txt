ACE Anti Cheat README

Purpose

This document is written for legitimate players, server owners, modders, and developers who want to understand fair play protection at a safe conceptual level. It does not include bypass steps, exploit details, cheat code, evasion procedures, or instructions for defeating protection.

ACE Anti Cheat is a game security system associated with Tencent and games that use Tencent security services. The name ACE is commonly understood as Anti Cheat Expert. It is used to protect online titles from cheat tools, account abuse, bots, and client tampering.

General design

ACE can combine client side protection, server side risk control, account reputation, device risk signals, and publisher operations tools. In large online games, anti cheat is usually part of a larger security system that also handles fraud, botting, emulator abuse, and account theft.

Client protection

At a safe conceptual level, ACE may check the protected game process, game files, suspicious memory access, unauthorized modules, automation tools, modified clients, debugging, and risky system states. The exact behavior depends on the game and platform.

Mobile and PC context

Tencent related games often span PC and mobile. Mobile anti cheat may focus on rooted devices, emulators, modified APK files, overlay tools, automation, memory editors, and network manipulation. PC anti cheat may focus more on drivers, injected code, and process tampering.

Server side risk control

Server systems can detect impossible combat results, abnormal currency gain, automated farming, device clusters, account sharing, and repeated suspicious reports. Account reputation helps identify repeat offenders and organized cheat groups.

Enforcement

ACE supported games may block launch, prevent matchmaking, remove players from matches, apply temporary or permanent bans, restrict devices, or flag suspicious accounts for review. Publisher policy controls the exact outcome.

Player advice

Use official installers, avoid modified clients, do not use rooted or tampered devices for protected games unless the publisher allows it, avoid automation tools, and use official appeal channels.

* Architecture: Multi-tier, cross-platform security (Kernel Ring 0 on PC)
* Mission: Real-time exploitation detection, data hardening, and fair-play enforcement

-------------------------------------------------------------------------------
1. TECHNICAL ARCHITECTURE & SYSTEMS OPERATION
-------------------------------------------------------------------------------
* Kernel Integration: On PC, ACE operates at Ring 0 (Kernel level). It boots 
  as an authorized system driver to protect memory and counter low-level hacks.
* Process Footprint: Registers multiple core services and system drivers:
  - Drivers: Named `ACE-*.sys` stored inside `C:\Windows\System32\drivers`
  - Services: `ACE-GAME`, `ACE-BASE`, `AntiCheatExpert Service`, and 
    `AntiCheatExpert Protection`.
* Lifecycle Control: Officially designed to run alongside the game client. 
  It sleeps or stops executing once the authenticated host process closes.

-------------------------------------------------------------------------------
2. CORE SECURITY FEATURES & MITIGATION CAPABILITIES
-------------------------------------------------------------------------------
* Anti-Debugging & Injection: Blocks dynamic analysis tools, hooking utilities, 
  and runtime injections to secure critical functions.
* Binary Hardening: Uses custom obfuscation frameworks to complicate local 
  static or reverse-engineering efforts.
* Secure Memory Types: Encrypts game data types dynamically in RAM via 
  proprietary classes (e.g., tracking health, currency variables).
* Speedhack Suppression: Identifies and intercepts systemic clock manipulation, 
  instantly terminating host applications violating sync boundaries.
* Virtual Machine Blocking: Features a 3-layer detection logic identifying 
  over 30 virtual environments (e.g., VirtualAPP, LBE, containers).
* AI Behavioral Analytics: Utilizes server-side deep learning models. 
  Analyzes user input/replay packets for impossible mechanical behavior (aimbots, 
  spinbots) instead of relying solely on file signature matches.

-------------------------------------------------------------------------------
3. COMPATIBILITY & DEPLOYMENT PARADOXES
-------------------------------------------------------------------------------
* Cross-Platform SDKs: Integrated natively across PC, Android, and iOS titles.
* Game Engine Support: Full wrapper compliance for Unity, Unreal Engine, and 
  Cocos 2D.
* Linux / Steam Deck: Restricts desktop Linux environments utilizing standard Proton 
  layers due to strict kernel calls. Exceptions exist for Steam Deck 
  environments with direct game-level developer adjustments.
* Mutual Exclusion Errors: The kernel-level presence of active ACE system components 
  frequently causes execution blocks with rival anti-cheat frameworks (such as 
  Easy Anti-Cheat) if overlapping hooks occur.

-------------------------------------------------------------------------------
4. NOTABLE RECENT & ACTIVE INTEGRATIONS (PC & MOBILE)
-------------------------------------------------------------------------------
ACE is standard security architecture for Tencent properties and partners:
* Arena Breakout: Infinite
* Delta Force
* Mecha BREAK
* Honor of Kings
* Call of Duty: Mobile
* ARC Raiders
* Age of Empires Mobile
* Duet Night Abyss

-------------------------------------------------------------------------------
5. DISPOSAL & RESIDUAL MANUAL CLEANUP GUIDE
-------------------------------------------------------------------------------
Uninstallation bugs may leave active system driver registries behind on Windows 
after removing a game. Use this complete guide to strip remaining artifacts:

STEP A: Purge Active Services
1. Run Command Prompt (CMD) or Windows PowerShell as an Administrator.
2. Execute the following script sequentially to remove system registration:
   sc stop ACE-GAME
   sc delete ACE-GAME
   sc stop ACE-BASE
   sc delete ACE-BASE
   sc delete "AntiCheatExpert Service"
   sc delete "AntiCheatExpert Protection"

STEP B: Wipe Disk Remnants
1. Reboot the PC to release hooks on active driver files.
2. Navigate to `C:\Program Files` and permanently delete the `AntiCheatExpert` directory.
3. Navigate to `C:\Windows\System32\drivers` and drop files named `ACE-GAME.sys` 
   or `ACE-BASE.sys` into the Recycle Bin.

Use code with caution.If you are encountering a specific system error, game crash, or driver conflict related to ACE, let me know which game you are playing and your operating system so I can provide customized troubleshooting steps!