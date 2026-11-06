import { useMutation, useQuery } from '@tanstack/react-query';
import type { Heatmap, LonLat, Place, Plan, PlanRequest } from '../types';
import { apiFetch } from './client';

export function usePlanMutation() {
  return useMutation({
    mutationFn: (request: PlanRequest) =>
      apiFetch<Plan>('/plan', { method: 'POST', body: JSON.stringify(request) }),
  });
}

/** Worldwide place search; `near` (e.g. the map's centre) ranks nearby results first. */
export function useGeocode(query: string, near: LonLat | null) {
  const q = query.trim();
  // Whole degrees, matching the backend's rounding, so small map pans reuse cached results.
  const bias = near ? ([Math.round(near[0]), Math.round(near[1])] as LonLat) : null;
  const params = new URLSearchParams({ q });
  if (bias) {
    params.set('lon', String(bias[0]));
    params.set('lat', String(bias[1]));
  }
  return useQuery({
    queryKey: ['geocode', q.toLowerCase(), bias?.join(',') ?? 'world'],
    queryFn: ({ signal }) => apiFetch<Place[]>(`/geocode?${params}`, { signal }),
    enabled: q.length >= 2,
    staleTime: 5 * 60_000,
    placeholderData: (previous) => previous,
  });
}

/** The plan's 0-48 h risk grid. Fetched once per plan; the slider never refetches. */
export function useHeatmap(planId: string | null) {
  return useQuery({
    queryKey: ['heatmap', planId],
    queryFn: ({ signal }) => apiFetch<Heatmap>(`/plan/${planId}/heatmap`, { signal }),
    enabled: planId !== null,
    staleTime: Infinity,
    retry: 1,
  });
}
