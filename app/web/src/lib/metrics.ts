import {
  Activity,
  BatteryCharging,
  Bike,
  Dumbbell,
  Flame,
  Footprints,
  Gauge,
  HeartPulse,
  Moon,
  Mountain,
  PersonStanding,
  Waves,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { C } from "./theme";

export interface MetricStyle {
  color: string;
  icon: LucideIcon;
  blurb: string;
}

export const METRIC_STYLES: Record<string, MetricStyle> = {
  hrv: { color: C.mint, icon: Waves, blurb: "Overnight heart-rate variability" },
  hrv_weekly: { color: C.mint, icon: Waves, blurb: "7-day HRV average" },
  resting_hr: { color: C.coral, icon: HeartPulse, blurb: "Lowest sustained heart rate" },
  sleep_hours: { color: C.violet, icon: Moon, blurb: "Time asleep" },
  sleep_score: { color: C.violet, icon: Moon, blurb: "Garmin sleep score" },
  deep_sleep_h: { color: C.violet, icon: Moon, blurb: "Deep sleep" },
  rem_sleep_h: { color: C.violet, icon: Moon, blurb: "REM sleep" },
  body_battery: { color: C.gold, icon: BatteryCharging, blurb: "Daily peak Body Battery" },
  body_battery_low: { color: C.gold, icon: BatteryCharging, blurb: "Daily low Body Battery" },
  stress: { color: C.amber, icon: Zap, blurb: "Average daily stress" },
  sleep_stress: { color: C.amber, icon: Zap, blurb: "Average stress while asleep" },
  steps: { color: C.lime, icon: Footprints, blurb: "Daily steps" },
  floors: { color: C.lime, icon: Mountain, blurb: "Floors climbed" },
  intensity_minutes: { color: C.lime, icon: Flame, blurb: "Moderate + vigorous minutes" },
  active_calories: { color: C.gold, icon: Flame, blurb: "Active calories burned" },
  respiration: { color: C.sky, icon: Wind, blurb: "Average waking respiration" },
  spo2: { color: C.coral, icon: HeartPulse, blurb: "Average blood oxygen" },
  training_load: { color: C.gold, icon: Activity, blurb: "Daily training load" },
  vo2max: { color: C.gold, icon: Gauge, blurb: "Garmin VO₂ max estimate" },
  fitness_age: { color: C.gold, icon: PersonStanding, blurb: "Garmin fitness age" },
};

export const fallbackStyle: MetricStyle = { color: C.cream, icon: Activity, blurb: "" };

interface ActivityFamily {
  label: string;
  icon: LucideIcon;
  color: string;
}

export const ACTIVITY_FAMILIES: Record<string, ActivityFamily> = {
  run: { label: "Run", icon: Footprints, color: C.lime },
  ride: { label: "Ride", icon: Bike, color: C.sky },
  swim: { label: "Swim", icon: Waves, color: C.mint },
  strength: { label: "Strength", icon: Dumbbell, color: C.coral },
  walk: { label: "Walk & hike", icon: Mountain, color: C.amber },
  mind: { label: "Yoga & mobility", icon: PersonStanding, color: C.violet },
  other: { label: "Other", icon: Activity, color: C.cream },
};

export function activityStyle(type: string, family: string) {
  const style = ACTIVITY_FAMILIES[family] ?? ACTIVITY_FAMILIES.other;
  const label = type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  return { ...style, label };
}
