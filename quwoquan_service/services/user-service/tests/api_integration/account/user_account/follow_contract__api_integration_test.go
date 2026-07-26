package api_integration

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-001
import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"sort"
	"testing"
	"time"

	mqpkg "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/mq"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

func urlQueryEscape(value string) string {
	return url.QueryEscape(value)
}

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

	waitForProfileCounters(t, "followee_1", 1, 0)
	waitForProfileCounters(t, "follower_1", 0, 1)

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

	waitForProfileCounters(t, "followee_2", 1, 0)
	waitForProfileCounters(t, "follower_2", 0, 1)
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

	waitForProfileCounters(t, "followee_reconcile", 42, 17)
	waitForProfileCounters(t, "follower_reconcile", 41, 18)
	repaired, err := relationshipCounterReconciler.ReconcileAll(
		context.Background(),
		100,
	)
	if err != nil {
		t.Fatalf("reconcile drifted counters: %v", err)
	}
	if repaired < 2 {
		t.Fatalf("expected at least two repaired owner profiles, got %d", repaired)
	}
	waitForProfileCounters(t, "followee_reconcile", 1, 0)
	waitForProfileCounters(t, "follower_reconcile", 0, 1)
	snapshot := reltelemetry.Collector().Snapshot()
	if snapshot[reltelemetry.MetricCounterMismatchCount] <= 0 {
		t.Fatalf("expected counter mismatch metric > 0 after repair, got %v", snapshot)
	}
}

func TestFollow_CommandP95DoesNotScaleWithHundredThousandFollowers(
	t *testing.T,
) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "scale_target", "scale_target")
	createTestPersonaFull(
		t,
		"scale_target_persona",
		"scale_target",
		"ps_scale_target",
		"scale_target",
		"default",
		true,
	)
	if _, err := pgPool.Exec(
		context.Background(),
		`INSERT INTO persona_relationships(
		   pair_id,
		   lower_persona_id,
		   upper_persona_id,
		   version,
		   created_at,
		   updated_at
		 )
		 SELECT 'scale_pair_' || value,
		        'ps_scale_target',
		        'scale_fan_' || value,
		        1,
		        NOW(),
		        NOW()
		 FROM generate_series(1, 100000) AS value;

		 INSERT INTO persona_relationship_directions(
		   pair_id,
		   source_persona_id,
		   target_persona_id,
		   following,
		   blocked,
		   follow_source,
		   followed_at,
		   updated_at
		 )
		 SELECT 'scale_pair_' || value,
		        'scale_fan_' || value,
		        'ps_scale_target',
		        TRUE,
		        FALSE,
		        'performance_contract',
		        NOW(),
		        NOW()
		 FROM generate_series(1, 100000) AS value;

		 UPDATE user_profiles
		 SET follower_count=100000
		 WHERE user_id='scale_target'`,
	); err != nil {
		t.Fatalf("seed 100k relationship fanout: %v", err)
	}

	const samples = 20
	latencies := make([]time.Duration, 0, samples)
	for index := 0; index < samples; index++ {
		ownerID := "scale_actor_" + string(rune('a'+index))
		personaID := "ps_" + ownerID
		createTestProfile(t, ownerID, ownerID)
		createTestPersonaFull(
			t,
			ownerID+"_persona",
			ownerID,
			personaID,
			ownerID,
			"default",
			true,
		)
		startedAt := time.Now()
		rec := doRequest(
			t,
			http.MethodPost,
			"/user/sub-accounts/ps_scale_target/follow",
			"",
			authHeadersForPersona(ownerID, personaID),
		)
		latencies = append(latencies, time.Since(startedAt))
		if rec.Code != http.StatusOK {
			t.Fatalf(
				"scale follow %d: expected 200, got %d: %s",
				index,
				rec.Code,
				rec.Body.String(),
			)
		}
	}
	sort.Slice(latencies, func(left, right int) bool {
		return latencies[left] < latencies[right]
	})
	p95 := latencies[18]
	t.Logf("100k-follower command P95=%s", p95)
	if p95 > 500*time.Millisecond {
		t.Fatalf(
			"100k-follower command P95=%s exceeds 500ms; samples=%v",
			p95,
			latencies,
		)
	}
	// 该测试的 command P95 与异步投影收敛是两个独立断言。10 万关系的
	// 已存在 fanout 不能改变写命令延迟，也不应把调度竞争误判为投影遗漏。
	waitForProfileCountersWithin(
		t,
		"scale_target",
		100000+samples,
		0,
		15*time.Second,
	)
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

	waitForProfileCounters(t, "followee_3", 0, 0)
	waitForProfileCounters(t, "follower_3", 0, 0)

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

