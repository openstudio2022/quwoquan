package auth

import (
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/operation"
)

var (
	ErrOIDCInvalidToken = errors.New("AUTH.OIDC.invalid")
	ErrOIDCKeyNotFound  = errors.New("AUTH.OIDC.key_not_found")
	ErrOIDCNotMFA       = errors.New("AUTH.OIDC.mfa_required")
)

type OIDCConfig struct {
	Issuer     string
	Audience   string
	JWKSURL    string
	ClockSkew  time.Duration
	CacheTTL   time.Duration
	RequireMFA bool
	HTTPClient *http.Client
}

type OIDCVerifier struct {
	config OIDCConfig
	client *http.Client
	mu     sync.RWMutex
	keys   map[string]*rsa.PublicKey
	loaded time.Time
}

type oidcHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
	KID string `json:"kid"`
}

type oidcClaims struct {
	Issuer    string          `json:"iss"`
	Audience  json.RawMessage `json:"aud"`
	Subject   string          `json:"sub"`
	Scope     string          `json:"scope,omitempty"`
	Scopes    []string        `json:"scopes,omitempty"`
	Role      json.RawMessage `json:"role,omitempty"`
	Roles     json.RawMessage `json:"roles,omitempty"`
	Perm      json.RawMessage `json:"permissions,omitempty"`
	Amr       []string        `json:"amr,omitempty"`
	Acr       string          `json:"acr,omitempty"`
	JWTID     string          `json:"jti,omitempty"`
	IssuedAt  int64           `json:"iat"`
	NotBefore int64           `json:"nbf,omitempty"`
	ExpiresAt int64           `json:"exp"`
}

type oidcJWKSet struct {
	Keys []oidcJWK `json:"keys"`
}

type oidcJWK struct {
	KTY string `json:"kty"`
	Use string `json:"use"`
	Alg string `json:"alg"`
	KID string `json:"kid"`
	N   string `json:"n"`
	E   string `json:"e"`
}

func NewOIDCVerifier(config OIDCConfig) (*OIDCVerifier, error) {
	config.Issuer = strings.TrimRight(strings.TrimSpace(config.Issuer), "/")
	config.Audience = strings.TrimSpace(config.Audience)
	config.JWKSURL = strings.TrimSpace(config.JWKSURL)
	if config.Issuer == "" || config.Audience == "" || config.JWKSURL == "" {
		return nil, errors.New("auth: oidc issuer, audience and jwks url are required")
	}
	if config.ClockSkew < 0 {
		return nil, errors.New("auth: oidc clock skew cannot be negative")
	}
	if config.CacheTTL <= 0 {
		config.CacheTTL = 5 * time.Minute
	}
	client := config.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}
	return &OIDCVerifier{
		config: config,
		client: client,
		keys:   map[string]*rsa.PublicKey{},
	}, nil
}

// NewOIDCVerifierFromEnv 只负责读取 composition 配置；是否在某个服务/环境中
// 强制启用由对应 composition root 决定。部分配置一律报错，禁止静默退回
// X-Actor 或 App HS256 token。
func NewOIDCVerifierFromEnv(prefix string) (*OIDCVerifier, error) {
	prefix = strings.TrimSuffix(strings.TrimSpace(prefix), "_")
	issuer := strings.TrimSpace(os.Getenv(prefix + "_ISSUER"))
	audience := strings.TrimSpace(os.Getenv(prefix + "_AUDIENCE"))
	jwksURL := strings.TrimSpace(os.Getenv(prefix + "_JWKS_URL"))
	if issuer == "" && audience == "" && jwksURL == "" {
		return nil, nil
	}
	config := OIDCConfig{
		Issuer: issuer, Audience: audience, JWKSURL: jwksURL,
		RequireMFA: true,
	}
	if raw := strings.TrimSpace(os.Getenv(prefix + "_CACHE_TTL_SECONDS")); raw != "" {
		seconds, err := strconv.Atoi(raw)
		if err != nil || seconds <= 0 {
			return nil, fmt.Errorf("auth: invalid %s_CACHE_TTL_SECONDS", prefix)
		}
		config.CacheTTL = time.Duration(seconds) * time.Second
	}
	return NewOIDCVerifier(config)
}

