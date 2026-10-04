# Android Companion & Mobile Deployment Guide
## Agent-Pilot: Mobile Web & Android TWA Architecture

This guide details the mobile architecture, PWA packaging, and native Android companion scaffolding for Agent-Pilot.

---

## 1. Architecture Overview

Agent-Pilot uses a **PWA-First Architecture** designed for seamless installation and native execution across modern mobile devices:

```
┌────────────────────────────────────────────────────────┐
│            Android Device / Chrome Browser             │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │   Trusted Web Activity (TWA) Native APK Wrapper  │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           │ Fullscreen Intent          │
│  ┌────────────────────────▼─────────────────────────┐  │
│  │   Agent-Pilot Mobile PWA                         │  │
│  │   - manifest.json (standalone display)           │  │
│  │   - Web Audio PCM 16kHz Recorder                 │  │
│  │   - Web Audio PCM 24kHz Player                   │  │
│  │   - Cyberpunk Flight Deck Canvas Wave HUD        │  │
│  └────────────────────────┬─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ WebSocket / REST API
┌───────────────────────────▼────────────────────────────┐
│      Cloudflare Edge Worker (soapy-pint.workers.dev)    │
│      - D1 Multi-Tenant Persistence                     │
│      - Gemini Live API Edge Proxy (16k in / 24k out)   │
│      - Edge Tools (Calculator, Search, Stocks, RAG)    │
└────────────────────────────────────────────────────────┘
```

---

## 2. Progressive Web App (PWA) Mobile Features

1. **Manifest Configuration**: [`frontend/public/manifest.json`](file:///d:/Main/Projects/Agent-Pilot/frontend/public/manifest.json)
   - `display: standalone`: Launches without browser address bars for a full-screen native app experience.
   - `theme_color: #09090b`: Matches the dark ambient glassmorphic color palette.
   - `background_color: #09090b`: Seamless splash screen rendering.
   - Maskable adaptive SVG and PNG high-resolution icons.

2. **Mobile Viewport Optimization**:
   - `viewport-fit=cover`: Supports notched displays and modern edge-to-edge Android status bars.
   - Native audio permission handling via `navigator.mediaDevices.getUserMedia`.

---

## 3. Native Android Companion APK Packaging

Using the `android` CLI and Bubblewrap, the live Cloudflare deployment can be packaged into a signed Android APK.

### Step 1: Install Android Prerequisites

Ensure Node.js and JDK 17+ are installed:
```powershell
npm install -g @bubblewrap/cli
```

### Step 2: Initialize Android TWA Project

```powershell
bubblewrap init --manifest https://agent-pilot.soapy-pint.workers.dev/manifest.json
```

Follow the interactive prompt:
- **Application Name**: `Agent-Pilot`
- **Package ID**: `com.agentpilot.app`
- **Host**: `agent-pilot.soapy-pint.workers.dev`
- **Start URL**: `/`
- **Display Mode**: `standalone`

### Step 3: Build & Sign Android APK

```powershell
bubblewrap build
```

This compiles `app-release-signed.apk` ready for installation on any physical device or Android Virtual Device (AVD).

---

## 4. Testing with Android CLI & ADB

To test on an Android Virtual Device (AVD):

```powershell
# List available emulators
emulator -list-avds

# Start target emulator
emulator -avd Pixel_8_Pro_API_34

# Install APK to device
adb install -r app-release-signed.apk

# Launch Agent-Pilot
adb shell am start -n com.agentpilot.app/.LauncherActivity
```

---

## 5. Mobile Audio Considerations

1. **Mic Permissions**:
   The TWA container shares Chrome's microphone permissions. The first time the user opens the Live Voice Flight Deck, Android displays the standard runtime permission prompt: `"Allow Agent-Pilot to record audio?"`.
2. **Audio Hardware Acceleration**:
   Android's native OpenSL ES and AAudio backends automatically resample 16kHz microphone capture and 24kHz speaker playback with low latency.
3. **Headphones / Echo Cancellation**:
   Always recommend using Bluetooth or wired earphones to prevent hardware acoustic feedback during full-duplex conversations.
