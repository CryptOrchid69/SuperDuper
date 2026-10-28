PunkBuster README

Purpose

This document is written for legitimate players, server owners, modders, and developers who want to understand fair play protection at a safe conceptual level. It does not include bypass steps, exploit details, cheat code, evasion procedures, or instructions for defeating protection.

PunkBuster is one of the older major PC game anti cheat systems. It was developed by Even Balance and was widely used in earlier online shooters and multiplayer games. Its purpose is to detect cheating software and remove cheating players from protected servers.

General design

PunkBuster is integrated into the game client and game server. The client side component runs on the player machine and communicates with the server side component. Server administrators can use PunkBuster tools to manage protected servers, review violation messages, and enforce kicks or bans.

Client checks

At a safe conceptual level, PunkBuster can scan memory, inspect game related files, look for known cheat signatures, verify certain client settings, and check whether the local protection component is up to date. It can also use screenshots or server requested checks depending on the game configuration.

Server administrator role

PunkBuster became popular partly because it gave server administrators direct tools. Admins could configure rules, receive violation notices, kick players, and manage ban lists. This made it useful for community hosted servers, especially in older games.

Updates

PunkBuster uses an update system so the protection files can change as new cheats appear. If the client or server is outdated, players may be kicked even if they are not cheating. Many PunkBuster issues in older games are caused by outdated services, missing files, firewall blocks, or old server configuration.

Enforcement

Enforcement can include warnings, kicks, game specific bans, global bans, and hardware linked restrictions in serious cases. Server administrators may also maintain local ban lists separate from global actions.

Strengths and weaknesses

PunkBuster helped define early online anti cheat enforcement. Its age means it may be less common in new games, and older installations can be fragile on modern Windows systems. It is still important historically and still appears in some legacy game communities.

Player advice

Use official game files, update PunkBuster only from official sources, avoid cheat tools and memory editors, and check firewall permissions if a clean player is being kicked for communication errors.

[PRODUCT OVERVIEW]
* Developer: Even Balance, Inc. [evenbalance.com]
* Architecture: Dual-Service Client/Server Architecture (User-Mode + Driver)
* Operational Class: Historically significant pioneer of consumer anti-cheat
* Core Philosophy: Continuous real-time scanning of memory space, background 
  process tracking, and automated file-integrity verification paired with 
  server-side Master Server polling.

-------------------------------------------------------------------------------
1. TECHNICAL ARCHITECTURE & OPERATIONAL FOOTPRINT
-------------------------------------------------------------------------------
* Dual Service Architecture: On Windows systems, PunkBuster splits its runtime 
  responsibilities across two distinct background services that run constantly 
  to maintain communication loops:
  - PnkBstrA: The base system service (`PnkBstrA.exe`). It initializes with 
    Windows to handle communications, dynamic updates, and game-detection handshakes.
  - PnkBstrB: The active monitoring service (`PnkBstrB.exe`). It starts up dynamically 
    when an official PunkBuster-secured game executable loads to execute memory scans.
* High-Privilege Helper Driver: Installs a specialized monitoring driver into the 
  file system, typically named `pbcl.sys` or `pbsv.sys` within protected directories.
* Disk Footprint: Manages core system binaries across two primary locations:
  - System Paths: `C:\Windows\System32\` or `C:\Windows\SysWOW64\`
  - Local Game Paths: Contained within a localized `<game-root-dir>\pb\` folder.

-------------------------------------------------------------------------------
2. SECURITY ASSURANCE & LEGACY EXPLOIT MITIGATION
-------------------------------------------------------------------------------
PunkBuster operates using an older, highly structured approach to prevent, catch, 
and penalize illicit third-party software integration:

* Direct Memory Verification: Continuously loops through the game client's active 
  RAM addresses to locate known cheat patterns, unauthorized injectors, or hooking hooks.
* Global Blacklisting Database: Matches running background process strings and MD5 
  file hashes against an extensive signature dictionary updated by Even Balance analysts.
* Dynamic PunkBuster Screenshots: Features a unique option allowing game servers 
  to silently prompt local clients to capture and upload a real-time JPEG image of 
  their in-game screen buffer to detect wallhack and ESP visual overlays.
* Guid & Hardware Enforced Bans: Combines unique CD-Key identities with structural 
  hardware biometric indices (PB GUID) to isolate and permanently exclude malicious 
  players via global ban lists (Master Server Blacklists).

-------------------------------------------------------------------------------
3. COMPATIBILITY BOUNDARIES & SYNC CHALLENGES
-------------------------------------------------------------------------------
* Outdated Auto-Update Engines: PunkBuster lacks a modern, unified auto-updater. 
  If a player reinstalls a legacy title via digital distribution storefronts (like Steam), 
  the game often packages an ancient PB version that fails to link with live servers, 
  causing instant kicks (e.g., "Losing Key Packets").
* Network Packet Fragility: Highly sensitive to firewall settings, localized network 
  latency, and packet loss. If `PnkBstrB.exe` encounters a brief routing delay when 
  communicating with `PnkBstrA.exe`, the game server instantly kicks the player.
* Modern OS and Linux Boundaries: Because it relies on older, rigid Windows service management 
  and deep API hooks, it faces massive compatibility issues under Valve's Linux Proton 
  layer, making Linux/Steam Deck support on older multiplayer games a common point of failure.

-------------------------------------------------------------------------------
4. HISTORICAL & RECENT DEPLOYMENTS
-------------------------------------------------------------------------------
PunkBuster served as the backbone for early to mid-2000s PC competitive gaming:
* Battlefield 4 / Battlefield 3 / Battlefield: Bad Company 2
* Battlefield 2142 / Battlefield 2 / Battlefield 1942
* Call of Duty 4: Modern Warfare / Call of Duty 2 / Call of Duty (Original)
* Medal of Honor (2010 / Warfighter)
* America's Army (Legacy Deployments)
* Far Cry / Far Cry 2
* Wolfenstein: Enemy Territory

-------------------------------------------------------------------------------
5. MAINTENANCE, REPAIR, & MANUAL UPDATE PROCEDURES
-------------------------------------------------------------------------------
Due to the brittle nature of older Even Balance distribution files, manual intervention 
is frequently required to resolve connection loops or execution faults.

STEP A: Use the Official Standalone PBSetup Tool
1. Navigate to the official Even Balance website and download the standalone tool `pbsetup.exe`.
2. Right-click `pbsetup.exe` and select "Run as Administrator".
3. Click "Add a Game", select your target legacy title from the dropdown, and point 
   the file explorer path to the game's root folder.
4. Click "Check for Updates" to force a clean, manual download of the latest system 
   definitions directly into your game's directory.

STEP B: Check and Fix Windows Service Registrations
1. Open the Run dialog (`Windows Key + R`), type `services.msc`, and press Enter.
2. Scroll down to locate `PnkBstrA` and `PnkBstrB`.
3. Double-click both entries, ensure their "Startup type" is configured to "Automatic", 
   and verify that their status says "Running".
4. If they are blocked, open an Administrator Command Prompt and execute:
   sc start PnkBstrA
   sc start PnkBstrB

STEP C: Thorough Manual Purging
1. Open an Administrator Command Prompt and run the following lines to clear service listings:
   sc stop PnkBstrB
   sc delete PnkBstrB
   sc stop PnkBstrA
   sc delete PnkBstrA
2. Restart your computer to release any locked processes.
3. Open Windows Explorer and manually wipe out any trailing `PnkBstr*` executables or 
   drivers located inside `C:\Windows\System32\` and `C:\Windows\SysWOW64\`.
===============================================================================