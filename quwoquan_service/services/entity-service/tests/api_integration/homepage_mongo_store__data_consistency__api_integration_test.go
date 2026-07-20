package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	homepageapp "quwoquan_service/services/entity-service/internal/application/homepage"
	homepagemodel "quwoquan_service/services/entity-service/internal/domain/homepage/model"
	homepageports "quwoquan_service/services/entity-service/internal/domain/homepage/ports"
	"quwoquan_service/services/entity-service/internal/generated"
	homepagepersistence "quwoquan_service/services/entity-service/internal/infrastructure/homepage/persistence"

	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
)

func TestHomepageMongoStoreIdentityCASReceiptOutboxAndProjections(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	container, err := tryRunReviewMongoContainer(ctx)
	if err != nil {
		t.Fatalf("mongo testcontainer unavailable: %v", err)
	}
	defer func() { _ = container.Terminate(context.Background()) }()
	uri, err := container.ConnectionString(ctx)
	if err != nil {
		t.Fatalf("mongo connection string: %v", err)
	}
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatalf("mongo connect: %v", err)
	}
	defer func() { _ = client.Disconnect(context.Background()) }()
	store := homepagepersistence.NewMongoHomepageStore(
		client.Database("entity_homepage_it"),
		true,
	)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure homepage indexes: %v", err)
	}
	commands, err := homepageapp.NewCommandFacade(store, store)
	if err != nil {
		t.Fatalf("new command facade: %v", err)
	}
	queries, err := homepageapp.NewQueryFacade(store, store)
	if err != nil {
		t.Fatalf("new query facade: %v", err)
	}

	created, err := commands.IntakeCandidate(
		ctx,
		homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "mongo-create"},
		homepageapp.Input{
			Title: "西湖", HomepageType: "sight",
			CanonicalEntityID: "entity:sight:west_lake",
		},
		"official_seed",
	)
	if err != nil {
		t.Fatalf("intake homepage: %v", err)
	}
	replayed, err := commands.IntakeCandidate(
		ctx,
		homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "mongo-create"},
		homepageapp.Input{
			Title: "西湖", HomepageType: "sight",
			CanonicalEntityID: "entity:sight:west_lake",
		},
		"official_seed",
	)
	if err != nil || replayed.ID != created.ID || replayed.Version != 1 {
		t.Fatalf("receipt replay failed: view=%+v err=%v", replayed, err)
	}
	if _, err := commands.SuggestCandidate(
		ctx,
		homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "mongo-create"},
		homepageapp.Input{Title: "黄山", HomepageType: "sight"},
	); !errorsIsRuntimeCode(err, generated.ErrIdempotencyConflict) {
		t.Fatalf("receipt digest conflict must fail, got %v", err)
	}

	alias, found, err := store.FindExact(ctx, homepageports.ExactLookup{
		LookupAlias: "西湖",
	})
	if err != nil || !found || alias.ID != created.ID {
		t.Fatalf("lookupAlias exact read: snapshot=%+v found=%v err=%v", alias, found, err)
	}

	first, found, err := store.Load(ctx, created.ID)
	if err != nil || !found {
		t.Fatalf("load first aggregate: found=%v err=%v", found, err)
	}
	stale, found, err := store.Load(ctx, created.ID)
	if err != nil || !found {
		t.Fatalf("load stale aggregate: found=%v err=%v", found, err)
	}
	now := time.Now().UTC()
	if err := first.Publish(now); err != nil {
		t.Fatalf("publish first aggregate: %v", err)
	}
	if _, err := store.Commit(ctx, mongoCommit(first, 1, "operator", "mongo-publish-1", "digest-publish-1", "evt-publish-1", now)); err != nil {
		t.Fatalf("commit first publish: %v", err)
	}
	if err := stale.Publish(now.Add(time.Second)); err != nil {
		t.Fatalf("publish stale aggregate: %v", err)
	}
	if _, err := store.Commit(ctx, mongoCommit(stale, 1, "operator-2", "mongo-publish-2", "digest-publish-2", "evt-publish-2", now.Add(time.Second))); !errorsIsRuntimeCode(err, generated.ErrVersionConflict) {
		t.Fatalf("stale CAS must conflict, got %v", err)
	}

	duplicate, err := homepagemodel.Intake(homepagemodel.IntakeParams{
		ID: "hp_duplicate_canonical", Title: "西湖别名", HomepageType: "sight",
		CanonicalEntityID: "entity:sight:west_lake", SourceType: "official_seed",
		Now: now.Add(2 * time.Second),
	})
	if err != nil {
		t.Fatalf("create duplicate aggregate: %v", err)
	}
	if _, err := store.Commit(ctx, mongoCommit(duplicate, 0, "operator-3", "mongo-duplicate", "digest-duplicate", "evt-duplicate", now.Add(2*time.Second))); !errorsIsRuntimeCode(err, generated.ErrVersionConflict) {
		t.Fatalf("canonical unique index must conflict, got %v", err)
	}

	if _, err := commands.ApplyClaimApproved(
		ctx,
		homepageapp.CommandMeta{ActorID: "claim-consumer", IdempotencyKey: "mongo-claim"},
		created.ID,
		"account-owner",
		"persona-owner",
		true,
	); err != nil {
		t.Fatalf("apply claim projection: %v", err)
	}
	updated, err := commands.UpdateClaimedBasics(
		ctx,
		homepageapp.CommandMeta{ActorID: "persona-owner", IdempotencyKey: "mongo-basics"},
		created.ID,
		homepageapp.BasicInput{Subtitle: "真实维护资料", City: "杭州"},
	)
	if err != nil || updated.OwnerUserID != "account-owner" || updated.Subtitle != "真实维护资料" {
		t.Fatalf("owner basics projection failed: view=%+v err=%v", updated, err)
	}
	if len(updated.ContentPreview) != 0 || len(updated.QuestionPreview) != 0 ||
		len(updated.RelatedGroups) != 0 {
		t.Fatalf("mongo read must preserve honest empty projections: %+v", updated)
	}

	if err := store.UpsertFollowerState(
		ctx, created.ID, "viewer-1", true, 1, now,
	); err != nil {
		t.Fatalf("upsert follower: %v", err)
	}
	view, err := queries.Get(ctx, created.ID, "viewer-1", true)
	if err != nil || view.FollowerCount != 1 || !view.ViewerFollows {
		t.Fatalf("follower projection view=%+v err=%v", view, err)
	}
	events, err := store.ReadAfter(ctx, "", 20)
	if err != nil || len(events) < 4 {
		t.Fatalf("homepage outbox facts=%d err=%v", len(events), err)
	}
}

