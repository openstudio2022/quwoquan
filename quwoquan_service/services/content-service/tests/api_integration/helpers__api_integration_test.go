package api_integration

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/services/content-service/internal/application/identity"
	"strings"
	"sync/atomic"
	"testing"
)

var helperRequestSequence atomic.Uint64

// createPost is a shared test helper: create draft then publish it, returning
// the published response body. Most feed/profile/comment contracts need a
// published post instead of a raw draft.
func createPost(t *testing.T, payload string) map[string]any {
	t.Helper()
	return createPostWithAuthor(t, "", payload)
}

// createPostWithAuthor creates a draft as the given author and immediately
// publishes it. Use distinct authors when tests need multiple items to pass
// recommendation rerank (maxAuthorPerFeed limits items per author).
func createPostWithAuthor(t *testing.T, authorID string, payload string) map[string]any {
	t.Helper()
	created := createDraftPostWithAuthor(t, authorID, payload)
	postID, _ := created["_id"].(string)
	if postID == "" {
		postID, _ = created["id"].(string)
	}
	if postID == "" {
		t.Fatalf("createPostWithAuthor: missing post id in draft response: %+v", created)
	}
	published := publishPostWithAuthor(t, authorID, postID, `{}`)
	for key, value := range created {
		if _, exists := published[key]; !exists {
			published[key] = value
		}
	}
	return published
}

// createDraftPost creates a raw draft and returns the parsed response body.
func createDraftPost(t *testing.T, payload string) map[string]any {
	t.Helper()
	return createDraftPostWithAuthor(t, "", payload)
}

// createDraftPostWithAuthor creates a draft as the given author
// (sets X-Client-User-Id and X-Client-Sub-Account-Id) and returns the draft payload.
func createDraftPostWithAuthor(t *testing.T, authorID string, payload string) map[string]any {
	t.Helper()
	payload = normalizeCreatePostPayloadForTest(t, payload)
	if strings.TrimSpace(authorID) == "" {
		authorID = identity.AnonymousFallbackSubAccountID
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", authorID)
	req.Header.Set("X-Client-Sub-Account-Id", authorID)
	ensureIdempotencyHeader(
		req,
		fmt.Sprintf("create-%s-%s-%d", authorID, t.Name(), helperRequestSequence.Add(1)),
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("createPost helper: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("createPost helper: decode response: %v", err)
	}
	return result
}

func normalizeCreatePostPayloadForTest(t *testing.T, payload string) string {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal([]byte(payload), &body); err != nil {
		t.Fatalf("normalize create post payload: %v", err)
	}
	if strings.TrimSpace(asTestString(body["contentType"])) == "article" &&
		strings.TrimSpace(asTestString(body["articleMarkdown"])) == "" {
		title := strings.TrimSpace(asTestString(body["title"]))
		summary := strings.TrimSpace(asTestString(body["summary"]))
		articleBody := strings.TrimSpace(asTestString(body["body"]))
		coverURL := strings.TrimSpace(asTestString(body["coverUrl"]))
		markdown := ""
		if title != "" {
			markdown += "# " + title + "\n\n"
		}
		if articleBody != "" {
			markdown += articleBody + "\n\n"
		} else if summary != "" {
			markdown += summary + "\n\n"
		}
		if coverURL != "" {
			markdown += "![cover](" + coverURL + ")\n"
		}
		body["articleMarkdown"] = strings.TrimSpace(markdown)
		if strings.TrimSpace(asTestString(body["articleMarkdownVersion"])) == "" {
			body["articleMarkdownVersion"] = "qwq-rich-md/1"
		}
		if body["articleAssetManifest"] == nil {
			body["articleAssetManifest"] = map[string]any{
				"assets": []any{},
			}
		}
		if body["articleRenderProfile"] == nil {
			body["articleRenderProfile"] = map[string]any{
				"template":   "journal",
				"fontPreset": "clean",
			}
		}
	}
	normalized, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal normalized create post payload: %v", err)
	}
	return string(normalized)
}

func asTestString(value any) string {
	if s, ok := value.(string); ok {
		return s
	}
	return ""
}

func publishPostWithAuthor(
	t *testing.T,
	authorID string,
	postID string,
	payload string,
) map[string]any {
	t.Helper()
	if strings.TrimSpace(authorID) == "" {
		authorID = identity.AnonymousFallbackSubAccountID
	}
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/publish",
		strings.NewReader(payload),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", authorID)
	req.Header.Set("X-Client-Sub-Account-Id", authorID)
	ensureIdempotencyHeader(req, "publish-"+postID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("publishPostWithAuthor: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("publishPostWithAuthor: decode response: %v", err)
	}
	drainPostOutbox(t)
	return result
}

func ensureIdempotencyHeader(req *http.Request, suffix string) {
	if req.Header.Get("Idempotency-Key") != "" || req.Header.Get("X-Request-Id") != "" {
		return
	}
	req.Header.Set("X-Request-Id", "api-integration-"+suffix)
}

func TestNormalizeCreatePostPayloadAddsTypedArticleContract(t *testing.T) {
	t.Parallel()
	normalized := normalizeCreatePostPayloadForTest(
		t,
		`{"contentType":"article","title":"Contract article","body":"Body"}`,
	)
	var payload map[string]any
	if err := json.Unmarshal([]byte(normalized), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["articleMarkdown"] != "# Contract article\n\nBody" ||
		payload["articleMarkdownVersion"] != "qwq-rich-md/1" {
		t.Fatalf("article helper did not produce canonical wire payload: %+v", payload)
	}
}
