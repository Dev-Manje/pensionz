import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  captureReceipt, confirmReceipt, declineReceipt, getReceipt, identifyReceipt, listReceipts, uploadProof,
  type ReceiptCaptureInput, type ReceiptConfirmInput, type ReceiptFilters,
} from "../api/receipts";

export const receiptKeys = {
  all: ["receipts"] as const,
  list: (fundId: string, f: ReceiptFilters) => ["receipts", "list", fundId, f] as const,
  detail: (id: string) => ["receipts", "detail", id] as const,
};

export function useReceipts(fundId: string, f: ReceiptFilters) {
  return useQuery({ queryKey: receiptKeys.list(fundId, f), queryFn: () => listReceipts(fundId, f), enabled: !!fundId, placeholderData: keepPreviousData });
}

export function useReceipt(id: string | undefined) {
  return useQuery({ queryKey: receiptKeys.detail(id ?? ""), queryFn: () => getReceipt(id!), enabled: !!id });
}

// Any receipt action can change lists, the ledger and the approvals queue.
function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: receiptKeys.all });
    qc.invalidateQueries({ queryKey: ["ledger"] });
    qc.invalidateQueries({ queryKey: ["approvals"] });
  };
}

export function useCaptureReceipt(fundId: string) {
  const done = useInvalidate();
  return useMutation({ mutationFn: (body: ReceiptCaptureInput) => captureReceipt(fundId, body), onSuccess: done });
}

export function useReceiptAction(id: string) {
  const done = useInvalidate();
  return useMutation({
    mutationFn: (
      a:
        | { action: "confirm"; body: ReceiptConfirmInput }
        | { action: "decline"; reason: string }
        | { action: "identify"; schemeId: string; note?: string }
        | { action: "proof"; file: File },
    ): Promise<unknown> => {
      switch (a.action) {
        case "confirm":
          return confirmReceipt(id, a.body);
        case "decline":
          return declineReceipt(id, a.reason);
        case "identify":
          return identifyReceipt(id, a.schemeId, a.note);
        case "proof":
          return uploadProof(id, a.file);
      }
    },
    onSuccess: done,
  });
}
