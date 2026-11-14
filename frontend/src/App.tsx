import { useEffect, useState } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import { ArrowUpRight, BookOpen, ChevronRight, Database, Flame, Globe2, Layers2, Menu, Satellite, X } from 'lucide-react';
import Explorer from './pages/Explorer';
import History from './pages/History';
import Sources from './pages/Sources';
import Methodology from './pages/Methodology';
import { request } from './api';

export default function App() {
  const [open, setOpen] = useState(false);
  const [apiConnected, setApiConnected] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    request('/health/live', controller.signal).then(() => setApiConnected(true)).catch(() => {});
    return () => controller.abort();
  }, []);
  return <div className="app-shell">
    <button className="mobile-menu icon-button" aria-label="Toggle navigation" aria-expanded={open} aria-controls="workspace-navigation" onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</button>
    <aside id="workspace-navigation" className={`sidebar ${open ? 'is-open' : ''}`}>
      <NavLink to="/" className="brand" onClick={() => setOpen(false)}><span className="brand-mark"><Flame size={24} fill="white" strokeWidth={1.5} /></span><span>FireScope<small>SATELLITE FIRE INTELLIGENCE</small></span></NavLink>
      <div className="nav-section-label">WORKSPACE</div>
      <nav aria-label="Main navigation"><NavLink to="/" end onClick={() => setOpen(false)}><Globe2 size={18} /> Explorer <ChevronRight className="nav-chevron" size={14} /></NavLink><NavLink to="/history" onClick={() => setOpen(false)}><Layers2 size={18} /> Historical intelligence</NavLink><NavLink to="/sources" onClick={() => setOpen(false)}><Database size={18} /> Data & provenance</NavLink><NavLink to="/methodology" onClick={() => setOpen(false)}><BookOpen size={18} /> Methodology</NavLink></nav>
      <div className="sidebar-divider" /><div className="nav-section-label">SENSOR CONSTELLATION</div>
      <div className="sensor-constellation"><div><i className="dot modis" /><span>MODIS<small>Terra · Aqua</small></span><span className="sensor-resolution">1 km</span></div><div><i className="dot viirs" /><span>VIIRS<small>S-NPP · NOAA-20 · NOAA-21</small></span><span className="sensor-resolution">375 m</span></div></div>
      <div className="sidebar-bottom"><div className="challenge-card"><span className="orbit-icon"><Satellite size={23} /></span><span className="eyebrow">BUILT FOR EXPLORATION</span><h3>NASA Space Apps<br />Challenge 2026</h3><p>Harmonizing MODIS & VIIRS<br />hot spot observations.</p><span className="foundation-label"><Layers2 size={12} /> FOUNDATION RELEASE</span></div><a className="nasa-link" href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">Explore NASA FIRMS <ArrowUpRight size={14} /></a><div className="sidebar-version"><span>FireScope v0.1.0</span><span className="local-label">LOCAL</span></div></div>
    </aside>
    <div className="main-shell"><div className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={12} /><span>Satellite fire intelligence</span></div><div className="topbar-right"><span className="foundation-badge">Research foundation</span><span className="api-indicator"><i className={`status-dot ${apiConnected ? '' : 'offline'}`} />API {apiConnected ? 'online' : 'offline'}</span><span className="avatar">FS</span></div></div><main><Routes><Route path="/" element={<Explorer />} /><Route path="/history" element={<History />} /><Route path="/sources" element={<Sources />} /><Route path="/methodology" element={<Methodology />} /><Route path="*" element={<div className="panel prose-panel"><h1>View not found</h1><NavLink to="/">Return to explorer</NavLink></div>} /></Routes><footer><span><Flame size={12} /> FireScope <b>·</b> An open view of a changing planet</span><span>NASA FIRMS data attribution retained at source</span></footer></main></div>
  </div>;
}
