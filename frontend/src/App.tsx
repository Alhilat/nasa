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
  const drawer = useRef<HTMLDialogElement>(null);
  const main = useRef<HTMLElement>(null);
  const location = useLocation();
  const previousPath = useRef(location.pathname);
  const current = navigation.find(n => n.to === location.pathname)?.label ?? 'Workspace';
  function closeNavigation() {
    if (drawer.current?.open && typeof drawer.current.close === 'function') drawer.current.close();
    setOpen(false);
    menu.current?.focus();
  }
  useEffect(() => {
    const controller = new AbortController();
    request('/health/live', controller.signal).then(() => setApiConnected(true)).catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!open || !drawer.current) return;
    const dialog = drawer.current;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const desktop = window.matchMedia?.('(min-width: 761px)');
    const resize = () => { if (desktop?.matches) closeNavigation(); };
    desktop?.addEventListener('change', resize);
    return () => {
      desktop?.removeEventListener('change', resize);
      document.body.style.overflow = previousOverflow;
      if (dialog.open && typeof dialog.close === 'function') dialog.close();
    };
  }, [open]);
  useEffect(() => {
    document.title = `PIRX · ${current}`;
    document.querySelector('meta[name="description"]')?.setAttribute('content', `${current}. Explore NASA FIRMS observations with scientific context and source provenance.`);
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
      main.current?.focus({ preventScroll: true });
    }
  }, [location.pathname, current]);
  const sidebar = <>
      <NavLink to="/" className="brand" aria-label="PIRX home" onClick={() => setOpen(false)}><img className="brand-wordmark" src="/pirx-wordmark.png" alt="" width="1280" height="426" /></NavLink>
      <nav aria-label="Main navigation">{navigation.map(({ to, label, Icon }) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setOpen(false)}><Icon size={18} /><span>{label}</span><ChevronRight className="nav-chevron" size={13} /></NavLink>)}</nav>
      <div className="sensor-heading">Sensor constellation</div>
      <div className="sensor-constellation"><div><i className="dot modis" /><span>MODIS<small>Terra · Aqua</small></span><span className="sensor-resolution">1 km</span></div><div><i className="dot viirs" /><span>VIIRS<small>S-NPP · NOAA-20 · NOAA-21</small></span><span className="sensor-resolution">375 m</span></div></div>
      <div className="sidebar-bottom"><div className="challenge-card"><Satellite size={23} /><p>Every observation has a source.<br />Every result has its limits.</p><NavLink to="/methodology" onClick={() => setOpen(false)}>Our scientific approach <ArrowUpRight size={14} /></NavLink></div><a className="nasa-link" href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS data <ArrowUpRight size={14} /></a><div className="sidebar-version"><span>FireScope v0.1.0</span></div></div>
  </>;
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <button ref={menu} className="mobile-menu icon-button" aria-label="Toggle navigation" aria-expanded={open} aria-controls="workspace-navigation" onClick={() => setOpen(!open)}><Menu aria-hidden="true" /></button>
    {open ? <dialog ref={drawer} id="workspace-navigation" className="sidebar is-open navigation-dialog" aria-label="Workspace navigation" onCancel={event => { event.preventDefault(); closeNavigation(); }} onClose={() => setOpen(false)} onClick={event => {
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeNavigation();
    }}><button className="nav-close icon-button" aria-label="Close navigation" onClick={closeNavigation} autoFocus><X aria-hidden="true" /></button>{sidebar}</dialog>
      : <aside id="workspace-navigation" className="sidebar">{sidebar}</aside>}
    <div className="main-shell" inert={open}><header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={12} /><span>{current}</span></div><div className="topbar-right"><span className="archive-context">Historical observations</span><span className="api-indicator"><i className={`status-dot ${apiConnected ? '' : 'offline'}`} />API {apiConnected ? 'reachable' : 'unreachable'}</span><span className="avatar">FS</span></div></header>
      <main ref={main} id="main-content" tabIndex={-1}><Suspense fallback={<div className="resource-state workspace-loading" role="status">Loading workspace…</div>}><Routes><Route path="/" element={<Dashboard />} /><Route path="/explorer" element={<Explorer />} /><Route path="/history" element={<History />} /><Route path="/sources" element={<Sources />} /><Route path="/methodology" element={<Methodology />} /><Route path="*" element={<div className="panel prose-panel"><h1>View not found</h1><NavLink className="text-link" to="/">Return to dashboard</NavLink></div>} /></Routes></Suspense><footer><span><Flame size={13} /> FireScope <b>·</b> Scientific context, preserved.</span><span>NASA FIRMS attribution retained · All times UTC</span></footer></main>
    </div>
  </div>;
}
