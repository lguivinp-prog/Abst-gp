import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import CasesList from './features/cases/CasesList';
import CaseDetail from './features/cases/CaseDetail';
import SettingsPage from './features/settings/SettingsPage';
import MonitoringDashboard from './features/monitoring/MonitoringDashboard';
import LoginPage from './features/auth/LoginPage';
import ProtectedRoute from './components/Layout/ProtectedRoute';
import { AuthProvider } from './features/auth/AuthContext';

import ErrorBoundary from './components/ErrorBoundary';

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            
            <Route element={<ProtectedRoute />}>
              <Route path="/" element={<Layout />}>
                <Route index element={<Navigate to="/cases" replace />} />
                <Route path="cases" element={<CasesList />} />
                <Route path="cases/:id" element={<CaseDetail />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="monitoring" element={<MonitoringDashboard />} />
              </Route>
            </Route>
            
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}


export default App;
