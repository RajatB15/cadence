import { motion } from "motion/react";
import { useId } from "react";

interface Props {
  values: number[];
  color: string;
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline({ values, color, width = 160, height = 44, className }: Props) {
  const id = useId();
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
            initial={{ width: 0 }}
            whileInView={{ width: width + 8 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2, ease: [0.2, 0.9, 0.1, 1] }}
          />
        </clipPath>
      </defs>
      <motion.path
        d={`${line} L${width},${height} L0,${height} Z`}
        fill={`url(#${id})`}
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, delay: 0.5 }}
      />
      <motion.path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        clipPath={`url(#${id}-reveal)`}
      />
      <motion.path
        d={`M${lx.toFixed(1)},${ly.toFixed(1)}h0`}
        stroke={color}
        strokeWidth="5"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ delay: 1.1 }}
      />
    </svg>
  );
}
