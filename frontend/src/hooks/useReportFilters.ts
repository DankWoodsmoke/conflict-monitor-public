import { useState } from "react";

/** Keep report criteria at workspace scope while feeds mount and unmount. */
export function useReportFilters() {
  const [search, setSearch] = useState("");
  const [minSev, setMinSev] = useState(1);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [sortMode, setSortMode] = useState<"new" | "sev" | "conf">("new");

  return {
    search, setSearch,
    minSev, setMinSev,
    typeFilter, setTypeFilter,
    sourceFilter, setSourceFilter,
    confirmedOnly, setConfirmedOnly,
    sortMode, setSortMode,
  };
}
