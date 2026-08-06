package auth

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"quwoquan_service/runtime/operation"
)

const (
	delegatedRunIDHeader            = "X-Delegated-Run-ID"
	delegatedToolInvocationIDHeader = "X-Delegated-Tool-Invocation-ID"
	delegatedIdempotencyHeader      = "X-Delegated-Idempotency-Key"
	delegatedApprovalRefHeader      = "X-Delegated-Approval-Ref"
	delegatedSurfaceHeader          = "X-Client-Surface"
)

type DelegatedOperationGuardConfig struct {
	Verifier        *DelegatedGrantVerifier
	CommandConsumer *DelegatedCommandGrantConsumer
	Audience        string
	DelegateService string
}

// DelegatedOperationGuard admits authority-signed delegated grants at the same
// generated operation boundary as normal principals. A command consumer is
// mandatory even for deployments that currently expose only queries so a
// future command descriptor cannot silently execute without replay storage.
type DelegatedOperationGuard struct {
	verifier        *DelegatedGrantVerifier
	commandConsumer *DelegatedCommandGrantConsumer
	audience        string
	delegateService string
}

func NewDelegatedOperationGuard(
	config DelegatedOperationGuardConfig,
) (*DelegatedOperationGuard, error) {
	if config.Verifier == nil {
		return nil, errors.New("delegated operation verifier is required")
	}
	if config.CommandConsumer == nil {
		return nil, errors.New("delegated operation command consumer is required")
	}
	if config.CommandConsumer.verifier != config.Verifier {
		return nil, errors.New("delegated operation verifier and consumer must share one verifier")
	}
	config.Audience = strings.TrimSpace(config.Audience)
	config.DelegateService = strings.TrimSpace(config.DelegateService)
	if config.Audience == "" || config.DelegateService == "" {
		return nil, errors.New("delegated operation audience and delegate service are required")
	}
	return &DelegatedOperationGuard{
		verifier:        config.Verifier,
		commandConsumer: config.CommandConsumer,
		audience:        config.Audience,
		delegateService: config.DelegateService,
	}, nil
}

// EnforceRuntimeOperationContract integrates delegated grant verification with
// the generated operation guard. Non-delegated requests retain the existing
// runtime behavior; unknown routes still pass to the owner router.
func (g *DelegatedOperationGuard) EnforceRuntimeOperationContract(
	descriptors []OperationSecurityDescriptor,
) func(http.Handler) http.Handler {
	compiled := mustCompileOperationDescriptors(descriptors)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			descriptor, matched := matchOperation(compiled, r.Method, r.URL.Path)
			if !matched {
				next.ServeHTTP(w, r)
				return
			}
			token, grantType, delegated := delegatedBearerGrant(r)
			if !delegated {
				authorizeGeneratedOperation(
					w,
					r,
					descriptor,
					runtimeOperationBoundary,
					next,
				)
				return
			}
			authorizedRequest, err := g.authorize(
				r,
				descriptor,
				token,
				grantType,
			)
			if err != nil {
				writeOperationGuardError(
					w,
					r,
					"forbidden",
					"delegated grant rejected: "+err.Error(),
				)
				return
			}
			authorizeGeneratedOperation(
				w,
				authorizedRequest,
				descriptor,
				runtimeOperationBoundary,
				next,
			)
		})
	}
}

func (g *DelegatedOperationGuard) authorize(
	r *http.Request,
	descriptor compiledOperationDescriptor,
	token string,
	grantType DelegatedGrantType,
) (*http.Request, error) {
	claims, err := g.verifier.parseAndVerifySignature(token)
	if err != nil {
		return nil, err
	}
	body, err := readAndRestoreRequestBody(r)
	if err != nil {
		return nil, ErrDelegatedGrantDigestMismatch
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		idempotencyKey = strings.TrimSpace(
			r.Header.Get(delegatedIdempotencyHeader),
		)
	}
	expected := DelegatedGrantExpectation{
		Audience:         g.audience,
		DelegateService:  g.delegateService,
		AccountID:        claims.AccountID,
		PersonaID:        claims.PersonaID,
		RunID:            strings.TrimSpace(r.Header.Get(delegatedRunIDHeader)),
		ToolInvocationID: strings.TrimSpace(r.Header.Get(delegatedToolInvocationIDHeader)),
		OperationID:      descriptor.CanonicalOperationID,
		Resource:         HTTPDelegatedResourceConstraint(r),
		RequestDigest:    DelegatedRequestDigest(body),
		Surface:          strings.TrimSpace(r.Header.Get(delegatedSurfaceHeader)),
		Scopes:           append([]string(nil), descriptor.Scopes...),
		IdempotencyKey:   idempotencyKey,
		ApprovalRef:      strings.TrimSpace(r.Header.Get(delegatedApprovalRefHeader)),
	}
	switch grantType {
	case DelegatedGrantTypeQuery:
		if !isSafeReadMethod(r.Method) ||
			strings.EqualFold(descriptor.OperationKind, "command") {
			return nil, ErrDelegatedGrantTargetMismatch
		}
		if _, err := g.verifier.VerifyQuery(
			r.Context(),
			token,
			expected,
		); err != nil {
			return nil, err
		}
	case DelegatedGrantTypeCommand:
		if isSafeReadMethod(r.Method) ||
			!strings.EqualFold(descriptor.OperationKind, "command") {
			return nil, ErrDelegatedGrantTargetMismatch
		}
		if _, err := g.verifier.VerifyCommand(
			r.Context(),
			token,
			expected,
		); err != nil {
			return nil, err
		}
	default:
		return nil, ErrDelegatedGrantInvalid
	}
	principal := delegatedPrincipal(claims)
	ctx := WithPrincipal(r.Context(), principal)
	if grantType == DelegatedGrantTypeCommand {
		ctx = contextWithPendingDelegatedCommand(
			ctx,
			pendingDelegatedCommand{
				consumer: g.commandConsumer,
				token:    token,
				expected: expected,
			},
		)
	}
	return r.WithContext(ctx), nil
}

