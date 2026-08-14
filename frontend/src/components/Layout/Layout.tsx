import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { FileText, Settings, LayoutDashboard, Activity } from 'lucide-react';
import { useAuth } from '../../features/auth/AuthContext';
import './Layout.css';

const Layout: React.FC = () => {
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const getBreadcrumb = () => {
    if (location.pathname.includes('/monitoring')) {
      return 'Administración / Monitoreo & SRE';
    }
    if (location.pathname.includes('/settings')) {
      return 'Configuración / Sistema';
    }
    if (location.pathname.includes('/cases/')) {
      return 'Gestión Documental / Detalle de Expediente';
    }
    return 'Gestión Documental / Expedientes';
  };

  return (
    <div className="layout-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo-icon">
            <FileText size={24} color="#ffffff" />
          </div>
          <h2>Abst-gp</h2>
        </div>
        
        <nav className="sidebar-nav">
          <Link 
            to="/cases" 
            className={`nav-item ${location.pathname.includes('/cases') ? 'active' : ''}`}
          >
            <LayoutDashboard size={20} />
            <span>Expedientes</span>
          </Link>
          {isAdmin && (
            <Link 
              to="/monitoring" 
              className={`nav-item ${location.pathname.includes('/monitoring') ? 'active' : ''}`}
            >
              <Activity size={20} />
              <span>Monitoreo SRE</span>
            </Link>
          )}
          <Link 
            to="/settings" 
            className={`nav-item ${location.pathname.includes('/settings') ? 'active' : ''}`}
          >
            <Settings size={20} />
            <span>Configuración</span>
          </Link>
        </nav>
        
        <div className="sidebar-footer">
          <div className="user-profile">
            <div className="avatar">{user?.username ? user.username.charAt(0).toUpperCase() : '?'}</div>
            <div className="user-info">
              <span className="user-name">{user?.username || 'Guest'}</span>
              <span className="user-role">{user?.role || 'None'}</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            {getBreadcrumb()}
          </div>
        </header>
        <div className="content-scroll">
          <div className="container">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};

export default Layout;

