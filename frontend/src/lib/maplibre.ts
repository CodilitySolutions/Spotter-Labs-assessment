import { setWorkerUrl } from 'maplibre-gl';
// Let Vite bundle MapLibre's worker (with its shared chunk) as a proper worker entry.
// MapLibre's default `new URL(file, import.meta.url)` lookup breaks under Vite's dependency
// pre-bundling in dev and isn't copied into production builds.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

setWorkerUrl(workerUrl);