// TestFollow_ForgedActorPersonaRejected 越权负例：合法账号 token + body 伪造他人
// persona 作为 actorSubAccountId，必须 403，且不得产生任何关系写入。
func TestFollow_ForgedActorPersonaRejected(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "forge_attacker", "forge_attacker")
	createTestProfile(t, "forge_victim", "forge_victim")
	createTestProfile(t, "forge_target", "forge_target")
	createTestPersonaFull(t, "forge_attacker_persona", "forge_attacker", "ps_forge_attacker", "forge_attacker", "default", true)
	createTestPersonaFull(t, "forge_victim_persona", "forge_victim", "ps_forge_victim", "forge_victim", "default", true)
	createTestPersonaFull(t, "forge_target_persona", "forge_target", "ps_forge_target", "forge_target", "default", true)

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_forge_target/follow",
		`{"actorSubAccountId":"ps_forge_victim"}`,
		authHeadersForPersona("forge_attacker", "ps_forge_attacker"),
	)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("forged actor follow: expected 403, got %d: %s", rec.Code, rec.Body.String())
	}

	var edgeCount int64
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM persona_relationship_directions WHERE source_persona_id = $1`,
		"ps_forge_victim",
	).Scan(&edgeCount); err != nil {
		t.Fatalf("query forged edges: %v", err)
	}
	if edgeCount != 0 {
		t.Fatalf("forged actor must not create relationship rows, got %d", edgeCount)
	}

	var victimFollowing int64
	if err := pgPool.QueryRow(
		context.Background(),
		"SELECT following_count FROM user_profiles WHERE user_id = $1",
		"forge_victim",
	).Scan(&victimFollowing); err != nil {
		t.Fatalf("query victim following_count: %v", err)
	}
	if victimFollowing != 0 {
		t.Fatalf("victim following_count must stay 0, got %d", victimFollowing)
	}
}

// TestFollow_ExplicitActorOwnedPersonaAllowed 同账号内显式指定另一个归属 persona
// 是 actor_self 合法场景，必须放行并以该 persona 记账。
func TestFollow_ExplicitActorOwnedPersonaAllowed(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "multi_owner", "multi_owner")
	createTestProfile(t, "multi_target", "multi_target")
	createTestPersonaFull(t, "multi_owner_primary", "multi_owner", "ps_multi_primary", "multi_primary", "default", true)
	// (user_id, is_active) 唯一：同账号第二分身只能非活跃；归属校验不要求 active。
	createTestPersonaFull(t, "multi_owner_second", "multi_owner", "ps_multi_second", "multi_second", "default", false, false)
	createTestPersonaFull(t, "multi_target_persona", "multi_target", "ps_multi_target", "multi_target", "default", true)

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_multi_target/follow",
		`{"actorSubAccountId":"ps_multi_second"}`,
		authHeadersForPersona("multi_owner", "ps_multi_primary"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("owned second persona follow: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	if body["actorSubAccountId"] != "ps_multi_second" {
		t.Fatalf("expected actorSubAccountId=ps_multi_second, got %#v", body)
	}
}

// TestFollow_RetiredExplicitActorRejected 已退役 persona 不得再作为显式 actor。
func TestFollow_RetiredExplicitActorRejected(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "retired_owner", "retired_owner")
	createTestProfile(t, "retired_target", "retired_target")
	createTestPersonaFull(t, "retired_owner_primary", "retired_owner", "ps_retired_primary", "retired_primary", "default", true)
	createTestPersonaFull(t, "retired_owner_old", "retired_owner", "ps_retired_old", "retired_old", "default", false, false)
	createTestPersonaFull(t, "retired_target_persona", "retired_target", "ps_retired_target", "retired_target", "default", true)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET status = 'retired', retired_at = NOW() WHERE sub_account_id = $1`,
		"ps_retired_old",
	); err != nil {
		t.Fatalf("retire persona fixture: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_retired_target/follow",
		`{"actorSubAccountId":"ps_retired_old"}`,
		authHeadersForPersona("retired_owner", "ps_retired_primary"),
	)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("retired actor follow: expected 403, got %d: %s", rec.Code, rec.Body.String())
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

// SIT2：粉丝/关注行必须携带 viewer→row 完整 relationshipCapability，
// 端侧行内动作矩阵不得从 relationState 单字段猜测。
func TestListFollowRowsCarryViewerRelationshipCapability(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "cap_viewer", "cap_viewer")
	createTestProfile(t, "cap_target", "cap_target")
	createTestProfile(t, "cap_mutual", "cap_mutual")
	createTestPersonaFull(t, "cap_viewer_persona", "cap_viewer", "ps_cap_viewer", "cap_viewer", "default", true)
	createTestPersonaFull(t, "cap_target_persona", "cap_target", "ps_cap_target", "cap_target", "default", true)
	createTestPersonaFull(t, "cap_mutual_persona", "cap_mutual", "ps_cap_mutual", "cap_mutual", "default", true)

	// viewer 关注 target 与 mutual；mutual 回关 viewer（形成互关）。
	for _, target := range []string{"ps_cap_target", "ps_cap_mutual"} {
		rec := doRequest(
			t,
			http.MethodPost,
			"/user/sub-accounts/"+target+"/follow",
			"",
			authHeadersForPersona("cap_viewer", "ps_cap_viewer"),
		)
		if rec.Code != http.StatusOK {
			t.Fatalf("seed follow %s: %d %s", target, rec.Code, rec.Body.String())
		}
	}
	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/ps_cap_viewer/follow",
		"",
		authHeadersForPersona("cap_mutual", "ps_cap_mutual"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("seed mutual follow: %d %s", rec.Code, rec.Body.String())
	}

	rec = doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_cap_viewer/following?limit=10",
		"",
		authHeadersForPersona("cap_viewer", "ps_cap_viewer"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("list following: %d %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok || len(items) != 2 {
		t.Fatalf("expected 2 following rows, got %#v", result)
	}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("unexpected row payload: %#v", raw)
		}
		capabilityRaw, exists := item["relationshipCapability"]
		if !exists {
			t.Fatalf("row must carry relationshipCapability, got %#v", item)
		}
		capability, ok := capabilityRaw.(map[string]any)
		if !ok {
			t.Fatalf("relationshipCapability must be an object, got %#v", capabilityRaw)
		}
		if capability["viewerSubAccountId"] != "ps_cap_viewer" {
			t.Fatalf("capability viewer must be request viewer, got %#v", capability)
		}
		if capability["targetSubAccountId"] != item["subAccountId"] {
			t.Fatalf("capability target must match row subject, got %#v", capability)
		}
		switch item["subAccountId"] {
		case "ps_cap_mutual":
			if capability["relationState"] != "mutual" || capability["isMutual"] != true {
				t.Fatalf("mutual row capability mismatch: %#v", capability)
			}
			if capability["canSendMessage"] != true {
				t.Fatalf("mutual row must allow direct message, got %#v", capability)
			}
		case "ps_cap_target":
			if capability["relationState"] != "following" || capability["canUnfollow"] != true {
				t.Fatalf("following row capability mismatch: %#v", capability)
			}
		}
	}
}

