package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"

	chathttp "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
)

func TestListContacts_IncludesSocialContactSources(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	socialServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/user/personas/viewer_1/following":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"items": []map[string]any{
					{
						"personaId":     "user_a",
						"userHandle":    "alice_follow",
						"displayName":   "Alice Follow",
						"avatarUrl":     "https://avatar/a.png",
						"followedAt":    "2026-06-06T12:00:00Z",
						"relationState": "following",
					},
				},
				"cursor": "",
			})
		case "/user/personas/viewer_1/followers":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"items": []map[string]any{
					{
						"personaId":     "user_a",
						"userHandle":    "alice_follow",
						"displayName":   "Alice Follow",
						"avatarUrl":     "https://avatar/a.png",
						"followedAt":    "2026-06-06T12:02:00Z",
						"relationState": "followed_by",
					},
					{
						"personaId":     "user_b",
						"userHandle":    "bob_follower",
						"displayName":   "Bob Follower",
						"avatarUrl":     "https://avatar/b.png",
						"followedAt":    "2026-06-06T12:03:00Z",
						"relationState": "followed_by",
					},
				},
				"cursor": "",
			})
		case "/user/contact-discovery/latest":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":                "discovery_1",
				"matchedPersonaIds": []string{"user_c"},
				"status":            "completed",
				"createdAt":         time.Date(2026, 6, 6, 12, 4, 0, 0, time.UTC),
			})
		default:
			writeTestUserNotFound(w, r, "unexpected "+r.Method+" "+r.URL.Path)
		}
	}))
	defer socialServer.Close()

	chatStore := persistence.NewMongoChatStore(mongoDB)
	chatStorage := chatStoragePorts(chatStore)
	convCache := cache.NewConversationCache(redisRouter.Scene("general"))
	profiles := testProfileResolver{}
	memberSvc := application.NewMemberService(
		chatStorage,
		convCache,
		eventPublisherForContractTest(),
		profiles,
		nil,
		nil,
		groupAvatarSchedulerForContractTest(),
		application.WithRelationshipGate(application.AllowRelationshipGateForTest()),
		application.WithSocialContactResolver(
			chathttp.NewUserSocialContactResolver(socialServer.URL, socialServer.Client()),
		),
	)
	handler := chathttp.NewChatHandler(
		application.NewConversationService(chatStorage, convCache, eventPublisherForContractTest(), profiles, application.DenyRelationshipGate(), nil, nil, groupAvatarSchedulerForContractTest()),
		application.NewMessageService(chatStorage, convCache, eventPublisherForContractTest(), application.DenyRelationshipGate(), testMediaAssetDeliveryReader{}),
		memberSvc,
		application.NewInboxService(chatStorage),
		nil,
	).Routes()

	req := httptest.NewRequest(http.MethodGet, "/chat/contacts?limit=10", nil)
	req.Header.Set("X-Client-User-Id", "viewer_1")
	req.Header.Set("X-Client-Persona-Id", "viewer_1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var payload map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	items, ok := payload["items"].([]any)
	if !ok {
		t.Fatalf("response missing items: %#v", payload)
	}
	if len(items) != 3 {
		t.Fatalf("expected 3 unique contacts, got %d", len(items))
	}

	byID := make(map[string]map[string]any, len(items))
	for _, raw := range items {
		row, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("unexpected row type: %T", raw)
		}
		id, _ := row["userId"].(string)
		byID[id] = row
	}

	if got := byID["user_a"]["relationState"]; got != "mutual" {
		t.Fatalf("expected user_a relationState mutual, got %v", got)
	}
	if got := byID["user_a"]["source"]; got != "mutual" {
		t.Fatalf("expected user_a source mutual, got %v", got)
	}
	if got := byID["user_a"]["userHandle"]; got != "alice_follow" {
		t.Fatalf("expected user_a canonical userHandle, got %v", got)
	}
	if got := byID["user_b"]["source"]; got != "following" {
		t.Fatalf("expected user_b source following, got %v", got)
	}
	if got := byID["user_c"]["source"]; got != "contact_discovery" {
		t.Fatalf("expected user_c source contact_discovery, got %v", got)
	}
	if got := byID["user_c"]["metFrom"]; got != "通讯录匹配" {
		t.Fatalf("expected user_c metFrom 通讯录匹配, got %v", got)
	}
	if got := byID["user_c"]["bio"]; got != "Bio_user_c" {
		t.Fatalf("expected user_c bio from profile snapshot, got %v", got)
	}
	if got := byID["user_c"]["userHandle"]; got != "handle_user_c" {
		t.Fatalf("expected discovery profile userHandle, got %v", got)
	}

	cursor := ""
	seenCursors := map[string]struct{}{}
	pagedIDs := map[string]struct{}{}
	for pageNumber := 0; pageNumber < 8; pageNumber++ {
		req := httptest.NewRequest(
			http.MethodGet,
			"/chat/contacts?limit=1&cursor="+url.QueryEscape(cursor),
			nil,
		)
		req.Header.Set("X-Client-User-Id", "viewer_1")
		req.Header.Set("X-Client-Persona-Id", "viewer_1")
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("paged contacts request failed: %d %s", rec.Code, rec.Body.String())
		}
		var page map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
			t.Fatalf("decode paged contacts response: %v", err)
		}
		rows, ok := page["items"].([]any)
		if !ok || len(rows) > 1 {
			t.Fatalf("contacts page must contain at most one row: %#v", page)
		}
		for _, raw := range rows {
			row, ok := raw.(map[string]any)
			if !ok {
				t.Fatalf("unexpected paged row type: %T", raw)
			}
			if userID, _ := row["userId"].(string); userID != "" {
				pagedIDs[userID] = struct{}{}
			}
		}
		next, _ := page["nextCursor"].(string)
		if next == "" {
			break
		}
		if _, exists := seenCursors[next]; exists {
			t.Fatalf("contacts cursor repeated: %q", next)
		}
		seenCursors[next] = struct{}{}
		cursor = next
		if pageNumber == 7 {
			t.Fatal("contacts cursor did not terminate")
		}
	}
	for _, expectedID := range []string{"user_a", "user_b", "user_c"} {
		if _, exists := pagedIDs[expectedID]; !exists {
			t.Fatalf("paged contacts omitted %s: %#v", expectedID, pagedIDs)
		}
	}
}

