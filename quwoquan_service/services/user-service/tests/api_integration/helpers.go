package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	xxhash "github.com/cespare/xxhash/v2"
	"go.mongodb.org/mongo-driver/v2/bson"
	rtauth "quwoquan_service/runtime/auth"
	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
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

// requestOtpCode 发送一次 OTP；测试仅从进程外 provider contract probe 读取投递内容，
// API response 永远不暴露验证码。
func requestOtpCode(t *testing.T, phone string) string {
	t.Helper()
	rec := doRequest(t, "POST", "/v1/auth/otp/send", `{"phone":"`+phone+`","deviceId":"ios-test","platform":"ios","appVersion":"1.0.0","sourceOperation":"test"}`, nil)
	if rec.Code != 200 {
		t.Fatalf("send otp: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	if _, leaked := body["debugCode"]; leaked {
		t.Fatalf("send otp response leaked debugCode: %#v", body)
	}
	code := externalInteractionRuntime.client.OTPCode(phone)
	if code == "" {
		t.Fatalf("send otp: provider contract probe did not observe delivery, got %#v", body)
	}
	return code
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
	// Phone must stay unique per fixture. A naive 16-char prefix truncation
	// collides whenever userIDs share a prefix (e.g. filtered_target_a/b/c/d/e
	// all truncate to "filtered_target_"). Derive a compact, collision-resistant
	// token from the full userID so the unique constraint never spuriously trips.
	phone := fmt.Sprintf("t_%016x", xxhash.Sum64String(userID))
	logicalShard := fixtureLogicalShard(userID)
	_, err := pgPool.Exec(context.Background(), `
		INSERT INTO user_profiles (
			user_id, account_state, identity_origin, logical_shard, anonymous_retention_policy,
			phone, nickname, nickname_customized, avatar_url, avatar_asset_id, avatar_version,
			background_url, bio, identity_tags, gender, region, owner_display_name,
			status, profile_version, sub_account_count, created_at, updated_at
		)
		VALUES (
			$1, 'active', 'migrated_seed', $2, 'preserve',
			$3, $4, false, '', '', 0,
			'', '', '', '', '', '',
			'active', 1, 1, NOW(), NOW()
		)
		ON CONFLICT (user_id) DO NOTHING`,
		userID, logicalShard, phone, nickname)
	if err != nil {
		t.Fatalf("create test profile: %v", err)
	}
}

func fixtureLogicalShard(userID string) int {
	const (
		ruleVersion = "01"
		originCode  = "mg"
		slotCount   = 16384
	)
	return int(xxhash.Sum64String(ruleVersion+"|"+originCode+"|"+strings.TrimSpace(userID)) % slotCount)
}

func createTestPersona(t *testing.T, personaID, userID, displayName string, isPrimary bool, isActiveOverride ...bool) {
	t.Helper()
	isActive := isPrimary
	if len(isActiveOverride) > 0 {
		isActive = isActiveOverride[0]
	}
	subAccountID := personaID + "_sa"
	_, err := pgPool.Exec(context.Background(), `
		INSERT INTO personas (user_id, sub_account_id, display_name, user_handle, phone, email, avatar_url, purpose_hint, inherits_profile_from_owner, overridden_profile_fields, is_primary, is_private, is_active, invite_count, created_at, updated_at)
		VALUES ($1, $2, $3, '', '', '', '', '', true, '{}', $4, false, $5, 0, NOW(), NOW())`,
		userID, subAccountID, displayName, isPrimary, isActive)
	if err != nil {
		t.Fatalf("create test persona: %v", err)
	}
}

func cleanAll(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	reltelemetry.Reset()
	if chatContractRuntime != nil {
		chatContractRuntime.Reset()
	}
	_, _ = pgPool.Exec(ctx, `TRUNCATE user_profiles, user_auth, personas, user_settings,
		persona_relationships, persona_relationship_directions,
		persona_relationship_command_receipts, persona_relationship_outbox,
		personas_command_receipts, personas_outbox,
		profile_update_proposals, profile_update_proposals_command_receipts, profile_update_proposals_outbox,
		greeting_requests, user_works, user_life_items, credential_bindings, anonymous_device_bindings,
		contact_discovery_records, invite_records, profile_qr_tokens, otp_challenges CASCADE`)
	if mongoDB != nil {
		_, _ = mongoDB.Collection("posts").DeleteMany(ctx, map[string]any{})
		_, _ = mongoDB.Collection("comments").DeleteMany(ctx, map[string]any{})
		_, _ = mongoDB.Collection("messages").DeleteMany(ctx, map[string]any{})
		_, _ = mongoDB.Collection("notifications").DeleteMany(ctx, map[string]any{})
	}
	if err := integrationRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush user integration Redis: %v", err)
	}
}

