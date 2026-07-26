package local_contract

import (
	"errors"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/model"
	"testing"
	"time"
)

func TestChangeSetEnforcesPlacementLifecycleAndVersion(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	placed, eventType, err := (ChangeSet{
		Kind: ChangePlace, PlacementID: "placement-1", PostID: "post-1",
		OwnerPersonaID: "persona-owner", CircleID: "circle-1", GroupID: "group-1",
		OccurredAt: now,
	}).Apply(nil)
	if err != nil || eventType != "CirclePostPlaced" || placed.Version != 1 ||
		placed.State != CirclePostPlacementStateActive {
		t.Fatalf("place result drift: placement=%+v event=%q err=%v", placed, eventType, err)
	}
	if _, _, err := (ChangeSet{
		Kind: ChangePin, PlacementID: placed.ID, CircleID: placed.CircleID,
		ExpectedVersion: 2, Enabled: true, OccurredAt: now.Add(time.Second),
	}).Apply(&placed); !errors.Is(err, ErrVersionConflict) {
		t.Fatalf("stale version must fail, got %v", err)
	}
	pinned, _, err := (ChangeSet{
		Kind: ChangePin, PlacementID: placed.ID, CircleID: placed.CircleID,
		ExpectedVersion: 1, Enabled: true, OccurredAt: now.Add(time.Second),
	}).Apply(&placed)
	if err != nil || !pinned.Pinned || pinned.Version != 2 || pinned.PinnedAt.IsZero() {
		t.Fatalf("pin result drift: %+v err=%v", pinned, err)
	}
	removed, _, err := (ChangeSet{
		Kind: ChangeRemove, PlacementID: pinned.ID, CircleID: pinned.CircleID,
		ExpectedVersion: 2, OccurredAt: now.Add(2 * time.Second),
	}).Apply(&pinned)
	if err != nil || removed.State != CirclePostPlacementStateRemoved ||
		removed.Pinned || removed.Version != 3 {
		t.Fatalf("remove result drift: %+v err=%v", removed, err)
	}
	if _, _, err := (ChangeSet{
		Kind: ChangeFeature, PlacementID: removed.ID, CircleID: removed.CircleID,
		ExpectedVersion: 3, Enabled: true, OccurredAt: now.Add(3 * time.Second),
	}).Apply(&removed); !errors.Is(err, ErrInactive) {
		t.Fatalf("removed placement must be terminal, got %v", err)
	}
}
