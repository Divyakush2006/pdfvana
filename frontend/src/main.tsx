import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import "@fontsource-variable/inter";
import "./index.css";
import { AppProvider } from "./store";
import { Footer, Header, Page } from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Home from "./pages/Home";
import ToolPage from "./pages/ToolPage";
import Privacy from "./pages/Privacy";

function ScrollTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function Shell() {
  const { pathname } = useLocation();
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <div className="flex-1">
        <Page>
          <ErrorBoundary key={pathname}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/:toolId" element={<ToolPage />} />
            </Routes>
          </ErrorBoundary>
        </Page>
      </div>
      <Footer />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <AppProvider>
        <BrowserRouter>
          <ScrollTop />
          <Shell />
        </BrowserRouter>
      </AppProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
