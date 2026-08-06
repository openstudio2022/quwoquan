package auth

import (
	"context"
	"crypto/hmac"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

const (
	// DelegatedQueryGrantMaxTTL keeps delegated reads short-lived while still
	// allowing one bounded remote query and its transport retries.
	DelegatedQueryGrantMaxTTL = 5 * time.Minute
	// DelegatedCommandGrantMaxTTL keeps an approved write usable only during
	// the immediate continuation window. Every command grant is also
	// single-use through DelegatedGrantJTIStore.
	DelegatedCommandGrantMaxTTL = time.Minute
)

var (
	ErrDelegatedGrantInvalid          = errors.New("AUTH.DELEGATED_GRANT.invalid")
	ErrDelegatedGrantAudienceMismatch = errors.New("AUTH.DELEGATED_GRANT.audience_mismatch")
	ErrDelegatedGrantActorMismatch    = errors.New("AUTH.DELEGATED_GRANT.actor_mismatch")
	ErrDelegatedGrantScopeMismatch    = errors.New("AUTH.DELEGATED_GRANT.scope_mismatch")
	ErrDelegatedGrantDigestMismatch   = errors.New("AUTH.DELEGATED_GRANT.digest_mismatch")
	ErrDelegatedGrantTargetMismatch   = errors.New("AUTH.DELEGATED_GRANT.target_mismatch")
	ErrDelegatedGrantAuthEpoch        = errors.New("AUTH.DELEGATED_GRANT.auth_epoch_mismatch")
	ErrDelegatedGrantReplay           = errors.New("AUTH.DELEGATED_GRANT.replay")
	ErrDelegatedGrantStoreUnavailable = errors.New("AUTH.DELEGATED_GRANT.store_unavailable")
)

type DelegatedGrantType string

const (
	DelegatedGrantTypeQuery   DelegatedGrantType = "delegated_query"
	DelegatedGrantTypeCommand DelegatedGrantType = "delegated_command"
)

// DelegatedResourceConstraint identifies the only resource a grant may touch.
// Type is the canonical object type where one exists; HTTP transports may use
// "http_request" with "<METHOD> <escaped-path>" as ID.
type DelegatedResourceConstraint struct {
	Type string `json:"type"`
	ID   string `json:"id"`
}

// DelegatedGrantClaims is the signed, common binding shared by query and
// command grants. AccountID is encoded as the JWT subject and DelegateService
// as the standard actor claim. There is no version envelope or alternate key.
type DelegatedGrantClaims struct {
	GrantType        DelegatedGrantType          `json:"grantType"`
	Issuer           string                      `json:"iss"`
	Audience         string                      `json:"aud"`
	AccountID        string                      `json:"sub"`
	PersonaID        string                      `json:"personaId"`
	AuthEpoch        int64                       `json:"authEpoch"`
	DelegateService  string                      `json:"act"`
	RunID            string                      `json:"runId"`
	ToolInvocationID string                      `json:"toolInvocationId"`
	OperationID      string                      `json:"operationId"`
	Resource         DelegatedResourceConstraint `json:"resource"`
	RequestDigest    string                      `json:"requestDigest"`
	Surface          string                      `json:"surface"`
	Scope            string                      `json:"scope"`
	IdempotencyKey   string                      `json:"idempotencyKey"`
	JWTID            string                      `json:"jti"`
	ApprovalRef      string                      `json:"approvalRef"`
	IssuedAt         int64                       `json:"iat"`
	ExpiresAt        int64                       `json:"exp"`
}

// DelegatedQueryGrant is intentionally distinct from a command grant so APIs
// cannot accidentally pass a read delegation into a write signing path.
type DelegatedQueryGrant struct {
	Claims DelegatedGrantClaims
}

// DelegatedCommandGrant represents an account-authority-approved, single-use
// write. ApprovalRef and IdempotencyKey are mandatory.
type DelegatedCommandGrant struct {
	Claims DelegatedGrantClaims
}

type DelegatedGrantSigner struct {
	secret []byte
	issuer string
}

func NewHS256DelegatedGrantSigner(
	secret []byte,
	issuer string,
) (*DelegatedGrantSigner, error) {
	if len(secret) < 32 {
		return nil, errors.New("delegated grant signing secret must contain at least 32 bytes")
	}
	issuer = strings.TrimSpace(issuer)
	if issuer == "" {
		return nil, errors.New("delegated grant issuer is required")
	}
	return &DelegatedGrantSigner{
		secret: append([]byte(nil), secret...),
		issuer: issuer,
	}, nil
}

func (s *DelegatedGrantSigner) SignQuery(
	grant DelegatedQueryGrant,
) (string, error) {
	claims := grant.Claims
	claims.GrantType = DelegatedGrantTypeQuery
	return s.sign(claims)
}

func (s *DelegatedGrantSigner) SignCommand(
	grant DelegatedCommandGrant,
) (string, error) {
	claims := grant.Claims
	claims.GrantType = DelegatedGrantTypeCommand
	return s.sign(claims)
}

func (s *DelegatedGrantSigner) sign(
	claims DelegatedGrantClaims,
) (string, error) {
	claims.Issuer = strings.TrimSpace(claims.Issuer)
	if claims.Issuer == "" {
		claims.Issuer = s.issuer
	}
	if claims.Issuer != s.issuer {
		return "", ErrDelegatedGrantInvalid
	}
	if err := validateDelegatedGrantClaims(claims); err != nil {
		return "", err
	}
	headerSegment, err := encodeSegment(jwtHeader{Alg: "HS256", Typ: "JWT"})
	if err != nil {
		return "", err
	}
	payloadSegment, err := encodeSegment(claims)
	if err != nil {
		return "", err
	}
	signingInput := headerSegment + "." + payloadSegment
	return signingInput + "." + sign(signingInput, s.secret), nil
}

// DelegatedGrantExpectation is built from the generated operation descriptor
// and the actual request. Empty expected fields are invalid: a verifier never
// silently skips issuer/audience/act/scope/digest/target/surface checks.
type DelegatedGrantExpectation struct {
	Audience         string
	DelegateService  string
	AccountID        string
	PersonaID        string
	RunID            string
	ToolInvocationID string
	OperationID      string
	Resource         DelegatedResourceConstraint
	RequestDigest    string
	Surface          string
	Scopes           []string
	IdempotencyKey   string
	ApprovalRef      string
}

type DelegatedGrantVerifierConfig struct {
	Secret                   []byte
	Issuer                   string
	ClockSkew                time.Duration
	AccountSecurityAuthority AccountSecurityAuthority
}

type DelegatedGrantVerifier struct {
	secret                   []byte
	issuer                   string
	clockSkew                time.Duration
	accountSecurityAuthority AccountSecurityAuthority
	now                      func() time.Time
}

func NewHS256DelegatedGrantVerifier(
	config DelegatedGrantVerifierConfig,
) (*DelegatedGrantVerifier, error) {
	if len(config.Secret) < 32 {
		return nil, errors.New("delegated grant verification secret must contain at least 32 bytes")
	}
	config.Issuer = strings.TrimSpace(config.Issuer)
	if config.Issuer == "" {
		return nil, errors.New("delegated grant issuer is required")
	}
	if config.ClockSkew < 0 {
		return nil, errors.New("delegated grant clock skew cannot be negative")
	}
	if config.AccountSecurityAuthority == nil {
		return nil, errors.New("delegated grant account security authority is required")
	}
	return &DelegatedGrantVerifier{
		secret:                   append([]byte(nil), config.Secret...),
		issuer:                   config.Issuer,
		clockSkew:                config.ClockSkew,
		accountSecurityAuthority: config.AccountSecurityAuthority,
		now:                      time.Now,
	}, nil
}

func (v *DelegatedGrantVerifier) VerifyQuery(
	ctx context.Context,
	token string,
	expected DelegatedGrantExpectation,
) (DelegatedQueryGrant, error) {
	claims, err := v.verify(ctx, token, DelegatedGrantTypeQuery, expected)
	if err != nil {
		return DelegatedQueryGrant{}, err
	}
	return DelegatedQueryGrant{Claims: claims}, nil
}

func (v *DelegatedGrantVerifier) VerifyCommand(
	ctx context.Context,
	token string,
	expected DelegatedGrantExpectation,
) (DelegatedCommandGrant, error) {
	claims, err := v.verify(ctx, token, DelegatedGrantTypeCommand, expected)
	if err != nil {
		return DelegatedCommandGrant{}, err
	}
	return DelegatedCommandGrant{Claims: claims}, nil
}

func (v *DelegatedGrantVerifier) verify(
	ctx context.Context,
	token string,
	grantType DelegatedGrantType,
	expected DelegatedGrantExpectation,
) (DelegatedGrantClaims, error) {
	if err := validateDelegatedGrantExpectation(expected); err != nil {
		return DelegatedGrantClaims{}, err
	}
	claims, err := v.parseAndVerifySignature(token)
	if err != nil {
		return DelegatedGrantClaims{}, err
	}
	if claims.GrantType != grantType || claims.Issuer != v.issuer {
		return DelegatedGrantClaims{}, ErrDelegatedGrantInvalid
	}
	if err := validateDelegatedGrantClaims(claims); err != nil {
		return DelegatedGrantClaims{}, err
	}
	nowUnix := v.now().UTC().Unix()
	skewSeconds := int64(v.clockSkew / time.Second)
	if nowUnix-skewSeconds >= claims.ExpiresAt {
		return DelegatedGrantClaims{}, ErrExpiredToken
	}
	if claims.IssuedAt > nowUnix+skewSeconds {
		return DelegatedGrantClaims{}, ErrTokenNotYetValid
	}
	if claims.Audience != expected.Audience {
		return DelegatedGrantClaims{}, ErrDelegatedGrantAudienceMismatch
	}
	if claims.DelegateService != expected.DelegateService {
		return DelegatedGrantClaims{}, ErrDelegatedGrantActorMismatch
	}
	if claims.AccountID != expected.AccountID ||
		claims.PersonaID != expected.PersonaID {
		return DelegatedGrantClaims{}, ErrDelegatedGrantActorMismatch
	}
	if claims.OperationID != expected.OperationID ||
		claims.RunID != expected.RunID ||
		claims.ToolInvocationID != expected.ToolInvocationID ||
		claims.Resource != expected.Resource ||
		claims.Surface != expected.Surface ||
		claims.IdempotencyKey != expected.IdempotencyKey ||
		claims.ApprovalRef != expected.ApprovalRef {
		return DelegatedGrantClaims{}, ErrDelegatedGrantTargetMismatch
	}
	if claims.RequestDigest != expected.RequestDigest {
		return DelegatedGrantClaims{}, ErrDelegatedGrantDigestMismatch
	}
	if !containsAll(strings.Fields(claims.Scope), normalizedGrants(expected.Scopes)) {
		return DelegatedGrantClaims{}, ErrDelegatedGrantScopeMismatch
	}
	snapshot, err := v.accountSecurityAuthority.ReadAccountSecurity(
		ctx,
		claims.AccountID,
	)
	if err != nil {
		return DelegatedGrantClaims{}, ErrAccountSecurityUnavailable
	}
	if strings.TrimSpace(snapshot.AccountState) != "active" ||
		snapshot.AuthEpoch != claims.AuthEpoch {
		return DelegatedGrantClaims{}, ErrDelegatedGrantAuthEpoch
	}
	return claims, nil
}

func (v *DelegatedGrantVerifier) parseAndVerifySignature(
	token string,
) (DelegatedGrantClaims, error) {
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 3 {
		return DelegatedGrantClaims{}, ErrDelegatedGrantInvalid
	}
	headerPayload, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return DelegatedGrantClaims{}, ErrDelegatedGrantInvalid
	}
	var header jwtHeader
	if err := json.Unmarshal(headerPayload, &header); err != nil ||
		header.Alg != "HS256" ||
		header.Typ != "JWT" {
		return DelegatedGrantClaims{}, ErrDelegatedGrantInvalid
	}
	signingInput := parts[0] + "." + parts[1]
	expectedSignature := sign(signingInput, v.secret)
	if !hmac.Equal([]byte(expectedSignature), []byte(parts[2])) {
		return DelegatedGrantClaims{}, ErrDelegatedGrantInvalid
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return DelegatedGrantClaims{}, ErrDelegatedGrantInvalid
	}
	var claims DelegatedGrantClaims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return DelegatedGrantClaims{}, ErrDelegatedGrantInvalid
	}
	return claims, nil
}

