import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import NewBrand from "./pages/NewBrand";
import BrandMemory from "./pages/BrandMemory";
import Campaigns from "./pages/Campaigns";
import Campaign from "./pages/Campaign";
import Strategy from "./pages/campaign/Strategy";
import Creatives from "./pages/campaign/Creatives";
import Launch from "./pages/campaign/Launch";
import Performance from "./pages/campaign/Performance";

// Routes follow the backend's entities: Brand → Campaign → (strategy, concepts, export, metrics).
export default function App() {
  return (
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
  );
}
