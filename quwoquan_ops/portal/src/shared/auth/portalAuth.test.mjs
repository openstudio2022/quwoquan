import assert from 'node:assert/strict';
import test from 'node:test';

// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-002
import { discoverOIDCProvider } from '../../../.test-dist/shared/auth/portalAuth.js';

const config = {
  issuer: 'https://id.example.com/tenant',
  clientId: 'ops-portal',
  redirectUri: 'https://ops.example.com/',
  audience: 'https://ops-api.example.com',
  scope: 'openid ops.platform.rollout.read',
};

function discoveryResponse(document) {
  return {
    ok: true,
    status: 200,
    json: async () => document,
  };
}

test('OIDC discovery accepts exact issuer and PKCE S256 endpoints', async () => {
  const originalFetch = globalThis.fetch;
  let requestedURL = '';
  globalThis.fetch = async (url) => {
    requestedURL = String(url);
    return discoveryResponse({
      issuer: config.issuer,
      authorization_endpoint: 'https://id.example.com/authorize',
      token_endpoint: 'https://id.example.com/oauth/token',
      code_challenge_methods_supported: ['S256'],
    });
  };
  try {
    const metadata = await discoverOIDCProvider(config);
    assert.equal(
      requestedURL,
      'https://id.example.com/tenant/.well-known/openid-configuration',
    );
    assert.equal(metadata.token_endpoint, 'https://id.example.com/oauth/token');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('OIDC discovery fails closed on issuer drift, insecure endpoint, or missing S256', async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const document of [
      {
        issuer: 'https://attacker.example.com',
        authorization_endpoint: 'https://id.example.com/authorize',
        token_endpoint: 'https://id.example.com/oauth/token',
        code_challenge_methods_supported: ['S256'],
      },
      {
        issuer: config.issuer,
        authorization_endpoint: 'http://id.example.com/authorize',
        token_endpoint: 'https://id.example.com/oauth/token',
        code_challenge_methods_supported: ['S256'],
      },
      {
        issuer: config.issuer,
        authorization_endpoint: 'https://id.example.com/authorize',
        token_endpoint: 'https://id.example.com/oauth/token',
        code_challenge_methods_supported: ['plain'],
      },
    ]) {
      globalThis.fetch = async () => discoveryResponse(document);
      await assert.rejects(() => discoverOIDCProvider(config));
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});