// DelegatedGrantJTIStore atomically records a consumed command JTI until its
// expiry. Production composition must provide a durable shared implementation;
// in-memory implementations belong only in tests.
type DelegatedGrantJTIStore interface {
	Consume(
		ctx context.Context,
		jti string,
		expiresAt time.Time,
	) (consumed bool, err error)
}

type DelegatedCommandGrantConsumer struct {
	verifier *DelegatedGrantVerifier
	store    DelegatedGrantJTIStore
}

func NewDelegatedCommandGrantConsumer(
	verifier *DelegatedGrantVerifier,
	store DelegatedGrantJTIStore,
) (*DelegatedCommandGrantConsumer, error) {
	if verifier == nil {
		return nil, errors.New("delegated command grant verifier is required")
	}
	if store == nil {
		return nil, errors.New("delegated command grant JTI store is required")
	}
	return &DelegatedCommandGrantConsumer{verifier: verifier, store: store}, nil
}

func (c *DelegatedCommandGrantConsumer) Consume(
	ctx context.Context,
	token string,
	expected DelegatedGrantExpectation,
) (DelegatedCommandGrant, error) {
	grant, err := c.verifier.VerifyCommand(ctx, token, expected)
	if err != nil {
		return DelegatedCommandGrant{}, err
	}
	consumed, err := c.store.Consume(
		ctx,
		grant.Claims.JWTID,
		time.Unix(grant.Claims.ExpiresAt, 0).UTC(),
	)
	if err != nil {
		return DelegatedCommandGrant{}, fmt.Errorf(
			"%w: %v",
			ErrDelegatedGrantStoreUnavailable,
			err,
		)
	}
	if !consumed {
		return DelegatedCommandGrant{}, ErrDelegatedGrantReplay
	}
	return grant, nil
}

