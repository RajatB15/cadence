import { motion, useReducedMotion } from "motion/react";
import { useId } from "react";

interface Props {
  values: number[];
  color: string;
  width?: number;
  height?: number;
  className?: string;
  /** Dashed "usual" line, drawn at this value when it lies within the series range. */
  baseline?: number | null;
}

export function Sparkline({ values, color, width = 160, height = 44, className, baseline }: Props) {
  const id = useId();
  const reduce = useReducedMotion();
  const still = Boolean(reduce);
  if (values.length < 2) return <div style={{ height }} className={className} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 3;
  const pts = values.map((v, i) => [
    (i / (values.length - 1)) * width,
    pad + (1 - (v - min) / span) * (height - pad * 2),
  ]);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lx, ly] = pts[pts.length - 1];
  const by = baseline != null && baseline >= min && baseline <= max ? pad + (1 - (baseline - min) / span) * (height - pad * 2) : null;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      style={{ height, width: "100%", overflow: "visible" }}
      aria-hidden
    >
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
        <clipPath id={`${id}-reveal`}>
          <motion.rect
            x="-4" y="-4" height={height + 8}
            initial={{ width: still ? width + 8 : 0 }}
            whileInView={{ width: width + 8 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2, ease: [0.2, 0.9, 0.1, 1] }}
          />
        </clipPath>
      </defs>
      {by != null && <line x1="0" x2={width} y1={by} y2={by} stroke={color} strokeOpacity="0.45" strokeWidth="1" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />}
      <motion.path
        d={`${line} L${width},${height} L0,${height} Z`}
        fill={`url(#${id})`}
        initial={{ opacity: still ? 1 : 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, delay: 0.5 }}
      />
      <motion.path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        clipPath={`url(#${id}-reveal)`}
      />
      <motion.path
        d={`M${lx.toFixed(1)},${ly.toFixed(1)}h0`}
        stroke={color}
        strokeOpacity="0.25"
        strokeWidth="11"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        initial={{ opacity: still ? 1 : 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ delay: 1.1 }}
      />
      <motion.path
        d={`M${lx.toFixed(1)},${ly.toFixed(1)}h0`}
        stroke={color}
        strokeWidth="5.5"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        initial={{ opacity: still ? 1 : 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ delay: 1.1 }}
      />
    </svg>
  );
}
