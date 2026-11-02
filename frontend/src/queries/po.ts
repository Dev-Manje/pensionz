import { useQuery } from "@tanstack/react-query";
import { getDashboard, getOrganisation, listMySchemes } from "../api/po";

export const poKeys = {
  all: ["po"] as const,
  schemes: ["po", "schemes"] as const,
  dashboard: ["po", "dashboard"] as const,
  organisation: (schemeId: string) => ["po", "organisation", schemeId] as const,
};

export function useMySchemes() {
  return useQuery({ queryKey: poKeys.schemes, queryFn: listMySchemes });
}

export function usePoDashboard() {
  return useQuery({ queryKey: poKeys.dashboard, queryFn: getDashboard });
}

export function useOrganisation(schemeId: string) {
  return useQuery({ queryKey: poKeys.organisation(schemeId), queryFn: () => getOrganisation(schemeId) });
}
