// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package api_integration

import (
	"errors"
	"strconv"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/runtime/accountrestriction"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/persistence"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
	placementpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
)

func TestUserAccountClosedTerminalMarkerRetainsSourcePELReference(
	t *testing.T,
) {
	cleanCollections(t)
	ctx := t.Context()
	projection := persistence.NewMongoUserAccountClosedProjection(
		mongoDB,
		redisRouter.Scene("general"),
	)
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	const sourceStreamID = "1710000000000-72"
	if attempts, err := projection.RecordUserAccountClosedFailure(
		ctx,
		sourceStreamID,
		"circle-account-closure-event-72",
		errors.New("scripted cleanup dependency failure"),
	); err != nil || attempts != 1 {
		t.Fatalf("record failure: attempts=%d err=%v", attempts, err)
	}
	if err := projection.MarkUserAccountClosedDeadLettered(
		ctx,
		sourceStreamID,
	); err != nil {
		t.Fatal(err)
	}
	var marker bson.M
	if err := mongoDB.Collection("circle_user_account_closed_failures").FindOne(
		ctx,
		bson.M{"sourceStreamId": sourceStreamID},
	).Decode(&marker); err != nil {
		t.Fatalf("read terminal marker by source reference: %v", err)
	}
	if marker["deadLetteredAt"] == nil {
		t.Fatalf("terminal marker lacks dead-letter state: %v", marker)
	}
	if _, exists := marker["expiresAt"]; exists {
		t.Fatalf("terminal marker retained transient TTL: %v", marker)
	}
}

