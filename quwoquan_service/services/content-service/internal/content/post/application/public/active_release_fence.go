// Package public contains stable Content application contracts intended for
// in-process service composition and future transport adapters. It exposes no
// storage implementation or MongoDB type.
package public

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
)

var canonicalManifestDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

const ActiveReleaseFenceInvalidCode = "CONTENT.RELEASE.ACTIVE_FENCE_INVALID"

// ActiveReleaseFence is the complete revision fence for one exact
// environment/sourceOwner binding.
type ActiveReleaseFence struct {
	Found             bool
	Environment       string
	SourceOwner       string
	ReleaseID         string
	ManifestDigest    string
	Revision          int64
	ReleaseClass      string
	ProjectionVersion int64
	ActivatedAt       time.Time
}

// ActiveReleaseFenceQuery is the exact lookup key. Callers must supply both
// dimensions; the port never falls back to a default owner or latest scan.
type ActiveReleaseFenceQuery struct {
	Environment string
	SourceOwner string
}

// ActiveReleaseFenceQueryPort is the application/public seam for Content's
// canonical active fence. HTTP/internal-client adapters can expose this same
// contract without sharing Content persistence.
type ActiveReleaseFenceQueryPort interface {
	ReadActiveReleaseFence(
		ctx context.Context,
		query ActiveReleaseFenceQuery,
	) (ActiveReleaseFence, error)
}

// ActiveReleaseFenceError is returned for malformed input and every non-empty
// legacy, incomplete, or drifted result. It is safe for errors.As checks.
type ActiveReleaseFenceError struct {
	Reason string
}

func (err *ActiveReleaseFenceError) Error() string {
	if err == nil || strings.TrimSpace(err.Reason) == "" {
		return ActiveReleaseFenceInvalidCode
	}
	return fmt.Sprintf("%s: %s", ActiveReleaseFenceInvalidCode, err.Reason)
}

func IsActiveReleaseFenceError(err error) bool {
	var invalid *ActiveReleaseFenceError
	return errors.As(err, &invalid)
}

// ActiveReleaseFenceQueryFacade validates both exact lookup key and returned
// tuple. Any partial not-found value or found identity drift fails closed.
type ActiveReleaseFenceQueryFacade struct {
	reader ActiveReleaseFenceQueryPort
}

func NewActiveReleaseFenceQueryFacade(
	reader ActiveReleaseFenceQueryPort,
) *ActiveReleaseFenceQueryFacade {
	return &ActiveReleaseFenceQueryFacade{reader: reader}
}

func (facade *ActiveReleaseFenceQueryFacade) ReadActiveReleaseFence(
	ctx context.Context,
	query ActiveReleaseFenceQuery,
) (ActiveReleaseFence, error) {
	query.Environment = strings.TrimSpace(query.Environment)
	query.SourceOwner = strings.TrimSpace(query.SourceOwner)
	if facade == nil || facade.reader == nil {
		return ActiveReleaseFence{}, &ActiveReleaseFenceError{
			Reason: "active release fence reader is not configured",
		}
	}
	if query.Environment == "" || query.SourceOwner == "" {
		return ActiveReleaseFence{}, &ActiveReleaseFenceError{
			Reason: "environment and sourceOwner are required",
		}
	}
	fence, err := facade.reader.ReadActiveReleaseFence(ctx, query)
	if err != nil {
		return ActiveReleaseFence{}, fmt.Errorf("read Content active release fence: %w", err)
	}
	if err := ValidateActiveReleaseFence(query, fence); err != nil {
		return ActiveReleaseFence{}, err
	}
	return fence, nil
}

// ValidateActiveReleaseFence is exported for HTTP/internal-client adapters
// that must enforce the same wire-to-typed fail-closed contract.
func ValidateActiveReleaseFence(
	query ActiveReleaseFenceQuery,
	fence ActiveReleaseFence,
) error {
	environment := strings.TrimSpace(query.Environment)
	sourceOwner := strings.TrimSpace(query.SourceOwner)
	if environment == "" || sourceOwner == "" {
		return &ActiveReleaseFenceError{Reason: "environment and sourceOwner are required"}
	}
	if !fence.Found {
		if strings.TrimSpace(fence.Environment) != environment ||
			strings.TrimSpace(fence.SourceOwner) != sourceOwner ||
			strings.TrimSpace(fence.ReleaseID) != "" ||
			strings.TrimSpace(fence.ManifestDigest) != "" ||
			strings.TrimSpace(fence.ReleaseClass) != "" ||
			fence.Revision != 0 || fence.ProjectionVersion != 0 ||
			!fence.ActivatedAt.IsZero() {
			return &ActiveReleaseFenceError{Reason: "not-found fence contains state"}
		}
		return nil
	}
	releaseClass := strings.TrimSpace(fence.ReleaseClass)
	if strings.TrimSpace(fence.Environment) != environment ||
		strings.TrimSpace(fence.SourceOwner) != sourceOwner ||
		strings.TrimSpace(fence.ReleaseID) == "" ||
		!canonicalManifestDigestPattern.MatchString(strings.TrimSpace(fence.ManifestDigest)) ||
		(releaseClass != "research" && releaseClass != "commercial") ||
		fence.Revision <= 0 || fence.ProjectionVersion <= 0 ||
		fence.ActivatedAt.IsZero() {
		return &ActiveReleaseFenceError{Reason: "found fence identity is incomplete or drifted"}
	}
	return nil
}

var _ ActiveReleaseFenceQueryPort = (*ActiveReleaseFenceQueryFacade)(nil)
