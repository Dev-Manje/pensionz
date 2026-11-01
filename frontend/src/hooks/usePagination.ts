import { useState, type ChangeEvent } from "react";

export function usePagination<T>(items: T[], initialRowsPerPage = 10) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(initialRowsPerPage);

  // Table content shifts (filters, deletions, reloads) can leave `page`
  // pointing past the new last page — clamp for display without setState
  // during render (that would risk an extra render / lint violation).
  const maxPage = Math.max(0, Math.ceil(items.length / rowsPerPage) - 1);
  const safePage = Math.min(page, maxPage);

  const start = safePage * rowsPerPage;
  const pageItems = items.slice(start, start + rowsPerPage);

  function handleChangePage(_: unknown, newPage: number) {
    setPage(newPage);
  }

  function handleChangeRowsPerPage(e: ChangeEvent<HTMLInputElement>) {
    setRowsPerPage(parseInt(e.target.value, 10));
    setPage(0);
  }

  return { page: safePage, rowsPerPage, pageItems, handleChangePage, handleChangeRowsPerPage };
}
