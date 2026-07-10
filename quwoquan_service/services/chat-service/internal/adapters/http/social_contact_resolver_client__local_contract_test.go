package http

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
)

func TestUserSocialContactResolverListContactsMergesSources(t *testing.T) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case strings.HasSuffix(r.URL.Path, "/following"):
			_ = json.NewEncoder(w).Encode(map[string]any{
				"items": []map[string]any{
					{
						"subAccountId":  "user_a",
						"displayName":   "Alice Follow",
						"avatarUrl":     "https://avatar/a.png",
						"followedAt":    "2026-06-06T12:00:00Z",
						"relationState": "following",
					},
					{
						"subAccountId":  "user_b",
						"displayName":   "Bob Mutual",
						"avatarUrl":     "https://avatar/b.png",
						"followedAt":    "2026-06-06T12:05:00Z",
						"relationState": "mutual",
					},
				},
				"cursor": "",
			})
		case strings.HasSuffix(r.URL.Path, "/followers"):
			_ = json.NewEncoder(w).Encode(map[string]any{
				"items": []map[string]any{
					{
						"subAccountId":  "user_a",
						"displayName":   "Alice Follow",
						"avatarUrl":     "https://avatar/a.png",
						"followedAt":    "2026-06-06T12:06:00Z",
						"relationState": "followed_by",
					},
					{
						"subAccountId":  "user_c",
						"displayName":   "Cora Follower",
						"avatarUrl":     "https://avatar/c.png",
						"followedAt":    "2026-06-06T12:07:00Z",
						"relationState": "followed_by",
					},
				},
				"cursor": "",
			})
		case strings.HasSuffix(r.URL.Path, "/contact-discovery/latest"):
			_ = json.NewEncoder(w).Encode(map[string]any{
				"id":                   "discovery_1",
				"matchedSubAccountIds": []string{"user_b", "user_d"},
				"status":               "completed",
				"createdAt":            time.Date(2026, 6, 6, 12, 8, 0, 0, time.UTC),
			})
		default:
			writeRuntimeNotFound(w, r, "unexpected "+r.Method+" "+r.URL.Path)
		}
	}))
	defer server.Close()

	resolver := NewUserSocialContactResolver(server.URL, server.Client())
	items, err := resolver.ListContacts(context.Background(), "viewer_1", 10)
	if err != nil {
		t.Fatalf("ListContacts failed: %v", err)
	}
	if len(items) != 4 {
		t.Fatalf("expected 4 merged contacts, got %d", len(items))
	}

	byID := map[string]map[string]any{}
	for _, item := range items {
		byID[item.UserID] = map[string]any{
			"displayName":     item.DisplayName,
			"avatarUrl":       item.AvatarURL,
			"relationState":   item.RelationState,
			"source":          item.Source,
			"metFrom":         item.MetFrom,
			"lastInteraction": item.LastInteraction,
		}
	}

	if got := byID["user_a"]["relationState"]; got != "mutual" {
		t.Fatalf("expected user_a mutual, got %v", got)
	}
	if got := byID["user_a"]["source"]; got != "mutual" {
		t.Fatalf("expected user_a source mutual, got %v", got)
	}
	if got := byID["user_b"]["relationState"]; got != "mutual" {
		t.Fatalf("expected user_b mutual, got %v", got)
	}
	if got := byID["user_b"]["source"]; got != "mutual" {
		t.Fatalf("expected user_b source mutual, got %v", got)
	}
	if got := byID["user_c"]["source"]; got != "following" {
		t.Fatalf("expected user_c source following, got %v", got)
	}
	if got := byID["user_d"]["source"]; got != "contact_discovery" {
		t.Fatalf("expected user_d source contact_discovery, got %v", got)
	}
	if got := byID["user_d"]["metFrom"]; got != "通讯录匹配" {
		t.Fatalf("expected user_d metFrom 通讯录匹配, got %v", got)
	}
}

func writeRuntimeNotFound(w http.ResponseWriter, r *http.Request, debugMessage string) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "not_found"), "用户资源不存在", debugMessage),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
