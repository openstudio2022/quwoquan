// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
// readiness_case: open-post-moderation-case-events-api
// readiness_case: open-post-moderation-case-api
// readiness_case: review-post-moderation-case-api
// readiness_case: decide-post-moderation-api
// readiness_case: supersede-post-moderation-case-api
// readiness_case: get-current-post-moderation-case-api
// readiness_case: get-post-publication-eligibility-api
package api_integration_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	contenthttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	moderationhttp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/adapters/inbound/http"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationpersistence "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/infrastructure/persistence"
)

func TestOpenHTTPCommitsCaseReceiptAuditAndOutboxInMongo(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "post_moderation_case_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := moderationpersistence.NewMongoPostModerationCaseStore(
		runtime.Database.Collection("post_moderation_cases"),
	)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	sequence := 0
	service := moderationapp.NewModerationService(
		moderationapp.BindDataPorts(store),
		moderationapp.WithClock(func() time.Time {
			return time.Date(2030, time.June, 7, 8, 9, 10, 0, time.UTC)
		}),
		moderationapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			sequence++
			if prefix == "pmc" {
				return "pmc-object-owned", nil
			}
			return fmt.Sprintf("%s-object-owned-%d", prefix, sequence), nil
		}),
	)
	handler := rtauth.EnforceRuntimeOperationContract(
		operationsecurity.ForDomain("content"),
	)(contenthttp.NewContentHandler(
		nil, nil, nil, nil, nil, nil, nil,
		contenthttp.WithPostModerationCaseHandler(
			moderationhttp.NewHandler(moderationapp.BindFacades(service)),
		),
	).Routes())
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/posts/post-moderated:open-moderation-case",
		strings.NewReader(`{"postVersion":3,"contentDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "open-moderation-once")
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		moderationServicePrincipal("content.post.moderation.open"),
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK || !strings.Contains(recorder.Body.String(), `"caseId":"pmc-object-owned"`) {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var opened struct {
		CaseID string `json:"caseId"`
		Status string `json:"status"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &opened); err != nil {
		t.Fatalf("decode opened moderation case: %v", err)
	}
	if opened.CaseID == "" || opened.Status != "pending" {
		t.Fatalf("opened moderation case drift: %+v", opened)
	}
	for _, collection := range []string{
		"post_moderation_cases",
		"post_moderation_case_command_receipts",
		"post_moderation_case_audit",
		"post_moderation_case_outbox",
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(context.Background(), bson.D{})
		if countErr != nil || count != 1 {
			t.Fatalf("%s count=%d err=%v", collection, count, countErr)
		}
	}

	current := executeModerationOperation(
		t,
		handler,
		http.MethodGet,
		"/internal/content/posts/post-moderated/moderation-case",
		"",
		"",
		moderationOperatorPrincipal(
			"ops.case.read",
			"content.moderation.read",
		),
	)
	if current.Code != http.StatusOK || !strings.Contains(current.Body.String(), `"status":"pending"`) {
		t.Fatalf("get current moderation case: status=%d body=%s", current.Code, current.Body.String())
	}

	reviewed := executeModerationOperation(
		t,
		handler,
		http.MethodPost,
		"/internal/content/posts/post-moderated:review-moderation",
		`{"caseId":"`+opened.CaseID+`"}`,
		"review-moderation-once",
		moderationOperatorPrincipal(
			"ops.case.write",
			"content.moderation.review",
		),
	)
	if reviewed.Code != http.StatusOK || !strings.Contains(reviewed.Body.String(), `"status":"reviewed"`) {
		t.Fatalf("review moderation case: status=%d body=%s", reviewed.Code, reviewed.Body.String())
	}

	decided := executeModerationOperation(
		t,
		handler,
		http.MethodPost,
		"/internal/content/posts/post-moderated:moderate",
		`{"caseId":"`+opened.CaseID+`","decision":"approve","decisionReason":"content is safe"}`,
		"decide-moderation-once",
		moderationOperatorPrincipal(
			"ops.case.write",
			"content.moderation.decide",
		),
	)
	if decided.Code != http.StatusOK || !strings.Contains(decided.Body.String(), `"status":"approved"`) {
		t.Fatalf("decide moderation case: status=%d body=%s", decided.Code, decided.Body.String())
	}

	eligibility := executeModerationOperation(
		t,
		handler,
		http.MethodGet,
		"/internal/content/posts/post-moderated/publication-eligibility?postVersion=3&contentDigest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		"",
		"",
		moderationServicePrincipal("content.post.publish"),
	)
	if eligibility.Code != http.StatusOK || !strings.Contains(eligibility.Body.String(), `"eligible":true`) {
		t.Fatalf("get publication eligibility: status=%d body=%s", eligibility.Code, eligibility.Body.String())
	}

	superseded := executeModerationOperation(
		t,
		handler,
		http.MethodPost,
		"/internal/content/posts/post-moderated:supersede-moderation",
		`{"caseId":"`+opened.CaseID+`"}`,
		"supersede-moderation-once",
		moderationServicePrincipal("content.post.moderation.supersede"),
	)
	if superseded.Code != http.StatusOK || !strings.Contains(superseded.Body.String(), `"status":"superseded"`) {
		t.Fatalf("supersede moderation case: status=%d body=%s", superseded.Code, superseded.Body.String())
	}
}

