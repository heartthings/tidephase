import { type SimulationNodeDatum, forceCollide, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force';
import { type PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from 'react';

import { type PlateForceItem, formatYi } from './types';

interface BubbleNode extends SimulationNodeDatum {
  code: string;
  displayR: number;
  name: string;
  side: 'in' | 'out';
  targetR: number;
  value: number;
}

interface Particle {
  alpha: number;
  life: number;
  side: 'in' | 'out';
  vx: number;
  vy: number;
  x: number;
  y: number;
}

interface Props {
  height?: number;
  items: PlateForceItem[];
  reducedMotion?: boolean;
}

const IN_COLOR = '#ff3b45';
const OUT_COLOR = '#2fd96a';
const MIN_R = 18;
const MAX_R = 78;

function radiusFromValue(absYi: number, maxAbs: number): number {
  if (maxAbs <= 0) return MIN_R;
  const t = Math.sqrt(absYi / maxAbs);
  return MIN_R + t * (MAX_R - MIN_R);
}

function drawBubble(ctx: CanvasRenderingContext2D, node: BubbleNode, opts: { now: number; reducedMotion: boolean }) {
  const { now, reducedMotion } = opts;
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  const r = node.displayR;
  const color = node.side === 'in' ? IN_COLOR : OUT_COLOR;

  const glow = ctx.createRadialGradient(x, y, r * 0.15, x, y, r * 1.35);
  glow.addColorStop(0, `${color}ee`);
  glow.addColorStop(0.55, `${color}99`);
  glow.addColorStop(1, `${color}00`);
  ctx.beginPath();
  ctx.fillStyle = glow;
  ctx.arc(x, y, r * 1.25, 0, Math.PI * 2);
  ctx.fill();

  const body = ctx.createRadialGradient(x - r * 0.25, y - r * 0.3, r * 0.1, x, y, r);
  body.addColorStop(0, '#ffffff33');
  body.addColorStop(0.35, `${color}dd`);
  body.addColorStop(1, `${color}aa`);
  ctx.beginPath();
  ctx.fillStyle = body;
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();

  ctx.beginPath();
  ctx.strokeStyle = `${color}cc`;
  ctx.lineWidth = 1.5;
  ctx.shadowColor = color;
  ctx.shadowBlur = 12;
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.shadowBlur = 0;

  if (!reducedMotion && r > 28) {
    const phase = (now / 1800 + (node.value > 0 ? 0 : 0.5)) % 1;
    for (let i = 0; i < 2; i += 1) {
      const p = (phase + i * 0.45) % 1;
      const ringR = r + 4 + p * 16;
      ctx.beginPath();
      ctx.strokeStyle = `${color}${Math.floor((1 - p) * 140)
        .toString(16)
        .padStart(2, '0')}`;
      ctx.lineWidth = 1.2;
      ctx.arc(x, y, ringR, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  const nameSize = Math.max(10, Math.min(15, r * 0.32));
  const valueSize = Math.max(9, Math.min(13, r * 0.26));
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#fff';
  ctx.font = `600 ${nameSize}px "PingFang SC", "Microsoft YaHei", sans-serif`;
  const shortName = node.name.length > 6 ? `${node.name.slice(0, 5)}…` : node.name;
  ctx.fillText(shortName, x, y - valueSize * 0.55);
  ctx.font = `500 ${valueSize}px "DIN Alternate", "Roboto Mono", monospace`;
  ctx.fillText(formatYi(node.value), x, y + nameSize * 0.55);
}

export function ForceBubbleChart({ height, items, reducedMotion = false }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ h: 720, w: 800 });
  const hoverRef = useRef<BubbleNode | null>(null);
  const [hoverLabel, setHoverLabel] = useState<string | null>(null);

  const nodesRef = useRef<BubbleNode[]>([]);
  const particlesRef = useRef<Particle[]>([]);
  const simRef = useRef<ReturnType<typeof forceSimulation<BubbleNode>> | null>(null);

  const prepared = useMemo(() => {
    const maxAbs = Math.max(...items.map(d => Math.abs(d.latestLargeForce)), 1);
    return items.map(d => {
      const value = d.latestLargeForce;
      const side: 'in' | 'out' = value >= 0 ? 'in' : 'out';
      return {
        code: d.code,
        displayR: radiusFromValue(Math.abs(value), maxAbs),
        name: d.name,
        side,
        targetR: radiusFromValue(Math.abs(value), maxAbs),
        value,
        x: undefined as number | undefined,
        y: undefined as number | undefined
      } satisfies BubbleNode;
    });
  }, [items]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      setSize({
        h: height ?? Math.max(560, rect.height),
        w: Math.max(320, rect.width)
      });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [height]);

  useEffect(() => {
    const { h, w } = size;
    const midY = h * 0.5;
    const prev = new Map(nodesRef.current.map(n => [n.code, n]));

    const nextNodes: BubbleNode[] = prepared.map(p => {
      const old = prev.get(p.code);
      const preferY = p.side === 'in' ? h * 0.28 : h * 0.72;
      return {
        ...p,
        displayR: old?.displayR ?? p.targetR * 0.6,
        vx: old?.vx ?? 0,
        vy: old?.vy ?? 0,
        x: old?.x ?? w * 0.5 + (Math.random() - 0.5) * w * 0.4,
        y: old?.y ?? preferY + (Math.random() - 0.5) * h * 0.12
      };
    });
    nodesRef.current = nextNodes;

    simRef.current?.stop();
    const sim = forceSimulation(nextNodes)
      .force('charge', forceManyBody().strength(-18))
      .force('x', forceX<BubbleNode>(w * 0.5).strength(0.06))
      .force('y', forceY<BubbleNode>(d => (d.side === 'in' ? h * 0.28 : h * 0.72)).strength(0.12))
      .force(
        'collide',
        forceCollide<BubbleNode>()
          .radius(d => d.displayR + 3)
          .iterations(2)
      )
      .alpha(0.7)
      .alphaDecay(0.022);

    // soft wall at midline
    sim.on('tick', () => {
      for (const n of nextNodes) {
        n.displayR += (n.targetR - n.displayR) * 0.08;
        if (n.side === 'in' && (n.y ?? 0) > midY - n.displayR - 6) {
          n.y = midY - n.displayR - 6;
          n.vy = (n.vy ?? 0) * -0.3;
        }
        if (n.side === 'out' && (n.y ?? 0) < midY + n.displayR + 6) {
          n.y = midY + n.displayR + 6;
          n.vy = (n.vy ?? 0) * -0.3;
        }
        n.x = Math.max(n.displayR, Math.min(w - n.displayR, n.x ?? 0));
        n.y = Math.max(n.displayR, Math.min(h - n.displayR, n.y ?? 0));
      }
      const collide = sim.force('collide') as ReturnType<typeof forceCollide<BubbleNode>>;
      collide.radius(d => d.displayR + 3);
    });

    simRef.current = sim;
    return () => {
      sim.stop();
    };
  }, [prepared, size]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;

    let raf = 0;
    let lastSpawn = 0;

    const loop = (now: number) => {
      const { h, w } = size;
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }

      ctx.clearRect(0, 0, w, h);

      // ambient
      const topGlow = ctx.createRadialGradient(w * 0.5, h * 0.22, 10, w * 0.5, h * 0.22, h * 0.4);
      topGlow.addColorStop(0, '#ff3b4522');
      topGlow.addColorStop(1, '#00000000');
      ctx.fillStyle = topGlow;
      ctx.fillRect(0, 0, w, h * 0.5);

      const botGlow = ctx.createRadialGradient(w * 0.5, h * 0.78, 10, w * 0.5, h * 0.78, h * 0.4);
      botGlow.addColorStop(0, '#2fd96a22');
      botGlow.addColorStop(1, '#00000000');
      ctx.fillStyle = botGlow;
      ctx.fillRect(0, h * 0.5, w, h * 0.5);

      const midY = h * 0.5;
      ctx.strokeStyle = '#ffffff22';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(w * 0.12, midY);
      ctx.lineTo(w * 0.88, midY);
      ctx.stroke();
      ctx.fillStyle = '#9aa3af';
      ctx.font = '12px "PingFang SC", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('主力净额 · 资金泡泡图', w * 0.5, midY - 8);

      if (!reducedMotion && now - lastSpawn > 90) {
        lastSpawn = now;
        for (let i = 0; i < 3; i += 1) {
          particlesRef.current.push({
            alpha: 0.55 + Math.random() * 0.3,
            life: 0.8 + Math.random() * 0.8,
            side: 'in',
            vx: (Math.random() - 0.5) * 0.4,
            vy: 0.6 + Math.random() * 0.9,
            x: w * (0.2 + Math.random() * 0.6),
            y: 8 + Math.random() * 20
          });
          particlesRef.current.push({
            alpha: 0.55 + Math.random() * 0.3,
            life: 0.8 + Math.random() * 0.8,
            side: 'out',
            vx: (Math.random() - 0.5) * 0.4,
            vy: -(0.6 + Math.random() * 0.9),
            x: w * (0.2 + Math.random() * 0.6),
            y: h - 8 - Math.random() * 20
          });
        }
        if (particlesRef.current.length > 160) {
          particlesRef.current.splice(0, particlesRef.current.length - 160);
        }
      }

      const nextParticles: Particle[] = [];
      for (const p of particlesRef.current) {
        p.x += p.vx;
        p.y += p.vy;
        p.life -= 0.016;
        p.alpha *= 0.985;
        const crossedMid = (p.side === 'in' && p.y > midY - 4) || (p.side === 'out' && p.y < midY + 4);
        const dead = p.life <= 0 || p.alpha < 0.05;
        if (!crossedMid && !dead) {
          ctx.beginPath();
          ctx.fillStyle = p.side === 'in' ? `rgba(255,59,69,${p.alpha})` : `rgba(47,217,106,${p.alpha})`;
          ctx.arc(p.x, p.y, 1.6, 0, Math.PI * 2);
          ctx.fill();
          nextParticles.push(p);
        }
      }
      particlesRef.current = nextParticles;

      const nodes = nodesRef.current;
      for (const n of nodes) {
        drawBubble(ctx, n, { now, reducedMotion });
      }

      const hover = hoverRef.current;
      if (hover) {
        const hx = hover.x ?? 0;
        const hy = hover.y ?? 0;
        ctx.beginPath();
        ctx.strokeStyle = '#ffffffaa';
        ctx.lineWidth = 2;
        ctx.arc(hx, hy, hover.displayR + 3, 0, Math.PI * 2);
        ctx.stroke();
      }

      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [reducedMotion, size]);

  const onPointerMove = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    let hit: BubbleNode | null = null;
    for (let i = nodesRef.current.length - 1; i >= 0; i -= 1) {
      const n = nodesRef.current[i];
      const dx = (n.x ?? 0) - x;
      const dy = (n.y ?? 0) - y;
      if (dx * dx + dy * dy <= n.displayR * n.displayR) {
        hit = n;
        break;
      }
    }
    hoverRef.current = hit;
    setHoverLabel(hit ? `${hit.name}  ${formatYi(hit.value)}` : null);
  };

  return (
    <div
      className="cf-chart-wrap"
      ref={wrapRef}
    >
      <canvas
        className="cf-canvas"
        ref={canvasRef}
        onPointerMove={onPointerMove}
        onPointerLeave={() => {
          hoverRef.current = null;
          setHoverLabel(null);
        }}
      />
      {hoverLabel ? <div className="cf-tooltip">{hoverLabel}</div> : null}
    </div>
  );
}