func validateDelegatedGrantClaims(claims DelegatedGrantClaims) error {
	required := []string{
		claims.Issuer,
		claims.Audience,
		claims.AccountID,
		claims.PersonaID,
		claims.DelegateService,
		claims.RunID,
		claims.ToolInvocationID,
		claims.OperationID,
		claims.Resource.Type,
		claims.Resource.ID,
		claims.RequestDigest,
		claims.Surface,
		claims.Scope,
		claims.IdempotencyKey,
		claims.JWTID,
	}
	for _, value := range required {
		if strings.TrimSpace(value) == "" {
			return ErrDelegatedGrantInvalid
		}
	}
	if claims.AuthEpoch <= 0 ||
		claims.IssuedAt <= 0 ||
		claims.ExpiresAt <= claims.IssuedAt {
		return ErrDelegatedGrantInvalid
	}
	ttl := time.Duration(claims.ExpiresAt-claims.IssuedAt) * time.Second
	switch claims.GrantType {
	case DelegatedGrantTypeQuery:
		if ttl > DelegatedQueryGrantMaxTTL {
			return ErrDelegatedGrantInvalid
		}
	case DelegatedGrantTypeCommand:
		if ttl > DelegatedCommandGrantMaxTTL ||
			strings.TrimSpace(claims.IdempotencyKey) == "" ||
			strings.TrimSpace(claims.ApprovalRef) == "" {
			return ErrDelegatedGrantInvalid
		}
	default:
		return ErrDelegatedGrantInvalid
	}
	return nil
}

func validateDelegatedGrantExpectation(
	expected DelegatedGrantExpectation,
) error {
	required := []string{
		expected.Audience,
		expected.DelegateService,
		expected.AccountID,
		expected.PersonaID,
		expected.RunID,
		expected.ToolInvocationID,
		expected.OperationID,
		expected.Resource.Type,
		expected.Resource.ID,
		expected.RequestDigest,
		expected.Surface,
		expected.IdempotencyKey,
	}
	for _, value := range required {
		if strings.TrimSpace(value) == "" {
			return ErrDelegatedGrantInvalid
		}
	}
	if len(normalizedGrants(expected.Scopes)) == 0 {
		return ErrDelegatedGrantInvalid
	}
	return nil
}
