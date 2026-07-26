import { ShieldCheck } from 'lucide-react';

import { usePortalAuth } from './portalAuth.js';

export function PortalLoginPage() {
  const { configured, error, loading, login } = usePortalAuth();
  return (
    <main className="portal-auth-page">
      <section className="portal-auth-card">
        <div className="portal-brand__logo portal-auth-card__logo">
          <ShieldCheck size={28} />
        </div>
        <h1>运维运营控制面</h1>
        <p>仅限已授权的运营人员访问。登录将跳转到企业单点登录并要求 MFA。</p>
        {!configured ? <p className="portal-auth-card__error">Portal 未配置 OIDC，请先注入生产登录配置。</p> : null}
        {error ? <p className="portal-auth-card__error">{error}</p> : null}
        <button
          type="button"
          className="portal-button portal-button--primary"
          disabled={!configured || loading}
          onClick={() => void login()}
        >
          {loading ? '正在验证登录…' : '使用企业账号登录'}
        </button>
      </section>
    </main>
  );
}
