import { useSearchParams } from "react-router-dom";

// One query-string parameter as state, so it survives refresh, works with
// the back button and can be shared as a link (?tab=banks, ?case=<id>).
// Other parameters on the URL are left alone.
export function useUrlParam(name: string): [string | null, (value: string | null) => void] {
  const [params, setParams] = useSearchParams();
  function set(value: string | null) {
    // Start from the live URL, not react-router's `prev`: two setters called
    // in one handler (e.g. a filter and resetting ?page) would otherwise both
    // start from the same stale params and the second would undo the first.
    const next = new URLSearchParams(window.location.search);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  }
  return [params.get(name), set];
}

// A tab bar's selected tab in ?tab=, falling back to the first tab when the
// URL has none (or one this screen doesn't have).
export function useUrlTab<T extends string>(tabs: readonly T[]): [T, (tab: T) => void] {
  const [value, setValue] = useUrlParam("tab");
  const tab = tabs.includes(value as T) ? (value as T) : tabs[0];
  return [tab, (next: T) => setValue(next === tabs[0] ? null : next)];
}
