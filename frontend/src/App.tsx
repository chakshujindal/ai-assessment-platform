import type { ReactNode } from "react";
import { BrowserRouter, Link, NavLink, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { getToken, setToken } from "./api";
import { BuilderPage } from "./pages/BuilderPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { PracticePage } from "./pages/PracticePage";
import { ResultsPage } from "./pages/ResultsPage";
import { TakeTestPage } from "./pages/TakeTestPage";

function RequireAuth({ children }: { children: ReactNode }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

function Shell({ candidate = false }: { candidate?: boolean }) {
  const navigate = useNavigate();
  const signedIn = !!getToken();
  const signOut = () => {
    setToken(null);
    navigate("/login");
  };
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        {candidate ? (
          <span className="brand">AI Assessment Platform</span>
        ) : (
          <Link to="/" className="brand">
            AI Assessment Platform
          </Link>
        )}
        {!candidate && (
          <nav aria-label="Main">
            {signedIn && (
              <NavLink to="/" end>
                Assessments
              </NavLink>
            )}
            <NavLink to="/practice">Practice</NavLink>
            {signedIn ? (
              <button type="button" className="link-button" onClick={signOut}>
                Sign out
              </button>
            ) : (
              <NavLink to="/login">Sign in</NavLink>
            )}
          </nav>
        )}
      </header>
      <main id="main" className="container">
        <Outlet />
      </main>
    </>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell candidate />}>
          <Route path="/take/:token" element={<TakeTestPage />} />
        </Route>
        <Route element={<Shell />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/practice" element={<PracticePage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            path="/assessments/:id"
            element={
              <RequireAuth>
                <BuilderPage />
              </RequireAuth>
            }
          />
          <Route
            path="/results/:inviteId"
            element={
              <RequireAuth>
                <ResultsPage />
              </RequireAuth>
            }
          />
          <Route
            path="*"
            element={
              <p>
                Page not found. <Link to="/">Go home</Link>
              </p>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