func TestUserAccountClosedRealProjectionNormalReplayAndConflict(
	t *testing.T,
) {
	cleanCollections(t)
	ctx := t.Context()
	now := time.Date(2026, 7, 20, 9, 0, 0, 0, time.UTC)
	seedAccountClosureTransferFixture(t, now)
	if err := redisRouter.Scene("general").Set(
		ctx,
		"cache:circle:circle-transfer",
		"stale",
		time.Minute,
	); err != nil {
		t.Fatal(err)
	}

	projection := persistence.NewMongoUserAccountClosedProjection(
		mongoDB,
		redisRouter.Scene("general"),
	)
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	restrictionProjection, err :=
		persistence.NewMongoUserAccountRestrictionProjection(mongoDB)
	if err != nil {
		t.Fatal(err)
	}
	if err := restrictionProjection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	suspension := accountrestriction.Event{
		EventID:        "event-suspend-circle-10",
		EventName:      accountrestriction.UserSuspendedEventName,
		AccountID:      "account-closed",
		AccountVersion: 10,
		UserID:         "account-closed",
		PersonaIDs:     []string{"persona-closed"},
		AccountState:   "suspended",
		AuthEpoch:      10,
		DecisionRef:    "decision-suspend-circle-10",
		OccurredAt:     now.Add(-time.Minute),
	}
	if result, err := restrictionProjection.Apply(ctx, suspension); err != nil || result.Replayed {
		t.Fatalf("apply Circle suspension: result=%+v err=%v", result, err)
	}
	sameVersionConflict := suspension
	sameVersionConflict.EventID = "event-suspend-circle-10-conflict"
	sameVersionConflict.DecisionRef = "decision-suspend-circle-10-conflict"
	if _, err := restrictionProjection.Apply(
		ctx,
		sameVersionConflict,
	); !errors.Is(err, application.ErrUserAccountRestrictionProjectionConflict) {
		t.Fatalf("same-version Circle restriction conflict err=%v", err)
	}
	// Closure also erases legacy rows from the superseded generic adapter.
	if _, err := mongoDB.Collection("circle_user_account_restrictions").InsertOne(
		ctx,
		bson.M{
			"_id": "account-closed", "subjects": []string{"account-closed", "persona-closed"},
			"restricted": true, "accountVersion": int64(9),
		},
	); err != nil {
		t.Fatal(err)
	}
	if _, err := mongoDB.Collection("circle_user_account_restriction_inbox").InsertOne(
		ctx,
		bson.M{
			"_id": "event-legacy-suspend-circle-9", "accountId": "account-closed",
			"accountVersion": int64(9),
		},
	); err != nil {
		t.Fatal(err)
	}
	consumer, err := messaging.NewUserAccountClosedConsumerWithConfig(
		circleMessageTransport,
		projection,
		projection,
		"account-closure-api-integration",
		nil,
		messaging.UserAccountClosedConsumerConfig{
			BatchSize: 10, MaxAttempts: 3, MinIdle: 0,
			ReadBlock: 0, PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	event := accountClosureEvent(
		"event-account-closure-transfer",
		"account-closed",
		11,
		[]string{"persona-closed"},
		now,
	)
	values := accountClosureStreamValues(event)
	if _, err := redisRouter.Scene("general").XAdd(
		ctx,
		messaging.UserAccountEventStream,
		values,
	); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("UserAccountClosed ProcessOnce count=%d err=%v", count, err)
	}
	if _, err := redisRouter.Scene("general").Get(
		ctx,
		"cache:circle:circle-transfer",
	); err == nil {
		t.Fatal("account closure must invalidate affected Circle cache")
	}

	assertAccountClosureTransferState(t)
	latePostProjection := placementpersistence.NewMongoPostLifecycleProjection(
		mongoDB,
	)
	if err := latePostProjection.ApplyPostLifecycle(
		ctx,
		placementports.PostLifecycleEvent{
			EventID: "late-post-event", EventType: "PostPublished",
			PostID: "late-post", PostVersion: 1,
			OwnerPersonaID: "persona-closed", State: "published",
			OccurredAt: now.Add(time.Minute),
		},
	); err != nil {
		t.Fatal(err)
	}
	if count := countDocuments(
		t,
		"circle_post_owner_views",
		bson.M{"_id": "late-post"},
	); count != 0 {
		t.Fatalf("late Content event recreated closed owner view")
	}
	if count := countDocuments(
		t,
		"circle_user_account_closed_inbox",
		bson.M{},
	); count != 1 {
		t.Fatalf("account-closure inbox count=%d want=1", count)
	}
	if count := countDocuments(
		t,
		"circle_closed_account_subjects",
		bson.M{},
	); count != 2 {
		t.Fatalf("closed-subject tombstone count=%d want=2", count)
	}
	if count := countDocuments(t, "circle_user_account_restrictions", bson.M{}); count != 0 {
		t.Fatalf("closed-account restriction state remaining=%d", count)
	}
	if count := countDocuments(t, "circle_user_account_restriction_inbox", bson.M{}); count != 0 {
		t.Fatalf("closed-account restriction inbox remaining=%d", count)
	}
	lateRestore := suspension
	lateRestore.EventID = "event-restore-circle-after-close-12"
	lateRestore.EventName = accountrestriction.UserRestoredEventName
	lateRestore.AccountVersion = 12
	lateRestore.AccountState = "active"
	lateRestore.AuthEpoch = 12
	lateRestore.DecisionRef = "decision-restore-circle-after-close-12"
	lateRestore.OccurredAt = now.Add(time.Minute)
	if late, err := restrictionProjection.Apply(ctx, lateRestore); err != nil ||
		!late.Replayed || !late.Stale || !late.Terminal || late.Affected != 0 {
		t.Fatalf("late Circle restore after closure: result=%+v err=%v", late, err)
	}
	delayedSuspend := suspension
	delayedSuspend.EventID = "event-delayed-suspend-circle-9"
	delayedSuspend.AccountVersion = 9
	delayedSuspend.AuthEpoch = 9
	delayedSuspend.DecisionRef = "decision-delayed-suspend-circle-9"
	delayedSuspend.OccurredAt = now.Add(-2 * time.Minute)
	if late, err := restrictionProjection.Apply(ctx, delayedSuspend); err != nil ||
		!late.Replayed || !late.Stale || !late.Terminal || late.Affected != 0 {
		t.Fatalf("delayed Circle suspend after closure: result=%+v err=%v", late, err)
	}
	if count := countDocuments(t, "circle_user_account_restrictions", bson.M{}); count != 0 {
		t.Fatalf("late events recreated Circle restriction state=%d", count)
	}
	if count := countDocuments(t, "circle_user_account_restriction_inbox", bson.M{}); count != 0 {
		t.Fatalf("late events recreated Circle restriction inbox=%d", count)
	}
	var terminalWatermark bson.M
	if err := mongoDB.Collection("circle_user_account_restriction_watermarks").FindOne(
		ctx,
		bson.M{"terminal": true, "accountVersion": int64(11)},
	).Decode(&terminalWatermark); err != nil {
		t.Fatalf("read Circle terminal restriction watermark: %v", err)
	}
	encodedWatermark, err := bson.MarshalExtJSON(terminalWatermark, false, false)
	if err != nil {
		t.Fatal(err)
	}
	for _, rawID := range []string{"account-closed", "persona-closed"} {
		if strings.Contains(string(encodedWatermark), rawID) {
			t.Fatalf("Circle terminal watermark retained raw identity %q: %s", rawID, encodedWatermark)
		}
	}

	if _, err := redisRouter.Scene("general").XAdd(
		ctx,
		messaging.UserAccountEventStream,
		values,
	); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("replayed UserAccountClosed count=%d err=%v", count, err)
	}
	if count := countDocuments(
		t,
		"circle_user_account_closed_inbox",
		bson.M{},
	); count != 1 {
		t.Fatalf("replay duplicated inbox: count=%d", count)
	}
	if count := countDocuments(
		t,
		"circle_membership_outbox",
		bson.M{},
	); count != 2 {
		t.Fatalf("replay duplicated CircleMembership outbox: count=%d", count)
	}

	conflictingID := event
	conflictingID.OccurredAt = event.OccurredAt.Add(time.Second)
	if _, err := projection.ApplyUserAccountClosed(
		ctx,
		conflictingID,
	); !errors.Is(err, application.ErrUserAccountClosedEventConflict) {
		t.Fatalf("eventId conflict error=%v", err)
	}
	conflictingVersion := event
	conflictingVersion.EventID = "different-event-same-account-version"
	if _, err := projection.ApplyUserAccountClosed(
		ctx,
		conflictingVersion,
	); !errors.Is(err, application.ErrUserAccountClosedEventConflict) {
		t.Fatalf("account-version conflict error=%v", err)
	}
}

