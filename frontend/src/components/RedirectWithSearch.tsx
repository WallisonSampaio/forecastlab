import { Navigate, useLocation } from "react-router-dom";

import { mergeSearch } from "../lib/routes";

/**
 * `<Navigate replace>` that keeps the query string (spec §1.3):
 * `/app/overview?region=Sul` -> `/app/relatorio/resumo?region=Sul`. When `to` already has a query
 * string the two are merged (`to` wins on duplicated keys): `/app/fva?x=1` -> `/app/models?tab=fva&x=1`.
 */
export function RedirectWithSearch({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={mergeSearch(to, location.search)} replace />;
}

export default RedirectWithSearch;
