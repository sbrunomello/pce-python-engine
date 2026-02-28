import { NavLink, Route, Routes } from 'react-router-dom';
import { OverviewPage } from './pages/Overview';
import { ApprovalsPage } from './pages/Approvals';
import { TwinPage } from './pages/Twin';
import { LiveFeedPage } from './pages/LiveFeed';
import { AgentsPage } from './pages/Agents';

export default function App(): JSX.Element {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>PCE-OS Control Room</h1>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>Overview</NavLink>
          <NavLink to="/feed" className={({ isActive }) => (isActive ? 'active' : '')}>Live Feed</NavLink>
          <NavLink to="/approvals" className={({ isActive }) => (isActive ? 'active' : '')}>Approvals</NavLink>
          <NavLink to="/twin" className={({ isActive }) => (isActive ? 'active' : '')}>Twin</NavLink>
          <NavLink to="/agents" className={({ isActive }) => (isActive ? 'active' : '')}>Agents</NavLink>
        </nav>
      </aside>

      <main className="content">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/feed" element={<LiveFeedPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/twin" element={<TwinPage />} />
          <Route path="/agents" element={<AgentsPage />} />
        </Routes>
      </main>
    </div>
  );
}
