package ports

import (
	"context"
	"time"
)

// ContentReleaseFence is the sole live fence for release-owned Creator reads.
// It must be supplied by Content's authoritative active tuple reader.
type ContentReleaseFence struct {
	Environment    string
	SourceOwner    string
	ReleaseID      string
	ManifestDigest string
}

type CreatorDisclosureView struct {
	Type        string `json:"type"`
	DisplayText string `json:"displayText"`
	Visible     bool   `json:"visible"`
}

type CreatorWorkView struct {
	Ref       string
	Title     string
	CoverURL  string
	WorkType  string
	SortOrder int
}

type CreatorRuntimeProfileView struct {
	CreatorID            string
	PersonaID            string
	Handle               string
	DisplayName          string
	Headline             string
	Bio                  string
	AvatarURL            string
	AvatarAssetID        string
	AvatarAccessMode     string
	AvatarVersion        int64
	CoverURL             string
	PublicProfileTagRefs []string
	Roles                []string
	Verticals            []string
	ExpertiseClaims      []string
	Disclosure           CreatorDisclosureView
	Works                []CreatorWorkView
	UpdatedAt            time.Time
}

// ContentReleaseFenceReader is an adapter seam for Content's active tuple.
// User must not implement this by maintaining its own active/latest pointer.
type ContentReleaseFenceReader interface {
	ActiveContentReleaseFence(ctx context.Context) (ContentReleaseFence, bool, error)
}

// CreatorRuntimeProfileReader reads only the candidate matching an exact
// authoritative Content fence; legacy content_release Persona is no fallback.
type CreatorRuntimeProfileReader interface {
	FindByExactContentFence(ctx context.Context, fence ContentReleaseFence, identity string) (*CreatorRuntimeProfileView, bool, error)
	ListWorksByExactContentFence(ctx context.Context, fence ContentReleaseFence, identity string) ([]CreatorWorkView, bool, error)
}
