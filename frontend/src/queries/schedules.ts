import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  allocateSchedule, createSchedule, getAllocationPreview, getSchedule, listSchedules, removeScheduleLine, reverseAllocation, saveScheduleLine, scheduleAction, uploadNewSchedule, uploadScheduleFile,
  type Schedule, type ScheduleFilters, type ScheduleLineInput,
} from "../api/schedules";

export const scheduleKeys = {
  all: ["schedules"] as const,
  list: (fundId: string, f: ScheduleFilters) => ["schedules", "list", fundId, f] as const,
  detail: (id: string) => ["schedules", "detail", id] as const,
};

export function useSchedules(fundId: string, f: ScheduleFilters) {
  return useQuery({ queryKey: scheduleKeys.list(fundId, f), queryFn: () => listSchedules(fundId, f), enabled: !!fundId, placeholderData: keepPreviousData });
}

export function useSchedule(id: string | undefined) {
  return useQuery({ queryKey: scheduleKeys.detail(id ?? ""), queryFn: () => getSchedule(id!), enabled: !!id });
}

export function useCreateSchedule(fundId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (a: { schemeId: string; month: string; supplementary: boolean; prefill: boolean; file?: File | null }) =>
      a.file
        ? uploadNewSchedule(fundId, a.schemeId, a.month, a.supplementary, a.file)
        : createSchedule(fundId, { scheme_id: a.schemeId, contribution_month: a.month, supplementary: a.supplementary, prefill: a.prefill }),
    onSuccess: () => qc.invalidateQueries({ queryKey: scheduleKeys.all }),
  });
}

// Every change returns the whole schedule: put it straight into the cache.
export function useScheduleChange(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (
      a:
        | { kind: "action"; action: "submit" | "reopen" | "cancel" | "fill-expected" }
        | { kind: "upload"; file: File }
        | { kind: "save"; lineId: string | null; body: ScheduleLineInput }
        | { kind: "remove"; lineId: string },
    ): Promise<Schedule> => {
      switch (a.kind) {
        case "action":
          return scheduleAction(id, a.action);
        case "upload":
          return uploadScheduleFile(id, a.file);
        case "save":
          return saveScheduleLine(id, a.lineId, a.body);
        case "remove":
          return removeScheduleLine(id, a.lineId);
      }
    },
    onSuccess: (data) => {
      qc.setQueryData(scheduleKeys.detail(id), data);
      qc.invalidateQueries({ queryKey: ["schedules", "list"] });
      qc.invalidateQueries({ queryKey: ["schedules", "allocation", id] });
    },
  });
}

export function useAllocationPreview(id: string, enabled: boolean) {
  return useQuery({ queryKey: ["schedules", "allocation", id], queryFn: () => getAllocationPreview(id), enabled });
}

export function useAllocate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (receipts: { receipt_id: string; amount: string }[] | null) => allocateSchedule(id, receipts),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scheduleKeys.all });
      qc.invalidateQueries({ queryKey: ["receipts"] });
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}

export function useReverseAllocation(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => reverseAllocation(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scheduleKeys.all });
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}
