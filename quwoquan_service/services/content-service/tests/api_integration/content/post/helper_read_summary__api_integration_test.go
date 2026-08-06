// readiness_case: get-helper-read-api
// readiness_case: generate-article-summary-api
// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/helper-read-summary/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"unicode/utf8"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestGenerateArticleSummaryHTTPIsDeterministicAndDoesNotPersistPost(
	t *testing.T,
) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	body := strings.Repeat("川", 101)
	payload, err := json.Marshal(map[string]string{
		"title": "标题",
		"body":  body,
	})
	if err != nil {
		t.Fatal(err)
	}

	call := func() string {
		req := httptest.NewRequest(
			http.MethodPost,
			"/content/articles/summary:generate",
			strings.NewReader(string(payload)),
		)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Idempotency-Key", "article-summary-same-input")
		req.Header.Set("X-Client-User-Id", "account_summary")
		req.Header.Set("X-Client-Persona-Id", "persona_summary")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
		}
		var response struct {
			Summary string `json:"summary"`
		}
		if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
			t.Fatalf("decode summary response: %v", err)
		}
		return response.Summary
	}

	first := call()
	second := call()
	if first != second {
		t.Fatalf("same idempotency/input replay diverged: %q != %q", first, second)
	}
	if !utf8.ValidString(first) {
		t.Fatalf("summary is not valid UTF-8: %q", first)
	}
	if got, want := utf8.RuneCountInString(first), 2+1+100; got != want {
		t.Fatalf("summary rune count=%d want=%d: %q", got, want, first)
	}
	count, err := requireMongoDB(t).Collection("posts").CountDocuments(
		context.Background(),
		bson.M{"_id": bson.M{"$ne": integrationSupplyPostID}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if count != 0 {
		t.Fatalf("summary draft computation persisted %d Post records", count)
	}
}

func TestGenerateArticleSummaryHTTPRejectsMissingReplayIdentity(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	req := httptest.NewRequest(
		http.MethodPost,
		"/content/articles/summary:generate",
		strings.NewReader(`{"title":"标题","body":"正文"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "account_summary")
	req.Header.Set("X-Client-Persona-Id", "persona_summary")
	rec := httptest.NewRecorder()

	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	var failure struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode missing-idempotency failure: %v", err)
	}
	if failure.Code != "CONTENT.USER.invalid_argument" {
		t.Fatalf("missing-idempotency code=%q", failure.Code)
	}
	count, err := requireMongoDB(t).Collection("posts").CountDocuments(
		context.Background(),
		bson.M{"_id": bson.M{"$ne": integrationSupplyPostID}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if count != 0 {
		t.Fatalf("rejected summary request persisted %d Post records", count)
	}
}

func TestGetHelperReadHTTPUsesRealProjectionAndHidesNonPublicPost(
	t *testing.T,
) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	public := submitPublishedPostWithAuthor(t, "public_author", `{
		"contentType":"article",
		"title":"川西环线",
		"body":"公开文章正文",
		"summary":"作者确认的摘要",
		"visibility":"public"
	}`)
	publicPostID, _ := public["postId"].(string)
	if publicPostID == "" {
		t.Fatalf("public publication receipt missing postId: %+v", public)
	}
	if _, err := requireMongoDB(t).Collection("posts").UpdateOne(
		context.Background(),
		bson.M{"_id": publicPostID},
		bson.M{"$set": bson.M{"helperReadSummary": "投影生成的帮读摘要"}},
	); err != nil {
		t.Fatalf("set helper-read projection: %v", err)
	}

	req := httptest.NewRequest(
		http.MethodGet,
		"/content/helper-read/"+publicPostID,
		nil,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var response map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode helper-read response: %v", err)
	}
	if response["postId"] != publicPostID ||
		response["contentType"] != "article" ||
		response["title"] != "川西环线" ||
		response["summary"] != "投影生成的帮读摘要" {
		t.Fatalf("helper-read projection mismatch: %+v", response)
	}

	private := submitPublishedPostWithAuthor(t, "private_author", `{
		"contentType":"article",
		"title":"私密文章",
		"body":"不得公开的正文",
		"visibility":"private"
	}`)
	privatePostID, _ := private["postId"].(string)
	privateReq := httptest.NewRequest(
		http.MethodGet,
		"/content/helper-read/"+privatePostID,
		nil,
	)
	privateRec := httptest.NewRecorder()
	testHandler.ServeHTTP(privateRec, privateReq)
	if privateRec.Code != http.StatusNotFound {
		t.Fatalf(
			"private helper-read must return 404, got %d: %s",
			privateRec.Code,
			privateRec.Body.String(),
		)
	}
	var failure struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(privateRec.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode helper-read failure: %v", err)
	}
	if failure.Code != "CONTENT.USER.post_not_found" {
		t.Fatalf("private helper-read code=%q", failure.Code)
	}
}
