// Package auth 提供轻量 HS256 JWT 的签发与本地验签。
//
// access token 与 device ticket 使用不同 TokenConfig；验签固定校验
// issuer、audience、token type、token version、iat/nbf/exp 与最大 TTL。
package auth

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidToken     = errors.New("AUTH.TOKEN.invalid")
	ErrExpiredToken     = errors.New("AUTH.TOKEN.expired")
	ErrTokenNotYetValid = errors.New("AUTH.TOKEN.not_yet_valid")
	ErrTokenVersion     = errors.New("AUTH.TOKEN.version_mismatch")
)

type TokenType string

const (
	TokenTypeAccess           TokenType = "access"
	TokenTypeDevice           TokenType = "device"
	TokenTypeDelegatedQuery   TokenType = "delegated_query"
	TokenTypeDelegatedCommand TokenType = "delegated_command"
)

type TokenConfig struct {
	Secret       []byte
	Issuer       string
	Audience     string
	Type         TokenType
	TokenVersion int
	TTL          time.Duration
	ClockSkew    time.Duration
}

func (c TokenConfig) validate() error {
	if len(c.Secret) < 32 {
		return errors.New("auth: signing secret must contain at least 32 bytes")
	}
	if strings.TrimSpace(c.Issuer) == "" {
		return errors.New("auth: issuer is required")
	}
	if strings.TrimSpace(c.Audience) == "" {
		return errors.New("auth: audience is required")
	}
	if c.Type != TokenTypeAccess && c.Type != TokenTypeDevice {
		return fmt.Errorf("auth: unsupported token type %q", c.Type)
	}
	if c.TokenVersion <= 0 {
		return errors.New("auth: token version must be positive")
	}
	if c.TTL <= 0 {
		return errors.New("auth: token TTL must be positive")
	}
	if c.ClockSkew < 0 {
		return errors.New("auth: clock skew cannot be negative")
	}
	return nil
}

type TokenSubject struct {
	AccountID     string
	PersonaID     string
	DeviceActorID string
	// ServiceActorID is the independently signed service actor for a service
	// acting on behalf of AccountID. It must never be encoded by replacing the
	// account subject with "service:<name>" because downstream ownership checks
	// need both identities without guessing.
	ServiceActorID string
	AuthEpoch      int64
	Scopes         []string
	Permissions    []string
	Roles          []string
}

// Claims 是已签名 credential 的载荷；ActorContext 只能由这些 claims 重建。
type Claims struct {
	Issuer         string    `json:"iss"`
	Audience       string    `json:"aud"`
	TokenType      TokenType `json:"tkn"`
	Subject        string    `json:"sub,omitempty"`
	Persona        string    `json:"psn,omitempty"`
	DeviceActorID  string    `json:"did,omitempty"`
	ServiceActorID string    `json:"act,omitempty"`
	AuthEpoch      int64     `json:"ae,omitempty"`
	TokenVersion   int       `json:"ver"`
	Scope          string    `json:"scope,omitempty"`
	Permissions    []string  `json:"permissions,omitempty"`
	Roles          []string  `json:"roles,omitempty"`
	JWTID          string    `json:"jti"`
	IssuedAt       int64     `json:"iat"`
	NotBefore      int64     `json:"nbf"`
	ExpiresAt      int64     `json:"exp"`
}

type jwtHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
}

// Signer 用对称密钥签发 access token。
type Signer struct {
	config TokenConfig
	now    func() time.Time
}

func NewHS256Signer(config TokenConfig) (*Signer, error) {
	if err := config.validate(); err != nil {
		return nil, err
	}
	config.Secret = append([]byte(nil), config.Secret...)
	return &Signer{config: config, now: time.Now}, nil
}

func (s *Signer) Sign(subject TokenSubject) (string, error) {
	accountID := strings.TrimSpace(subject.AccountID)
	personaID := strings.TrimSpace(subject.PersonaID)
	deviceActorID := strings.TrimSpace(subject.DeviceActorID)
	serviceActorID := strings.TrimSpace(subject.ServiceActorID)
	roles := normalizedGrants(subject.Roles)
	authEpoch := subject.AuthEpoch
	switch s.config.Type {
	case TokenTypeAccess:
		if accountID == "" || deviceActorID != "" {
			return "", errors.New("auth: access token requires only an account subject")
		}
		if serviceActorID != "" &&
			(strings.HasPrefix(accountID, "service:") ||
				!containsGrant(roles, "service")) {
			return "", errors.New(
				"auth: delegated service account token requires distinct account and service actors",
			)
		}
		if serviceActorID == "" &&
			containsGrant(roles, "service") &&
			!strings.HasPrefix(accountID, "service:") {
			return "", errors.New(
				"auth: service role with an account subject requires a service actor",
			)
		}
		if authEpoch < 0 {
			return "", errors.New("auth: access token auth epoch cannot be negative")
		}
		if authEpoch == 0 && !strings.HasPrefix(accountID, "service:") {
			authEpoch = 1
		}
	case TokenTypeDevice:
		if deviceActorID == "" || accountID != "" || personaID != "" ||
			serviceActorID != "" || authEpoch != 0 {
			return "", errors.New("auth: device ticket requires only a device actor")
		}
	}
	issued := s.now().UTC()
	jwtID, err := randomJWTID()
	if err != nil {
		return "", err
	}
	claims := Claims{
		Issuer:         strings.TrimSpace(s.config.Issuer),
		Audience:       strings.TrimSpace(s.config.Audience),
		TokenType:      s.config.Type,
		Subject:        accountID,
		Persona:        personaID,
		DeviceActorID:  deviceActorID,
		ServiceActorID: serviceActorID,
		AuthEpoch:      authEpoch,
		TokenVersion:   s.config.TokenVersion,
		Scope:          strings.Join(normalizedGrants(subject.Scopes), " "),
		Permissions:    normalizedGrants(subject.Permissions),
		Roles:          roles,
		JWTID:          jwtID,
		IssuedAt:       issued.Unix(),
		NotBefore:      issued.Unix(),
		ExpiresAt:      issued.Add(s.config.TTL).Unix(),
	}
	headerSeg, err := encodeSegment(jwtHeader{Alg: "HS256", Typ: "JWT"})
	if err != nil {
		return "", err
	}
	payloadSeg, err := encodeSegment(claims)
	if err != nil {
		return "", err
	}
	signingInput := headerSeg + "." + payloadSeg
	sig := sign(signingInput, s.config.Secret)
	return signingInput + "." + sig, nil
}

