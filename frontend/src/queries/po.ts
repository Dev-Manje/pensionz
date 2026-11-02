import { useQuery } from "@tanstack/react-query";
import { listMySchemes } from "../api/po";

export const poKeys = {
  all: ["po"] as const,
  schemes: ["po", "schemes"] as const,
};

export function useMySchemes() {
  return useQuery({ queryKey: poKeys.schemes, queryFn: listMySchemes });
}
