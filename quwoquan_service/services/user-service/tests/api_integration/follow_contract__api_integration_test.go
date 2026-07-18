package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	mqpkg "quwoquan_service/services/user-service/internal/adapters/mq"
	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
)

func TestFollow_Success(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "follower_1", "follower1")
	createTestProfile(t, "followee_1", "followee1")
	createTestPersonaFull(t, "follower_1_persona", "follower_1", "ps_follower_1", "follower1", "default", true)
	createTestPersonaFull(t, "followee_1_persona", "followee_1", "ps_followee_1", "followee1", "default", true)

	eventCh := subscribeUserProfileEvents(t)

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_followee_1/follow",
		"",
		authHeadersForPersona("follower_1", "ps_follower_1"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var followerCount int64
	err := pgPool.QueryRow(context.Background(),
		"SELECT follower_count FROM user_profiles WHERE user_id = $1", "followee_1").Scan(&followerCount)
	if err != nil {
		t.Fatalf("query follower_count: %v", err)
	}
	if followerCount != 1 {
		t.Errorf("expected follower_count=1, got %d", followerCount)
	}
	var followingCount int64
	err = pgPool.QueryRow(context.Background(),
		"SELECT following_count FROM user_profiles WHERE user_id = $1", "follower_1").Scan(&followingCount)
	if err != nil {
		t.Fatalf("query following_count: %v", err)
	}
	if followingCount != 1 {
		t.Errorf("expected following_count=1, got %d", followingCount)
	}

	event := waitForUserEvent(t, eventCh)
	if event.Type != "PersonaFollowStateChanged" {
		t.Fatalf("expected PersonaFollowStateChanged event, got %+v", event)
	}
	if event.UserID != "ps_followee_1" || event.ActorID != "ps_follower_1" {
		t.Fatalf("unexpected event routing: %+v", event)
	}
	if event.Payload["targetPersonaId"] != "ps_followee_1" || event.Payload["sourcePersonaId"] != "ps_follower_1" {
		t.Fatalf("unexpected event payload: %+v", event.Payload)
	}
	snapshot := reltelemetry.Collector().Snapshot()
	if snapshot[reltelemetry.MetricCommandLatencyMs] <= 0 {
		t.Fatalf("expected follow command latency metric > 0, got %v", snapshot)
	}
}

func TestFollow_Idempotent(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "follower_2", "follower2")
	createTestProfile(t, "followee_2", "followee2")
	createTestPersonaFull(t, "follower_2_persona", "follower_2", "ps_follower_2", "follower2", "default", true)
	createTestPersonaFull(t, "followee_2_persona", "followee_2", "ps_followee_2", "followee2", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_followee_2/follow",
		"",
		authHeadersForPersona("follower_2", "ps_follower_2"),
	)
	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_followee_2/follow",
		"",
		authHeadersForPersona("follower_2", "ps_follower_2"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var count int64
	_ = pgPool.QueryRow(context.Background(),
		"SELECT follower_count FROM user_profiles WHERE user_id = $1", "followee_2").Scan(&count)
	if count != 1 {
		t.Errorf("expected follower_count=1 after idempotent follow, got %d", count)
	}
	snapshot := reltelemetry.Collector().Snapshot()
	if snapshot[reltelemetry.MetricDuplicateCommandCount] != 1 {
		t.Fatalf("expected duplicate follow metric=1, got %v", snapshot)
	}
}