func TestHomepageMongoImporterUpsertsBySourceIdentity(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	container, err := tryRunReviewMongoContainer(ctx)
	if err != nil {
		t.Fatalf("mongo testcontainer unavailable: %v", err)
	}
	defer func() { _ = container.Terminate(context.Background()) }()
	uri, err := container.ConnectionString(ctx)
	if err != nil {
		t.Fatalf("mongo connection string: %v", err)
	}
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatalf("mongo connect: %v", err)
	}
	defer func() { _ = client.Disconnect(context.Background()) }()
	store := homepagepersistence.NewMongoHomepageStore(
		client.Database("entity_homepage_import_it"),
		true,
	)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure homepage indexes: %v", err)
	}
	commands, _ := homepageapp.NewCommandFacade(store, store)
	imports, _ := homepageapp.NewImportFacade(commands, store, store)
	input := homepageapp.ImportedInput{
		EntityRef: "地点/景区/黄龙", Title: "黄龙", HomepageType: "sight", City: "阿坝",
	}
	first, err := imports.Reconcile(ctx, homepageapp.ImportRequest{
		Mode: homepageapp.ImportModeUpsert, SourceOwner: "qwq_data",
		SourceReleaseID: "release-001", Inputs: []homepageapp.ImportedInput{input},
	})
	if err != nil {
		t.Fatalf("first source import: %v", err)
	}
	second, err := imports.Reconcile(ctx, homepageapp.ImportRequest{
		Mode: homepageapp.ImportModeUpsert, SourceOwner: "qwq_data",
		SourceReleaseID: "release-002", Inputs: []homepageapp.ImportedInput{input},
	})
	if err != nil {
		t.Fatalf("second source import: %v", err)
	}
	firstID := first.EntityRefToHomepageID[input.EntityRef]
	if firstID == "" || second.EntityRefToHomepageID[input.EntityRef] != firstID ||
		len(first.Created) != 1 || len(second.Updated) != 1 {
		t.Fatalf("source upsert identity drift: first=%+v second=%+v", first, second)
	}
	snapshot, found, err := store.FindExact(ctx, homepageports.ExactLookup{
		SourceOwner: "qwq_data", SourceEntityRef: input.EntityRef,
	})
	if err != nil || !found || snapshot.ID != firstID || snapshot.SourceReleaseID != "release-002" {
		t.Fatalf("source exact read: snapshot=%+v found=%v err=%v", snapshot, found, err)
	}
}

func mongoCommit(
	aggregate *homepagemodel.Homepage,
	expectedVersion int64,
	actorID string,
	key string,
	digest string,
	eventID string,
	now time.Time,
) homepageports.Commit {
	payload, _ := json.Marshal(aggregate.Snapshot())
	return homepageports.Commit{
		Aggregate: aggregate, ExpectedVersion: expectedVersion,
		ActorID: actorID, IdempotencyKey: key, CommandName: "MongoStoreTest",
		CommandDigest: digest, ReceiptExpiresAt: now.Add(24 * time.Hour),
		Event: homepageports.OutboxEvent{
			EventID: eventID, EventType: "HomepageMongoStoreTest",
			AggregateID: aggregate.ID(), AggregateVersion: aggregate.Version(),
			Payload: payload, OccurredAt: now,
		},
	}
}

func errorsIsRuntimeCode(err error, code error) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) && appError.Code.String() == code.Error()
}