func (v *OIDCVerifier) Verify(token string) (Principal, error) {
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 3 {
		return Principal{}, ErrOIDCInvalidToken
	}
	headerBytes, err := decodeOIDCSegment(parts[0])
	if err != nil {
		return Principal{}, ErrOIDCInvalidToken
	}
	var header oidcHeader
	if err := json.Unmarshal(headerBytes, &header); err != nil ||
		header.Alg != "RS256" || header.Typ != "JWT" || strings.TrimSpace(header.KID) == "" {
		return Principal{}, ErrOIDCInvalidToken
	}
	payloadBytes, err := decodeOIDCSegment(parts[1])
	if err != nil {
		return Principal{}, ErrOIDCInvalidToken
	}
	var claims oidcClaims
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return Principal{}, ErrOIDCInvalidToken
	}
	if strings.TrimRight(strings.TrimSpace(claims.Issuer), "/") != v.config.Issuer ||
		!oidcAudienceContains(claims.Audience, v.config.Audience) ||
		strings.TrimSpace(claims.Subject) == "" ||
		claims.ExpiresAt <= 0 ||
		claims.IssuedAt <= 0 {
		return Principal{}, ErrOIDCInvalidToken
	}
	now := time.Now().UTC().Unix()
	skew := int64(v.config.ClockSkew / time.Second)
	if now-skew >= claims.ExpiresAt ||
		claims.IssuedAt > now+skew ||
		(claims.NotBefore > 0 && claims.NotBefore > now+skew) {
		return Principal{}, ErrOIDCInvalidToken
	}
	if v.config.RequireMFA && !oidcMFAClaimPresent(claims) {
		return Principal{}, ErrOIDCNotMFA
	}
	key, err := v.keyFor(header.KID, true)
	if err != nil {
		return Principal{}, err
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || len(signature) != key.Size() {
		return Principal{}, ErrOIDCInvalidToken
	}
	digest := sha256.Sum256([]byte(parts[0] + "." + parts[1]))
	if err := rsa.VerifyPKCS1v15(key, crypto.SHA256, digest[:], signature); err != nil {
		return Principal{}, ErrOIDCInvalidToken
	}
	roles := oidcStringList(claims.Roles)
	if len(roles) == 0 {
		roles = oidcStringList(claims.Role)
	}
	permissions := oidcStringList(claims.Perm)
	scopes := append([]string(nil), claims.Scopes...)
	if claims.Scope != "" {
		scopes = append(scopes, strings.Fields(claims.Scope)...)
	}
	claimsOut := Claims{
		Issuer:       claims.Issuer,
		Audience:     v.config.Audience,
		TokenType:    TokenTypeAccess,
		Subject:      strings.TrimSpace(claims.Subject),
		Scope:        strings.Join(normalizedGrants(scopes), " "),
		Permissions:  normalizedGrants(permissions),
		Roles:        normalizedGrants(roles),
		JWTID:        strings.TrimSpace(claims.JWTID),
		IssuedAt:     claims.IssuedAt,
		NotBefore:    claims.NotBefore,
		ExpiresAt:    claims.ExpiresAt,
		TokenVersion: 1,
	}
	return Principal{
		Claims: claimsOut,
		Actor:  operation.ActorContext{AccountID: strings.TrimSpace(claims.Subject)},
	}, nil
}

