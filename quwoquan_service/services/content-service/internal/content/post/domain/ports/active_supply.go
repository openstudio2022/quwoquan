package ports

import (
	"context"
	"regexp"
	"strings"
)

var canonicalReleaseDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// ActiveSupplySnapshot identifies the canonical data release whose materialized
// Post and discovery-feed projections may serve a
// release-bound initial page. The counts are live readback counts, never the
// importer's attempted-write counters.
type ActiveSupplySnapshot struct {
	Environment     string
	SourceOwner     string
	Status          string
	ActiveReleaseID string
	ManifestDigest  string
	ReadbackStatus  string
	Posts           int64
	DiscoveryPosts  int64
	PlayableVideos  int64
}

func (snapshot ActiveSupplySnapshot) ReleaseBoundReadbackReady() bool {
	return strings.TrimSpace(snapshot.Environment) != "" &&
		strings.TrimSpace(snapshot.SourceOwner) == "qwq_data" &&
		strings.TrimSpace(snapshot.Status) == "active" &&
		strings.TrimSpace(snapshot.ActiveReleaseID) != "" &&
		canonicalReleaseDigestPattern.MatchString(strings.TrimSpace(snapshot.ManifestDigest)) &&
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
		strings.TrimSpace(snapshot.ReadbackStatus) == "" &&
		snapshot.Posts == 0 &&
		snapshot.DiscoveryPosts == 0 &&
		snapshot.PlayableVideos == 0
}

func (snapshot ActiveSupplySnapshot) DiscoveryReady() bool {
	return snapshot.ReleaseBoundReadbackReady() &&
		snapshot.Posts > 0 &&
		snapshot.DiscoveryPosts > 0
}

func (snapshot ActiveSupplySnapshot) PlayableVideoReady() bool {
	return snapshot.DiscoveryReady() && snapshot.PlayableVideos > 0
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
