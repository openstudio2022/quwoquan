// Package skillcontext assembles the minimum context declared by the selected
// Skill. It does not load all user, device or memory context eagerly.
package skillcontext

import (
	"context"
	"errors"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type Requirement struct {
	SlotID              string
	Required            bool
	AcceptedSourceKinds []string
	Authority           generated.AssistantContextAuthority
	Sensitivity         generated.AssistantContextSensitivity
	ConsentScopes       []string
	Freshness           time.Duration
	TokenBudget         int
	ResolverRef         string
	FallbackPolicy      string
}

type Profile struct {
	ProfileID    string
	Requirements []Requirement
	AssetDigest  string
}

type DeliveryVisibility string

const (
	DeliveryPersonal DeliveryVisibility = "personal"
	DeliveryShared   DeliveryVisibility = "shared"
	DeliveryPublic   DeliveryVisibility = "public"
)

type AssembleRequest struct {
	RunID              string
	OwnerID            string
	SkillID            string
	Visibility         DeliveryVisibility
	AllowedSensitivity generated.AssistantContextSensitivity
}

type ResolveRequest struct {
	RunID       string
	SkillID     string
	Requirement Requirement
}

type ResolvedContext struct {
	Kind        string
	SourceRef   string
	Authority   generated.AssistantContextAuthority
	Sensitivity generated.AssistantContextSensitivity
	CapturedAt  time.Time
	ExpiresAt   time.Time
	TokenCost   int
	Value       map[string]any
	ArtifactRef string
	Summary     string
}

type Segment struct {
	SegmentID   string
	SlotID      string
	Kind        string
	SourceRef   string
	Authority   generated.AssistantContextAuthority
	Sensitivity generated.AssistantContextSensitivity
	CapturedAt  time.Time
	ExpiresAt   time.Time
	Digest      string
	TokenCost   int
	Value       map[string]any
	ArtifactRef string
}

type Snapshot struct {
	SnapshotID string
	CapturedAt time.Time
	Segments   []Segment
	Missing    []MissingRequirement
	TokenCost  int
}

type MissingRequirement struct {
	SlotID         string
	FallbackPolicy string
	Reason         string
}

type Resolver interface {
	Resolve(context.Context, ResolveRequest) (ResolvedContext, error)
}

type ConsentReader interface {
	AllowsContext(
		context.Context,
		string,
		string,
		[]string,
	) (bool, error)
}

type ConsentReaderFunc func(
	context.Context,
	string,
	string,
	[]string,
) (bool, error)

func (read ConsentReaderFunc) AllowsContext(
	ctx context.Context,
	ownerID string,
	skillID string,
	scopes []string,
) (bool, error) {
	return read(ctx, ownerID, skillID, scopes)
}

var (
	ErrInvalidProfile      = errors.New("invalid assistant context profile")
	ErrResolverUnavailable = errors.New("assistant context resolver unavailable")
	ErrContextRejected     = errors.New("assistant context rejected by platform policy")
	ErrConsentUnavailable  = errors.New("assistant context consent unavailable")
)
