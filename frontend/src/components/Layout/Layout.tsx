import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { FileText, Settings, LayoutDashboard } from 'lucide-react';
import './Layout.css';

const Layout: React.FC = () => {
  const location = useLocation();

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
            <div className="avatar">A</div>
            <div className="user-info">
              <span className="user-name">Admin Usuario</span>
              <span className="user-role">Administrador</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            Gestión Documental / Expedientes
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