// SIT2：followers/following 搜索走云侧 query + cursor + limit（服务端过滤），
// 端侧不接受本地 contains 伪搜索。
func TestListFollowing_QueryFiltersWithinSubject(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "query_owner", "query_owner")
	createTestPersonaFull(t, "query_owner_persona", "query_owner", "ps_query_owner", "query_owner", "default", true)
	targets := map[string]string{
		"query_alpha_cat":  "旅行猫", // displayName 命中
		"query_beta_dog":   "摄影犬",
		"query_gamma_bird": "旅行鸟",
	}
	for uid, displayName := range targets {
		createTestProfile(t, uid, displayName)
		createTestPersonaFull(
			t,
			uid+"_persona",
			uid,
			"ps_"+uid,
			displayName,
			"default",
			true,
		)
		if _, err := pgPool.Exec(
			context.Background(),
			`UPDATE personas SET user_handle=$1 WHERE sub_account_id=$2`,
			uid,
			"ps_"+uid,
		); err != nil {
			t.Fatalf("seed query userHandle: %v", err)
		}
		rec := doRequest(
			t,
			http.MethodPost,
			"/user/sub-accounts/ps_"+uid+"/follow",
			"",
			authHeadersForPersona("query_owner", "ps_query_owner"),
		)
		if rec.Code != http.StatusOK {
			t.Fatalf("seed follow %s: %d %s", uid, rec.Code, rec.Body.String())
		}
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_query_owner/following?limit=10&query="+urlQueryEscape("旅行"),
		"",
		authHeadersForPersona("query_owner", "ps_query_owner"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("query following: %d %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatalf("missing items: %#v", result)
	}
	if len(items) != 2 {
		t.Fatalf("expected 2 matches for 旅行, got %d: %#v", len(items), items)
	}
	for _, raw := range items {
		item := raw.(map[string]any)
		name, _ := item["displayName"].(string)
		if name != "旅行猫" && name != "旅行鸟" {
			t.Fatalf("unexpected search hit: %#v", item)
		}
	}

	// username 子串匹配（不区分大小写）。
	rec = doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_query_owner/following?limit=10&query=BETA",
		"",
		authHeadersForPersona("query_owner", "ps_query_owner"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("query following by username: %d %s", rec.Code, rec.Body.String())
	}
	result = parseJSON(t, rec)
	items, _ = result["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 username match for BETA, got %#v", result)
	}
}