func TestUserAccountClosedOwnerlessAggregatesArchiveFailClosed(
	t *testing.T,
) {
	cleanCollections(t)
	ctx := t.Context()
	now := time.Date(2026, 7, 20, 10, 0, 0, 0, time.UTC)
	seedAccountClosureArchiveFixture(t, now)
	projection := persistence.NewMongoUserAccountClosedProjection(
		mongoDB,
		redisRouter.Scene("general"),
	)
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	event := accountClosureEvent(
		"event-account-closure-archive",
		"account-archive",
		3,
		[]string{"persona-group-owner", "persona-circle-owner"},
		now,
	)
	if _, err := projection.ApplyUserAccountClosed(ctx, event); err != nil {
		t.Fatal(err)
	}

	var forced struct {
		Status  string `bson:"status"`
		OwnerID string `bson:"ownerId"`
	}
	if err := mongoDB.Collection("circles").FindOne(
		ctx,
		bson.M{"_id": "circle-default-group-ownerless"},
	).Decode(&forced); err != nil {
		t.Fatal(err)
	}
	if forced.Status != "archived" || forced.OwnerID != "persona-still-open" {
		t.Fatalf("default-group fail-closed Circle drift: %#v", forced)
	}
	var ownerless struct {
		Status  string `bson:"status"`
		OwnerID string `bson:"ownerId"`
	}
	if err := mongoDB.Collection("circles").FindOne(
		ctx,
		bson.M{"_id": "circle-ownerless"},
	).Decode(&ownerless); err != nil {
		t.Fatal(err)
	}
	if ownerless.Status != "archived" ||
		!strings.HasPrefix(ownerless.OwnerID, "closed_") {
		t.Fatalf("ownerless Circle must archive and anonymize owner: %#v", ownerless)
	}
	var group struct {
		Status string `bson:"status"`
	}
	if err := mongoDB.Collection("circle_groups").FindOne(
		ctx,
		bson.M{"_id": "group-default-ownerless"},
	).Decode(&group); err != nil {
		t.Fatal(err)
	}
	if group.Status != "archived" {
		t.Fatalf("ownerless default CircleGroup status=%q", group.Status)
	}
	if count := countDocuments(
		t,
		"circles",
		bson.M{
			"_id": bson.M{"$in": bson.A{
				"circle-default-group-ownerless",
				"circle-ownerless",
			}},
			"status": "active",
		},
	); count != 0 {
		t.Fatalf("ownerless active Circle count=%d want=0", count)
	}
}

