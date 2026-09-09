// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package domain_test

import (
	"testing"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestActiveSupplySnapshotRequiresReleaseBoundPlayableReadback(t *testing.T) {
	ready := postports.ActiveSupplySnapshot{
		Environment:       "alpha",
		SourceOwner:       "qwq_data",
		Status:            "active",
		ActiveReleaseID:   "rel_pilot_002",
		ManifestDigest:    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ProjectionVersion: 11,
		Revision:          3,
		ActivatedAt:       time.Unix(1_800_000_000, 0).UTC(),
		ReadbackStatus:    "passed",
		Posts:             3,
		PlayableVideos:    1,
	}
	if !ready.Ready() {
		t.Fatalf("complete active supply must be ready: %+v", ready)
	}
	if !ready.ReleaseBoundReadbackReady() || !ready.ContentReady() || !ready.PlayableVideoReady() {
		t.Fatalf("complete snapshot must satisfy every release-bound view: %+v", ready)
	}
	if !(postports.ActiveSupplySnapshot{}).IsEmpty() {
		t.Fatal("zero snapshot must be the sole no-active-release sentinel")
	}

	cases := map[string]func(*postports.ActiveSupplySnapshot){
		"wrong owner":              func(value *postports.ActiveSupplySnapshot) { value.SourceOwner = "other" },
		"missing release identity": func(value *postports.ActiveSupplySnapshot) { value.ActiveReleaseID = "" },
		"missing environment":      func(value *postports.ActiveSupplySnapshot) { value.Environment = "" },
		"invalid digest":           func(value *postports.ActiveSupplySnapshot) { value.ManifestDigest = "bad" },
		"zero projection version":  func(value *postports.ActiveSupplySnapshot) { value.ProjectionVersion = 0 },
		"zero revision":            func(value *postports.ActiveSupplySnapshot) { value.Revision = 0 },
		"missing activated at":     func(value *postports.ActiveSupplySnapshot) { value.ActivatedAt = time.Time{} },
		"readback pending":         func(value *postports.ActiveSupplySnapshot) { value.ReadbackStatus = "pending" },
		"zero posts":               func(value *postports.ActiveSupplySnapshot) { value.Posts = 0 },
		"zero playable video":      func(value *postports.ActiveSupplySnapshot) { value.PlayableVideos = 0 },
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
	zeroSupply.PlayableVideos = 0
	if !zeroSupply.ReleaseBoundReadbackReady() || zeroSupply.IsEmpty() || zeroSupply.ContentReady() {
		t.Fatalf("healthy zero-supply release must remain bound but not ready: %+v", zeroSupply)
	}
}
