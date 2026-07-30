package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

func TestBlock_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_1", "blocker1")
	createTestPersonaFull(t, "blocker_1_persona", "blocker_1", "ps_blocker_1", "blocker1", "default", true)
	createTestProfile(t, "blocked_owner_1", "blocked1")
	createTestPersonaFull(t, "blocked_1_persona", "blocked_owner_1", "blocked_1", "blocked1", "default", true)

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/personas/blocked_1/block",
		"",
		authHeadersForPersona("blocker_1", "ps_blocker_1"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	command := parseJSON(t, rec)
	if command["targetPersonaId"] != "blocked_1" ||
		command["blocked"] != true ||
		command["updatedAt"] == "" {
		t.Fatalf("unexpected block result: %#v", command)
	}

	rec = doRequest(
		t,
		http.MethodGet,
		"/user/personas/blocked_1/relationship/capability",
		"",
		authHeadersForPersona("blocker_1", "ps_blocker_1"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["isBlocked"] != true {
		t.Errorf("expected isBlocked=true, got %v", result["isBlocked"])
	}
}

func TestBlock_Idempotent(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_2", "blocker2")
	createTestPersonaFull(t, "blocker_2_persona", "blocker_2", "ps_blocker_2", "blocker2", "default", true)
	createTestProfile(t, "blocked_owner_2", "blocked2")
	createTestPersonaFull(t, "blocked_2_persona", "blocked_owner_2", "blocked_2", "blocked2", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/user/personas/blocked_2/block",
		"",
		authHeadersForPersona("blocker_2", "ps_blocker_2"),
	)
	rec := doRequest(
		t,
		http.MethodPost,
		"/user/personas/blocked_2/block",
		"",
		authHeadersForPersona("blocker_2", "ps_blocker_2"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for idempotent block, got %d", rec.Code)
	}
}

func TestBlock_CounterProjectionClearsBothDirectionsOnce(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "block_counter_a", "block_counter_a")
	createTestProfile(t, "block_counter_b", "block_counter_b")
	createTestPersonaFull(
		t,
		"block_counter_a_persona",
		"block_counter_a",
		"ps_block_counter_a",
		"block_counter_a",
		"default",
		true,
	)
	createTestPersonaFull(
		t,
		"block_counter_b_persona",
		"block_counter_b",
		"ps_block_counter_b",
		"block_counter_b",
		"default",
		true,
	)

	for _, edge := range []struct {
		owner  string
		actor  string
		target string
	}{
		{
			owner:  "block_counter_a",
			actor:  "ps_block_counter_a",
			target: "ps_block_counter_b",
		},
		{
			owner:  "block_counter_b",
			actor:  "ps_block_counter_b",
			target: "ps_block_counter_a",
		},
	} {
		rec := doRequest(
			t,
			http.MethodPost,
			"/user/personas/"+edge.target+"/follow",
			"",
			authHeadersForPersona(edge.owner, edge.actor),
		)
		if rec.Code != http.StatusOK {
			t.Fatalf("seed mutual follow: %d %s", rec.Code, rec.Body.String())
		}
	}
	waitForProfileCounters(t, "block_counter_a", 1, 1)
	waitForProfileCounters(t, "block_counter_b", 1, 1)

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/personas/ps_block_counter_b/block",
		"",
		authHeadersForPersona("block_counter_a", "ps_block_counter_a"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("block mutual pair: %d %s", rec.Code, rec.Body.String())
	}
	waitForProfileCounters(t, "block_counter_a", 0, 0)
	waitForProfileCounters(t, "block_counter_b", 0, 0)

	var (
		event     relmodel.OutboxEvent
		payload   []byte
		projected bool
	)
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT event_id, event_name, payload_json, counter_projected_at IS NOT NULL
		 FROM persona_relationship_outbox
		 WHERE event_name = 'PersonaBlocked'
		 ORDER BY occurred_at DESC
		 LIMIT 1`,
	).Scan(
		&event.EventID,
		&event.EventName,
		&payload,
		&projected,
	); err != nil {
		t.Fatalf("query projected block event: %v", err)
	}
	if err := json.Unmarshal(payload, &event.Payload); err != nil {
		t.Fatalf("decode projected block event: %v", err)
	}
	if !projected ||
		!event.Payload.SourceFollowCleared ||
		!event.Payload.TargetFollowCleared ||
		event.Payload.ClearedFollowDirections != 2 {
		t.Fatalf("block event lost directional counter facts: %+v", event)
	}
	if err := relationshipCounterProjector.Apply(
		context.Background(),
		event,
	); err != nil {
		t.Fatalf("replay projected block event: %v", err)
	}
	waitForProfileCounters(t, "block_counter_a", 0, 0)
	waitForProfileCounters(t, "block_counter_b", 0, 0)
}

func TestUnblock_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_3", "blocker3")
	createTestPersonaFull(t, "blocker_3_persona", "blocker_3", "ps_blocker_3", "blocker3", "default", true)
	createTestProfile(t, "blocked_owner_3", "blocked3")
	createTestPersonaFull(t, "blocked_3_persona", "blocked_owner_3", "blocked_3", "blocked3", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/user/personas/blocked_3/block",
		"",
		authHeadersForPersona("blocker_3", "ps_blocker_3"),
	)
	rec := doRequest(
		t,
		http.MethodDelete,
		"/user/personas/blocked_3/block",
		"",
		authHeadersForPersona("blocker_3", "ps_blocker_3"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	rec = doRequest(
		t,
		http.MethodGet,
		"/user/personas/blocked_3/relationship/capability",
		"",
		authHeadersForPersona("blocker_3", "ps_blocker_3"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["isBlocked"] != false {
		t.Errorf("expected isBlocked=false after unblock, got %v", result["isBlocked"])
	}
}

func TestListBlocked(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_4", "blocker4")
	createTestPersonaFull(t, "blocker_4_persona", "blocker_4", "ps_blocker_4", "blocker4", "default", true)
	createTestProfile(t, "victim_owner_a", "victim_owner_a")
	createTestProfile(t, "victim_owner_b", "victim_owner_b")
	createTestPersonaFull(t, "victim_persona_a", "victim_owner_a", "victim_a", "被拉黑甲", "default", true)
	createTestPersonaFull(t, "victim_persona_b", "victim_owner_b", "victim_b", "被拉黑乙", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/user/personas/victim_a/block",
		"",
		authHeadersForPersona("blocker_4", "ps_blocker_4"),
	)
	doRequest(
		t,
		http.MethodPost,
		"/user/personas/victim_b/block",
		"",
		authHeadersForPersona("blocker_4", "ps_blocker_4"),
	)

	rec := doRequest(t, http.MethodGet, "/user/blocked", "", authHeadersForPersona("blocker_4", "ps_blocker_4"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("missing items")
	}
	if len(items) != 2 {
		t.Errorf("expected 2 blocked items, got %d", len(items))
	}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("blocked item must be an object: %#v", raw)
		}
		if item["targetPersonaId"] == "" ||
			item["displayName"] == "" ||
			item["blockedAt"] == "" {
			t.Fatalf("blocked item missing display fields: %#v", item)
		}
		if _, exists := item["pairId"]; exists {
			t.Fatalf("blocked item leaked aggregate identity: %#v", item)
		}
	}
}
