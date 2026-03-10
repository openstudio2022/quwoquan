package tests

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func doRequest(t *testing.T, method, path string, body string, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	var reader *strings.Reader
	if body != "" {
		reader = strings.NewReader(body)
	} else {
		reader = strings.NewReader("")
	}
	req := httptest.NewRequest(method, path, reader)
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	return rec
}

func parseJSON(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("parse JSON: %v (body: %s)", err, rec.Body.String())
	}
	return result
}

func createTestProfile(t *testing.T, userID, nickname string) {
	t.Helper()
	// phone must fit VARCHAR(20); use hash of userID for uniqueness
	phone := userID
	if len(phone) > 16 {
		phone = phone[:16]
	}
	phone = "t_" + phone
	_, err := pgPool.Exec(context.Background(), `
		INSERT INTO user_profiles (user_id, phone, nickname, avatar_url, bio, gender, region, owner_display_name, status, profile_version, created_at, updated_at)
		VALUES ($1, $2, $3, '', '', '', '', '', 'active', 1, NOW(), NOW())
		ON CONFLICT (user_id) DO NOTHING`,
		userID, phone, nickname)
	if err != nil {
		t.Fatalf("create test profile: %v", err)
	}
}

func createTestPersona(t *testing.T, id, userID, displayName string, isPrimary, isActive bool) {
	t.Helper()
	subAccountID := id + "_sa"
	_, err := pgPool.Exec(context.Background(), `
		INSERT INTO personas (id, user_id, sub_account_id, display_name, avatar_url, purpose_hint, is_primary, is_private, is_active, invite_count, created_at, updated_at)
		VALUES ($1, $2, $3, $4, '', '', $5, false, $6, 0, NOW(), NOW())`,
		id, userID, subAccountID, displayName, isPrimary, isActive)
	if err != nil {
		t.Fatalf("create test persona: %v", err)
	}
}

func cleanAll(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	_, _ = pgPool.Exec(ctx, `TRUNCATE user_profiles, personas, user_settings, block_edges,
		user_works, user_life_items, credential_bindings,
		contact_discovery_records, invite_records CASCADE`)
	if mongoDB != nil {
		_ = mongoDB.Collection("follow_edges").Drop(ctx)
		_, _ = mongoDB.Collection("follow_edges").InsertOne(ctx, bson.M{"_cleanup": true})
		_, _ = mongoDB.Collection("follow_edges").DeleteMany(ctx, bson.M{})
	}
	mr.FlushAll()
}

// createTestPersonaFull creates a persona with sub_account_id and isolation_level.
func createTestPersonaFull(t *testing.T, id, userID, subAccountID, displayName, isolationLevel string, isPrimary, isActive bool) {
	t.Helper()
	_, err := pgPool.Exec(context.Background(), `
		INSERT INTO personas (id, user_id, sub_account_id, display_name, avatar_url, purpose_hint, isolation_level, is_primary, is_private, is_active, invite_count, created_at, updated_at)
		VALUES ($1, $2, $3, $4, '', '', $5, $6, false, $7, 0, NOW(), NOW())`,
		id, userID, subAccountID, displayName, isolationLevel, isPrimary, isActive)
	if err != nil {
		t.Fatalf("createTestPersonaFull: %v", err)
	}
}

// createTestCredential inserts a credential binding directly.
func createTestCredential(t *testing.T, id, ownerID, credType, credKey string) {
	t.Helper()
	_, err := pgPool.Exec(context.Background(), `
		INSERT INTO credential_bindings (id, owner_id, credential_type, credential_key, display_label, is_active, bound_at)
		VALUES ($1, $2, $3, $4, '', true, NOW())`,
		id, ownerID, credType, credKey)
	if err != nil {
		t.Fatalf("createTestCredential: %v", err)
	}
}

func authHeaders(userID string) map[string]string {
	return map[string]string{"X-Client-User-Id": userID}
}
