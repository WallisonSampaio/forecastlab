import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { isReportPath, PRESENTATION_PARAM } from "../lib/routes";

/**
 * Presentation mode (spec §1.6): `?apresentacao=1` on `/app/relatorio/*`. The shell (`Layout`) hides the
 * sidebar, topbar and footer and shows a floating "Sair da apresentação" button; Esc also leaves it.
 * The report uses `toggle` for its "Apresentar" button and the `P` key. Changes replace the history entry.
 */
export function usePresentationMode() {
  const location = useLocation();
  const navigate = useNavigate();
  const active =
    isReportPath(location.pathname) && new URLSearchParams(location.search).get(PRESENTATION_PARAM) === "1";

  const set = useCallback(
    (on: boolean) => {
      const sp = new URLSearchParams(location.search);
      if (on) sp.set(PRESENTATION_PARAM, "1");
      else sp.delete(PRESENTATION_PARAM);
      const search = sp.toString();
      navigate({ pathname: location.pathname, search: search ? `?${search}` : "" }, { replace: true });
    },
    [location.pathname, location.search, navigate],
  );

  const enter = useCallback(() => set(true), [set]);
  const exit = useCallback(() => set(false), [set]);
  const toggle = useCallback(() => set(!active), [set, active]);
  return { active, enter, exit, toggle };
}
