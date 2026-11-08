import { BarChart, CustomChart, LineChart, RadarChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef, useState } from "react";
import { C } from "../lib/theme";

echarts.use([
  LineChart,
  ScatterChart,
  BarChart,
  CustomChart,
  RadarChart,
  RadarComponent,
  GridComponent,
  TooltipComponent,
  MarkLineComponent,
  MarkAreaComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

export type ChartOption = echarts.EChartsCoreOption;

export const chartBase = {
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Manrope Variable, sans-serif", color: C.mute },
  animationDuration: 900,
  animationEasing: "cubicOut" as const,
  grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
  tooltip: {
    trigger: "axis",
    confine: true,
    backgroundColor: C.coal,
    borderColor: C.lineStrong,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: C.paper, fontSize: 12 },
    axisPointer: { type: "line", lineStyle: { color: C.faint, type: "dashed" } },
  },
  xAxis: {
    type: "time",
    axisLine: { lineStyle: { color: C.line } },
    axisTick: { show: false },
    axisLabel: { color: C.mute, fontSize: 11, hideOverlap: true },
    splitLine: { show: false },
  },
  yAxis: {
    type: "value",
    scale: true,
    axisLabel: { color: C.mute, fontSize: 11 },
    splitLine: { lineStyle: { color: C.grid } },
  },
};

const groupCounts = new Map<string, number>();

/** Identity of an option by content (functions by source), so re-renders that rebuild an identical option don't re-animate the chart. */
export function optionKey(option: ChartOption): string {
  try {
    return JSON.stringify(option, (_k, v) => (typeof v === "function" ? String(v) : v));
  } catch {
    return String(Math.random());
  }
}

export function Chart({
  option,
  height = 320,
  label,
  group,
  onPickX,
}: {
  option: ChartOption;
  height?: number;
  label: string;
  group?: string;
  onPickX?: (x: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [visible, setVisible] = useState(false);
  const pick = useRef(onPickX);
  pick.current = onPickX;

  useEffect(() => {
    if (!ref.current) return;
    const instance = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current = instance;
    instance.getZr().on("click", (e: { offsetX: number; offsetY: number }) => {
      if (!pick.current || !instance.containPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY])) return;
      const [x] = instance.convertFromPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY]) as number[];
      pick.current(x);
    });
    if (group) {
      instance.group = group;
      groupCounts.set(group, (groupCounts.get(group) ?? 0) + 1);
      echarts.connect(group);
    }
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      instance.dispose();
      if (group) {
        const left = (groupCounts.get(group) ?? 1) - 1;
        if (left <= 0) {
          groupCounts.delete(group);
          echarts.disconnect(group);
        } else groupCounts.set(group, left);
      }
      chart.current = null;
    };
  }, [group]);

  useEffect(() => {
    const node = ref.current;
    if (!node || visible) return;
    // Charts draw their entrance animation when scrolled into view, not while off-screen.
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && setVisible(true), { threshold: 0.15 });
    io.observe(node);
    return () => io.disconnect();
  }, [visible]);

  const latest = useRef(option);
  latest.current = option;
  const key = optionKey(option);
  useEffect(() => {
    if (!visible) return;
    const o = latest.current;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Keep tooltips inside the chart box so they never spill off a phone screen.
    chart.current?.setOption(
      { ...o, tooltip: Array.isArray(o.tooltip) ? o.tooltip : { confine: true, ...(o.tooltip ?? {}) }, animation: o.animation === false ? false : !reduce, animationDuration: 1100, animationEasing: "cubicOut" },
      { notMerge: true },
    );
  }, [key, visible, group]);

  return <div ref={ref} role="img" aria-label={label} style={{ height, width: "100%" }} />;
}
