package api_integration

import (
	"context"
	"net/http"
	"testing"
)

// TestPersonaCommandPacketCommitsStateReceiptOutboxAtomically 验证 Persona
// 直接命令走对象专属 packet：state、personas_command_receipts 与
// personas_outbox 同事务提交，同一 Idempotency-Key 重放返回首次结果。
func TestPersonaCommandPacketCommitsStateReceiptOutboxAtomically(t *testing.T) {
	cleanAll(t)
	ownerID := canonicalOwnerIDForTest(
		t,
		"ph",
		"01j00000000000000000000011",
	)
	primaryPersonaID := canonicalPersonaIDForTest(
		t,
		ownerID,
		"01j00000000000000000000012",
	)
	createTestProfile(t, ownerID, "packet owner")
	createTestPersonaFull(t, "", ownerID, primaryPersonaID, "主分身", "open", true)

	headers := authHeaders(ownerID)
	headers["Idempotency-Key"] = "persona-packet-create-1"
	first := doRequest(t, http.MethodPost, "/user/personas",
		`{"displayName":"分身甲","isolationLevel":"open"}`, headers)
	if first.Code != http.StatusCreated {
		t.Fatalf("create persona: expected 201, got %d: %s", first.Code, first.Body.String())
	}
	firstBody := parseJSON(t, first)
	personaID, _ := firstBody["personaId"].(string)
	if personaID == "" {
		t.Fatalf("create persona result missing personaId: %v", firstBody)
	}

	replay := doRequest(t, http.MethodPost, "/user/personas",
		`{"displayName":"分身甲","isolationLevel":"open"}`, headers)
	if replay.Code != http.StatusCreated {
		t.Fatalf("replay create persona: expected 201, got %d: %s", replay.Code, replay.Body.String())
	}

	ctx := context.Background()
	var personaCount int
	if err := pgPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM personas WHERE user_id=$1 AND persona_id <> $2`,
		ownerID,
		primaryPersonaID,
	).Scan(&personaCount); err != nil {
		t.Fatalf("count personas: %v", err)
	}
	if personaCount != 1 {
		t.Fatalf("idempotent create must persist exactly one persona, got %d", personaCount)
	}

	var receiptCount, outboxCount int
	if err := pgPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM personas_command_receipts WHERE aggregate_id=$1`,
		personaID,
	).Scan(&receiptCount); err != nil {
		t.Fatalf("count receipts: %v", err)
	}
	if err := pgPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1 AND event_type='PersonaCreated'`,
		personaID,
	).Scan(&outboxCount); err != nil {
		t.Fatalf("count outbox: %v", err)
	}
	if receiptCount != 1 || outboxCount != 1 {
		t.Fatalf("packet mismatch: receipts=%d outbox=%d", receiptCount, outboxCount)
	}

	// 同一 key 复用于不同命令负载必须冲突，禁止静默重放。
	conflict := doRequest(t, http.MethodPost, "/user/personas",
		`{"displayName":"分身乙","isolationLevel":"open"}`, headers)
	if conflict.Code == http.StatusCreated {
		t.Fatalf("same key with different payload must not create another persona: %s",
			conflict.Body.String())
	}

	// 命名状态迁移（激活）也走 packet：版本推进 + PersonaActivated 事实。
	activateHeaders := authHeaders(ownerID)
	activateHeaders["Idempotency-Key"] = "persona-packet-activate-1"
	activated := doRequest(t, http.MethodPost, "/user/personas/"+personaID+"/activate",
		"", activateHeaders)
	if activated.Code != http.StatusOK {
		t.Fatalf("activate persona: expected 200, got %d: %s", activated.Code, activated.Body.String())
	}
	var activatedVersion int64
	if err := pgPool.QueryRow(ctx,
		`SELECT version FROM personas WHERE persona_id=$1`, personaID,
	).Scan(&activatedVersion); err != nil {
		t.Fatalf("read activated version: %v", err)
	}
	if activatedVersion != 2 {
		t.Fatalf("activation must advance aggregate version to 2, got %d", activatedVersion)
	}
	var activatedEvents int
	if err := pgPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1 AND event_type='PersonaActivated' AND aggregate_version=2`,
		personaID,
	).Scan(&activatedEvents); err != nil {
		t.Fatalf("count activation events: %v", err)
	}
	if activatedEvents != 1 {
		t.Fatalf("activation must append exactly one PersonaActivated fact, got %d", activatedEvents)
	}
}
