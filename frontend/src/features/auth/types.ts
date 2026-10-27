export interface DecodedToken {
  sub: string;
  role: string;
  exp: number;
  iat: number;
}

export type Role = "SUPERADMIN" | "ADMIN" | "SUPERVISOR" | "OPERATOR" | "READONLY" | string;

export interface User {
  id?: number;
  username: string;
  role: Role;
  // Note: tenant_id is NOT in the JWT payload by default. The backend resolves it dynamically.
  // We only rely on what the token gives us or what a future /me endpoint might provide.
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isInitializing: boolean;
}

export interface DomainError {
  code: string;
  message: string;
  request_id?: string;
}

export interface DomainErrorResponse {
  error: DomainError;
}
