package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/chat-service/internal/application"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

// apiIntegrationIdempotencySeq 为 doPost 等命令 helper 提供进程内唯一幂等键。
var apiIntegrationIdempotencySeq int64

func chatStoragePorts(store *persistence.MongoChatStore) application.ChatStoragePorts {
	return application.ChatStoragePorts{
		Transactions:             store,
		Conversations:            store,
		CircleGroupConversations: store,
		Messages:                 store,
		MessageProjection:        store,
		Members:                  store,
		UserStates:               store,
		Receipts:                 store,
		ConversationCommands: persistence.NewMongoAggregateCommandStore(
			mongoDB, "conversations_command_receipts", "conversations_outbox",
		),
		MembershipCommands: persistence.NewMongoAggregateCommandStore(
			mongoDB, "conversation_memberships_command_receipts", "conversation_memberships_outbox",
		),
		UserStateCommands: persistence.NewMongoAggregateCommandStore(
			mongoDB, "conversation_user_states_command_receipts", "conversation_user_states_outbox",
		),
		CircleGroupMembershipProjections:  store,
		CircleGroupChatBindingProjections: store,
	}
}

func testDerivedMediaFileServer(localRoot string) http.Handler {
	root := filepath.Clean(strings.TrimSpace(localRoot))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			writeTestMediaError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "请求方法不支持", "method not allowed"))
			return
		}
		rel := strings.TrimPrefix(r.URL.Path, "/media/")
		rel = strings.Trim(rel, "/")
		if rel == "" || strings.Contains(rel, "..") {
			writeTestMediaError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "媒体路径无效", "bad path"))
			return
		}
		full := filepath.Join(root, filepath.FromSlash(rel))
		cleanRoot := root
		cleanFull := filepath.Clean(full)
		sep := string(filepath.Separator)
		if cleanFull != cleanRoot && !strings.HasPrefix(cleanFull, cleanRoot+sep) {
			writeTestMediaError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "媒体路径无效", "bad path"))
			return
		}
		fi, err := os.Stat(cleanFull)
		if err != nil || fi.IsDir() {
			writeTestMediaError(
				w,
				r,
				rterr.NewAppError(rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "not_found"), "媒体不存在", "media not found"),
			)
			return
		}
		http.ServeFile(w, r, cleanFull)
	})
}

func TestDerivedMediaFileServerServesCanonicalArtifact(t *testing.T) {
	root := t.TempDir()
	artifactPath := filepath.Join(root, "voice", "sample.m4a")
	if err := os.MkdirAll(filepath.Dir(artifactPath), 0o755); err != nil {
		t.Fatalf("create media directory: %v", err)
	}
	if err := os.WriteFile(artifactPath, []byte("voice-payload"), 0o600); err != nil {
		t.Fatalf("write media artifact: %v", err)
	}
	request := httptest.NewRequest(http.MethodGet, "/media/voice/sample.m4a", nil)
	recorder := httptest.NewRecorder()
	testDerivedMediaFileServer(root).ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK || recorder.Body.String() != "voice-payload" {
		t.Fatalf("derived media response=%d body=%q", recorder.Code, recorder.Body.String())
	}
}

func writeTestMediaError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeTestUserNotFound(w http.ResponseWriter, r *http.Request, debugMessage string) {
	writeTestMediaError(
		w,
		r,
		rterr.NewAppError(rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "not_found"), "用户资源不存在", debugMessage),
	)
}

func createConversation(t *testing.T, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/chat/conversations", payload, "user_test_001", http.StatusCreated)
}

func createConversationAs(t *testing.T, userId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/chat/conversations", payload, userId, http.StatusCreated)
}

func sendMessage(t *testing.T, conversationId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/chat/conversations/"+conversationId+"/messages", payload, "user_test_001", http.StatusCreated)
}

func sendMessageAs(t *testing.T, userId, conversationId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/chat/conversations/"+conversationId+"/messages", payload, userId, http.StatusCreated)
}

func doPost(t *testing.T, path, payload, userId string, expectedStatus int) map[string]any {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userId)
	req.Header.Set("X-Client-Account-Id", userId)
	req.Header.Set("X-Client-Sub-Account-Id", userId)
	req.Header.Set("X-Client-Persona-Id", userId)
	req = req.WithContext(operation.WithContext(req.Context(), operation.Context{
		OperationID: "api_integration." + strings.Trim(path, "/"),
		RequestID:   "api_integration.request",
		TraceID:     "api_integration.trace",
		// 每次调用生成新幂等键（模拟客户端新意图）；重放语义由显式复用
		// 同一 key 的专项测试覆盖。
		IdempotencyKey: fmt.Sprintf(
			"api-int-%d",
			atomic.AddInt64(&apiIntegrationIdempotencySeq, 1),
		),
		Actor: operation.ActorContext{
			AccountID: userId,
			PersonaID: userId,
		},
	}))
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if testMessageOutboxRelay != nil {
		if _, err := testMessageOutboxRelay.Drain(context.Background(), 100); err != nil {
			t.Fatalf("doPost %s: drain message outbox: %v", path, err)
		}
	}
	drainAggregateOutboxRelays(t, path)
	if rec.Code != expectedStatus {
		t.Fatalf("doPost %s: expected %d, got %d: %s", path, expectedStatus, rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("doPost %s: decode response: %v", path, err)
	}
	return result
}