type Verifier struct {
	config TokenConfig
	now    func() time.Time
}

func NewHS256Verifier(config TokenConfig) (*Verifier, error) {
	if err := config.validate(); err != nil {
		return nil, err
	}
	config.Secret = append([]byte(nil), config.Secret...)
	return &Verifier{config: config, now: time.Now}, nil
}

func (v *Verifier) Verify(token string) (*Claims, error) {
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 3 {
		return nil, ErrInvalidToken
	}
	headerPayload, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, ErrInvalidToken
	}
	var header jwtHeader
	if err := json.Unmarshal(headerPayload, &header); err != nil ||
		header.Alg != "HS256" ||
		header.Typ != "JWT" {
		return nil, ErrInvalidToken
	}
	signingInput := parts[0] + "." + parts[1]
	expected := sign(signingInput, v.config.Secret)
	if !hmac.Equal([]byte(expected), []byte(parts[2])) {
		return nil, ErrInvalidToken
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, ErrInvalidToken
	}
	var claims Claims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return nil, ErrInvalidToken
	}
	if claims.Issuer != strings.TrimSpace(v.config.Issuer) ||
		claims.Audience != strings.TrimSpace(v.config.Audience) ||
		claims.TokenType != v.config.Type ||
		strings.TrimSpace(claims.JWTID) == "" {
		return nil, ErrInvalidToken
	}
	if claims.TokenVersion != v.config.TokenVersion {
		return nil, ErrTokenVersion
	}
	now := v.now().UTC()
	nowUnix := now.Unix()
	skewSeconds := int64(v.config.ClockSkew / time.Second)
	if claims.ExpiresAt <= 0 ||
		claims.IssuedAt <= 0 ||
		claims.NotBefore <= 0 ||
		claims.ExpiresAt <= claims.IssuedAt ||
		time.Duration(claims.ExpiresAt-claims.IssuedAt)*time.Second >
			v.config.TTL+v.config.ClockSkew {
		return nil, ErrInvalidToken
	}
	if nowUnix-skewSeconds >= claims.ExpiresAt {
		return nil, ErrExpiredToken
	}
	if claims.NotBefore > nowUnix+skewSeconds ||
		claims.IssuedAt > nowUnix+skewSeconds {
		return nil, ErrTokenNotYetValid
	}
	switch v.config.Type {
	case TokenTypeAccess:
		if strings.TrimSpace(claims.Subject) == "" ||
			strings.TrimSpace(claims.DeviceActorID) != "" ||
			claims.AuthEpoch < 0 {
			return nil, ErrInvalidToken
		}
		serviceActorID := strings.TrimSpace(claims.ServiceActorID)
		if serviceActorID != "" &&
			(strings.HasPrefix(strings.TrimSpace(claims.Subject), "service:") ||
				!containsGrant(claims.Roles, "service")) {
			return nil, ErrInvalidToken
		}
		if serviceActorID == "" &&
			containsGrant(claims.Roles, "service") &&
			!strings.HasPrefix(strings.TrimSpace(claims.Subject), "service:") {
			return nil, ErrInvalidToken
		}
	case TokenTypeDevice:
		if strings.TrimSpace(claims.DeviceActorID) == "" ||
			strings.TrimSpace(claims.Subject) != "" ||
			strings.TrimSpace(claims.Persona) != "" ||
			strings.TrimSpace(claims.ServiceActorID) != "" ||
			claims.AuthEpoch != 0 {
			return nil, ErrInvalidToken
		}
	}
	if !grantsAreCanonical(claims.Permissions) ||
		!grantsAreCanonical(claims.Roles) {
		return nil, ErrInvalidToken
	}
	return &claims, nil
}

func randomJWTID() (string, error) {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return "", fmt.Errorf("auth: generate jti: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(raw), nil
}

func normalizedGrants(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	out := make([]string, 0, len(values))
	for _, value := range values {
		normalized := strings.TrimSpace(value)
		if normalized == "" {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	return out
}

func grantsAreCanonical(values []string) bool {
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		if value == "" || strings.TrimSpace(value) != value {
			return false
		}
		if _, ok := seen[value]; ok {
			return false
		}
		seen[value] = struct{}{}
	}
	return true
}

func containsGrant(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}

func encodeSegment(v any) (string, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(raw), nil
}

func sign(input string, secret []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(input))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}
