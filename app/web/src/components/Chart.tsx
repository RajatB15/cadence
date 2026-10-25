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
  textStyle: { fontFamily: "Manrope Variable, sans-serif", color: "#8d8a82" },
  animationDuration: 900,
  animationEasing: "cubicOut" as const,
  grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#121213",
    borderColor: "#34343a",
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: "#ecebe6", fontSize: 12 },
    axisPointer: { type: "line", lineStyle: { color: "#5c5a55", type: "dashed" } },
  },
  xAxis: {
    type: "time",
    axisLine: { lineStyle: { color: "#262629" } },
    axisTick: { show: false },
    axisLabel: { color: "#5c5a55", fontSize: 11, hideOverlap: true },
    splitLine: { show: false },
  },
  yAxis: {
    type: "value",
    scale: true,
    axisLabel: { color: "#5c5a55", fontSize: 11 },
    splitLine: { lineStyle: { color: "#1c1c1f" } },
  },
};

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
      echarts.connect(group);
    }
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      instance.dispose();
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

  useEffect(() => {
    if (!visible) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    chart.current?.setOption({ ...option, animation: option.animation === false ? false : !reduce, animationDuration: 1100, animationEasing: "cubicOut" }, { notMerge: true });
  }, [option, visible]);

  return <div ref={ref} role="img" aria-label={label} style={{ height, width: "100%" }} />;
}
