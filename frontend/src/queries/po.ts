import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDashboard, getOrganisation, getPayment, getPortalSchedule, getRemittances, listMySchemes } from "../api/po";
import type { Schedule } from "../api/schedules";

export const poKeys = {
  all: ["po"] as const,
  schemes: ["po", "schemes"] as const,
  dashboard: ["po", "dashboard"] as const,
  organisation: (schemeId: string) => ["po", "organisation", schemeId] as const,
  remittances: (schemeId: string) => ["po", "remittances", schemeId] as const,
  schedule: (id: string) => ["po", "schedule", id] as const,
  payment: (id: string) => ["po", "payment", id] as const,
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

export function useRemittances(schemeId: string) {
  return useQuery({ queryKey: poKeys.remittances(schemeId), queryFn: () => getRemittances(schemeId) });
}

export function usePortalSchedule(id: string | undefined) {
  return useQuery({ queryKey: poKeys.schedule(id ?? ""), queryFn: () => getPortalSchedule(id!), enabled: !!id });
}

export function usePayment(id: string | undefined) {
  return useQuery({ queryKey: poKeys.payment(id ?? ""), queryFn: () => getPayment(id!), enabled: !!id });
}

// Every schedule change returns the whole schedule: keep it, and refresh the history and dashboard.
export function usePortalScheduleChange<A>(id: string, fn: (args: A) => Promise<Schedule>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      qc.setQueryData(poKeys.schedule(id), data);
      qc.invalidateQueries({ queryKey: ["po", "remittances"] });
      qc.invalidateQueries({ queryKey: poKeys.dashboard });
    },
  });
}
