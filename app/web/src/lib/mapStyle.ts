import type { SkySpecification, StyleSpecification, TerrainSpecification } from "maplibre-gl";

export type Basemap = "dark" | "streets" | "satellite";

// Free, keyless providers. Viewing a map sends the visible tile area to them (never the activity data itself).
export const OFM = "https://tiles.openfreemap.org/styles";
export const DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
export const DEM_ATTRIBUTION =
  '<a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noopener">Terrain: Mapzen, AWS Open Data</a>';
const SAT_YEAR = 2025;
export const SATELLITE: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {
    satellite: {
      type: "raster",
      tiles: [`https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-${SAT_YEAR}_3857/default/g/{z}/{y}/{x}.jpg`],
      tileSize: 256,
      maxzoom: 14,
      attribution: `<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH</a> (Contains modified Copernicus Sentinel data ${SAT_YEAR})`,
    },
  },
  layers: [{ id: "satellite", type: "raster", source: "satellite", paint: { "raster-contrast": 0.1, "raster-saturation": 0.15 } }],
};
export const STYLES: Record<Basemap, string | StyleSpecification> = {
  dark: `${OFM}/dark`,
  streets: `${OFM}/liberty`,
  satellite: SATELLITE,
};
export const BASEMAPS: { value: Basemap; label: string }[] = [
  { value: "dark", label: "Dark" },
  { value: "streets", label: "Streets" },
  { value: "satellite", label: "Satellite" },
];
export const terrainFor = (exaggeration: number): TerrainSpecification => ({ source: "dem", exaggeration });
export const SKY: SkySpecification = {
  "sky-color": "#0d1117",
  "horizon-color": "#2b3340",
  "fog-color": "#0b0b0c",
  "sky-horizon-blend": 0.6,
  "horizon-fog-blend": 0.7,
  "fog-ground-blend": 0.5,
  "atmosphere-blend": 0,
};