func seedAccountClosureTransferFixture(t *testing.T, now time.Time) {
	t.Helper()
	ctx := t.Context()
	mustInsertMany(t, "circles", []any{
		bson.M{
			"_id": "circle-transfer", "version": int64(1),
			"name": "transfer", "ownerId": "persona-closed",
			"ownerDisplayNameSnapshot": "closed name",
			"category":                 "interest", "tags": bson.A{"tag"},
			"status": "active", "defaultPublicGroupId": "group-transfer",
			"memberCount": int64(4), "weeklyActiveCount": int64(4),
			"createdAt": now.Add(-24 * time.Hour), "updatedAt": now.Add(-time.Hour),
		},
	})
	mustInsertMany(t, "circle_memberships", []any{
		accountClosureMembership(
			"membership-owner",
			"circle-transfer",
			"persona-closed",
			"owner",
			"active",
			now.Add(-4*time.Hour),
		),
		accountClosureMembership(
			"membership-admin",
			"circle-transfer",
			"persona-admin",
			"admin",
			"active",
			now.Add(-2*time.Hour),
		),
		accountClosureMembership(
			"membership-member",
			"circle-transfer",
			"persona-member",
			"member",
			"active",
			now.Add(-20*time.Hour),
		),
		accountClosureMembership(
			"membership-pending",
			"circle-transfer",
			"account-closed",
			"member",
			"pending",
			now.Add(-time.Hour),
		),
	})
	mustInsertMany(t, "circle_groups", []any{
		bson.M{
			"_id": "group-transfer", "version": int64(1),
			"circleId": "circle-transfer", "groupType": "self_built",
			"createdByPersonaId": "persona-closed", "status": "active",
			"isDefaultPublicGroup": false,
			"createdAt":            now.Add(-4 * time.Hour), "updatedAt": now.Add(-time.Hour),
		},
	})
	mustInsertMany(t, "circle_group_memberships", []any{
		accountClosureGroupMembership(
			"group-membership-owner",
			"group-transfer",
			"circle-transfer",
			"persona-closed",
			"owner",
			"active",
			now.Add(-4*time.Hour),
		),
		accountClosureGroupMembership(
			"group-membership-manager",
			"group-transfer",
			"circle-transfer",
			"persona-manager",
			"manager",
			"active",
			now.Add(-2*time.Hour),
		),
		accountClosureGroupMembership(
			"group-membership-pending",
			"group-transfer",
			"circle-transfer",
			"account-closed",
			"member",
			"pending",
			now.Add(-time.Hour),
		),
	})
	mustInsertMany(t, "circle_files", []any{
		bson.M{
			"_id": "file-closed", "version": int64(1),
			"circleId": "circle-transfer", "uploaderPersonaId": "persona-closed",
			"status": "active", "createdAt": now.Add(-time.Hour),
			"updatedAt": now.Add(-time.Hour),
		},
	})
	mustInsertMany(t, "circle_behavior_facts", []any{
		bson.M{
			"_id": "behavior-closed", "circleId": "circle-transfer",
			"personaId": "persona-closed", "actorKind": "persona",
			"occurredAt": now.Add(-time.Minute),
		},
		bson.M{
			"_id": "behavior-open", "circleId": "circle-transfer",
			"personaId": "persona-open", "actorKind": "persona",
			"occurredAt": now.Add(-time.Minute),
		},
	})
	mustInsertMany(t, "circle_behavior_fact_outbox", []any{
		bson.M{
			"_id":         "behavior-outbox-closed",
			"aggregateId": "behavior-closed",
			"payloadJson": `{"personaId":"persona-closed"}`,
		},
	})
	mustInsertMany(t, "circle_post_placements", []any{
		bson.M{
			"_id": "placement-closed", "version": int64(1),
			"postId": "post-closed", "ownerPersonaId": "persona-closed",
			"circleId": "circle-transfer", "groupId": "group-transfer",
			"state": "published", "pinned": true, "featured": true,
			"createdAt": now.Add(-time.Hour), "updatedAt": now.Add(-time.Hour),
		},
	})
	mustInsertMany(t, "circle_feed_items", []any{
		bson.M{
			"_id": "post-closed", "authorId": "persona-closed",
			"circleId": "circle-transfer",
		},
	})
	mustInsertMany(t, "circle_post_owner_views", []any{
		bson.M{
			"_id": "post-closed", "ownerPersonaId": "persona-closed",
			"state": "published", "postVersion": int64(1),
		},
	})
	mustInsertMany(t, "circle_membership_outbox", []any{
		bson.M{
			"_id":            "existing-membership-event",
			"outboxSequence": int64(1), "eventType": "CircleMembershipJoined",
			"aggregateId": "membership-owner", "aggregateVersion": int64(1),
			"payloadJson": `{"personaId":"persona-closed"}`,
			"occurredAt":  now.Add(-time.Hour),
		},
	})
	mustInsertMany(t, "circle_membership_outbox_sequences", []any{
		bson.M{"_id": "CircleMembership", "value": int64(1)},
	})
	if _, err := mongoDB.Collection("circle_outbox").InsertOne(
		ctx,
		bson.M{
			"_id":            "existing-circle-event",
			"outboxSequence": int64(1), "eventType": "CircleCreated",
			"aggregateId": "circle-transfer", "aggregateVersion": int64(1),
			"payloadJson": `{"ownerId":"persona-closed"}`,
			"occurredAt":  now.Add(-time.Hour),
		},
	); err != nil {
		t.Fatal(err)
	}
	mustInsertMany(t, "circle_outbox_sequences", []any{
		bson.M{"_id": "Circle", "value": int64(1)},
	})
}

