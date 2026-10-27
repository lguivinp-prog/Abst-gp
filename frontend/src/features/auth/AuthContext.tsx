/**
 * AuthContext.tsx
 *
 * P14-R2-15: Token de sesion almacenado EXCLUSIVAMENTE en sessionStorage.
 *
 * EXPOSICION RESIDUAL DOCUMENTADA (XSS):
 * sessionStorage NO previene el robo de tokens ante un ataque XSS exitoso.
 * Si un atacante logra ejecutar JavaScript arbitrario en el contexto de la
 * aplicacion, puede leer sessionStorage igual que localStorage.
 * La diferencia operativa es que sessionStorage NO persiste entre tabs o
 * reinicios del navegador, reduciendo la ventana de exposicion post-cierre
 * de la pestana. La mitigacion real contra XSS es CSP estricta, sanitizacion
 * de entradas, y revocacion server-side del JTI via /auth/logout y
 * /auth/logout-all.
 *
 * localStorage fue ELIMINADO completamente como almacen de tokens de acceso
 * en cumplimiento de R2-15. Ningun flujo debe escribir ni leer tokens
 * desde localStorage.
 */

import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { jwtDecode } from 'jwt-decode';
import type { AuthState, DecodedToken } from './types';

interface AuthContextType extends AuthState {
  login: (token: string) => void;
  logout: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    isAuthenticated: false,
    isInitializing: true,
  });

  const checkToken = (token: string | null) => {
    if (!token) return null;
    try {
      const decoded = jwtDecode<DecodedToken>(token);
      const currentTime = Date.now() / 1000;
      if (decoded.exp < currentTime) {
        return null; // Expired
      }
      return decoded;
    } catch (e) {
      return null;
    }
  };

  useEffect(() => {
    // P14-R2-15: Solo sessionStorage — localStorage eliminado como fuente de tokens
    const token = sessionStorage.getItem('access_token');
    const decoded = checkToken(token);

    if (token && decoded) {
      setState({
        user: { username: decoded.sub, role: decoded.role },
        token,
        isAuthenticated: true,
        isInitializing: false,
      });
    } else {
      if (token) {
        sessionStorage.removeItem('access_token');
      }
      setState((prev) => ({
        ...prev,
        isInitializing: false,
      }));
    }
  }, []);

  const login = (token: string) => {
    const decoded = checkToken(token);
    if (decoded) {
      // P14-R2-15: Solo sessionStorage — no se persiste en localStorage
      sessionStorage.setItem('access_token', token);
      setState({
        user: { username: decoded.sub, role: decoded.role },
        token,
        isAuthenticated: true,
        isInitializing: false,
      });
    }
  };

  const logout = async (): Promise<boolean> => {
    // P14-R2-15: Token de sesion solo desde state o sessionStorage
    const currentToken = state.token || sessionStorage.getItem('access_token');
    let revokedOnBackend = false;
    if (currentToken) {
      try {
        const response = await fetch('/auth/logout', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${currentToken}`,
            'Content-Type': 'application/json',
          },
        });
        if (response.ok) {
          revokedOnBackend = true;
        } else {
          console.error('Backend session revocation failed with status:', response.status);
        }
      } catch (e) {
        console.error('Backend logout network error:', e);
      }
    }
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('mfa_challenge_token');
    setState({
      user: null,
      token: null,
      isAuthenticated: false,
      isInitializing: false,
    });
    return revokedOnBackend;
  };

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
