// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// readiness_case: materialize-active-persona-profile-api
// readiness_case: list-personas-api
package api_integration

import (
	"context"
	"net/http"
	"testing"

	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

// T3 Persona 隔离防护契约测试

func TestPersona_CreateAndList(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	ownerID := canonicalOwnerIDForTest(
		t,
		"ph",
		"01j00000000000000000000010",
	)
	createTestProfile(t, ownerID, "sub_owner1")
	createTestCredential(t, "cred1", ownerID, "phone", "hash_13800000001")

	// 创建分身
	rec := doRequest(t, http.MethodPost, "/user/personas",
		`{"displayName":"匿名分身","isolationLevel":"strict"}`,
		authHeaders(ownerID))
	if rec.Code != http.StatusCreated {
		t.Fatalf("create persona: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	personaID, _ := result["personaId"].(string)
	if personaID == "" {
		t.Fatal("expected non-empty personaId in response")
	}

	// 列出分身
	rec = doRequest(t, http.MethodGet, "/user/personas", "", authHeaders(ownerID))
	if rec.Code != http.StatusOK {
		t.Fatalf("list personas: expected 200, got %d", rec.Code)
	}
	list := parseJSON(t, rec)
	accounts, _ := list["items"].([]any)
	if len(accounts) == 0 {
		t.Fatal("expected at least one persona")
	}
}

func TestPersona_ActivateSwitchesExclusively(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sub_owner_2", "sub_owner2")
	createTestPersonaFull(t, "sub_a", "sub_owner_2", "sa_id_a", "SubA", "open", true, true)
	createTestPersonaFull(t, "sub_b", "sub_owner_2", "sa_id_b", "SubB", "open", false, false)

	// 激活 sub_b
	rec := doRequest(t, http.MethodPost, "/user/personas/sa_id_b/activate", "", authHeaders("sub_owner_2"))
	if rec.Code != http.StatusOK {
		projectionStore, projectorErr := useraccountpersistence.NewPersonaProfileProjector(pgPool)
		if projectorErr == nil {
			var projector *useraccountapp.PersonaProfileProjector
			projector, projectorErr = useraccountapp.NewPersonaProfileProjector(
				projectionStore,
			)
			if projectorErr == nil {
				_, projectorErr = projector.ProjectNext(context.Background())
			}
		}
		t.Fatalf(
			"activate persona: expected 200, got %d: %s; pending projector diagnosis: %v",
			rec.Code,
			rec.Body.String(),
			projectorErr,
		)
	}

	// 验证 DB：只有一个激活的Persona
	var activeCount int
	err := pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM personas WHERE user_id = $1 AND is_active = true`,
		"sub_owner_2").Scan(&activeCount)
	if err != nil {
		t.Fatalf("query active count: %v", err)
	}
	if activeCount != 1 {
		t.Errorf("expected exactly 1 active persona, got %d", activeCount)
	}

	var activePersonaID string
	_ = pgPool.QueryRow(context.Background(),
		`SELECT persona_id FROM personas WHERE user_id = $1 AND is_active = true`,
		"sub_owner_2").Scan(&activePersonaID)
	if activePersonaID != "sa_id_b" {
		t.Errorf("expected sa_id_b to be active, got %s", activePersonaID)
	}

	var (
		projectedNickname string
		projectedAt       *string
	)
	if err := pgPool.QueryRow(context.Background(), `
SELECT nickname
FROM user_profiles
WHERE user_id=$1`, "sub_owner_2").Scan(&projectedNickname); err != nil {
		t.Fatalf("read active Persona projection: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `
SELECT profile_projected_at::text
FROM personas_outbox
WHERE aggregate_id=$1 AND event_type='PersonaActivated'
ORDER BY aggregate_version DESC
LIMIT 1`, "sa_id_b").Scan(&projectedAt); err != nil {
		t.Fatalf("read activation projection checkpoint: %v", err)
	}
	if projectedNickname != "SubB" || projectedAt == nil || *projectedAt == "" {
		t.Fatalf(
			"activation must synchronously project the new active Persona: nickname=%q checkpoint=%v",
			projectedNickname,
			projectedAt,
		)
	}

	// Simulate a projection write lost after the durable Persona packet. The
	// background drain must converge from the outbox coordinate without a
	// UserAccount/Profile write fallback.
	if _, err := pgPool.Exec(context.Background(), `
UPDATE user_profiles SET nickname='stale_projection' WHERE user_id=$1`, "sub_owner_2"); err != nil {
		t.Fatalf("prepare stale Persona projection: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(), `
UPDATE personas_outbox
SET profile_projected_at=NULL
WHERE aggregate_id=$1 AND event_type='PersonaActivated'`, "sa_id_b"); err != nil {
		t.Fatalf("prepare Persona projection recovery checkpoint: %v", err)
	}
	projectionStore, err := useraccountpersistence.NewPersonaProfileProjector(pgPool)
	if err != nil {
		t.Fatalf("create Persona profile projector: %v", err)
	}
	projector, err := useraccountapp.NewPersonaProfileProjector(projectionStore)
	if err != nil {
		t.Fatalf("create Persona profile application facet: %v", err)
	}
	didWork, err := projector.ProjectNext(context.Background())
	if err != nil {
		t.Fatalf("recover Persona profile projection: %v", err)
	}
	if !didWork {
		t.Fatal("expected pending Persona profile projection recovery work")
	}
	if err := pgPool.QueryRow(context.Background(), `
SELECT nickname
FROM user_profiles
WHERE user_id=$1`, "sub_owner_2").Scan(&projectedNickname); err != nil {
		t.Fatalf("read recovered Persona projection: %v", err)
	}
	if projectedNickname != "SubB" {
		t.Fatalf("projection recovery must converge to Persona authority, got %q", projectedNickname)
	}
}

func TestPersona_RetireForbidsLast(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sub_owner_3", "sub_owner3")
	createTestPersonaFull(t, "only_sub", "sub_owner_3", "sa_only", "OnlySub", "open", true, true)

	// 退役唯一的分身应该被拒绝
	rec := doRequest(t, http.MethodPost, "/user/personas/sa_only/retire", "", authHeaders("sub_owner_3"))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 when retiring the last persona, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestPersona_StrictIsolationHidesFromContactDiscovery(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	// 用户 A 拥有 strict 隔离Persona
	createTestProfile(t, "strict_owner", "strict_user")
	createTestPersonaFull(t, "strict_persona", "strict_owner", "sa_strict", "Strict", "strict", true, true)
	// A 有手机号凭证
	createTestCredential(t, "cred_strict", "strict_owner", "phone", "hash_strict_phone")

	// 用户 B 发起通讯录发现，包含 A 的手机号哈希
	createTestProfile(t, "discover_owner", "discover_user")
	rec := doRequest(t, http.MethodPost, "/owner/contact-discovery",
		`{"hashedPhones":["hash_strict_phone"]}`,
		authHeaders("discover_owner"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate contact discovery: expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	// strict 隔离用户不应出现在匹配结果中
	matchedRaw, _ := result["matchedPersonaIds"].([]any)
	for _, m := range matchedRaw {
		if s, ok := m.(string); ok && s == "sa_strict" {
			t.Error("strict isolation persona should NOT appear in contact discovery results")
		}
	}
}

func TestPersona_ListDoesNotLeakPrivateFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "leaktest_owner", "leaktest_user")
	createTestPersonaFull(t, "lk_persona", "leaktest_owner", "sa_lktest", "LeakTest", "open", true, true)

	rec := doRequest(t, http.MethodGet, "/user/personas", "", authHeaders("leaktest_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list personas: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	accounts, _ := result["items"].([]any)
	if len(accounts) == 0 {
		t.Fatal("expected at least one persona")
	}

	// purposeHint 属于私有管理字段，不应出现在列表响应
	for _, acc := range accounts {
		am, _ := acc.(map[string]any)
		if _, has := am["purposeHint"]; has {
			t.Error("purposeHint is a private field and should NOT appear in persona list response")
		}
	}
}
