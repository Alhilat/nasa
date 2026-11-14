import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { ArrowUpRight, BookOpen, ChevronRight, Database, Flame, Globe2, LayoutDashboard, Menu, Satellite, X } from 'lucide-react';
import { request } from './api';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Explorer = lazy(() => import('./pages/Explorer'));
const History = lazy(() => import('./pages/History'));
const Sources = lazy(() => import('./pages/Sources'));
const Methodology = lazy(() => import('./pages/Methodology'));
const navigation = [
  { to: '/', label: 'Intelligence dashboard', Icon: LayoutDashboard },
  { to: '/explorer', label: 'Observation explorer', Icon: Globe2 },
  { to: '/history', label: 'Historical analysis', Icon: Satellite },
  { to: '/sources', label: 'Data & provenance', Icon: Database },
  { to: '/methodology', label: 'Methodology', Icon: BookOpen },
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
      <NavLink to="/" className="brand" onClick={() => setOpen(false)}><span className="brand-mark"><Flame size={25} /></span><span>FireScope<small>EARTH OBSERVATION INTELLIGENCE</small></span></NavLink>
      <div className="nav-section-label">WORKSPACE</div>
      <nav aria-label="Main navigation">{navigation.map(({ to, label, Icon }) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setOpen(false)}><Icon size={18} /><span>{label}</span><ChevronRight className="nav-chevron" size={13} /></NavLink>)}</nav>
      <div className="sidebar-divider" /><div className="nav-section-label">SENSOR CONSTELLATION</div>
      <div className="sensor-constellation"><div><i className="dot modis" /><span>MODIS<small>Terra · Aqua</small></span><span className="sensor-resolution">1 km</span></div><div><i className="dot viirs" /><span>VIIRS<small>S-NPP · NOAA-20 · NOAA-21</small></span><span className="sensor-resolution">375 m</span></div></div>
      <div className="sidebar-bottom"><div className="challenge-card"><Satellite size={23} /><span className="eyebrow">SCIENCE BEFORE SIGNAL</span><p>Every observation has a source.<br />Every result has its limits.</p><NavLink to="/methodology" onClick={() => setOpen(false)}>Our scientific approach <ArrowUpRight size={14} /></NavLink></div><a className="nasa-link" href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS data <ArrowUpRight size={14} /></a><div className="sidebar-version"><span>FireScope v0.1.0</span><span className="local-label">RESEARCH</span></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={12} /><span>{current}</span></div><div className="topbar-right"><span className="foundation-badge">Historical observations</span><span className="api-indicator"><i className={`status-dot ${apiConnected ? '' : 'offline'}`} />API {apiConnected ? 'reachable' : 'unreachable'}</span><span className="avatar">FS</span></div></header>
      <main id="main-content" tabIndex={-1}><Suspense fallback={<div className="resource-state" role="status">Loading workspace…</div>}><Routes><Route path="/" element={<Dashboard />} /><Route path="/explorer" element={<Explorer />} /><Route path="/history" element={<History />} /><Route path="/sources" element={<Sources />} /><Route path="/methodology" element={<Methodology />} /><Route path="*" element={<div className="panel prose-panel"><h1>View not found</h1><NavLink className="text-link" to="/">Return to dashboard</NavLink></div>} /></Routes></Suspense><footer><span><Flame size={13} /> FireScope <b>·</b> Scientific context, preserved.</span><span>NASA FIRMS attribution retained · All times UTC</span></footer></main>
    </div>
  </div>;
}
