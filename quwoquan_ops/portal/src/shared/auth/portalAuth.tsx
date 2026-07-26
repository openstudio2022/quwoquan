import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

const accessTokenStorageKey = 'quwoquan.ops.portal.access_token';
const pkceVerifierStorageKey = 'quwoquan.ops.portal.pkce_verifier';
const oauthStateStorageKey = 'quwoquan.ops.portal.oauth_state';

export type PortalAuthConfig = {
  issuer: string;
  clientId: string;
  redirectUri: string;
  audience: string;
  scope: string;
};

export type OIDCProviderMetadata = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  code_challenge_methods_supported?: string[];
};

function isSecureOIDCEndpoint(url: URL): boolean {
  return url.protocol === 'https:'
    || (url.protocol === 'http:' && (url.hostname === 'localhost' || url.hostname === '127.0.0.1'));
}

type PortalTokenClaims = {
  exp?: number;
  permissions?: unknown;
  roles?: unknown;
  scope?: unknown;
  sub?: string;
  email?: string;
  name?: string;
};

export type PortalAuthState = {
  configured: boolean;
  loading: boolean;
  token: string | null;
  claims: PortalTokenClaims;
  error: string | null;
  login: () => Promise<void>;
  logout: () => void;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
};

const PortalAuthContext = createContext<PortalAuthState | null>(null);

function envValue(key: string): string {
  const importMetaEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
  const processEnv = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return (importMetaEnv?.[key] ?? processEnv?.[key] ?? '').trim();
}

function authConfig(): PortalAuthConfig {
  const issuer = envValue('VITE_OIDC_ISSUER').replace(/\/+$/, '');
  return {
    issuer,
    clientId: envValue('VITE_OIDC_CLIENT_ID'),
    redirectUri: envValue('VITE_OIDC_REDIRECT_URI') || window.location.origin + window.location.pathname,
    audience: envValue('VITE_OIDC_AUDIENCE'),
    scope: envValue('VITE_OIDC_SCOPE') || 'openid profile email',
  };
}

export async function discoverOIDCProvider(config: PortalAuthConfig): Promise<OIDCProviderMetadata> {
  const response = await fetch(`${config.issuer}/.well-known/openid-configuration`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`OIDC discovery endpoint returned ${response.status}`);
  }
  const metadata = (await response.json()) as Partial<OIDCProviderMetadata>;
  const metadataIssuer = (metadata.issuer ?? '').replace(/\/+$/, '');
  const authorizationEndpoint = new URL(metadata.authorization_endpoint ?? '');
  const tokenEndpoint = new URL(metadata.token_endpoint ?? '');
  if (
    metadataIssuer !== config.issuer
    || !metadata.authorization_endpoint
    || !metadata.token_endpoint
    || !isSecureOIDCEndpoint(authorizationEndpoint)
    || !isSecureOIDCEndpoint(tokenEndpoint)
  ) {
    throw new Error('OIDC discovery metadata 的 issuer 或 endpoint 非法。');
  }
  if (
    !Array.isArray(metadata.code_challenge_methods_supported)
    || !metadata.code_challenge_methods_supported.includes('S256')
  ) {
    throw new Error('OIDC provider 未声明支持 PKCE S256。');
  }
  return metadata as OIDCProviderMetadata;
}

function decodeClaims(token: string): PortalTokenClaims {
  const payload = token.split('.')[1];
  if (!payload) {
    return {};
  }
  try {
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(window.atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '='))) as PortalTokenClaims;
  } catch {
    return {};
  }
}

function stringList(value: unknown): string[] {
  if (typeof value === 'string') {
    return value.split(/\s+/).map((item) => item.trim()).filter(Boolean);
  }
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string' && item.trim() !== '');
  }
  return [];
}

function randomBase64Url(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function createPkcePair(): Promise<{ verifier: string; challenge: string }> {
  const verifier = randomBase64Url(window.crypto.getRandomValues(new Uint8Array(32)));
  const digest = await window.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(verifier),
  );
  return { verifier, challenge: randomBase64Url(new Uint8Array(digest)) };
}

function clearCallbackQuery(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete('code');
  url.searchParams.delete('state');
  url.searchParams.delete('error');
  url.searchParams.delete('error_description');
  window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
}

export function getPortalAccessToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const token = window.sessionStorage.getItem(accessTokenStorageKey);
  if (!token) {
    return null;
  }
  const claims = decodeClaims(token);
  if (typeof claims.exp === 'number' && claims.exp <= Math.floor(Date.now() / 1000)) {
    window.sessionStorage.removeItem(accessTokenStorageKey);
    return null;
  }
  return token;
}

export function notifyPortalAuthExpired(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('quwoquan-portal-auth-expired'));
  }
}