func TestListContacts_FiltersBlockedContacts(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	socialServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/user/personas/viewer_1/following":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"items": []map[string]any{
					{
						"personaId":     "user_a",
						"displayName":   "Alice Follow",
						"avatarUrl":     "https://avatar/a.png",
						"followedAt":    "2026-06-06T12:00:00Z",
						"relationState": "following",
					},
				},
				"cursor": "",
			})
		case "/user/personas/viewer_1/followers":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"items": []map[string]any{
					{
						"personaId":     "user_a",
						"displayName":   "Alice Follow",
						"avatarUrl":     "https://avatar/a.png",
						"followedAt":    "2026-06-06T12:02:00Z",
						"relationState": "followed_by",
					},
				},
				"cursor": "",
			})
		case "/user/contact-discovery/latest":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":                "discovery_1",
				"matchedPersonaIds": []string{"user_b"},
				"status":            "completed",
				"createdAt":         time.Date(2026, 6, 6, 12, 4, 0, 0, time.UTC),
			})
		default:
			writeTestUserNotFound(w, r, "unexpected "+r.Method+" "+r.URL.Path)
		}
	}))
	defer socialServer.Close()

	chatStore := persistence.NewMongoChatStore(mongoDB)
	chatStorage := chatStoragePorts(chatStore)
	convCache := cache.NewConversationCache(redisRouter.Scene("general"))
	memberSvc := application.NewMemberService(
		chatStorage,
		convCache,
		eventPublisherForContractTest(),
		testProfileResolver{},
		nil,
		nil,
		groupAvatarSchedulerForContractTest(),
		application.WithRelationshipGate(relationshipGateForContractTest(
			t,
			application.RelationshipCapability{IsBlocked: true, IsBlockedBy: true},
			nil,
		)),
		application.WithSocialContactResolver(
			chathttp.NewUserSocialContactResolver(socialServer.URL, socialServer.Client()),
		),
	)
	handler := chathttp.NewChatHandler(
		application.NewConversationService(chatStorage, convCache, eventPublisherForContractTest(), testProfileResolver{}, application.DenyRelationshipGate(), nil, nil, groupAvatarSchedulerForContractTest()),
		application.NewMessageService(chatStorage, convCache, eventPublisherForContractTest(), application.DenyRelationshipGate(), testMediaAssetDeliveryReader{}),
		memberSvc,
		application.NewInboxService(chatStorage),
		nil,
	).Routes()

	req := httptest.NewRequest(http.MethodGet, "/chat/contacts?limit=10", nil)
	req.Header.Set("X-Client-User-Id", "viewer_1")
	req.Header.Set("X-Client-Persona-Id", "viewer_1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var payload map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	items, ok := payload["items"].([]any)
	if !ok {
		t.Fatalf("response missing items: %#v", payload)
	}
	if len(items) != 0 {
		t.Fatalf("expected blocked contacts to be filtered out, got %d items", len(items))
	}
}
