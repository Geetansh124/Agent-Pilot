"use client";

import React, { useEffect, useRef } from "react";
import { VoiceProviderId } from "./voiceProviders";

interface QuantumVoiceVisualizerProps {
  isAiSpeaking: boolean;
  micMuted: boolean;
  connected: boolean;
  connecting: boolean;
  provider: VoiceProviderId;
  micLevelRef: React.MutableRefObject<number>;
  aiLevelRef: React.MutableRefObject<number>;
}

interface Particle {
  x: number;
  y: number;
  angle: number;
  radius: number;
  baseRadius: number;
  speed: number;
  size: number;
  alpha: number;
  color: string;
}

export default function QuantumVoiceVisualizer({
  isAiSpeaking,
  micMuted,
  connected,
  connecting,
  provider,
  micLevelRef,
  aiLevelRef,
}: QuantumVoiceVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const smoothedAmpRef = useRef<number>(0.1);

  // Initialize particles once
  useEffect(() => {
    const particles: Particle[] = [];
    const colors = [
      "rgba(99, 102, 241, 0.8)",  // indigo
      "rgba(168, 85, 247, 0.85)", // violet
      "rgba(56, 189, 248, 0.9)",  // cyan
      "rgba(236, 72, 153, 0.75)", // pink
    ];

    for (let i = 0; i < 36; i++) {
      const angle = (i / 36) * Math.PI * 2;
      const baseRadius = 45 + Math.random() * 35;
      particles.push({
        x: 0,
        y: 0,
        angle,
        radius: baseRadius,
        baseRadius,
        speed: (Math.random() * 0.015 + 0.008) * (i % 2 === 0 ? 1 : -1),
        size: Math.random() * 2.5 + 1.2,
        alpha: Math.random() * 0.6 + 0.3,
        color: colors[i % colors.length],
      });
    }
    particlesRef.current = particles;
  }, []);

  // Main Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let phase = 0;

    const render = () => {
      const width = canvas.width;
      const height = canvas.height;
      const cx = width / 2;
      const cy = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Target amplitude computation
      let targetAmp = 0.08;
      if (connecting) {
        targetAmp = 0.25 + Math.sin(phase * 0.08) * 0.15;
      } else if (isAiSpeaking) {
        targetAmp = Math.max(aiLevelRef.current, 0.55);
      } else if (connected && !micMuted) {
        targetAmp = Math.max(micLevelRef.current, 0.12);
      } else if (micMuted) {
        targetAmp = 0.04;
      }

      // Smooth amplitude dampening (lerp)
      smoothedAmpRef.current += (targetAmp - smoothedAmpRef.current) * 0.18;
      const amp = smoothedAmpRef.current;

      // Color scheme based on state
      const primaryColor = isAiSpeaking
        ? "168, 85, 247"  // Violet/Purple
        : connecting
        ? "234, 179, 8"   // Amber
        : "99, 102, 241"; // Indigo/Electric blue

      const secondaryColor = isAiSpeaking
        ? "236, 72, 153"  // Pink
        : connecting
        ? "249, 115, 22"  // Orange
        : "56, 189, 248";  // Cyan

      // 1. Multi-layered Fluid Harmonic Waves
      const waves = [
        {
          freq: 0.012,
          speed: 0.04,
          amp: amp * 70,
          color: `rgba(${secondaryColor}, 0.75)`,
          fill: `rgba(${secondaryColor}, 0.06)`,
          width: 2.5,
        },
        {
          freq: 0.018,
          speed: -0.03,
          amp: amp * 55,
          color: `rgba(${primaryColor}, 0.8)`,
          fill: `rgba(${primaryColor}, 0.08)`,
          width: 3.0,
        },
        {
          freq: 0.024,
          speed: 0.055,
          amp: amp * 40,
          color: "rgba(56, 189, 248, 0.85)",
          fill: "rgba(56, 189, 248, 0.05)",
          width: 2.0,
        },
        {
          freq: 0.032,
          speed: -0.045,
          amp: amp * 25,
          color: "rgba(147, 51, 234, 0.6)",
          fill: "transparent",
          width: 1.5,
        },
      ];

      // Draw waves with harmonic envelope (attenuates near edges for clean containment)
      waves.forEach((w) => {
        ctx.beginPath();
        for (let x = 0; x <= width; x += 3) {
          // Envelope: cosine window to taper wave at canvas borders
          const env = Math.sin((x / width) * Math.PI);
          const y = cy + Math.sin(x * w.freq + phase * w.speed) * w.amp * env;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }

        ctx.strokeStyle = w.color;
        ctx.lineWidth = w.width;
        ctx.stroke();

        // Fluid gradient under-fill
        if (w.fill !== "transparent") {
          ctx.lineTo(width, height);
          ctx.lineTo(0, height);
          ctx.closePath();
          ctx.fillStyle = w.fill;
          ctx.fill();
        }
      });

      // 2. Radiant 3D Quantum Energy Orb (Center)
      const orbRadius = 40 + amp * 38;
      const outerGlowRadius = orbRadius * 2.4;

      // Outer radial aura
      const auraGrad = ctx.createRadialGradient(cx, cy, orbRadius * 0.4, cx, cy, outerGlowRadius);
      auraGrad.addColorStop(0, `rgba(${primaryColor}, ${0.5 + amp * 0.4})`);
      auraGrad.addColorStop(0.5, `rgba(${secondaryColor}, ${0.2 + amp * 0.25})`);
      auraGrad.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.fillStyle = auraGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, outerGlowRadius, 0, Math.PI * 2);
      ctx.fill();

      // Pulsating orbital rings
      const rings = [
        { r: orbRadius * 1.05, stroke: `rgba(${secondaryColor}, 0.7)`, width: 1.5, rot: phase * 0.02 },
        { r: orbRadius * 0.85, stroke: `rgba(${primaryColor}, 0.85)`, width: 2.0, rot: -phase * 0.025 },
        { r: orbRadius * 0.65, stroke: "rgba(255, 255, 255, 0.9)", width: 1.2, rot: phase * 0.035 },
      ];

      rings.forEach((ring) => {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(ring.rot);
        ctx.beginPath();
        // Slightly eccentric ellipse for 3D orbital perspective
        ctx.ellipse(0, 0, ring.r, ring.r * 0.88, 0, 0, Math.PI * 2);
        ctx.strokeStyle = ring.stroke;
        ctx.lineWidth = ring.width;
        ctx.stroke();
        ctx.restore();
      });

      // Quantum Core
      const coreGrad = ctx.createRadialGradient(cx - 5, cy - 5, 2, cx, cy, orbRadius * 0.6);
      coreGrad.addColorStop(0, "rgba(255, 255, 255, 0.95)");
      coreGrad.addColorStop(0.35, `rgba(${secondaryColor}, 0.8)`);
      coreGrad.addColorStop(0.8, `rgba(${primaryColor}, 0.9)`);
      coreGrad.addColorStop(1, "rgba(0, 0, 0, 0.1)");

      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, orbRadius * 0.6, 0, Math.PI * 2);
      ctx.fill();

      // 3. Floating Quantum Particle Constellation
      particlesRef.current.forEach((p) => {
        p.angle += p.speed;
        const currentDist = p.baseRadius + amp * 60;
        p.x = cx + Math.cos(p.angle) * currentDist;
        p.y = cy + Math.sin(p.angle) * (currentDist * 0.85);

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * (1 + amp * 0.5), 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0;
      });

      phase += 1;
      animFrameRef.current = requestAnimationFrame(render);
    };

    render();
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [isAiSpeaking, micMuted, connected, connecting, provider]);

  return (
    <div className="relative flex items-center justify-center w-full h-[280px]">
      <canvas
        ref={canvasRef}
        width={760}
        height={280}
        className="w-full max-w-[760px] h-[280px] drop-shadow-[0_0_35px_rgba(99,102,241,0.25)]"
      />
    </div>
  );
}
