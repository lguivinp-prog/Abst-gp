import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { jwtDecode } from 'jwt-decode';
import type { AuthState, DecodedToken } from './types';

interface AuthContextType extends AuthState {
  login: (token: string) => void;
  logout: () => void;
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
    const token = localStorage.getItem('access_token');
    const decoded = checkToken(token);

    if (token && decoded) {
      setState({
        user: { username: decoded.sub, role: decoded.role },
        token,
        isAuthenticated: true,
        isInitializing: false,
      });
    } else {
      if (token) localStorage.removeItem('access_token');
      setState((prev) => ({
        ...prev,
        isInitializing: false,
      }));
    }
  }, []);

  const login = (token: string) => {
    const decoded = checkToken(token);
    if (decoded) {
      localStorage.setItem('access_token', token);
      setState({
        user: { username: decoded.sub, role: decoded.role },
        token,
        isAuthenticated: true,
        isInitializing: false,
      });
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    setState({
      user: null,
      token: null,
      isAuthenticated: false,
      isInitializing: false,
    });
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
