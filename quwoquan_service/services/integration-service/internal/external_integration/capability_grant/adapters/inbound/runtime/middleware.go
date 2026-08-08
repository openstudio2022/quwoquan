package runtimeadapter

import (
	"context"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
)

// Middleware is the inbound transport for the post-authorization capability
// grant runtime entrypoint. The HTTP owner supplies a typed authorization that
// it constructed only from a verified principal; this adapter never reads an
// account identifier from an untrusted request payload.
type Middleware struct {
	session *grantapp.CapabilityGrantSessionFacade
}

func NewMiddleware(session *grantapp.CapabilityGrantSessionFacade) *Middleware {
	return &Middleware{session: session}
}

func (middleware *Middleware) ResolveConnectorGrant(
	ctx context.Context,
	authorization grantapp.TrustedRuntimeAuthorization,
	request grantapp.ConnectorResolutionRequest,
) (grantapp.ConnectorGrantDecision, error) {
	if middleware == nil || middleware.session == nil || ctx == nil {
		return grantapp.ConnectorGrantDecision{}, grantapp.ErrCapabilityGrantSessionUnavailable
	}
	return middleware.session.ResolveConnectorGrant(ctx, authorization, request)
}

var _ grantapp.ConnectorGrantResolver = (*Middleware)(nil)
