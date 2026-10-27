import { BrowserRouter, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import Deliveries from "./pages/Deliveries";

function Layout({ children }) {
  const { logout } = useAuth();
  return (
    <div className="shell">
      <header className="topbar">
        <strong>PayLedger</strong>
        <nav className="nav">
          <NavLink to="/" end>Accounts</NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/deliveries">Webhooks</NavLink>
        </nav>
        <button onClick={logout}>Log out</button>
      </header>
      <main>{children}</main>
    </div>
  );
}

function Protected({ children }) {
  const { token } = useAuth();
  return token ? <Layout>{children}</Layout> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Protected><Dashboard /></Protected>} />
          <Route path="/history" element={<Protected><History /></Protected>} />
          <Route path="/deliveries" element={<Protected><Deliveries /></Protected>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}