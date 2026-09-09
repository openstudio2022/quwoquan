package ports

import (
	"context"
	"regexp"
	"strings"
	"time"
)

var canonicalReleaseDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// IsKnownReleaseClass 只接受 Data producer 的单一现役类别 production。
// 历史封存类别不得进入 active pointer 或在线读面。
func IsKnownReleaseClass(releaseClass string) bool {
	return releaseClass == "production"
}

// ActiveSupplySnapshot identifies the canonical data release whose materialized
// Posts may serve a release-bound initial page. Recommendation candidate
// readiness belongs to recommendation-service and is not duplicated here.
type ActiveSupplySnapshot struct {
	Environment     string
	SourceOwner     string
	Status          string
	ActiveReleaseID string
	ManifestDigest  string
	// ReleaseClass 由 importer 从 release.json 落到 data_release_state；
	// 活跃类别只允许 production，历史类别不能作为在线供给。
	ReleaseClass      string
	ProjectionVersion int64
	Revision          int64
	ActivatedAt       time.Time
	ReadbackStatus    string
	Posts             int64
	PlayableVideos    int64
}

func (snapshot ActiveSupplySnapshot) ReleaseBoundReadbackReady() bool {
	releaseClass := strings.TrimSpace(snapshot.ReleaseClass)
	return strings.TrimSpace(snapshot.Environment) != "" &&
		strings.TrimSpace(snapshot.SourceOwner) == "qwq_data" &&
		strings.TrimSpace(snapshot.Status) == "active" &&
		strings.TrimSpace(snapshot.ActiveReleaseID) != "" &&
		canonicalReleaseDigestPattern.MatchString(strings.TrimSpace(snapshot.ManifestDigest)) &&
		IsKnownReleaseClass(releaseClass) &&
		snapshot.ProjectionVersion > 0 &&
		snapshot.Revision > 0 &&
		!snapshot.ActivatedAt.IsZero() &&
		strings.TrimSpace(snapshot.ReadbackStatus) == "passed"
}

// IsEmpty means the authoritative reader completed successfully and found no
// active canonical release. A partially populated snapshot is invalid rather
// than empty and must fail closed at the application boundary.
func (snapshot ActiveSupplySnapshot) IsEmpty() bool {
	return strings.TrimSpace(snapshot.Environment) == "" &&
		strings.TrimSpace(snapshot.SourceOwner) == "" &&
		strings.TrimSpace(snapshot.Status) == "" &&
		strings.TrimSpace(snapshot.ActiveReleaseID) == "" &&
		strings.TrimSpace(snapshot.ManifestDigest) == "" &&
		strings.TrimSpace(snapshot.ReleaseClass) == "" &&
		snapshot.ProjectionVersion == 0 &&
		snapshot.Revision == 0 &&
		snapshot.ActivatedAt.IsZero() &&
		strings.TrimSpace(snapshot.ReadbackStatus) == "" &&
		snapshot.Posts == 0 &&
		snapshot.PlayableVideos == 0
}

func (snapshot ActiveSupplySnapshot) ContentReady() bool {
	return snapshot.ReleaseBoundReadbackReady() &&
		snapshot.Posts > 0
}

func (snapshot ActiveSupplySnapshot) PlayableVideoReady() bool {
	return snapshot.ContentReady() && snapshot.PlayableVideos > 0
}

func (snapshot ActiveSupplySnapshot) Ready() bool {
	return snapshot.PlayableVideoReady()
}

type ActiveSupplyReader interface {
	ActiveSupplySnapshot(ctx context.Context) (ActiveSupplySnapshot, error)
}

// PlayableVideoSupplyReader counts canonical playable video Posts bound to the
// same active release. Premium recommendation eligibility belongs exclusively
// to recommendation-service and is not part of Content release attestation.
type PlayableVideoSupplyReader interface {
	CountActiveReleasePlayableVideos(
		ctx context.Context,
		activeReleaseID string,
		manifestDigest string,
	) (int64, error)
}
