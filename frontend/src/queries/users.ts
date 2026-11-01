import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listUsers, proposeUser, proposeUserUpdate, sendPasswordLink } from "../api/users";
import type { UserCreateInput, UserUpdateInput } from "../api/types";

export function useUsers(q: string) {
  return useQuery({ queryKey: ["users", q], queryFn: () => listUsers(q || undefined) });
}

export function useProposeUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: UserCreateInput) => proposeUser(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });
}

export function useProposeUserUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UserUpdateInput }) => proposeUserUpdate(id, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });
}

export function useSendPasswordLink() {
  return useMutation({ mutationFn: (id: string) => sendPasswordLink(id) });
}