func TestFollow_ReconcilesDriftedCounters(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "follower_reconcile", "follower_reconcile")
	createTestProfile(t, "followee_reconcile", "followee_reconcile")
	createTestPersonaFull(t, "follower_reconcile_persona", "follower_reconcile", "ps_follower_reconcile", "follower_reconcile", "default", true)
	createTestPersonaFull(t, "followee_reconcile_persona", "followee_reconcile", "ps_followee_reconcile", "followee_reconcile", "default", true)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles SET follower_count = 41, following_count = 17 WHERE user_id IN ($1, $2)`,
		"follower_reconcile",
		"followee_reconcile",
	); err != nil {
		t.Fatalf("seed drifted counters: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_followee_reconcile/follow",
		"",
		authHeadersForPersona("follower_reconcile", "ps_follower_reconcile"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var followerCount int64
	if err := pgPool.QueryRow(
		context.Background(),
		"SELECT follower_count FROM user_profiles WHERE user_id = $1",
		"followee_reconcile",
	).Scan(&followerCount); err != nil {
		t.Fatalf("query repaired follower_count: %v", err)
	}
	if followerCount != 1 {
		t.Fatalf("expected repaired follower_count=1, got %d", followerCount)
	}

	var followingCount int64
	if err := pgPool.QueryRow(
		context.Background(),
		"SELECT following_count FROM user_profiles WHERE user_id = $1",
		"follower_reconcile",
	).Scan(&followingCount); err != nil {
		t.Fatalf("query repaired following_count: %v", err)
	}
	if followingCount != 1 {
		t.Fatalf("expected repaired following_count=1, got %d", followingCount)
	}
	snapshot := reltelemetry.Collector().Snapshot()
	if snapshot[reltelemetry.MetricCounterMismatchCount] <= 0 {
		t.Fatalf("expected counter mismatch metric > 0 after repair, got %v", snapshot)
	}
}

func TestUnfollow_Success(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "follower_3", "follower3")
	createTestProfile(t, "followee_3", "followee3")
	createTestPersonaFull(t, "follower_3_persona", "follower_3", "ps_follower_3", "follower3", "default", true)
	createTestPersonaFull(t, "followee_3_persona", "followee_3", "ps_followee_3", "followee3", "default", true)

	eventCh := subscribeUserProfileEvents(t)

	doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_followee_3/follow",
		"",
		authHeadersForPersona("follower_3", "ps_follower_3"),
	)
	firstEvent := waitForUserEvent(t, eventCh)
	if firstEvent.Type != "PersonaFollowStateChanged" {
		t.Fatalf("expected first event PersonaFollowStateChanged, got %+v", firstEvent)
	}

	rec := doRequest(
		t,
		http.MethodDelete,
		"/user/sub-accounts/ps_followee_3/follow",
		"",
		authHeadersForPersona("follower_3", "ps_follower_3"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var followerCount int64
	_ = pgPool.QueryRow(context.Background(),
		"SELECT follower_count FROM user_profiles WHERE user_id = $1", "followee_3").Scan(&followerCount)
	if followerCount != 0 {
		t.Errorf("expected follower_count=0 after unfollow, got %d", followerCount)
	}
	var followingCount int64
	_ = pgPool.QueryRow(context.Background(),
		"SELECT following_count FROM user_profiles WHERE user_id = $1", "follower_3").Scan(&followingCount)
	if followingCount != 0 {
		t.Errorf("expected following_count=0 after unfollow, got %d", followingCount)
	}

	event := waitForUserEvent(t, eventCh)
	if event.Type != "PersonaFollowStateChanged" {
		t.Fatalf("expected PersonaFollowStateChanged event, got %+v", event)
	}
	if event.Payload["targetPersonaId"] != "ps_followee_3" || event.Payload["sourcePersonaId"] != "ps_follower_3" {
		t.Fatalf("unexpected unfollow payload: %+v", event.Payload)
	}
}

func TestUnfollowWithoutExistingRelationshipReturnsIdempotentReceipt(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "unfollow_missing_owner", "unfollow_missing_owner")
	createTestPersonaFull(t, "unfollow_missing_owner_persona", "unfollow_missing_owner", "ps_unfollow_missing_owner", "unfollow_missing_owner", "default", true)

	rec := doRequest(
		t,
		http.MethodDelete,
		"/user/sub-accounts/ps_unfollow_missing_target/follow",
		`{"clientRequestId":"unfollow-missing-001"}`,
		authHeadersForPersona("unfollow_missing_owner", "ps_unfollow_missing_owner"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("unfollow missing relationship: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	if body["idempotentReplay"] != true {
		t.Fatalf("missing relationship unfollow must be idempotent, got %#v", body)
	}
}

func TestGetRelationship_Mutual(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_a", "user_a")
	createTestProfile(t, "user_b", "user_b")
	createTestPersonaFull(t, "user_a_persona", "user_a", "ps_user_a", "user_a", "default", true)
	createTestPersonaFull(t, "user_b_persona", "user_b", "ps_user_b", "user_b", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_user_b/follow",
		"",
		authHeadersForPersona("user_a", "ps_user_a"),
	)
	doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_user_a/follow",
		"",
		authHeadersForPersona("user_b", "ps_user_b"),
	)

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_user_b/relationship",
		"",
		authHeadersForPersona("user_a", "ps_user_a"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["relationState"] != "mutual" {
		t.Errorf("expected relationState=mutual, got %v", result["relationState"])
	}
}

func TestListFollowing_Pagination(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "paginator", "paginator")
	createTestPersonaFull(t, "paginator_persona", "paginator", "ps_paginator", "paginator", "default", true)
	for i := 0; i < 5; i++ {
		uid := "target_" + string(rune('a'+i))
		createTestProfile(t, uid, "target_"+string(rune('a'+i)))
		subAccountID := "ps_" + uid
		createTestPersonaFull(t, uid+"_persona", uid, subAccountID, uid, "default", true)
		doRequest(
			t,
			http.MethodPost,
			"/user/sub-accounts/"+subAccountID+"/follow",
			"",
			authHeadersForPersona("paginator", "ps_paginator"),
		)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_paginator/following?limit=3",
		"",
		authHeadersForPersona("paginator", "ps_paginator"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("missing items field")
	}
	if len(items) != 3 {
		t.Errorf("expected 3 items, got %d", len(items))
	}
}

func TestListFollowing_PaginationFillsVisibleItemsAfterFiltering(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	reltelemetry.Reset()
	t.Cleanup(reltelemetry.Reset)
	createTestProfile(t, "paginator_filtered", "paginator_filtered")
	createTestPersonaFull(t, "paginator_filtered_persona", "paginator_filtered", "ps_paginator_filtered", "paginator_filtered", "default", true)

	targets := []string{"a", "b", "c", "d", "e"}
	for _, suffix := range targets {
		ownerID := "filtered_target_" + suffix
		subjectID := "ps_filtered_target_" + suffix
		createTestProfile(t, ownerID, ownerID)
		createTestPersonaFull(t, ownerID+"_persona", ownerID, subjectID, ownerID, "open", true)
		doRequest(
			t,
			http.MethodPost,
			"/user/sub-accounts/"+subjectID+"/follow",
			"",
			authHeadersForPersona("paginator_filtered", "ps_paginator_filtered"),
		)
	}
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET isolation_level = 'strict' WHERE sub_account_id = $1`,
		"ps_filtered_target_b",
	); err != nil {
		t.Fatalf("mark strict persona: %v", err)
	}
	blockRec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_paginator_filtered/block",
		"",
		authHeadersForPersona("filtered_target_c", "ps_filtered_target_c"),
	)
	if blockRec.Code != http.StatusOK {
		t.Fatalf("seed block edge failed: %d %s", blockRec.Code, blockRec.Body.String())
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_paginator_filtered/following?limit=3",
		"",
		authHeadersForPersona("paginator_filtered", "ps_paginator_filtered"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("missing items field")
	}
	if len(items) != 3 {
		t.Fatalf("expected overfetch+fill to return 3 visible items, got %d (%#v)", len(items), result)
	}
	seen := map[string]struct{}{}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("unexpected item payload: %#v", raw)
		}
		subAccountID := item["subAccountId"]
		if subAccountID == "ps_filtered_target_b" || subAccountID == "ps_filtered_target_c" {
			t.Fatalf("filtered targets should not leak into visible page, got %#v", item)
		}
		if _, exists := seen[subAccountID.(string)]; exists {
			t.Fatalf("expected no duplicate visible items, got %#v", items)
		}
		seen[subAccountID.(string)] = struct{}{}
	}
	snapshot := reltelemetry.Collector().Snapshot()
	if snapshot[reltelemetry.MetricFilterMismatchCount] <= 0 {
		t.Fatalf("expected graph filter mismatch metric > 0, got %v", snapshot)
	}
	if snapshot[reltelemetry.MetricListLatencyMs] <= 0 {
		t.Fatalf("expected graph list latency metric > 0, got %v", snapshot)
	}
}

