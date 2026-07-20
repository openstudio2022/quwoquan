package local_contract

import (
	"errors"
	"testing"
	"time"

	homepagemodel "quwoquan_service/services/entity-service/internal/domain/homepage/model"
)

func TestHomepageAggregateStableIdentityRestoreAndCASVersion(t *testing.T) {
	now := time.Date(2026, 7, 20, 1, 0, 0, 0, time.UTC)
	firstID := homepagemodel.StableID(
		"entity:sight:west_lake",
		"qwq_data",
		"地点/景区/西湖",
		"sight",
		"西湖",
	)
	secondID := homepagemodel.StableID(
		"entity:sight:ignored",
		"qwq_data",
		"地点/景区/西湖",
		"sight",
		"不同标题",
	)
	if firstID != secondID || firstID[:3] != "hp_" {
		t.Fatalf("source identity must derive one stable hp_ id: %q %q", firstID, secondID)
	}

	aggregate, err := homepagemodel.Intake(homepagemodel.IntakeParams{
		ID: firstID, Title: "西湖", HomepageType: "sight",
		CanonicalEntityID: "entity:sight:west_lake",
		SourceType:        "official_seed", SourceOwner: "qwq_data",
		SourceEntityRef: "地点/景区/西湖", SourceReleaseID: "release-001",
		CategoryTags: []string{"Entity/地点/景区"},
		Now:          now,
	})
	if err != nil {
		t.Fatalf("intake aggregate: %v", err)
	}
	if aggregate.Version() != 1 || aggregate.Status() != homepagemodel.StatusCandidate {
		t.Fatalf("unexpected initial state: %+v", aggregate.Snapshot())
	}
	if err := aggregate.Publish(now.Add(time.Minute)); err != nil {
		t.Fatalf("publish aggregate: %v", err)
	}
	if aggregate.Version() != 2 || aggregate.Status() != homepagemodel.StatusPublished {
		t.Fatalf("publish must advance version and state: %+v", aggregate.Snapshot())
	}

	snapshot := aggregate.Snapshot()
	snapshot.ID = "homepage_legacy_original"
	restored, err := homepagemodel.Restore(snapshot)
	if err != nil {
		t.Fatalf("restore legacy id: %v", err)
	}
	if restored.ID() != "homepage_legacy_original" {
		t.Fatalf("restore must preserve stored id, got %q", restored.ID())
	}
	if len(restored.Snapshot().ContentPreview) != 0 ||
		len(restored.Snapshot().QuestionPreview) != 0 ||
		len(restored.Snapshot().RelatedGroups) != 0 {
		t.Fatal("aggregate must not synthesize shell projections")
	}
}

func TestHomepageAggregateRejectsCanonicalIdentityMutationAndInvalidTransition(t *testing.T) {
	now := time.Date(2026, 7, 20, 2, 0, 0, 0, time.UTC)
	aggregate, err := homepagemodel.Intake(homepagemodel.IntakeParams{
		Title: "西湖", HomepageType: "sight",
		CanonicalEntityID: "entity:sight:west_lake",
		SourceType:        "official_seed", PublishImmediately: true, Now: now,
	})
	if err != nil {
		t.Fatalf("intake aggregate: %v", err)
	}
	if err := aggregate.Publish(now.Add(time.Minute)); !errors.Is(err, homepagemodel.ErrInvalidTransition) {
		t.Fatalf("published -> published must reject transition, got %v", err)
	}
	if err := aggregate.ApplyImportedProjection(homepagemodel.ImportedProjection{
		Title: "西湖", HomepageType: "hotel", SourceOwner: "qwq_data",
		SourceEntityRef: "地点/住宿/西湖", SourceReleaseID: "release-002", Now: now.Add(time.Minute),
	}); !errors.Is(err, homepagemodel.ErrCanonicalIdentityEdit) {
		t.Fatalf("homepageType mutation must fail, got %v", err)
	}
}
