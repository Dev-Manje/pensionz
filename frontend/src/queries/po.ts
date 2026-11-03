import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getDashboard, getOrganisation, getPayment, getPortalImport, getPortalMember, getPortalRequest, getPortalSchedule, getRemittances, listMySchemes,
  listPortalCategories, listPortalMembers, listPortalRequests,
} from "../api/po";
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

export function usePortalMembers(schemeId: string, q: string, currentOnly: boolean) {
  return useQuery({ queryKey: ["po", "members", schemeId, q, currentOnly], queryFn: () => listPortalMembers(schemeId, q, currentOnly) });
}

export function usePortalCategories(schemeId: string) {
  return useQuery({ queryKey: ["po", "categories", schemeId], queryFn: () => listPortalCategories(schemeId), staleTime: 5 * 60_000 });
}

export function usePortalMember(id: string | undefined) {
  return useQuery({ queryKey: ["po", "member", id], queryFn: () => getPortalMember(id!), enabled: !!id });
}

export function usePortalRequests(schemeId: string) {
  return useQuery({ queryKey: ["po", "requests", schemeId], queryFn: () => listPortalRequests(schemeId) });
}

export function usePortalRequest(id: string | undefined) {
  return useQuery({ queryKey: ["po", "request", id], queryFn: () => getPortalRequest(id!), enabled: !!id });
}

export function usePortalImport(id: string | undefined) {
  return useQuery({ queryKey: ["po", "import", id], queryFn: () => getPortalImport(id!), enabled: !!id });
}

// After a member request: refresh members, requests and the member page.
export function usePortalMemberRequest<A>(fn: (args: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["po", "members"] });
      qc.invalidateQueries({ queryKey: ["po", "member"] });
      qc.invalidateQueries({ queryKey: ["po", "requests"] });
    },
  });
}