// commandOperationTestContext 为直接调用 application service 的测试提供
// 带唯一幂等键的 operation 上下文（模拟客户端每次新意图）。
func commandOperationTestContext() context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "api_integration.direct_service_command",
		IdempotencyKey: fmt.Sprintf(
			"api-int-svc-%d",
			atomic.AddInt64(&apiIntegrationIdempotencySeq, 1),
		),
		Actor: operation.ActorContext{
			AccountID: "user_test_001",
			PersonaID: "user_test_001",
		},
	})
}

// commandOperationContext 为写命令 helper 注入 actor 与唯一幂等键。
func commandOperationContext(req *http.Request, path, userId string) *http.Request {
	return req.WithContext(operation.WithContext(req.Context(), operation.Context{
		OperationID: "api_integration." + strings.Trim(path, "/"),
		RequestID:   "api_integration.request",
		TraceID:     "api_integration.trace",
		IdempotencyKey: fmt.Sprintf(
			"api-int-%d",
			atomic.AddInt64(&apiIntegrationIdempotencySeq, 1),
		),
		Actor: operation.ActorContext{
			AccountID: userId,
			PersonaID: userId,
		},
	}))
}

func doGet(t *testing.T, path, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("X-Client-User-Id", userId)
	req.Header.Set("X-Client-Sub-Account-Id", userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doPatch(t *testing.T, path, payload, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPatch, path, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userId)
	req.Header.Set("X-Client-Sub-Account-Id", userId)
	req = commandOperationContext(req, path, userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	drainAggregateOutboxRelays(t, path)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doPut(t *testing.T, path, payload, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPut, path, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userId)
	req.Header.Set("X-Client-Sub-Account-Id", userId)
	req = commandOperationContext(req, path, userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	drainAggregateOutboxRelays(t, path)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doDelete(t *testing.T, path, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete, path, nil)
	req.Header.Set("X-Client-User-Id", userId)
	req.Header.Set("X-Client-Sub-Account-Id", userId)
	req = commandOperationContext(req, path, userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	drainAggregateOutboxRelays(t, path)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func seedConversationWithAssistantMember(
	t *testing.T,
	conversationID string,
	ownerUserID string,
	title string,
	assistantSkillID string,
) {
	t.Helper()
	db := requireMongoDB(t)
	now := time.Now().UTC()
	conversation := &model.Conversation{
		ID:                    conversationID,
		Type:                  "group",
		Title:                 title,
		CreatorId:             ownerUserID,
		MemberCount:           2,
		MembersRosterRevision: 1,
		MaxGroupSize:          500,
		ReceiptEnabled:        true,
		Status:                "active",
		CreatedAt:             now,
		UpdatedAt:             now,
	}
	if _, err := db.Collection("conversations").InsertOne(context.Background(), conversation); err != nil {
		t.Fatalf("seed conversation %s: %v", conversationID, err)
	}
	ownerMember := &model.ConversationMember{
		ID:             conversationID + "_owner_member",
		ConversationId: conversationID,
		UserId:         ownerUserID,
		DisplayName:    "Display_" + ownerUserID,
		AvatarUrl:      "https://test.avatar/" + ownerUserID,
		AvatarAssetId:  "ua_" + ownerUserID,
		AvatarVersion:  1,
		MemberType:     "user",
		Role:           "owner",
		JoinedAt:       now,
	}
	if _, err := db.Collection("conversation_memberships").InsertOne(context.Background(), ownerMember); err != nil {
		t.Fatalf("seed owner member %s: %v", conversationID, err)
	}
	assistantMember := &model.ConversationMember{
		ID:               conversationID + "_assistant_member",
		ConversationId:   conversationID,
		UserId:           "assistant",
		DisplayName:      "Display_assistant",
		AvatarUrl:        "https://test.avatar/assistant",
		AvatarAssetId:    "ua_assistant",
		AvatarVersion:    1,
		MemberType:       "assistant",
		Role:             "member",
		AssistantSkillId: assistantSkillID,
		InvitedBy:        ownerUserID,
		JoinedAt:         now.Add(time.Second),
	}
	if _, err := db.Collection("conversation_memberships").InsertOne(context.Background(), assistantMember); err != nil {
		t.Fatalf("seed assistant member %s: %v", conversationID, err)
	}
}

// drainAggregateOutboxRelays 把三个非 Message 聚合 outbox 的事件同步投递，
// 使事件断言测试在命令返回后立即可观察（与生产 relay 循环等价）。
func drainAggregateOutboxRelays(t *testing.T, path string) {
	t.Helper()
	for _, relay := range testAggregateOutboxRelays {
		if relay == nil {
			continue
		}
		if _, err := relay.Drain(context.Background(), 100); err != nil {
			t.Fatalf("%s: drain aggregate outbox: %v", path, err)
		}
	}
}
