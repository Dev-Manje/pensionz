import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api/client";

// One cache for the whole app. Keys follow the backend's shape:
// ["party", id], ["distributor", "me"], ["distributor", id, "clients"] ...
// Mutations invalidate exactly the keys they change.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // A 4xx won't fix itself on retry (403, 404, validation) — only retry
      // network/server failures, and only once.
      retry: (failureCount, error) => !(error instanceof ApiError && error.status < 500) && failureCount < 1,
    },
  },
});
