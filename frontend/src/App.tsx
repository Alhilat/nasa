import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { ArrowUpRight, BookOpen, ChevronRight, Database, LayoutDashboard, Menu, Satellite, X } from 'lucide-react';
import { request } from './api';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const History = lazy(() => import('./pages/History'));
const Sources = lazy(() => import('./pages/Sources'));
const Methodology = lazy(() => import('./pages/Methodology'));
const navigation = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/history', label: 'History', Icon: Satellite },
  { to: '/sources', label: 'Data sources', Icon: Database },
  { to: '/methodology', label: 'Methods', Icon: BookOpen },
];

export default function App() {
  const [open, setOpen] = useState(false), [apiConnected, setApiConnected] = useState(false);
  const menu = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  useEffect(() => {
    const controller = new AbortController();
    request('/health/live', controller.signal).then(() => setApiConnected(true)).catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && open) { setOpen(false); menu.current?.focus(); } };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [open]);
  const current = navigation.find(n => n.to === location.pathname)?.label ?? 'Workspace';
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <button ref={menu} className="mobile-menu icon-button" aria-label="Toggle navigation" aria-expanded={open} aria-controls="workspace-navigation" onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</button>
    {open && <button className="nav-backdrop" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside id="workspace-navigation" className={`sidebar ${open ? 'is-open' : ''}`}>
      <NavLink to="/" className="brand" aria-label="PIRX home" onClick={() => setOpen(false)}><img className="brand-logo" src="/pirx-logo.png" alt="" width="64" height="64" /><span>PIRX</span></NavLink>
      <nav aria-label="Main navigation">{navigation.map(({ to, label, Icon }) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setOpen(false)}><Icon size={18} /><span>{label}</span><ChevronRight className="nav-chevron" size={13} /></NavLink>)}</nav>
      <div className="sidebar-divider" /><div className="nav-section-label">SENSORS</div>
      <div className="sensor-constellation"><div><i className="dot modis" /><span>MODIS<small>Terra · Aqua</small></span><span className="sensor-resolution">1 km</span></div><div><i className="dot viirs" /><span>VIIRS<small>S-NPP · NOAA-20 · NOAA-21</small></span><span className="sensor-resolution">375 m</span></div></div>
      <div className="sidebar-bottom"><a className="nasa-link" href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS data <ArrowUpRight size={14} /></a></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb">PIRX <ChevronRight size={12} /><span>{current}</span></div><div className="topbar-right"><span className="api-indicator"><i className={`status-dot ${apiConnected ? '' : 'offline'}`} />API {apiConnected ? 'connected' : 'unavailable'}</span></div></header>
      <main id="main-content" tabIndex={-1}><Suspense fallback={<div className="resource-state" role="status">Loading…</div>}><Routes><Route path="/" element={<Dashboard />} /><Route path="/explorer" element={<Navigate to="/" replace />} /><Route path="/history" element={<History />} /><Route path="/sources" element={<Sources />} /><Route path="/methodology" element={<Methodology />} /><Route path="*" element={<div className="panel prose-panel"><h1>Page not found</h1><NavLink className="text-link" to="/">Return to dashboard</NavLink></div>} /></Routes></Suspense><footer><span>Data: NASA FIRMS</span><span>All times UTC</span></footer></main>
    </div>
  </div>;
}