func TestListFollowers_DoesNotExposeOwnerMapping(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "target_owner_graph", "target_owner_graph")
	createTestProfile(t, "shared_owner_graph", "shared_owner_graph")
	createTestProfile(t, "viewer_owner_graph", "viewer_owner_graph")
	createTestPersonaFull(t, "target_owner_graph_persona", "target_owner_graph", "ps_target_owner_graph", "target_owner_graph", "default", true)
	createTestPersonaFull(t, "shared_owner_graph_persona_1", "shared_owner_graph", "ps_shared_owner_graph_1", "shared_owner_graph_1", "default", true)
	createTestPersonaFull(t, "shared_owner_graph_persona_2", "shared_owner_graph", "ps_shared_owner_graph_2", "shared_owner_graph_2", "default", false)
	createTestPersonaFull(t, "viewer_owner_graph_persona", "viewer_owner_graph", "ps_viewer_owner_graph", "viewer_owner_graph", "default", true)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles SET avatar_url = $1, avatar_version = $2 WHERE user_id = $3`,
		"https://cdn.example.com/shared-owner-avatar.png",
		6,
		"shared_owner_graph",
	); err != nil {
		t.Fatalf("seed follower avatar version: %v", err)
	}

	doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_target_owner_graph/follow",
		"",
		authHeadersForPersona("shared_owner_graph", "ps_shared_owner_graph_1"),
	)
	doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_target_owner_graph/follow",
		"",
		authHeadersForPersona("shared_owner_graph", "ps_shared_owner_graph_2"),
	)

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_target_owner_graph/followers?limit=10",
		"",
		authHeadersForPersona("viewer_owner_graph", "ps_viewer_owner_graph"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("missing items field")
	}
	if len(items) != 2 {
		t.Fatalf("expected 2 follower personas, got %d: %#v", len(items), result)
	}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("unexpected follower item: %#v", raw)
		}
		if _, exists := item["ownerUserId"]; exists {
			t.Fatalf("public follower row must not expose ownerUserId, got %#v", item)
		}
		if item["avatarUrl"] != "https://cdn.example.com/shared-owner-avatar.png?v=6" {
			t.Fatalf("expected versioned follower avatarUrl, got %#v", item["avatarUrl"])
		}
		if item["avatarVersion"] != float64(6) {
			t.Fatalf("expected follower avatarVersion=6, got %#v", item["avatarVersion"])
		}
	}
}

func TestFollow_BlockGateRejectsBothDirections(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	reltelemetry.Reset()
	t.Cleanup(reltelemetry.Reset)
	createTestProfile(t, "block_owner_a", "block_owner_a")
	createTestProfile(t, "block_owner_b", "block_owner_b")
	createTestPersonaFull(t, "block_owner_a_persona", "block_owner_a", "ps_block_owner_a", "block_owner_a", "default", true)
	createTestPersonaFull(t, "block_owner_b_persona", "block_owner_b", "ps_block_owner_b", "block_owner_b", "default", true)

	blockRec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_block_owner_b/block",
		"",
		authHeadersForPersona("block_owner_a", "ps_block_owner_a"),
	)
	if blockRec.Code != http.StatusOK {
		t.Fatalf("block should succeed, got %d: %s", blockRec.Code, blockRec.Body.String())
	}

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_block_owner_b/follow",
		"",
		authHeadersForPersona("block_owner_a", "ps_block_owner_a"),
	)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for blocker->blocked follow, got %d: %s", rec.Code, rec.Body.String())
	}
	rec = doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_block_owner_a/follow",
		"",
		authHeadersForPersona("block_owner_b", "ps_block_owner_b"),
	)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for blocked->blocker follow, got %d: %s", rec.Code, rec.Body.String())
	}

	snapshot := reltelemetry.Collector().Snapshot()
	if snapshot[reltelemetry.MetricBlockRejectionCount] != 2 {
		t.Fatalf("expected block rejection metric=2, got %v", snapshot)
	}
}

func subscribeUserProfileEvents(t *testing.T) <-chan mqpkg.DomainEvent {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	t.Cleanup(cancel)
	sub, err := redisClient.Subscribe(ctx, "event:user-profile")
	if err != nil {
		t.Fatalf("subscribe user-profile events: %v", err)
	}
	t.Cleanup(func() { _ = sub.Close() })

	out := make(chan mqpkg.DomainEvent, 8)
	go func() {
		defer close(out)
		for msg := range sub.Channel() {
			var evt mqpkg.DomainEvent
			if err := json.Unmarshal([]byte(msg.Payload), &evt); err != nil {
				continue
			}
			out <- evt
		}
	}()
	time.Sleep(20 * time.Millisecond)
	return out
}

func waitForUserEvent(t *testing.T, ch <-chan mqpkg.DomainEvent) mqpkg.DomainEvent {
	t.Helper()
	select {
	case evt, ok := <-ch:
		if !ok {
			t.Fatal("event channel closed before receiving user event")
		}
		return evt
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for user event")
		return mqpkg.DomainEvent{}
	}
}
