import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "../../lib/api";
import type { GymExercise } from "../../lib/types";

/** The whole library (about 140 exercises) once, so steps can show names and measures without a request per row. */
export function useGymLibrary() {
  const q = useQuery({ queryKey: ["gym", "library-all"], queryFn: () => api.gymLibrary({ limit: 200 }), staleTime: 3_600_000 });
  const byId = useMemo(() => new Map<string, GymExercise>((q.data?.exercises ?? []).map((e) => [e.id, e])), [q.data]);
  return { ...q, byId };
}

export const useGymSettings = () => useQuery({ queryKey: ["gym", "settings"], queryFn: api.gymSettings });
export const useGymSessions = () => useQuery({ queryKey: ["gym", "sessions"], queryFn: api.gymSessions });
export const useGymTemplates = () => useQuery({ queryKey: ["gym", "templates"], queryFn: api.gymTemplates, staleTime: 3_600_000 });

export const PATTERN_LABEL: Record<string, string> = {
  squat: "Squat", hinge: "Hinge", lunge: "Lunge", push: "Push", pull: "Pull", carry: "Carry", core: "Core", plyometric: "Jumps",
  olympic: "Olympic", calves: "Calves", hips: "Hips", cardio: "Cardio", drill: "Drills", mobility: "Mobility",
};
export const LEVEL_LABEL = ["", "Very easy", "Easy", "Moderate", "Hard", "Very hard"];
export const EQUIPMENT_LABEL: Record<string, string> = {
  dumbbell: "Dumbbells", kettlebell: "Kettlebell", barbell: "Barbell", bench: "Bench", rack: "Rack", pullup_bar: "Pull-up bar", cable: "Cable machine", machine: "Machines",
  band: "Resistance band", box: "Box or step", sled: "Sled", skierg: "SkiErg", rower: "Rower", treadmill: "Treadmill", medicine_ball: "Medicine ball", sandbag: "Sandbag", rings: "Rings", bike: "Bike",
};
