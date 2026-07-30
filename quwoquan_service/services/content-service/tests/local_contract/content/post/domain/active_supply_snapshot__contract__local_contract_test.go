// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package domain_test

import (
	"testing"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestActiveSupplySnapshotRequiresReleaseBoundPlayableReadback(t *testing.T) {
	ready := postports.ActiveSupplySnapshot{
		Environment:           "alpha",
		SourceOwner:           "qwq_data",
		Status:                "active",
		ActiveReleaseID:       "rel_pilot_002",
		ManifestDigest:        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ReadbackStatus:        "passed",
		Posts:                 3,
		DiscoveryPosts:        3,
		PremiumPlayableVideos: 1,
	}
	if !ready.Ready() {
		t.Fatalf("complete active supply must be ready: %+v", ready)
	}
	if !ready.ReleaseBoundReadbackReady() || !ready.DiscoveryReady() || !ready.PremiumVideoReady() {
		t.Fatalf("complete snapshot must satisfy every release-bound view: %+v", ready)
	}
	if !(postports.ActiveSupplySnapshot{}).IsEmpty() {
		t.Fatal("zero snapshot must be the sole no-active-release sentinel")
	}

	cases := map[string]func(*postports.ActiveSupplySnapshot){
		"wrong owner":      func(value *postports.ActiveSupplySnapshot) { value.SourceOwner = "other" },
		"invalid digest":   func(value *postports.ActiveSupplySnapshot) { value.ManifestDigest = "bad" },
		"readback pending": func(value *postports.ActiveSupplySnapshot) { value.ReadbackStatus = "pending" },
		"zero posts":       func(value *postports.ActiveSupplySnapshot) { value.Posts = 0 },
		"zero discovery":   func(value *postports.ActiveSupplySnapshot) { value.DiscoveryPosts = 0 },
		"zero premium":     func(value *postports.ActiveSupplySnapshot) { value.PremiumPlayableVideos = 0 },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			candidate := ready
			mutate(&candidate)
			if candidate.Ready() {
				t.Fatalf("incomplete snapshot must fail closed: %+v", candidate)
			}
		})
	}

	zeroSupply := ready
	zeroSupply.Posts = 0
	zeroSupply.DiscoveryPosts = 0
	zeroSupply.PremiumPlayableVideos = 0
	if !zeroSupply.ReleaseBoundReadbackReady() || zeroSupply.IsEmpty() || zeroSupply.DiscoveryReady() {
		t.Fatalf("healthy zero-supply release must remain bound but not ready: %+v", zeroSupply)
	}
}
