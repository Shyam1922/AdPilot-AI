import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";

// Pages load on demand, so heavy dependencies (Recharts) only ship with the page that uses them.
const Home = lazy(() => import("./pages/Home"));
const NewBrand = lazy(() => import("./pages/NewBrand"));
const BrandMemory = lazy(() => import("./pages/BrandMemory"));
const Campaigns = lazy(() => import("./pages/Campaigns"));
const Campaign = lazy(() => import("./pages/Campaign"));
const Strategy = lazy(() => import("./pages/campaign/Strategy"));
const Creatives = lazy(() => import("./pages/campaign/Creatives"));
const Launch = lazy(() => import("./pages/campaign/Launch"));
const Performance = lazy(() => import("./pages/campaign/Performance"));

// Routes follow the backend's entities: Brand → Campaign → (strategy, concepts, export, metrics).
export default function App() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-canvas" />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/brands/new" element={<NewBrand />} />
        <Route path="/brands/:brandId" element={<Layout />}>
          <Route index element={<BrandMemory />} />
          <Route path="campaigns" element={<Campaigns />} />
          <Route path="campaigns/:campaignId" element={<Campaign />}>
            <Route index element={<Navigate to="strategy" replace />} />
            <Route path="strategy" element={<Strategy />} />
            <Route path="creatives" element={<Creatives />} />
            <Route path="launch" element={<Launch />} />
            <Route path="performance" element={<Performance />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
