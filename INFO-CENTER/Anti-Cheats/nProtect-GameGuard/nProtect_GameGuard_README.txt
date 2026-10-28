nProtect GameGuard README

Purpose

This document is written for legitimate players, server owners, modders, and developers who want to understand fair play protection at a safe conceptual level. It does not include bypass steps, exploit details, cheat code, evasion procedures, or instructions for defeating protection.

nProtect GameGuard is an online game security product from INCA Internet. It is commonly used by online games to protect the game client, block known hack tools, and reduce botting, tampering, and unauthorized automation.

General design

GameGuard starts with the protected game and loads security components that monitor the game environment. It can update itself as new cheat patterns appear. If GameGuard cannot start correctly, the protected game may refuse to launch or may close during play.

Client protection

At a safe conceptual level, GameGuard can watch game memory, process interaction, suspicious modules, altered files, abnormal input automation, known hack tools, speed manipulation, and attempts to interfere with the protected game. It may also use anti malware style pattern detection for tools associated with cheating.

Self protection

Anti cheat systems often protect themselves because cheat tools may try to stop the anti cheat first. GameGuard can use self protection ideas such as guarding its files, checking its own integrity, and reacting when another program tries to disable or alter it.

Why it can feel intrusive

GameGuard has a reputation for being strict because it runs deeply enough to observe sensitive system behavior around the game. This may cause conflicts with accessibility tools, overlays, security software, macro tools, and some drivers. The goal is game protection, but compatibility problems can happen.

Publisher role

The game publisher decides how GameGuard is used in that title. One game may configure stricter blocking, while another may focus on logging and review. The publisher also controls account discipline in most cases.

Enforcement

GameGuard can block startup, close the game, report suspicious detections, or help the publisher apply bans. It may also produce error codes when files are missing, blocked by antivirus, or unable to update.

Player advice

Use official game installers, keep antivirus exclusions limited and only when recommended by official support, avoid macro tools and memory editors, and restart after updates if GameGuard asks. For uninstalling or repair, use official GameGuard or game publisher instructions.

]
* Core Classification: Kernel-Level (Ring 0) Anti-Cheat & Anti-Malware Rootkit
* Operational Era: Active since the early 2000s; heavily utilizes legacy 
  and modern kernel-hooking architectures to protect B2B2C online game spaces.
* Primary Mission: Intercepting active memory modification, blocking peripheral 
  automation (macros), and validating game binary integrity through direct OS 
  and API manipulation.

-------------------------------------------------------------------------------
1. TECHNICAL ARCHITECTURE & OPERATIONAL FOOTPRINT
-------------------------------------------------------------------------------
* High-Privilege Driver: Deploys a persistent Ring 0 device driver designed to 
  monitor, intercept, and block unauthorized API requests at the Windows kernel level.
* Core System Binaries: Drops and manages localized security architecture:
  - Local Directories: Typically structured inside `<game-root-dir>\bin\GameGuard\` 
    or `<game-root-dir>\tools\`.
  - Windows Drivers: Installs `npggmsfk.sys`, `npngasfk.sys`, or related `nProtect` 
    device configurations inside `C:\Windows\System32\drivers`.
  - Local Manager Binaries: Executes `GameMon.des` (the main monitor module) alongside 
    `w9xpopen.exe` and `dump_*.dmp` debugging wrappers.
* Dynamic Update Hooking: Every single initialization forces the client to download 
  and cross-verify fresh rule configurations and signature patches from the INCA 
  Internet Content Delivery Network (CDN) before allowing game-client clearance.

-------------------------------------------------------------------------------
2. SECURITY ASSURANCE & RIGID PROTECTION RULES
-------------------------------------------------------------------------------
nProtect GameGuard operates using highly aggressive, invasive client-side routines 
to freeze out malicious third-party processes:

* Low-Level Memory Shrouding: Monitors and locks game RAM pages against dynamic 
  memory allocation manipulation (blocking common memory scanners like Cheat Engine).
* Automated Macro Suppression: Actively drops or intercept hardware/software inputs 
  originating from unverified keyboard recorders, automated mouse macros, or virtual 
  peripheral drivers.
* Aggressive Process Blacklisting: Features an internal, hardcoded list of unapproved 
  background programs. If it spots active debugging configurations, unverified overlay 
  injectors, or system-monitoring diagnostics, it forcibly terminates either the 
  offending program or the game client itself.
* Direct Kernel Hooking: Restricts certain vital Windows system API calls to stop 
  untrusted processes from generating handles or querying strings from the game process.

-------------------------------------------------------------------------------
3. COMPATIBILITY BOUNDARIES & SYSTEM REPERCUSSIONS
-------------------------------------------------------------------------------
* System Aggression Legacy: Due to its intrusive historical design, GameGuard is 
  notorious for causing "mutual exclusion" software blocks. It has been documented 
  crashing, locking out, or misidentifying mainstream applications like web browsers, 
  VoIP clients (Discord), streaming layers, or custom overlay controllers.
* Linux / Valve Proton Support: While inherently a Windows-centric kernel product, 
  recent modern deployments have added structural support layers to enable translation 
  compatibility with Valve's Proton layer, allowing execution on Steam Deck / SteamOS 
  for specific major titles.
* Antivirus False Positives: Because GameGuard injects itself into OS functions and 
  employs rootkit-like monitoring behavior, third-party security software 
  (such as Windows Defender, Avast, or Bitdefender) frequently quarantines its modules, 
  causing startup initialization failures.

-------------------------------------------------------------------------------
4. NOTABLE RECENT & HISTORICAL ECOSYSTEM INTEGRATIONS
-------------------------------------------------------------------------------
GameGuard remains a massive staple of South Korean online game security architectures, 
and protects several global multiplayer properties:
* Helldivers 2
* Blade & Soul
* Black Squad
* Undecember
* Elsword
* Lineage / Lineage II
* Phantasy Star Online 2 (Legacy deployments prior to engine updates)
* Ragnarok Online (Legacy deployment variants)

-------------------------------------------------------------------------------
5. MAINTENANCE, REPAIR, & MANUAL CLEANSING GUIDE
-------------------------------------------------------------------------------
Stalled server downloads or corrupted cache blocks frequently throw error loops 
(such as Error Codes 114, 340, 360, or 380). Use these exact steps to resolve or 
wipe the software entirely:

STEP A: Execute Integrated Developer Cleaning Tools
1. Open your game's structural installation directory (e.g., via Steam: Right-click 
   game -> Manage -> Browse local files).
2. Look for a subfolder designated as `tools` or `GameGuard`.
3. Locate and run `gguninst.exe` or `GGUninstall` as an Administrator to naturally 
   unhook the core system services.

STEP B: Forcing a Clean Directory Rebuild (Fixes Update Errors)
1. Navigate directly to your game's root execution path (e.g., `...\common\Helldivers 2\bin\`).
2. Locate the folder explicitly named `GameGuard` and delete it entirely.
3. Open your game launcher (such as Steam), right-click the game properties, select 
   "Installed Files", and click "Verify integrity of game files". This forces the 
   system to download fresh, uncorrupted base binaries.

STEP C: Manual Windows Service Cleanup
1. If the game is removed but background remnants linger, open Windows Command Prompt 
   as an Administrator.
2. Execute the following terminal commands to strip service registrations:
   sc stop npggsvc
   sc delete npggsvc
3. Restart your PC to fully unlock lingering driver objects in memory.
4. Navigate to `C:\Windows\System32\drivers` and permanently remove files matching 
   the `npgg*.sys` profile.
===============================================================================