// createTestPersonaFull creates a persona fixture keyed by sub_account_id.
func createTestPersonaFull(t *testing.T, _ string, userID, subAccountID, displayName, isolationLevel string, isPrimary bool, isActiveOverride ...bool) {
	t.Helper()
	isActive := isPrimary
	if len(isActiveOverride) > 0 {
		isActive = isActiveOverride[0]
	}
	_, err := pgPool.Exec(context.Background(), `
		INSERT INTO personas (user_id, sub_account_id, display_name, user_handle, phone, email, avatar_url, purpose_hint, isolation_level, inherits_profile_from_owner, overridden_profile_fields, is_primary, is_private, is_active, invite_count, created_at, updated_at)
		VALUES ($1, $2, $3, '', '', '', '', '', $4, true, '{}', $5, false, $6, 0, NOW(), NOW())`,
		userID, subAccountID, displayName, isolationLevel, isPrimary, isActive)
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
	token, err := testAccessSigner.Sign(rtauth.TokenSubject{AccountID: userID})
	if err != nil {
		panic("sign user-service api integration access token: " + err.Error())
	}
	return map[string]string{"Authorization": "Bearer " + token}
}

func authHeadersForPersona(userID, subAccountID string) map[string]string {
	token, err := testAccessSigner.Sign(rtauth.TokenSubject{
		AccountID: userID,
		PersonaID: subAccountID,
	})
	if err != nil {
		panic("sign user-service api integration persona access token: " + err.Error())
	}
	return map[string]string{"Authorization": "Bearer " + token}
}

func seedPersonaPostHistory(t *testing.T, subAccountID string) {
	t.Helper()
	requireMongoBackedRuntime(t)
	_, err := mongoDB.Collection("posts").InsertOne(context.Background(), bson.M{
		"_id":                       "post_" + subAccountID,
		"authorId":                  subAccountID,
		"authorDisplayNameSnapshot": "Post Persona",
		"authorAvatarUrlSnapshot":   "https://example.com/post.jpg",
		"status":                    "published",
		"createdAt":                 time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("seed persona post history: %v", err)
	}
}

func seedPersonaCommentHistory(t *testing.T, subAccountID string) {
	t.Helper()
	requireMongoBackedRuntime(t)
	_, err := mongoDB.Collection("comments").InsertOne(context.Background(), bson.M{
		"_id":                       "comment_" + subAccountID,
		"postId":                    "post_for_" + subAccountID,
		"authorId":                  subAccountID,
		"authorDisplayNameSnapshot": "Comment Persona",
		"authorAvatarUrlSnapshot":   "https://example.com/comment.jpg",
		"content":                   "记录评论",
		"createdAt":                 time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("seed persona comment history: %v", err)
	}
}

func seedPersonaChatHistory(t *testing.T, subAccountID string) {
	t.Helper()
	requireMongoBackedRuntime(t)
	_, err := mongoDB.Collection("messages").InsertOne(context.Background(), bson.M{
		"_id":                       "message_" + subAccountID,
		"conversationId":            "conv_" + subAccountID,
		"seq":                       1,
		"senderId":                  subAccountID,
		"senderSubAccountId":        subAccountID,
		"senderDisplayNameSnapshot": "Chat Persona",
		"senderAvatarUrlSnapshot":   "https://example.com/chat.jpg",
		"content":                   "记录聊天",
		"timestamp":                 time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("seed persona chat history: %v", err)
	}
}

func seedPersonaNotificationHistory(t *testing.T, subAccountID string) {
	t.Helper()
	requireMongoBackedRuntime(t)
	_, err := mongoDB.Collection("notifications").InsertOne(context.Background(), bson.M{
		"_id":          "notification_" + subAccountID,
		"userId":       "viewer_" + subAccountID,
		"type":         "social",
		"title":        "记录通知",
		"body":         "由分身触发的通知",
		"senderUserId": subAccountID,
		"targetType":   "post",
		"targetId":     "post_" + subAccountID,
		"createdAt":    time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("seed persona notification history: %v", err)
	}
}