func delegatedPrincipal(claims DelegatedGrantClaims) Principal {
	tokenType := TokenTypeDelegatedQuery
	if claims.GrantType == DelegatedGrantTypeCommand {
		tokenType = TokenTypeDelegatedCommand
	}
	return Principal{
		Claims: Claims{
			Issuer:    claims.Issuer,
			Audience:  claims.Audience,
			TokenType: tokenType,
			Subject:   claims.AccountID,
			Persona:   claims.PersonaID,
			AuthEpoch: claims.AuthEpoch,
			Scope:     claims.Scope,
			Roles:     []string{"delegated"},
			JWTID:     claims.JWTID,
			IssuedAt:  claims.IssuedAt,
			NotBefore: claims.IssuedAt,
			ExpiresAt: claims.ExpiresAt,
		},
		Actor: operation.ActorContext{
			AccountID: claims.AccountID,
			PersonaID: claims.PersonaID,
		},
	}
}

func delegatedBearerGrant(
	r *http.Request,
) (string, DelegatedGrantType, bool) {
	authorization := strings.TrimSpace(r.Header.Get("Authorization"))
	if !strings.HasPrefix(authorization, "Bearer ") {
		return "", "", false
	}
	token := strings.TrimSpace(strings.TrimPrefix(authorization, "Bearer "))
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return "", "", false
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return "", "", false
	}
	var marker struct {
		GrantType DelegatedGrantType `json:"grantType"`
	}
	if err := json.Unmarshal(payload, &marker); err != nil {
		return "", "", false
	}
	switch marker.GrantType {
	case DelegatedGrantTypeQuery, DelegatedGrantTypeCommand:
		return token, marker.GrantType, true
	default:
		return "", "", false
	}
}

func readAndRestoreRequestBody(r *http.Request) ([]byte, error) {
	if r.Body == nil {
		return nil, nil
	}
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return nil, err
	}
	r.Body = io.NopCloser(bytes.NewReader(body))
	return body, nil
}

// DelegatedRequestDigest returns the only request digest representation used by
// delegated grants.
func DelegatedRequestDigest(body []byte) string {
	sum := sha256.Sum256(body)
	return "sha256:" + hex.EncodeToString(sum[:])
}

func HTTPDelegatedResourceConstraint(
	r *http.Request,
) DelegatedResourceConstraint {
	path := r.URL.EscapedPath()
	if path == "" {
		path = "/"
	}
	if r.URL.RawQuery != "" {
		path += "?" + r.URL.RawQuery
	}
	return DelegatedResourceConstraint{
		Type: "http_request",
		ID:   strings.ToUpper(strings.TrimSpace(r.Method)) + " " + path,
	}
}

type pendingDelegatedCommandContextKey struct{}

type pendingDelegatedCommand struct {
	consumer *DelegatedCommandGrantConsumer
	token    string
	expected DelegatedGrantExpectation
}

func contextWithPendingDelegatedCommand(
	ctx context.Context,
	pending pendingDelegatedCommand,
) context.Context {
	return context.WithValue(ctx, pendingDelegatedCommandContextKey{}, pending)
}

func consumePendingDelegatedCommand(ctx context.Context) error {
	pending, ok := ctx.Value(
		pendingDelegatedCommandContextKey{},
	).(pendingDelegatedCommand)
	if !ok {
		return nil
	}
	if pending.consumer == nil {
		return ErrDelegatedGrantStoreUnavailable
	}
	if _, err := pending.consumer.Consume(
		ctx,
		pending.token,
		pending.expected,
	); err != nil {
		return fmt.Errorf("consume delegated command: %w", err)
	}
	return nil
}

func isSafeReadMethod(method string) bool {
	switch strings.ToUpper(strings.TrimSpace(method)) {
	case http.MethodGet, http.MethodHead, http.MethodOptions:
		return true
	default:
		return false
	}
}
