import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createApplication, getApplication, getMyApplication, getSuggestedTerms, listApplicationFunds, listApplications, listMyApplications,
  proposeTerms, rejectApplication, returnApplication, saveApplication, startApplicationKyc, submitApplication, withdrawApplication,
  type EmployerApplicationInput, type EmployerApplicationStatus, type FinalTermsInput,
} from "../api/employerApplications";

export const applicationKeys = {
  all: ["employer-applications"] as const,
  funds: ["employer-applications", "funds"] as const,
  mine: ["employer-applications", "mine"] as const,
  myOne: (id: string) => ["employer-applications", "mine", id] as const,
  staff: (status?: string) => ["employer-applications", "staff", status ?? "all"] as const,
  staffOne: (id: string) => ["employer-applications", "staff-one", id] as const,
};

// ---- portal

export const useApplicationFunds = () => useQuery({ queryKey: applicationKeys.funds, queryFn: listApplicationFunds });
export const useMyApplications = () => useQuery({ queryKey: applicationKeys.mine, queryFn: listMyApplications });
export const useMyApplication = (id: string | undefined) =>
  useQuery({ queryKey: applicationKeys.myOne(id ?? ""), queryFn: () => getMyApplication(id!), enabled: !!id });

function useApplicationMutation<T, R>(fn: (arg: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: applicationKeys.all });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["po"] });
    },
  });
}

export const useCreateApplication = () => useApplicationMutation((input: EmployerApplicationInput) => createApplication(input));
export const useSaveApplication = () =>
  useApplicationMutation(({ id, input }: { id: string; input: EmployerApplicationInput }) => saveApplication(id, input));
export const useStartApplicationKyc = () => useApplicationMutation((id: string) => startApplicationKyc(id));
export const useSubmitApplication = () => useApplicationMutation((id: string) => submitApplication(id));
export const useWithdrawApplication = () => useApplicationMutation((id: string) => withdrawApplication(id));

// ---- staff

export const useApplications = (status?: EmployerApplicationStatus) =>
  useQuery({ queryKey: applicationKeys.staff(status), queryFn: () => listApplications(status) });
export const useApplication = (id: string | undefined) =>
  useQuery({ queryKey: applicationKeys.staffOne(id ?? ""), queryFn: () => getApplication(id!), enabled: !!id });
export const useSuggestedTerms = (id: string, enabled: boolean) =>
  useQuery({ queryKey: ["employer-applications", "suggested", id], queryFn: () => getSuggestedTerms(id), enabled });
export const useReturnApplication = () => useApplicationMutation(({ id, note }: { id: string; note: string }) => returnApplication(id, note));
export const useRejectApplication = () => useApplicationMutation(({ id, note }: { id: string; note: string }) => rejectApplication(id, note));
export const useProposeTerms = () =>
  useApplicationMutation(({ id, input }: { id: string; input: FinalTermsInput }) => proposeTerms(id, input));
