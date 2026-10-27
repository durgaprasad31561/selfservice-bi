import { Link, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./components/Layout";
import { EmptyState } from "./components/ui";
import { AskPage } from "./pages/AskPage";
import { CatalogPage } from "./pages/CatalogPage";
import { DashboardDetailPage } from "./pages/DashboardDetailPage";
import { DashboardsPage } from "./pages/DashboardsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";

function NotFound() {
  return (
    <EmptyState title="Page not found">
      <Link to="/" className="text-accent hover:underline">
        Back to the overview
      </Link>
    </EmptyState>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route index element={<OverviewPage />} />
        <Route path="ask" element={<AskPage />} />
        <Route path="dashboards" element={<DashboardsPage />} />
        <Route path="dashboards/:id" element={<DashboardDetailPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
