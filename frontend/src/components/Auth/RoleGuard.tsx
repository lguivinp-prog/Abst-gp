import React from 'react';
import { useAuth } from '../../features/auth/AuthContext';
import type { Role } from '../../features/auth/types';

interface RoleGuardProps {
  roles: Role[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Componente para ocultar secciones de la UI según el rol del usuario autenticado.
 * NO reemplaza la seguridad del backend, solo mejora la experiencia de usuario.
 */
export const RoleGuard: React.FC<RoleGuardProps> = ({ roles, children, fallback = null }) => {
  const { user } = useAuth();

  if (!user) {
    return <>{fallback}</>;
  }

  // Verifica si el rol del usuario está incluido en los roles permitidos
  if (roles.includes(user.role)) {
    return <>{children}</>;
  }

  return <>{fallback}</>;
};
