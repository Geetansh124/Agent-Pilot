# Agent-Pilot: Pure Motion.dev Animation Architecture
> **Production Implementation Blueprint powered by [Motion (formerly Framer Motion)](https://motion.dev/)**
> React Animation Library Specification for Autonomous Workspace UI

---

## 1. Executive Summary & Design Vision

The animation system for **Agent-Pilot** is built authentically after **[Motion.dev](https://motion.dev/)** (`framer-motion`), providing declarative physics-based spring kinematics, native draggable gestures with elastic boundary returns, 3D cursor-tracking transforms via `useMotionValue`, interactive spring impulse oscillators, and fluid shared layout transitions using `layoutId`.

```
                  ╭────────────────────────────────────────╮
                  │   Motion.dev Engine · v13.5.0          │
                  │   Agent-Pilot Autonomous Workspace     │
                  ╰───────────────────┬────────────────────╯
                                      │
       ╭─────────────────┬────────────┴────┬─────────────────╮
       ▼                 ▼                 ▼                 ▼
[ 01 Gestures ]   [ 02 Transforms ]  [ 03 Springs ]   [ 04 Layout ]
(drag={true} &    (3D Cursor Tilt    (Stiffness: 450,  (layoutId Pill &
 spring snapback)  useMotionValue)    Oscillator Wave)  Morphing Cards)
```

---

## 2. Motion.dev Core Architecture

| Component | Motion.dev Primitives & Hooks | Realized Behavioral Effects |
| :--- | :--- | :--- |
| **`HeroMotionDeck.tsx`** | `motion.div`, `AnimatePresence`, `useMotionValue`, `useTransform`, `useSpring`, `layoutId` | • **Interactive Segmented Tabs**: Sliding background pill animated with `layoutId="motion-stage-pill"`.<br>• **Draggable Gestures Stage**: Pilot Core with `drag`, `dragConstraints`, and elastic spring snap-back (`bounceStiffness: 420`).<br>• **3D Tilt Stage**: Mouse coordinates drive perspective tilt via `useMotionValue` & `useSpring`.<br>• **Spring Kinematics**: Interactive oscillator trigger with real-time telemetry readout.<br>• **Capability Atlas**: 3 feature cards with spring hover (`whileHover={{ y: -3, scale: 1.02 }}`) and prompt loader dispatchers. |
| **`MotionThinkingBadge.tsx`** | `motion.div`, `motion.span`, `AnimatePresence` | • **Orbital Carrier Ring**: Continuously rotating carrier with a pulsing energy dot (`rotate: 360` in `1.8s`).<br>• **Equalizer Activity Bars**: Staggered keyframe scaling (`scaleY: [0.2, 1, 0.2]`) across 4 color channels.<br>• **Spring Mode Presence**: Tool telemetry pills mount/unmount using `<AnimatePresence mode="wait">`. |
| **Chat Message Stream** | `motion.div`, `AnimatePresence` | • **Presence Fade-in**: Incoming assistant responses and streaming chunks mount with smooth vertical entrance (`initial={{ opacity: 0, y: 8 }}`). |

---

## 3. Motion.dev Code Patterns Implemented

### A. Real-Time Draggable Gesture with Spring Snap-Back
```tsx
<motion.div
  drag
  dragConstraints={{ left: -110, right: 110, top: -35, bottom: 35 }}
  dragElastic={0.25}
  dragTransition={{ bounceStiffness: 420, bounceDamping: 24 }}
  whileHover={{ scale: 1.06, cursor: "grab" }}
  whileDrag={{ scale: 1.15, cursor: "grabbing" }}
  onDrag={(_, info) => setDragOffset({ x: Math.round(info.offset.x), y: Math.round(info.offset.y) })}
  onDragEnd={() => setDragOffset({ x: 0, y: 0 })}
>
  ...
</motion.div>
```

### B. 3D Tilt Stage Driven by Motion Values & Spring Physics
```tsx
const cardX = useMotionValue(0);
const cardY = useMotionValue(0);
const rotateXRaw = useTransform(cardY, [-60, 60], [14, -14]);
const rotateYRaw = useTransform(cardX, [-100, 100], [-16, 16]);
const rotateX = useSpring(rotateXRaw, { stiffness: 350, damping: 25 });
const rotateY = useSpring(rotateYRaw, { stiffness: 350, damping: 25 });
```

### C. Animated Segmented Controller with `layoutId`
```tsx
{isActive && (
  <motion.div
    layoutId="motion-stage-pill"
    className="absolute inset-0 rounded-lg bg-white/[0.12] border border-white/15"
    transition={{ type: "spring", stiffness: 450, damping: 30 }}
  />
)}
```

---

## 4. Ruflo Swarm Topology & Verification Status

- **Swarm ID**: `swarm-1790882421603-if5e4b` (Hierarchical topology, 8 max agents).
- **Active Agents**: `researcher`, `architect`, `coder`, `tester`, `reviewer`.
- **Diagnostics**: `ruflo doctor` passed (21 passed).
- **Build Status**: `npm run build` completed with **exit code 0** (zero warnings or type errors).
- **File Lengths**: Both `HeroMotionDeck.tsx` (458 lines) and `page.tsx` (459 lines) remain strictly under 500 lines.
- **Local Dev Server**: Active on `http://localhost:3000` (Next.js 14, 200 OK).
- **Backend API**: Active on `http://127.0.0.1:8000` (FastAPI, status: ok).
