package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/chat-service/internal/application"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

func chatStoragePorts(store *persistence.MongoChatStore) application.ChatStoragePorts {
	return application.ChatStoragePorts{
		Transactions:      store,
		Conversations:     store,
		Messages:          store,
		MessageProjection: store,
		Members:           store,
		UserStates:        store,
		Receipts:          store,
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
	return doPost(t, "/v1/chat/conversations", payload, "user_test_001", http.StatusCreated)
}

func createConversationAs(t *testing.T, userId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/v1/chat/conversations", payload, userId, http.StatusCreated)
}

func sendMessage(t *testing.T, conversationId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/v1/chat/conversations/"+conversationId+"/messages", payload, "user_test_001", http.StatusCreated)
}

func sendMessageAs(t *testing.T, userId, conversationId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/v1/chat/conversations/"+conversationId+"/messages", payload, userId, http.StatusCreated)
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
	if rec.Code != expectedStatus {
		t.Fatalf("doPost %s: expected %d, got %d: %s", path, expectedStatus, rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("doPost %s: decode response: %v", path, err)
	}
	return result
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
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
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
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doDelete(t *testing.T, path, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete, path, nil)
	req.Header.Set("X-Client-User-Id", userId)
	req.Header.Set("X-Client-Sub-Account-Id", userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
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