func TestListFollowers_QueryFiltersWithinSubject(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "fanned_owner", "fanned_owner")
	createTestPersonaFull(t, "fanned_owner_persona", "fanned_owner", "ps_fanned_owner", "fanned_owner", "default", true)
	fans := map[string]string{
		"fan_query_one": "同城旅行家",
		"fan_query_two": "美食家",
	}
	for uid, displayName := range fans {
		createTestProfile(t, uid, displayName)
		createTestPersonaFull(
			t,
			uid+"_persona",
			uid,
			"ps_"+uid,
			displayName,
			"default",
			true,
		)
		rec := doRequest(
			t,
			http.MethodPost,
			"/user/sub-accounts/ps_fanned_owner/follow",
			"",
			authHeadersForPersona(uid, "ps_"+uid),
		)
		if rec.Code != http.StatusOK {
			t.Fatalf("seed fan %s: %d %s", uid, rec.Code, rec.Body.String())
		}
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/ps_fanned_owner/followers?limit=10&query="+urlQueryEscape("旅行"),
		"",
		authHeadersForPersona("fanned_owner", "ps_fanned_owner"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("query followers: %d %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, _ := result["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 follower match for 旅行, got %#v", result)
	}
	if items[0].(map[string]any)["displayName"] != "同城旅行家" {
		t.Fatalf("unexpected follower hit: %#v", items[0])
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

func waitForProfileCounters(
	t *testing.T,
	ownerID string,
	expectedFollowers int64,
	expectedFollowing int64,
) {
	waitForProfileCountersWithin(
		t,
		ownerID,
		expectedFollowers,
		expectedFollowing,
		3*time.Second,
	)
}

func waitForProfileCountersWithin(
	t *testing.T,
	ownerID string,
	expectedFollowers int64,
	expectedFollowing int64,
	timeout time.Duration,
) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	var (
		followers int64
		following int64
		lastErr   error
	)
	for time.Now().Before(deadline) {
		lastErr = pgPool.QueryRow(
			context.Background(),
			`SELECT follower_count, following_count
			 FROM user_profiles
			 WHERE user_id = $1`,
			ownerID,
		).Scan(&followers, &following)
		if lastErr == nil &&
			followers == expectedFollowers &&
			following == expectedFollowing {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf(
		"profile %s counters=(%d,%d), want=(%d,%d), lastErr=%v",
		ownerID,
		followers,
		following,
		expectedFollowers,
		expectedFollowing,
		lastErr,
	)
}
