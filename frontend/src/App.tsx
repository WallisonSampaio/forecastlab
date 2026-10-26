import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { AppLayout } from "./components/Layout";
import { RedirectWithSearch } from "./components/RedirectWithSearch";
import { Loader } from "./components/ui";
import { chapterOrDefault, ROUTES } from "./lib/routes";
import Home from "./pages/Home";

/* Journey (spec §1.1): Entrada -> Relatório -> Desvios. */
const Entrada = lazy(() => import("./pages/Entrada"));
const Relatorio = lazy(() => import("./pages/Relatorio"));
const Desvios = lazy(() => import("./pages/Desvios"));
/* Tools and governance. */
const Data = lazy(() => import("./pages/Data"));
const Forecasting = lazy(() => import("./pages/Forecasting"));
const ModelPerformance = lazy(() => import("./pages/ModelPerformance"));
const Scenarios = lazy(() => import("./pages/Scenarios"));
const AIAnalyst = lazy(() => import("./pages/AIAnalyst"));
const Alerts = lazy(() => import("./pages/Alerts"));

/**
 * `/app/relatorio/:capitulo`: an unknown chapter goes to `resumo` (keeping the query string). The same
 * element stays mounted across chapters, so changing chapters never remounts the report.
 */
function ReportRoute() {
  const { capitulo } = useParams();
  if (chapterOrDefault(capitulo) !== capitulo) return <RedirectWithSearch to={ROUTES.relatorio("resumo")} />;
  return <Relatorio />;
}

/** Routes and redirects (spec §1.3). */
export default function App() {
  return (
    <Suspense fallback={<Loader className="h-screen" />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/app" element={<AppLayout />}>
          <Route index element={<Navigate to={ROUTES.entrada()} replace />} />
          <Route path="entrada" element={<Entrada />} />
          <Route path="relatorio" element={<RedirectWithSearch to={ROUTES.relatorio("resumo")} />} />
          <Route path="relatorio/:capitulo" element={<ReportRoute />} />
          <Route path="desvios" element={<Desvios />} />
          <Route path="forecasting" element={<Forecasting />} />
          <Route path="scenarios" element={<Scenarios />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="ai" element={<AIAnalyst />} />
          <Route path="models" element={<ModelPerformance />} />
          <Route path="data" element={<Data />} />
          {/* Legacy pages folded into the journey. */}
          <Route path="overview" element={<RedirectWithSearch to={ROUTES.relatorio("resumo")} />} />
          <Route path="sop" element={<RedirectWithSearch to={ROUTES.relatorio("meta")} />} />
          <Route path="fva" element={<RedirectWithSearch to={ROUTES.modelos("fva")} />} />
          <Route path="settings" element={<Navigate to={ROUTES.entrada()} replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