func (v *OIDCVerifier) keyFor(kid string, refreshOnMiss bool) (*rsa.PublicKey, error) {
	v.mu.RLock()
	key, found := v.keys[kid]
	loaded := v.loaded
	v.mu.RUnlock()
	if found && time.Since(loaded) < v.config.CacheTTL {
		return key, nil
	}
	if err := v.refreshKeys(); err != nil {
		if found {
			return key, nil
		}
		return nil, err
	}
	v.mu.RLock()
	key, found = v.keys[kid]
	v.mu.RUnlock()
	if found {
		return key, nil
	}
	if refreshOnMiss {
		if err := v.refreshKeys(); err == nil {
			v.mu.RLock()
			key, found = v.keys[kid]
			v.mu.RUnlock()
			if found {
				return key, nil
			}
		}
	}
	return nil, ErrOIDCKeyNotFound
}

func (v *OIDCVerifier) refreshKeys() error {
	req, err := http.NewRequest(http.MethodGet, v.config.JWKSURL, nil)
	if err != nil {
		return err
	}
	resp, err := v.client.Do(req)
	if err != nil {
		return fmt.Errorf("oidc jwks fetch: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("oidc jwks fetch status %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 512*1024))
	if err != nil {
		return err
	}
	var set oidcJWKSet
	if err := json.Unmarshal(body, &set); err != nil {
		return fmt.Errorf("decode oidc jwks: %w", err)
	}
	keys := make(map[string]*rsa.PublicKey, len(set.Keys))
	for _, jwk := range set.Keys {
		if jwk.KTY != "RSA" || strings.TrimSpace(jwk.KID) == "" ||
			strings.TrimSpace(jwk.N) == "" || strings.TrimSpace(jwk.E) == "" {
			continue
		}
		key, err := oidcRSAKey(jwk.N, jwk.E)
		if err != nil {
			continue
		}
		keys[jwk.KID] = key
	}
	if len(keys) == 0 {
		return errors.New("oidc jwks contains no usable rsa keys")
	}
	v.mu.Lock()
	v.keys = keys
	v.loaded = time.Now()
	v.mu.Unlock()
	return nil
}

func oidcRSAKey(rawN, rawE string) (*rsa.PublicKey, error) {
	nBytes, err := base64.RawURLEncoding.DecodeString(rawN)
	if err != nil || len(nBytes) == 0 {
		return nil, ErrOIDCInvalidToken
	}
	eBytes, err := base64.RawURLEncoding.DecodeString(rawE)
	if err != nil || len(eBytes) == 0 || len(eBytes) > 4 {
		return nil, ErrOIDCInvalidToken
	}
	exponent := 0
	for _, value := range eBytes {
		exponent = exponent<<8 | int(value)
	}
	if exponent < 2 {
		return nil, ErrOIDCInvalidToken
	}
	return &rsa.PublicKey{N: new(big.Int).SetBytes(nBytes), E: exponent}, nil
}

func oidcAudienceContains(raw json.RawMessage, expected string) bool {
	var one string
	if json.Unmarshal(raw, &one) == nil {
		return strings.TrimSpace(one) == expected
	}
	var many []string
	if json.Unmarshal(raw, &many) != nil {
		return false
	}
	for _, item := range many {
		if strings.TrimSpace(item) == expected {
			return true
		}
	}
	return false
}

func oidcMFAClaimPresent(claims oidcClaims) bool {
	if strings.EqualFold(strings.TrimSpace(claims.Acr), "mfa") {
		return true
	}
	for _, method := range claims.Amr {
		switch strings.ToLower(strings.TrimSpace(method)) {
		case "mfa", "otp", "totp", "webauthn", "hwk":
			return true
		}
	}
	return false
}

func oidcStringList(raw json.RawMessage) []string {
	if len(raw) == 0 {
		return nil
	}
	var one string
	if json.Unmarshal(raw, &one) == nil {
		return []string{one}
	}
	var many []string
	if json.Unmarshal(raw, &many) == nil {
		return many
	}
	return nil
}

func decodeOIDCSegment(value string) ([]byte, error) {
	return base64.RawURLEncoding.DecodeString(value)
}
