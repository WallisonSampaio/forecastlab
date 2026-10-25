import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/Layout";
import { Loader } from "./components/ui";
import Home from "./pages/Home";

const Overview = lazy(() => import("./pages/Overview"));
const Data = lazy(() => import("./pages/Data"));
const Forecasting = lazy(() => import("./pages/Forecasting"));
const ModelPerformance = lazy(() => import("./pages/ModelPerformance"));
const Scenarios = lazy(() => import("./pages/Scenarios"));
const SOP = lazy(() => import("./pages/SOP"));
const FVA = lazy(() => import("./pages/FVA"));
const AIAnalyst = lazy(() => import("./pages/AIAnalyst"));
const Alerts = lazy(() => import("./pages/Alerts"));
const Settings = lazy(() => import("./pages/Settings"));

export default function App() {
  return (
    <Suspense fallback={<Loader className="h-screen" />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/app" element={<AppLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<Overview />} />
          <Route path="data" element={<Data />} />
          <Route path="forecasting" element={<Forecasting />} />
          <Route path="models" element={<ModelPerformance />} />
          <Route path="scenarios" element={<Scenarios />} />
          <Route path="sop" element={<SOP />} />
          <Route path="fva" element={<FVA />} />
          <Route path="ai" element={<AIAnalyst />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
