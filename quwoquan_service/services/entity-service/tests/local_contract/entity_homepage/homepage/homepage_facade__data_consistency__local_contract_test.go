package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

func TestHomepageFacadesUseOneStoreForReceiptOutboxAliasAndHonestEmptyState(t *testing.T) {
	ctx := context.Background()
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		t.Fatalf("new memory store: %v", err)
	}
	commands, err := homepageapp.NewCommandFacade(store, store)
	if err != nil {
		t.Fatalf("new command facade: %v", err)
	}
	queries, err := homepageapp.NewQueryFacade(store, store)
	if err != nil {
		t.Fatalf("new query facade: %v", err)
	}
	now := time.Date(2026, 7, 20, 3, 0, 0, 0, time.UTC)
	commands.SetClock(func() time.Time { return now })
	meta := homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "create-001"}
	created, err := commands.IntakeCandidate(ctx, meta, homepageapp.Input{
		Title: "西湖", HomepageType: "sight",
		CanonicalEntityID: "entity:sight:west_lake",
	}, "official_seed")
	if err != nil {
		t.Fatalf("intake candidate: %v", err)
	}
	replayed, err := commands.IntakeCandidate(ctx, meta, homepageapp.Input{
		Title: "西湖", HomepageType: "sight",
		CanonicalEntityID: "entity:sight:west_lake",
	}, "official_seed")
	if err != nil || replayed.ID != created.ID || replayed.Version != created.Version {
		t.Fatalf("receipt replay mismatch: view=%+v err=%v", replayed, err)
	}
	if _, err := commands.SuggestCandidate(ctx, meta, homepageapp.Input{
		Title: "黄山", HomepageType: "sight",
	}); err == nil {
		t.Fatal("same actor-scoped idempotency key with another digest must conflict")
	}

	published, err := commands.PublishCandidate(
		ctx,
		homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "publish-001"},
		created.ID,
	)
	if err != nil || published.Version != 2 {
		t.Fatalf("publish candidate: view=%+v err=%v", published, err)
	}
	detail, err := queries.Get(ctx, "entity:sight:west_lake", "", false)
	if err != nil {
		t.Fatalf("canonical exact lookup: %v", err)
	}
	if detail.ID != created.ID {
		t.Fatalf("canonical lookup id=%q want=%q", detail.ID, created.ID)
	}
	if detail.ContentPreview == nil || detail.QuestionPreview == nil ||
		detail.RelatedGroups == nil || detail.RelationEdges == nil {
		t.Fatalf("honest empty projections must be [] on wire view: %+v", detail)
	}
	if len(detail.ContentPreview) != 0 || len(detail.QuestionPreview) != 0 ||
		len(detail.RelatedGroups) != 0 || len(detail.RelationEdges) != 0 {
		t.Fatalf("empty projections must not be synthesized: %+v", detail)
	}
	events, err := store.ReadAfter(ctx, "", 10)
	if err != nil || len(events) != 2 {
		t.Fatalf("durable outbox facts=%d err=%v", len(events), err)
	}
}

func TestHomepageFacadesApplyOwnerBasicsAndFollowerProjectionOutsideAggregate(t *testing.T) {
	ctx := context.Background()
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		t.Fatalf("new memory store: %v", err)
	}
	commands, _ := homepageapp.NewCommandFacade(store, store)
	queries, _ := homepageapp.NewQueryFacade(store, store)
	created, err := commands.IntakeCandidate(
		ctx,
		homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "create-owner"},
		homepageapp.Input{Title: "青城山", HomepageType: "sight"},
		"official_seed",
	)
	if err != nil {
		t.Fatalf("intake candidate: %v", err)
	}
	if _, err := commands.ApplyClaimApproved(
		ctx,
		homepageapp.CommandMeta{ActorID: "claim-consumer", IdempotencyKey: "claim-owner"},
		created.ID,
		"account-owner",
		"persona-owner",
		true,
	); err != nil {
		t.Fatalf("apply claim projection: %v", err)
	}
	if _, err := commands.UpdateClaimedBasics(
		ctx,
		homepageapp.CommandMeta{ActorID: "persona-intruder", IdempotencyKey: "update-intruder"},
		created.ID,
		homepageapp.BasicInput{Subtitle: "越权修改"},
	); err == nil {
		t.Fatal("non-owner homepage update must be rejected")
	} else {
		var appError *rterr.AppError
		if !errors.As(err, &appError) ||
			appError.Code.String() != generated.ErrPermissionDenied.Error() ||
			appError.HTTPStatus != 403 {
			t.Fatalf("non-owner update must return structured 403: %v", err)
		}
	}
	updated, err := commands.UpdateClaimedBasics(
		ctx,
		homepageapp.CommandMeta{ActorID: "persona-owner", IdempotencyKey: "update-owner"},
		created.ID,
		homepageapp.BasicInput{Subtitle: "真实认领资料", City: "成都"},
	)
	if err != nil || updated.Subtitle != "真实认领资料" || updated.City != "成都" {
		t.Fatalf("update owner basics: view=%+v err=%v", updated, err)
	}
	if err := store.UpsertFollowerState(
		ctx, created.ID, "viewer-1", true, 7, time.Now().UTC(),
	); err != nil {
		t.Fatalf("upsert follower projection: %v", err)
	}
	view, err := queries.Get(ctx, created.ID, "viewer-1", true)
	if err != nil {
		t.Fatalf("get homepage with follower view: %v", err)
	}
	if view.FollowerCount != 1 || !view.ViewerFollows {
		t.Fatalf("follower projection not assembled: %+v", view)
	}
	aggregate, found, err := store.Load(ctx, created.ID)
	if err != nil || !found {
		t.Fatalf("load aggregate: found=%v err=%v", found, err)
	}
	if aggregate.Snapshot().RatingCount != 0 {
		t.Fatalf("unrelated projection changed aggregate: %+v", aggregate.Snapshot())
	}
}
