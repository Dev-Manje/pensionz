import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { describeLists, listRows, proposeListRow } from "../api/setup";

export function useListSpecs() {
  return useQuery({ queryKey: ["setup", "specs"], queryFn: describeLists, staleTime: Infinity });
}

export function useListRows(name: string | null, parent?: string | null) {
  return useQuery({ queryKey: ["setup", "rows", name, parent ?? null], queryFn: () => listRows(name!, parent), enabled: !!name });
}

export function useProposeListRow(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: Record<string, unknown> }) => proposeListRow(name, body, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["setup", "rows", name] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}
