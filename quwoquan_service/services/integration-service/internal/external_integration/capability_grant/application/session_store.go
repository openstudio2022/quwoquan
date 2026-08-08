package application

import (
	"context"
	"errors"
	"time"

	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

var ErrCapabilityGrantSessionNotFound = errors.New(
	"capability grant session not found",
)

// StoredSession is the immutable authorization receipt persisted for the
// fixed 300-second session. It contains only identities and digests; raw
// input, confirmation, permit, credential and Provider proof material are
// forbidden.
type StoredSession struct {
	ResolutionID       string
	AccountDigest      string
	ServiceActorDigest string
	CapabilityKey      string
	SurfaceKind        string
	BindingKind        grantmodel.BindingKind
	BindingDigest      string
	InputDigest        string
	ConfirmationDigest string
	PermitDigest       string
	IdempotencyDigest  string
	ResolvedAt         time.Time
	ExpiresAt          time.Time
}

type SessionStore interface {
	Save(context.Context, grantmodel.ResolvedCapabilityGrant) error
	Load(context.Context, string) (StoredSession, error)
}
