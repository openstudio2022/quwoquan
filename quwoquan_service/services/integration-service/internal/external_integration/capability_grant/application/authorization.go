package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

var ErrRuntimeAuthorizationInvalid = errors.New(
	"capability grant runtime authorization is invalid",
)

const (
	AssistantServiceActorID         = "assistant-service"
	IntegrationServiceWorkerActorID = "integration-service-worker"
)

// TrustedRuntimeAuthorization carries the two independently verified actors
// admitted by the transport: the real account subject and the calling service
// actor. The account is never derived from a service:* subject or request body.
type TrustedRuntimeAuthorization struct {
	AccountID      string
	ServiceActorID string
}

// TrustedRuntimeWorkerAuthorization is deliberately narrower than a service
// principal. It can only resume a session that was originally authorized for
// the Assistant service and never creates a new grant by itself.
type TrustedRuntimeWorkerAuthorization struct {
	AccountID     string
	WorkerActorID string
}

func NewTrustedRuntimeAuthorization(
	accountID string,
	serviceActorID string,
) (TrustedRuntimeAuthorization, error) {
	accountID = strings.TrimSpace(accountID)
	serviceActorID = strings.TrimSpace(serviceActorID)
	if accountID == "" || strings.HasPrefix(accountID, "service:") ||
		serviceActorID != AssistantServiceActorID {
		return TrustedRuntimeAuthorization{}, ErrRuntimeAuthorizationInvalid
	}
	return TrustedRuntimeAuthorization{
		AccountID:      accountID,
		ServiceActorID: serviceActorID,
	}, nil
}

func NewTrustedRuntimeWorkerAuthorization(
	accountID string,
	workerActorID string,
) (TrustedRuntimeWorkerAuthorization, error) {
	accountID = strings.TrimSpace(accountID)
	workerActorID = strings.TrimSpace(workerActorID)
	if accountID == "" || strings.HasPrefix(accountID, "service:") ||
		workerActorID != IntegrationServiceWorkerActorID {
		return TrustedRuntimeWorkerAuthorization{}, ErrRuntimeAuthorizationInvalid
	}
	return TrustedRuntimeWorkerAuthorization{
		AccountID: accountID, WorkerActorID: workerActorID,
	}, nil
}

type ConnectorResolutionRequest struct {
	ResolutionID   string
	CapabilityKey  string
	SurfaceKind    string
	ConnectionRefs []string
}

type ConnectorGrantDecision struct {
	Allowed       bool
	CapabilityKey string
	SurfaceKind   string
	ConnectionID  string
	ConnectorID   string
	FreshnessAt   *time.Time
	ExpiresAt     *time.Time
	Reason        string
}

type ConnectorGrantResolver interface {
	ResolveConnectorGrant(
		ctx context.Context,
		authorization TrustedRuntimeAuthorization,
		request ConnectorResolutionRequest,
	) (ConnectorGrantDecision, error)
}