func executeModerationOperation(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
	idempotencyKey string,
	principal rtauth.Principal,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func moderationServicePrincipal(scope string) rtauth.Principal {
	return rtauth.Principal{
		Claims: rtauth.Claims{Subject: "service:content-publication", Scope: scope, Roles: []string{"service"}},
		Actor:  operation.ActorContext{AccountID: "service:content-publication"},
	}
}

func moderationOperatorPrincipal(scope string, permission string) rtauth.Principal {
	return rtauth.Principal{
		Claims: rtauth.Claims{
			Subject: "operator-content-reviewer", Scope: scope,
			Roles: []string{"operator"}, Permissions: []string{permission},
		},
		Actor: operation.ActorContext{AccountID: "operator-content-reviewer"},
	}
}

func TestSubmissionLifecycleConsumerPersistsPendingCaseAndAcknowledgesReplay(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "post_moderation_case_consumer")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := moderationpersistence.NewMongoPostModerationCaseStore(
		runtime.Database.Collection("post_moderation_cases"),
	)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	service := moderationapp.NewModerationService(
		moderationapp.BindDataPorts(store),
		moderationapp.WithClock(func() time.Time {
			return time.Date(2030, time.June, 7, 8, 9, 10, 0, time.UTC)
		}),
		moderationapp.WithIdentifierGenerator(func(string) (string, error) {
			return "pmc-consumer-owned", nil
		}),
	)
	opener := moderationapp.NewPostSubmissionModerationHandler(service)
	event := postports.OutboxEvent{
		EventID: "post-submission-consumer:1", EventType: "PostSubmittedForReview",
		AggregateType: "Post", AggregateID: "post-consumer-owned", AggregateVersion: 4,
		Payload:    []byte(`{"postId":"post-consumer-owned","status":"pending_review","moderationStatus":"pending","contentDigest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}`),
		OccurredAt: time.Date(2030, time.June, 7, 8, 9, 10, 0, time.UTC),
	}
	if err := opener.Publish(context.Background(), event); err != nil {
		t.Fatalf("consume PostSubmittedForReview: %v", err)
	}
	if err := opener.Publish(context.Background(), event); err != nil {
		t.Fatalf("acknowledge replayed PostSubmittedForReview: %v", err)
	}
	var persisted struct {
		Status      string `bson:"status"`
		PostID      string `bson:"postId"`
		PostVersion int64  `bson:"postVersion"`
	}
	if err := runtime.Database.Collection("post_moderation_cases").FindOne(
		context.Background(),
		bson.M{"_id": "pmc-consumer-owned"},
	).Decode(&persisted); err != nil {
		t.Fatalf("read projected moderation case: %v", err)
	}
	if persisted.Status != "pending" || persisted.PostID != event.AggregateID ||
		persisted.PostVersion != event.AggregateVersion {
		t.Fatalf("projected moderation case drifted: %+v", persisted)
	}
	if count, err := runtime.Database.Collection("post_moderation_cases").CountDocuments(
		context.Background(),
		bson.M{"postId": event.AggregateID, "postVersion": event.AggregateVersion},
	); err != nil || count != 1 {
		t.Fatalf("replayed event created duplicate case: count=%d err=%v", count, err)
	}
}
