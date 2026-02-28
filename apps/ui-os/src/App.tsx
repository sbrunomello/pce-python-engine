import { NavLink, Route, Routes } from 'react-router-dom';
import { OverviewPage } from './pages/Overview';
import { ApprovalsPage } from './pages/Approvals';
import { TwinPage } from './pages/Twin';

export default function App(): JSX.Element {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>PCE-OS UI</h1>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Overview
          </NavLink>
          <NavLink to="/approvals" className={({ isActive }) => (isActive ? 'active' : '')}>
            Approvals
          </NavLink>
          <NavLink to="/twin" className={({ isActive }) => (isActive ? 'active' : '')}>
            Twin
          </NavLink>
        </nav>
      </aside>

      <main className="content">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/twin" element={<TwinPage />} />
        </Routes>
      </main>
    </div>
  );
}
