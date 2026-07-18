package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/application/identity"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func TestPostPublicationIntentConcurrentReplayCreatesOnePost(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	const (
		workers         = 16
		publishIntentID = "publication-intent-concurrent"
		localDraftID    = "publication-draft-concurrent"
	)
	body := `{
		"publishIntentId":"` + publishIntentID + `",
		"localDraftId":"` + localDraftID + `",
		"contentType":"micro",
		"body":"并发发布只创建一次",
		"visibility":"public"
	}`

	responses := make(chan *httptest.ResponseRecorder, workers)
	var group sync.WaitGroup
	for range workers {
		group.Add(1)
		go func() {
			defer group.Done()
			request := httptest.NewRequest(
				http.MethodPost,
				"/content/posts:publish",
				strings.NewReader(body),
			)
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set(
				"X-Client-User-Id",
				identity.AnonymousFallbackSubAccountID,
			)
			request.Header.Set(
				"X-Client-Sub-Account-Id",
				identity.AnonymousFallbackSubAccountID,
			)
			request.Header.Set("Idempotency-Key", publishIntentID)
			recorder := httptest.NewRecorder()
			testHandler.ServeHTTP(recorder, request)
			responses <- recorder
		}()
	}
	group.Wait()
	close(responses)

	var firstReceipt map[string]any
	for response := range responses {
		if response.Code != http.StatusAccepted {
			t.Fatalf(
				"concurrent publication status=%d body=%s",
				response.Code,
				response.Body.String(),
			)
		}
		var receipt map[string]any
		if err := json.Unmarshal(response.Body.Bytes(), &receipt); err != nil {
			t.Fatalf("decode publication receipt: %v", err)
		}
		if firstReceipt == nil {
			firstReceipt = receipt
			continue
		}
		for _, field := range []string{
			"publishIntentId",
			"localDraftId",
			"postId",
			"state",
			"committedVersion",
			"acceptedAt",
		} {
			if receipt[field] != firstReceipt[field] {
				t.Fatalf(
					"publication receipt %s diverged: first=%v replay=%v",
					field,
					firstReceipt[field],
					receipt[field],
				)
			}
		}
	}

	ctx := context.Background()
	postFilter := bson.M{
		"authorId":        identity.AnonymousFallbackSubAccountID,
		"publishIntentId": publishIntentID,
		"localDraftId":    localDraftID,
	}
	if count, err := mongoDB.Collection("posts").CountDocuments(
		ctx,
		postFilter,
	); err != nil || count != 1 {
		t.Fatalf("published Post count=%d err=%v", count, err)
	}
	if count, err := mongoDB.Collection("content_outbox").CountDocuments(
		ctx,
		bson.M{"eventType": "PostPublished", "aggregateId": firstReceipt["postId"]},
	); err != nil || count != 1 {
		t.Fatalf("PostPublished outbox count=%d err=%v", count, err)
	}
}

func TestPostPublicationIntentFirstAcceptedDraftWinsPermanently(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	const localDraftID = "publication-draft-first-wins"
	first := submitPostPublicationIntent(
		t,
		"publication-intent-first",
		localDraftID,
		"首次发布内容",
	)
	changedReplay := submitPostPublicationIntent(
		t,
		"publication-intent-first",
		localDraftID,
		"后续重放不得覆盖",
	)
	accidentalNewIntent := submitPostPublicationIntent(
		t,
		"publication-intent-accidental",
		localDraftID,
		"误生成新意图也不得再次发布",
	)
	for _, replay := range []map[string]any{changedReplay, accidentalNewIntent} {
		for _, field := range []string{
			"publishIntentId",
			"localDraftId",
			"postId",
			"state",
			"committedVersion",
			"acceptedAt",
		} {
			if replay[field] != first[field] {
				t.Fatalf(
					"first accepted receipt %s changed: first=%v replay=%v",
					field,
					first[field],
					replay[field],
				)
			}
		}
	}

	var stored struct {
		Body string `bson:"body"`
	}
	if err := mongoDB.Collection("posts").FindOne(
		context.Background(),
		bson.M{
			"authorId":     identity.AnonymousFallbackSubAccountID,
			"localDraftId": localDraftID,
		},
	).Decode(&stored); err != nil {
		t.Fatal(err)
	}
	if stored.Body != "首次发布内容" {
		t.Fatalf("published content was overwritten: %q", stored.Body)
	}
	if count, err := mongoDB.Collection("posts").CountDocuments(
		context.Background(),
		bson.M{
			"authorId":     identity.AnonymousFallbackSubAccountID,
			"localDraftId": localDraftID,
		},
	); err != nil || count != 1 {
		t.Fatalf("published Post count=%d err=%v", count, err)
	}
	if count, err := mongoDB.Collection("content_outbox").CountDocuments(
		context.Background(),
		bson.M{"eventType": "PostPublished", "aggregateId": first["postId"]},
	); err != nil || count != 1 {
		t.Fatalf("PostPublished outbox count=%d err=%v", count, err)
	}
}

func TestPostPublicationIntentRejectsReuseForAnotherDraft(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	const publishIntentID = "publication-intent-reused"
	first := submitPostPublicationIntent(
		t,
		publishIntentID,
		"publication-draft-original",
		"首次发布内容",
	)
	payload, err := json.Marshal(map[string]any{
		"publishIntentId": publishIntentID,
		"localDraftId":    "publication-draft-other",
		"contentType":     "micro",
		"body":            "同一意图不得发布另一草稿",
		"visibility":      "public",
	})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		strings.NewReader(string(payload)),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(
		"X-Client-User-Id",
		identity.AnonymousFallbackSubAccountID,
	)
	request.Header.Set(
		"X-Client-Sub-Account-Id",
		identity.AnonymousFallbackSubAccountID,
	)
	request.Header.Set("Idempotency-Key", publishIntentID)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusConflict {
		t.Fatalf(
			"reused publication intent status=%d body=%s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
	var failure map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode reused intent failure: %v", err)
	}
	if failure["code"] != contentgenerated.ErrIdempotencyConflict.Error() {
		t.Fatalf("reused publication intent failure=%v", failure)
	}
	if count, err := mongoDB.Collection("posts").CountDocuments(
		context.Background(),
		bson.M{"publishIntentId": publishIntentID},
	); err != nil || count != 1 {
		t.Fatalf("reused intent post count=%d err=%v first=%v", count, err, first)
	}
}

func submitPostPublicationIntent(
	t *testing.T,
	publishIntentID string,
	localDraftID string,
	body string,
) map[string]any {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"publishIntentId": publishIntentID,
		"localDraftId":    localDraftID,
		"contentType":     "micro",
		"body":            body,
		"visibility":      "public",
	})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		strings.NewReader(string(payload)),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(
		"X-Client-User-Id",
		identity.AnonymousFallbackSubAccountID,
	)
	request.Header.Set(
		"X-Client-Sub-Account-Id",
		identity.AnonymousFallbackSubAccountID,
	)
	request.Header.Set("Idempotency-Key", publishIntentID)
	response := httptest.NewRecorder()
	testHandler.ServeHTTP(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf(
			"publication status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
	var receipt map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &receipt); err != nil {
		t.Fatal(err)
	}
	return receipt
}
