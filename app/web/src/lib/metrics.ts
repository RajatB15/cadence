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

export interface MetricStyle {
  color: string;
  icon: LucideIcon;
  blurb: string;
}

export const METRIC_STYLES: Record<string, MetricStyle> = {
  hrv: { color: "#9b8cff", icon: Waves, blurb: "Overnight heart-rate variability" },
  hrv_weekly: { color: "#9b8cff", icon: Waves, blurb: "7-day HRV average" },
  resting_hr: { color: "#ff6a55", icon: HeartPulse, blurb: "Lowest sustained heart rate" },
  sleep_hours: { color: "#6cc7ff", icon: Moon, blurb: "Time asleep" },
  sleep_score: { color: "#6cc7ff", icon: Moon, blurb: "Garmin sleep score" },
  deep_sleep_h: { color: "#6cc7ff", icon: Moon, blurb: "Deep sleep" },
  rem_sleep_h: { color: "#6cc7ff", icon: Moon, blurb: "REM sleep" },
  body_battery: { color: "#c8f560", icon: BatteryCharging, blurb: "Daily peak Body Battery" },
  body_battery_low: { color: "#c8f560", icon: BatteryCharging, blurb: "Daily low Body Battery" },
  stress: { color: "#ffbe55", icon: Zap, blurb: "Average daily stress" },
  sleep_stress: { color: "#ffbe55", icon: Zap, blurb: "Average stress while asleep" },
  steps: { color: "#5be3b0", icon: Footprints, blurb: "Daily steps" },
  floors: { color: "#5be3b0", icon: Mountain, blurb: "Floors climbed" },
  intensity_minutes: { color: "#ff9a5b", icon: Flame, blurb: "Moderate + vigorous minutes" },
  active_calories: { color: "#ff9a5b", icon: Flame, blurb: "Active calories burned" },
  respiration: { color: "#6cc7ff", icon: Wind, blurb: "Average waking respiration" },
  spo2: { color: "#ff6a55", icon: HeartPulse, blurb: "Average blood oxygen" },
  training_load: { color: "#d9b26a", icon: Activity, blurb: "Daily training load" },
  vo2max: { color: "#d9b26a", icon: Gauge, blurb: "Garmin VO₂ max estimate" },
  fitness_age: { color: "#d9b26a", icon: PersonStanding, blurb: "Garmin fitness age" },
};

export const fallbackStyle: MetricStyle = { color: "#f2e8cf", icon: Activity, blurb: "" };

interface ActivityFamily {
  label: string;
  icon: LucideIcon;
  color: string;
}

export const ACTIVITY_FAMILIES: Record<string, ActivityFamily> = {
  run: { label: "Run", icon: Footprints, color: "#c8f560" },
  ride: { label: "Ride", icon: Bike, color: "#6cc7ff" },
  swim: { label: "Swim", icon: Waves, color: "#5be3b0" },
  strength: { label: "Strength", icon: Dumbbell, color: "#ff6a55" },
  walk: { label: "Walk & hike", icon: Mountain, color: "#ffbe55" },
  mind: { label: "Yoga & mobility", icon: PersonStanding, color: "#9b8cff" },
  other: { label: "Other", icon: Activity, color: "#f2e8cf" },
};

export function activityStyle(type: string, family: string) {
  const style = ACTIVITY_FAMILIES[family] ?? ACTIVITY_FAMILIES.other;
  const label = type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  return { ...style, label };
}
