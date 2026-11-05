import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

// One shared worker URL for every map (route map, share video) so the worker chunk is built and set once.
let done = false;
export function ensureMapWorker(): void {
  if (done) return;
  done = true;
  setWorkerUrl(workerUrl);
}
ensureMapWorker();