func seedAccountClosureArchiveFixture(t *testing.T, now time.Time) {
	t.Helper()
	mustInsertMany(t, "circles", []any{
		bson.M{
			"_id": "circle-default-group-ownerless", "version": int64(1),
			"name": "forced", "ownerId": "persona-still-open",
			"category": "interest", "tags": bson.A{},
			"status": "active", "defaultPublicGroupId": "group-default-ownerless",
			"createdAt": now.Add(-time.Hour), "updatedAt": now.Add(-time.Hour),
		},
		bson.M{
			"_id": "circle-ownerless", "version": int64(1),
			"name": "ownerless", "ownerId": "persona-circle-owner",
			"category": "interest", "tags": bson.A{},
			"status": "active", "defaultPublicGroupId": "",
			"createdAt": now.Add(-time.Hour), "updatedAt": now.Add(-time.Hour),
		},
	})
	mustInsertMany(t, "circle_memberships", []any{
		accountClosureMembership(
			"membership-open-owner",
			"circle-default-group-ownerless",
			"persona-still-open",
			"owner",
			"active",
			now.Add(-time.Hour),
		),
		accountClosureMembership(
			"membership-closed-owner",
			"circle-ownerless",
			"persona-circle-owner",
			"owner",
			"active",
			now.Add(-time.Hour),
		),
	})
	mustInsertMany(t, "circle_groups", []any{
		bson.M{
			"_id": "group-default-ownerless", "version": int64(1),
			"circleId":           "circle-default-group-ownerless",
			"groupType":          "public_default",
			"createdByPersonaId": "persona-group-owner",
			"status":             "active", "isDefaultPublicGroup": true,
			"createdAt": now.Add(-time.Hour), "updatedAt": now.Add(-time.Hour),
		},
	})
	mustInsertMany(t, "circle_group_memberships", []any{
		accountClosureGroupMembership(
			"group-membership-closed-owner",
			"group-default-ownerless",
			"circle-default-group-ownerless",
			"persona-group-owner",
			"owner",
			"active",
			now.Add(-time.Hour),
		),
	})
}

