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
