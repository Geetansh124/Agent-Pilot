# UI/UX Design Specification
## Authentication, User Spaces & Google Drive Document Hub

| Design Spec | Details |
|---|---|
| **Theme** | Midnight Glass (Dark Mode with Ambient Indigo Glow) |
| **Typography** | Inter (`next/font/google`), Tracking-tight |
| **Styling Tokens** | Tailwind CSS + Glassmorphism Utilities (`.glass-input-box`, `.surface-card`, `.ambient-glow`) |
| **Components** | Auth Modal, User Profile Menu, Knowledge Base Cloud Drawer |

---

## 1. Visual Aesthetics & Design System Tokens

```
Surface Layers:
  --bg-primary:      #09090b (Deep obsidian)
  --bg-glass:        rgba(18, 18, 22, 0.75) with backdrop-blur-xl
  --border-subtle:   rgba(255, 255, 255, 0.08)
  --border-specular: rgba(255, 255, 255, 0.16)

Accent Gradients:
  --accent-cyan:     #38bdf8 (Web scraping & tools)
  --accent-indigo:   #6366f1 (Primary pilot action & branding)
  --accent-emerald:  #10b981 (Connected / Drive Synced state)
  --accent-amber:    #f59e0b (Data profiling & warnings)
```

---

## 2. Authentication Modal Wireframe

When an unauthenticated user opens Agent-Pilot or clicks "Sign In", an elegant glassmorphic modal opens:

```
┌────────────────────────────────────────────────────────┐
│                   Agent-Pilot Login                    │
│                                                        │
│       [ ✈️ Agent-Pilot Metallic 3D Logo ]              │
│                                                        │
│          [  Sign In  ]   [  Create Account  ]          │
│  ────────────────────────────────────────────────────  │
│                                                        │
│  Email Address                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ user@example.com                                 │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  Password                                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ••••••••••••••••••                           [👁️] │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Sign In to Workspace                │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  🔒 Multi-tenant encrypted storage · Google Drive sync │
└────────────────────────────────────────────────────────┘
```

---

## 3. Sidebar & User Profile Component

The sidebar bottom section displays the active authenticated user profile:

```
┌──────────────────────────────────────┐
│ [≡] Agent-Pilot   Autonomous Space   │
├──────────────────────────────────────┤
│ [+ New Chat]                         │
│                                      │
│ KNOWLEDGE BASE                       │
│ ┌──────────────────────────────────┐ │
│ │ ☁️ 4 Documents Synced (G-Drive)  │ │
│ │ [ Manage Document Hub ]          │ │
│ └──────────────────────────────────┘ │
│                                      │
│ CHATS                                │
│ • Financial Modeling Q3              │
│ • Deep Research - AI SDK             │
│ • Python Sandbox Run                 │
│                                      │
├──────────────────────────────────────┤
│ 👤 Alex Vance                        │
│    alex@company.com  [PRO]           │
│    [⚙️ Settings]   [🚪 Sign Out]      │
└──────────────────────────────────────┘
```

---

## 4. Google Drive Document Management Hub (Drawer/Modal)

Users can review their permanently stored Google Drive documents even across sessions:

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 📄 Document Cloud Hub                                                   [✕]│
│ All documents are securely stored in your personal Google Drive space.     │
├────────────────────────────────────────────────────────────────────────────┤
│                                                        [+ Upload Document] │
│                                                                            │
│  Document Name          Size     Chunks    Drive Status        Action      │
│ ────────────────────────────────────────────────────────────────────────── │
│  📄 Q3_Earnings.pdf     2.4 MB   48 chunks  🟢 Synced to Drive  [Attach] [🗑]│
│  📄 Tech_Spec_v2.docx   850 KB   18 chunks  🟢 Synced to Drive  [Attach] [🗑]│
│  📊 Users_Churn.csv     1.1 MB   32 chunks  🟢 Synced to Drive  [Attach] [🗑]│
│                                                                            │
│ 💡 Click [Attach] to ground your current chat conversation in any document.│
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Interaction States & Micro-Animations

1. **Drive Syncing Pulse**: When uploading, the cloud icon gently breathes with an amber-to-emerald transition (`animate-pulse`).
2. **Document Attached Chip**: In the chat input, an attached document appears as a persistent pill tag with a dismiss (`✕`) button.
3. **Session Restore Indicator**: When opening the app, a subtle 1-second toast appears: `☁️ Workspace restored from Google Drive`.
