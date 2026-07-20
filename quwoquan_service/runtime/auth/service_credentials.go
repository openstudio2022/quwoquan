package auth

import (
	"context"
	"fmt"
	"strings"
)

// ServiceAuthorizationProvider creates a short-lived authorization header for
// one service-to-service request. Production composition derives it from the
// same runtime signing config used by inbound verifiers; long-lived bearer
// strings are intentionally not part of this contract.
type ServiceAuthorizationProvider interface {
	AuthorizationHeader(ctx context.Context) (string, error)
}

// DelegatedPersonaAuthorizationProvider 为服务间只读调用签发带真实 persona actor
// 的短期凭据。调用方服务身份保留在 account subject，禁止使用可伪造的自定义 header。
type DelegatedPersonaAuthorizationProvider interface {
	AuthorizationHeaderForPersona(
		ctx context.Context,
		personaID string,
	) (string, error)
}

type HS256ServiceAuthorizationProvider struct {
	signer  *Signer
	subject TokenSubject
}

func NewHS256ServiceAuthorizationProvider(
	config TokenConfig,
	serviceName string,
	scopes []string,
) (*HS256ServiceAuthorizationProvider, error) {
	normalizedService := strings.TrimSpace(serviceName)
	if normalizedService == "" {
		return nil, fmt.Errorf("service credential subject is required")
	}
	if len(scopes) == 0 {
		return nil, fmt.Errorf("service credential scope is required")
	}
	signer, err := NewHS256Signer(config)
	if err != nil {
		return nil, fmt.Errorf("service credential signer invalid: %w", err)
	}
	return &HS256ServiceAuthorizationProvider{
		signer: signer,
		subject: TokenSubject{
			AccountID: "service:" + normalizedService,
			Scopes:    append([]string(nil), scopes...),
			Roles:     []string{"service"},
		},
	}, nil
}

func (p *HS256ServiceAuthorizationProvider) AuthorizationHeader(
	_ context.Context,
) (string, error) {
	if p == nil || p.signer == nil {
		return "", fmt.Errorf("service credential provider is not initialized")
	}
	token, err := p.signer.Sign(p.subject)
	if err != nil {
		return "", err
	}
	return "Bearer " + token, nil
}

type HS256DelegatedPersonaAuthorizationProvider struct {
	signer      *Signer
	serviceName string
	scopes      []string
}

func NewHS256DelegatedPersonaAuthorizationProvider(
	config TokenConfig,
	serviceName string,
	scopes []string,
) (*HS256DelegatedPersonaAuthorizationProvider, error) {
	normalizedService := strings.TrimSpace(serviceName)
	if normalizedService == "" {
		return nil, fmt.Errorf("delegated credential service subject is required")
	}
	if len(scopes) == 0 {
		return nil, fmt.Errorf("delegated credential scope is required")
	}
	signer, err := NewHS256Signer(config)
	if err != nil {
		return nil, fmt.Errorf("delegated credential signer invalid: %w", err)
	}
	return &HS256DelegatedPersonaAuthorizationProvider{
		signer:      signer,
		serviceName: normalizedService,
		scopes:      append([]string(nil), scopes...),
	}, nil
}

func (p *HS256DelegatedPersonaAuthorizationProvider) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	if p == nil || p.signer == nil {
		return "", fmt.Errorf("delegated credential provider is not initialized")
	}
	normalizedPersona := strings.TrimSpace(personaID)
	if normalizedPersona == "" {
		return "", fmt.Errorf("delegated credential persona is required")
	}
	token, err := p.signer.Sign(TokenSubject{
		AccountID: "service:" + p.serviceName,
		PersonaID: normalizedPersona,
		Scopes:    append([]string(nil), p.scopes...),
		Roles:     []string{"service"},
	})
	if err != nil {
		return "", err
	}
	return "Bearer " + token, nil
}