export function PortalAuthProvider({ children }: { children: ReactNode }) {
  const config = useMemo(authConfig, []);
  const [token, setToken] = useState<string | null>(() => getPortalAccessToken());
  const [loading, setLoading] = useState<boolean>(() => Boolean(window.location.search.includes('code=')));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onExpired = () => {
      window.sessionStorage.removeItem(accessTokenStorageKey);
      setToken(null);
      setError('登录会话已过期，请重新登录。');
    };
    window.addEventListener('quwoquan-portal-auth-expired', onExpired);
    return () => window.removeEventListener('quwoquan-portal-auth-expired', onExpired);
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    const code = url.searchParams.get('code');
    const returnedState = url.searchParams.get('state');
    const callbackError = url.searchParams.get('error_description') || url.searchParams.get('error');
    if (!code && !callbackError) {
      return;
    }
    if (callbackError) {
      setError(`单点登录失败：${callbackError}`);
      setLoading(false);
      clearCallbackQuery();
      return;
    }
    if (!code) {
      setError('单点登录回调缺少授权码，请重新登录。');
      setLoading(false);
      clearCallbackQuery();
      return;
    }
    const expectedState = window.sessionStorage.getItem(oauthStateStorageKey);
    const verifier = window.sessionStorage.getItem(pkceVerifierStorageKey);
    if (!returnedState || returnedState !== expectedState || !verifier || !config.issuer || !config.clientId) {
      setError('单点登录回调校验失败，请重新登录。');
      setLoading(false);
      clearCallbackQuery();
      return;
    }
    void (async () => {
      try {
        const provider = await discoverOIDCProvider(config);
        const response = await fetch(provider.token_endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            grant_type: 'authorization_code',
            client_id: config.clientId,
            redirect_uri: config.redirectUri,
            code,
            code_verifier: verifier,
          }),
        });
        if (!response.ok) {
          throw new Error(`token endpoint returned ${response.status}`);
        }
        const body = (await response.json()) as { access_token?: string };
        if (!body.access_token) {
          throw new Error('token endpoint did not return access_token');
        }
        window.sessionStorage.setItem(accessTokenStorageKey, body.access_token);
        setToken(body.access_token);
        setError(null);
      } catch (callbackExchangeError) {
        setError(callbackExchangeError instanceof Error ? callbackExchangeError.message : '单点登录交换失败。');
      } finally {
        window.sessionStorage.removeItem(oauthStateStorageKey);
        window.sessionStorage.removeItem(pkceVerifierStorageKey);
        setLoading(false);
        clearCallbackQuery();
      }
    })();
  }, [config]);

  const value = useMemo<PortalAuthState>(() => {
    const claims = token ? decodeClaims(token) : {};
    const permissions = new Set(stringList(claims.permissions).concat(stringList(claims.scope)));
    const roles = new Set(stringList(claims.roles));
    return {
      configured: Boolean(config.issuer && config.clientId && config.audience),
      loading,
      token,
      claims,
      error,
      login: async () => {
        if (!config.issuer || !config.clientId || !config.audience) {
          setError('Portal 未完整配置 OIDC issuer/client_id/audience。');
          return;
        }
        try {
          const provider = await discoverOIDCProvider(config);
          const pkce = await createPkcePair();
          const state = randomBase64Url(window.crypto.getRandomValues(new Uint8Array(24)));
          window.sessionStorage.setItem(pkceVerifierStorageKey, pkce.verifier);
          window.sessionStorage.setItem(oauthStateStorageKey, state);
          const loginUrl = new URL(provider.authorization_endpoint);
          loginUrl.search = new URLSearchParams({
            response_type: 'code',
            client_id: config.clientId,
            redirect_uri: config.redirectUri,
            scope: config.scope,
            state,
            code_challenge: pkce.challenge,
            code_challenge_method: 'S256',
            audience: config.audience,
          }).toString();
          window.location.assign(loginUrl.toString());
        } catch (loginError) {
          setError(loginError instanceof Error ? loginError.message : '单点登录初始化失败。');
        }
      },
      logout: () => {
        window.sessionStorage.removeItem(accessTokenStorageKey);
        window.sessionStorage.removeItem(pkceVerifierStorageKey);
        window.sessionStorage.removeItem(oauthStateStorageKey);
        setToken(null);
        setError(null);
      },
      hasPermission: (permission: string) => permissions.has(permission) || roles.has('admin'),
      hasRole: (role: string) => roles.has(role) || roles.has('admin'),
    };
  }, [config, error, loading, token]);

  return <PortalAuthContext.Provider value={value}>{children}</PortalAuthContext.Provider>;
}

export function usePortalAuth(): PortalAuthState {
  const context = useContext(PortalAuthContext);
  if (!context) {
    throw new Error('usePortalAuth must be used inside PortalAuthProvider');
  }
  return context;
}
