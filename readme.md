# 📱 Android Game Network Protocol Analysis & Reversing Notes

This repository documents a hands-on journey of reverse-engineering a mobile game (built on a custom C++ engine). It covers the complete workflow from bypassing environment detection (Root/anti-debugging) and SSL Pinning, to distinguishing between proxy-based and raw NIC packet capture, and ultimately analyzing custom TCP protocols.

> ⚠️ **Disclaimer**: This project is for educational and cybersecurity research purposes only. All sensitive information (e.g., real IP addresses, Session Tokens, account credentials) has been sanitized. Do not use these techniques for cheating or any illegal activities.

---

## 📑 Table of Contents
1. [Network Architecture & Capture Limitations](#1-network-architecture--capture-limitations)
2. [Environment Setup & Anti-Detection Bypass](#2-environment-setup--anti-detection-bypass)
3. [Packet Capture: Raw NIC Mode & TCP Reassembly](#3-packet-capture-raw-nic-mode--tcp-reassembly)
4. [Custom Private Protocol Reverse Engineering](#4-custom-private-protocol-reverse-engineering)
5. [Analysis Scripts](#5-analysis-scripts)

---

## 1. Initial Troubleshooting & Capture Limitations

### 1.1 First Attempt: App-Layer Injection (Failed)
To understand the game's logic, the first logical step was to use an App-layer capture tool (which injects a hook into the target process to intercept Socket APIs directly).

<img src="images/app-layer.png" alt="App-Layer Injection Crash" width="600">
*   **Symptom**:
    *   When attempting to hook the game by **restarting the target app** (`Restart Target App` enabled), the client would instantly freeze on a black screen and refuse to launch. This indicated that the injection process itself was detected during the early startup phase.
    *   When attempting to attach to the **already running process** (without restarting), the injection failed entirely, returning an error (`target_app_not_running`). The game's anti-debugging module actively blocked the hooking attempt.
    
<img src="images/App-layer-defeat.png" alt="App-Layer Injection Crash" width="600">

*   **Analysis**: The game employs robust anti-debugging and anti-injection mechanisms. Upon launching, it scans its own process memory. Detecting the injected capture module (e.g., Frida agent), the game triggered a self-protection routine and terminated itself.

### 1.2 Second Attempt: Raw NIC Capture (Successful but Limited)
Since the process rejected injection, the next approach was **Raw NIC (Network Interface Card) Capture** (Data Link/Network layer). By putting the virtual NIC into Promiscuous Mode, we bypassed the API level entirely.

*   **Result**: We successfully intercepted raw TCP/IP traffic (specifically on Port `22158`). We discovered the game used a long-polling raw TCP connection instead of standard HTTP.
*   **Limitation**: Raw capture provides the "what" (the raw bytes), but not the "meaning". While unencrypted custom text protocols (like Heartbeats) were readable, critical business logic packets appeared only as unreadable ciphertext. The packet header started with `78 9C` (a Zlib compression header), but attempts to decompress failed (`unsupported compression method`). This indicated the data was **first Zlib-compressed, then wrapped in an additional layer of AES or custom encryption**.

   **Some readable information**：Heartbeat and Attack information.
<img src="images/attack.png" alt="App-Layer Injection Crash" width="600">

<img src="images/heartbeat.png" alt="App-Layer Injection Crash" width="600">
   **Some of them are absolutely not readable**:

<img src="images/unreadable.png" alt="App-Layer Injection Crash" width="600">

### 1.3 Third Attempt: System HTTP Proxy (The Breakthrough)
Since we couldn't decrypt the custom protocol immediately, we analyzed the traffic fingerprint and found that the game mixed network architectures. Certain APIs (like Login and Recharge) actually used standard HTTPS.

*   **Problem**: Configuring a system HTTP proxy (e.g., `Burp Suite` or `TraceEagle` in Proxy Mode) resulted in "Network Connection Error". The game implemented **SSL Pinning**, refusing to trust the user-installed CA certificate.
*   **Conclusion**: To see the plaintext of these HTTPS requests, we had to build a heavily modified, stealthy Root environment to bypass SSL Pinning (detailed in Section 2).

---

## 2. Environment Setup & Anti-Detection Bypass

To perform App-layer injection and bypass SSL Pinning, standard Root privileges are insufficient. The game employs multi-layered environmental checks (Root detection, emulator detection, and integrity checks). We had to construct a stealthy, systemless Root environment on an Android 14 emulator.

### 2.1 Bypassing Root & Injection Detection (Kitsune Mask + Zygisk Next)
*   **The Problem**: The game scans its own process memory and system files for traces of `su` and known debugging frameworks. Using the emulator's built-in Root caused the App-layer capture tool to trigger an immediate black screen and crash during injection.
*   **The Solution**:
    1.  **Systemless Root**: Abandoned the crude built-in Root. Flashed **Kitsune Mask (Magisk Delta)** via recovery. This provides a more covert Root environment.
    2.  **Zygisk Replacement**: Disabled the built-in Zygisk (which has known signatures) and deployed **Zygisk Next**. This provides a stealthier injection mechanism, preventing the game from detecting the Zygisk environment itself.
    3.  **Configuring the Routing (KSU WebUI)**: Used **KSU WebUI** to manage the Zygisk Next settings. Enabled "Anonymous Memory" to hide the injected modules from memory scans.
    4.  **DenyList Enforcement**: Added the target game package to the Magisk DenyList. This prevents the game from seeing the Root environment and the injected Xposed/LSPosed frameworks during its initial integrity check.
*   **The Outcome**: Despite the heavy stealth setup, the game's anti-injection mechanism was still too aggressive. When the App-layer capture tool attempted to attach to the running process, the game detected the hook and killed itself (`target_app_not_running`). We had to abandon App-layer injection and switch to Raw NIC capture.

### 2.2 Bypassing SSL Pinning (LSPosed + TrustMeAlready)
Even with a stealth Root environment, the HTTP Proxy mode failed in log-in process because the game implemented **SSL Pinning**. The client strictly validates the server's certificate fingerprint and refuses to trust user-installed CA certificates.

*   **The Solution**:
    1.  Flashed the **LSPosed** framework (activated via Zygisk Next. Although the stealth environment failed to fully bypass the anti-injection protection, it became the perfect foundation for fixing the **SSL Pinning** issue we encountered later during HTTP Proxy capture. ).
    2.  Installed the LSPosed module **TrustMeAlready**.
    3.  Scoped the module strictly to the target game package. This module hooks low-level Java APIs (e.g., `javax.net.ssl.SSLContext` and `OkHttp` certificate checkers) and forces them to return `true`, effectively disabling certificate validation.
*   **Validation**: We successfully captured the plaintext JSON payload for Login, Recharge, and Inventory synchronization via the HTTP Proxy.

### 2.3 Resolving Proxy Conflicts (The "Target App Not Running" Error)
*   **The Problem**: While testing the App-layer capture tool with the stealth environment active, an error `target_app_not_running` occurred.
*   **The Root Cause**: The injection tool attempted to hook the app during its startup phase. The game's anti-injection module detected the hook attempt and immediately killed the process.
*   **The Workaround**: We bypassed the instant-launch injection. Instead of hooking the app at startup, we let the game fully load to the login screen, then manually triggered the App-layer capture. With the Kitsune Mask DenyList and Zygisk Next active, the game failed to detect the late-stage injection, allowing us to intercept the Socket traffic successfully.


## 3. Packet Capture: Raw NIC Mode & TCP Reassembly

Since the App-layer injection was terminated by the game's anti-cheat, and the HTTP Proxy could only intercept standard HTTPS traffic, we switched to **Raw NIC (Network Interface Card) Capture** to intercept the underlying raw TCP traffic.

### 3.1 Traffic Fingerprinting & Port Identification
Initial raw captures were flooded with `mDNS` and `ICMP` background noise. By applying filtering rules and tracing DNS resolutions, we isolated the core game traffic:

*   **Persistent Destination IP**: The client maintained a long-lived connection to a specific IP (redacted for privacy).
*   **Port Signature**: The traffic was heavily concentrated on **Port `22158`**. 
*   **Protocol**: The traffic is pure raw TCP, not wrapped in HTTP/2 or WebSocket. This explains why the HTTP Proxy failed to capture it.

### 3.2 TCP Stream Reassembly & Heartbeat Analysis
By filtering the capture with `tcp.port == 22158`, we observed a distinct communication pattern:

1.  **Heartbeat Mechanism**: Every ~10 seconds, the client and server exchanged extremely small payloads (around 16 bytes).
2.  **Custom Text Protocol**: By extracting the raw TCP Payload and converting it from Hex to ASCII, a surprising discovery was made. The game **uses a custom, HTTP-like text protocol**. Despite running over raw TCP, the payload mimics a URL-encoded format:
    ```text
    bv=99.0.0&request=[{"func":"HeartBeat","time":1794227766}]&seq=393&session=xxxx
    ```
**Protocol Field Breakdown:**
*   `bv`: Client version.
*   `request`: A JSON array containing the functional command (e.g., `HeartBeat`).
*   `seq`: A sequence number used for anti-replay protection.
*   `session`: The player's authentication token.

### 3.3 Encryption Detection (The Limitation)

While the heartbeat packets and some configuration packets were in plaintext, the critical business logic packets (e.g., combat results, pet refinement, gacha rewards) were strongly encrypted and appeared as unreadable ciphertext.

*   **Hex Signature**: The encrypted payload starts with `78 9C`, which is a standard Zlib compression header.
*   **Decompression Attempt & Failure**: Based on the header, I extracted the hex stream and attempted to decompress it using CyberChef (with the `Zlib Inflate` operation). However, the tool returned an error: `unsupported compression method`.
*   **Analysis & Conclusion**: This failure proved that the data was not simply compressed. It is **first compressed with Zlib, and then wrapped in an additional layer of strong encryption (likely AES or custom XOR)**. The `78 9C` header is either a remnant of the original compression or deliberately left there to mislead analysts. Without the decryption keys hidden deep inside the `libHOGame.so` native library, raw NIC capture alone cannot reveal the plaintext of these critical packets.