func assertAccountClosureTransferState(t *testing.T) {
	t.Helper()
	ctx := t.Context()
	var circle struct {
		OwnerID           string `bson:"ownerId"`
		Status            string `bson:"status"`
		MemberCount       int64  `bson:"memberCount"`
		WeeklyActiveCount int64  `bson:"weeklyActiveCount"`
	}
	if err := mongoDB.Collection("circles").FindOne(
		ctx,
		bson.M{"_id": "circle-transfer"},
	).Decode(&circle); err != nil {
		t.Fatal(err)
	}
	if circle.OwnerID != "persona-admin" ||
		circle.Status != "active" ||
		circle.MemberCount != 2 ||
		circle.WeeklyActiveCount != 1 {
		t.Fatalf("Circle closure reconciliation drift: %#v", circle)
	}
	if count := countDocuments(
		t,
		"circle_memberships",
		bson.M{
			"circleId":  "circle-transfer",
			"personaId": "persona-admin",
			"role":      "owner",
			"state":     "active",
		},
	); count != 1 {
		t.Fatalf("deterministic admin successor count=%d want=1", count)
	}
	assertClosedSubjectAnonymized(t, "circle_memberships", "membership-owner")
	assertClosedSubjectAnonymized(t, "circle_memberships", "membership-pending")
	if count := countDocuments(
		t,
		"circle_group_memberships",
		bson.M{
			"groupId":   "group-transfer",
			"personaId": "persona-manager",
			"role":      "owner",
			"state":     "active",
		},
	); count != 1 {
		t.Fatalf("deterministic manager successor count=%d want=1", count)
	}
	assertClosedSubjectAnonymized(
		t,
		"circle_group_memberships",
		"group-membership-owner",
	)
	assertClosedSubjectAnonymized(
		t,
		"circle_group_memberships",
		"group-membership-pending",
	)
	for collection, filter := range map[string]bson.M{
		"circle_behavior_facts":       {"_id": "behavior-closed"},
		"circle_behavior_fact_outbox": {"aggregateId": "behavior-closed"},
		"circle_feed_items":           {"_id": "post-closed"},
		"circle_post_owner_views":     {"_id": "post-closed"},
	} {
		if count := countDocuments(t, collection, filter); count != 0 {
			t.Fatalf("%s retained closed-subject data", collection)
		}
	}
	var file struct {
		UploaderPersonaID string `bson:"uploaderPersonaId"`
	}
	if err := mongoDB.Collection("circle_files").FindOne(
		ctx,
		bson.M{"_id": "file-closed"},
	).Decode(&file); err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(file.UploaderPersonaID, "closed_") {
		t.Fatalf("CircleFile uploader was not anonymized: %#v", file)
	}
	var group struct {
		CreatedByPersonaID string `bson:"createdByPersonaId"`
		Status             string `bson:"status"`
	}
	if err := mongoDB.Collection("circle_groups").FindOne(
		ctx,
		bson.M{"_id": "group-transfer"},
	).Decode(&group); err != nil {
		t.Fatal(err)
	}
	if group.Status != "active" ||
		!strings.HasPrefix(group.CreatedByPersonaID, "closed_") {
		t.Fatalf("CircleGroup provenance drift: %#v", group)
	}
	var placement struct {
		OwnerPersonaID string `bson:"ownerPersonaId"`
		State          string `bson:"state"`
		Pinned         bool   `bson:"pinned"`
		Featured       bool   `bson:"featured"`
	}
	if err := mongoDB.Collection("circle_post_placements").FindOne(
		ctx,
		bson.M{"_id": "placement-closed"},
	).Decode(&placement); err != nil {
		t.Fatal(err)
	}
	if placement.State != "removed" ||
		placement.Pinned ||
		placement.Featured ||
		!strings.HasPrefix(placement.OwnerPersonaID, "closed_") {
		t.Fatalf("CirclePostPlacement closure drift: %#v", placement)
	}
	for _, collection := range []string{
		"circle_outbox",
		"circle_membership_outbox",
	} {
		if count := countDocuments(
			t,
			collection,
			bson.M{
				"payloadJson": bson.M{
					"$regex": "persona-closed|account-closed",
				},
			},
		); count != 0 {
			t.Fatalf("%s retained raw closed-subject payload", collection)
		}
	}
}

