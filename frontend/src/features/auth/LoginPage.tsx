import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/client';
import { useAuth } from './AuthContext';
import type { DomainErrorResponse } from './types';
import { Loader2, ShieldCheck } from 'lucide-react';
import './LoginPage.css';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mfaChallengeToken, setMfaChallengeToken] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handlePrimarySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    try {
      const response = await apiClient.post('/auth/token', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });
      
      const data = response.data;
      if (data.mfa_required && data.mfa_challenge_token) {
        setMfaChallengeToken(data.mfa_challenge_token);
      } else if (data.access_token) {
        login(data.access_token);
        navigate('/expedientes', { replace: true });
      }
    } catch (err: any) {
      if (!err.response) {
        setError('No se pudo conectar con el servidor');
      } else {
        const status = err.response.status;
        if (status === 401 || status === 403) {
          setError('Usuario o contraseña incorrectos');
        } else if (status === 429) {
          setError('Demasiados intentos fallidos. Por favor espere unos minutos.');
        } else if (status === 422) {
          if (err.response.data && err.response.data.error) {
             setError(err.response.data.error.message || 'Error de validación');
          } else {
             setError('Error de validación');
          }
        } else if (status >= 500) {
          setError('No se pudo iniciar sesión por un error del servidor');
        } else if (err.response.data && err.response.data.error) {
          const domainError = err.response.data as DomainErrorResponse;
          setError(domainError.error.message || 'Error de autenticación');
        } else {
          setError('Error de red al contactar al servidor.');
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const response = await apiClient.post('/auth/mfa/verify', {
        mfa_challenge_token: mfaChallengeToken,
        totp_code: totpCode.trim(),
      });

      const data = response.data;
      if (data.access_token) {
        login(data.access_token);
        navigate('/expedientes', { replace: true });
      }
    } catch (err: any) {
      if (err.response && err.response.status === 401) {
        setError('Código TOTP incorrecto o expirado');
      } else {
        setError('Error al verificar segundo factor de autenticación');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <h1>ABST-GP</h1>
          <p>{mfaChallengeToken ? 'Verificación de Segundo Factor (MFA)' : 'Inicia sesión para continuar'}</p>
        </div>
        
        {error && (
          <div className="login-error">
            {error}
          </div>
        )}

        {!mfaChallengeToken ? (
          <form onSubmit={handlePrimarySubmit} className="login-form">
            <div className="form-group">
              <label htmlFor="username">Usuario</label>
              <input
                id="username"
                name="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                required
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="password">Contraseña</label>
              <input
                id="password"
                name="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                required
              />
            </div>
            
            <button 
              type="submit" 
              className="login-button" 
              disabled={isLoading || !username || !password}
            >
              {isLoading ? <Loader2 className="animate-spin mr-2" size={20} /> : null}
              {isLoading ? ' Iniciando sesión...' : 'Ingresar'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleMfaSubmit} className="login-form">
            <div className="form-group">
              <label htmlFor="totpCode">
                <ShieldCheck className="inline-block mr-1 text-blue-500" size={18} />
                Código de Autenticación (6 dígitos)
              </label>
              <input
                id="totpCode"
                name="totpCode"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                placeholder="123456"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                disabled={isLoading}
                autoFocus
                required
              />
            </div>

            <button 
              type="submit" 
              className="login-button" 
              disabled={isLoading || totpCode.trim().length !== 6}
            >
              {isLoading ? <Loader2 className="animate-spin mr-2" size={20} /> : null}
              {isLoading ? ' Verificando...' : 'Verificar e Ingresar'}
            </button>

            <button
              type="button"
              className="mt-2 text-sm text-gray-500 hover:text-gray-700 underline text-center w-full"
              onClick={() => {
                setMfaChallengeToken(null);
                setTotpCode('');
                setError(null);
              }}
            >
              Volver al inicio de sesión
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