func assertClosedSubjectAnonymized(
	t *testing.T,
	collection string,
	id string,
) {
	t.Helper()
	var document struct {
		PersonaID string `bson:"personaId"`
		Role      string `bson:"role"`
		State     string `bson:"state"`
	}
	if err := mongoDB.Collection(collection).FindOne(
		t.Context(),
		bson.M{"_id": id},
	).Decode(&document); err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(document.PersonaID, "closed_") ||
		document.Role != "member" ||
		document.State != "removed" {
		t.Fatalf("%s/%s anonymization drift: %#v", collection, id, document)
	}
}

func accountClosureEvent(
	eventID string,
	accountID string,
	version int64,
	personaIDs []string,
	now time.Time,
) application.UserAccountClosedEvent {
	return application.UserAccountClosedEvent{
		EventID: eventID, AccountID: accountID, UserID: accountID,
		AccountVersion: version, PersonaIDs: personaIDs,
		AccountState: "closed", UpdatedAt: now.UTC(), OccurredAt: now.UTC(),
	}
}

func accountClosureStreamValues(
	event application.UserAccountClosedEvent,
) map[string]string {
	personaJSON := `["` + strings.Join(event.PersonaIDs, `","`) + `"]`
	return map[string]string{
		"eventId":        event.EventID,
		"eventName":      application.UserAccountClosedEventName,
		"accountId":      event.AccountID,
		"accountVersion": strconv.FormatInt(event.AccountVersion, 10),
		"payload": `{"userId":"` + event.UserID +
			`","personaIds":` + personaJSON +
			`,"accountState":"closed","updatedAt":"` +
			event.UpdatedAt.UTC().Format(time.RFC3339Nano) + `"}`,
		"occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}
}

func accountClosureMembership(
	id string,
	circleID string,
	personaID string,
	role string,
	state string,
	createdAt time.Time,
) bson.M {
	return bson.M{
		"_id": id, "version": int64(1), "circleId": circleID,
		"personaId": personaID, "role": role, "state": state,
		"joinedAt": createdAt.UTC(), "lastActiveAt": createdAt.UTC(),
		"contribution": int64(8), "createdAt": createdAt.UTC(),
		"updatedAt": createdAt.UTC(),
	}
}

func accountClosureGroupMembership(
	id string,
	groupID string,
	circleID string,
	personaID string,
	role string,
	state string,
	createdAt time.Time,
) bson.M {
	return bson.M{
		"_id": id, "version": int64(1), "groupId": groupID,
		"circleId": circleID, "personaId": personaID,
		"role": role, "state": state, "joinedAt": createdAt.UTC(),
		"decidedAt":          createdAt.UTC(),
		"decidedByPersonaId": personaID,
		"createdAt":          createdAt.UTC(), "updatedAt": createdAt.UTC(),
	}
}

func mustInsertMany(t *testing.T, collection string, documents []any) {
	t.Helper()
	if len(documents) == 0 {
		return
	}
	if _, err := mongoDB.Collection(collection).InsertMany(
		t.Context(),
		documents,
	); err != nil {
		t.Fatalf("seed %s: %v", collection, err)
	}
}

func countDocuments(
	t *testing.T,
	collection string,
	filter bson.M,
) int64 {
	t.Helper()
	count, err := mongoDB.Collection(collection).CountDocuments(
		t.Context(),
		filter,
	)
	if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
		t.Fatalf("count %s: %v", collection, err)
	}
	return count
}
