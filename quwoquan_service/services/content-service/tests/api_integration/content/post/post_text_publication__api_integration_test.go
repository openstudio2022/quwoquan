// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t3
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t4
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
// readiness_case: apply-post-lifecycle-events-api
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/commandmeta"
	rtoperation "quwoquan_service/runtime/operation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	contenthttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postgovernance "quwoquan_service/services/content-service/internal/content/post/infrastructure/governance"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
)

type textPublicationHTTPHarness struct {
	handler http.Handler
	store   *persistence.MongoPostStore
	service *postapp.PostService
}

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-002
func TestTextPublicationLengthAndRateAdmissionThroughHTTP(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	harness := newTextPublicationHTTPHarness(
		t,
		postgovernance.NewRedisPublicationRateGate(
			requireTestRouter(t).Scene("general"),
		),
		testsupport.FixedPublicationSafetyGate{
			Decision: postports.PublicationSafetyAllow,
		},
	)
	authorID := "persona-text-publication-rate"
	overLimit := publishTextThroughHarness(
		t,
		harness.handler,
		authorID,
		"intent-over-length",
		"draft-over-length",
		map[string]any{
			"contentType": "micro",
			"title": strings.Repeat(
				"文",
				contentgenerated.PostPublicationTitleMaxRunes+1,
			),
			"body":       "正文",
			"visibility": "public",
		},
	)
	assertRuntimeErrorResponse(
		t,
		overLimit,
		http.StatusBadRequest,
		contentgenerated.ErrContentTooLong.Error(),
	)

	for index := 0; index < contentgenerated.PostPublicationPersonaMaxPublications; index++ {
		response := publishTextThroughHarness(
			t,
			harness.handler,
			authorID,
			fmt.Sprintf("intent-rate-%d", index),
			fmt.Sprintf("draft-rate-%d", index),
			map[string]any{
				"contentType": "micro",
				"body":        fmt.Sprintf("窗口内文字发布 %d", index),
				"visibility":  "public",
			},
		)
		if response.Code != http.StatusAccepted {
			t.Fatalf(
				"publication %d status=%d body=%s",
				index,
				response.Code,
				response.Body.String(),
			)
		}
	}
	rateLimited := publishTextThroughHarness(
		t,
		harness.handler,
		authorID,
		"intent-rate-over-limit",
		"draft-rate-over-limit",
		map[string]any{
			"contentType": "micro",
			"body":        "窗口外额外发布",
			"visibility":  "public",
		},
	)
	assertRuntimeErrorResponse(
		t,
		rateLimited,
		http.StatusTooManyRequests,
		contentgenerated.ErrRateLimited.Error(),
	)
	if count, err := mongoDB.Collection("posts").CountDocuments(
		context.Background(),
		bson.M{"authorId": authorID},
	); err != nil || count != int64(contentgenerated.PostPublicationPersonaMaxPublications) {
		t.Fatalf("admitted Post count=%d err=%v", count, err)
	}
}

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
func TestTextPublicationSafetyAndModerationRoundTripThroughHTTP(t *testing.T) {
	testCases := []struct {
		name             string
		safety           testsupport.FixedPublicationSafetyGate
		initialState     string
		initialHTTP      int
		terminalDecision moderationmodel.Decision
		terminalState    string
	}{
		{
			name: "allow publishes immediately",
			safety: testsupport.FixedPublicationSafetyGate{
				Decision: postports.PublicationSafetyAllow,
			},
			initialState: "published",
			initialHTTP:  http.StatusAccepted,
		},
		{
			name: "review approves exact revision",
			safety: testsupport.FixedPublicationSafetyGate{
				Decision: postports.PublicationSafetyReview,
			},
			initialState:     "pending_review",
			initialHTTP:      http.StatusAccepted,
			terminalDecision: moderationmodel.DecisionApprove,
			terminalState:    "published",
		},
		{
			name: "unavailable rejects after manual review",
			safety: testsupport.FixedPublicationSafetyGate{
				Err: errors.New("safety provider timeout"),
			},
			initialState:     "pending_review",
			initialHTTP:      http.StatusAccepted,
			terminalDecision: moderationmodel.DecisionReject,
			terminalState:    "rejected",
		},
		{
			name: "reject writes nothing",
			safety: testsupport.FixedPublicationSafetyGate{
				Decision:   postports.PublicationSafetyReject,
				ReasonCode: "unsafe_content",
			},
			initialHTTP: http.StatusUnprocessableEntity,
		},
	}

	for index, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			cleanPosts(t)
			cleanModerationCases(t)
			t.Cleanup(func() {
				cleanPosts(t)
				cleanModerationCases(t)
			})
			harness := newTextPublicationHTTPHarness(
				t,
				testsupport.AllowPublicationRateGate{},
				testCase.safety,
			)
			authorID := fmt.Sprintf("persona-text-safety-%d", index)
			intentID := fmt.Sprintf("intent-text-safety-%d", index)
			response := publishTextThroughHarness(
				t,
				harness.handler,
				authorID,
				intentID,
				fmt.Sprintf("draft-text-safety-%d", index),
				map[string]any{
					"contentType": "micro",
					"body":        fmt.Sprintf("文字安全准入场景 %d", index),
					"visibility":  "public",
				},
			)
			if response.Code != testCase.initialHTTP {
				t.Fatalf(
					"initial status=%d want=%d body=%s",
					response.Code,
					testCase.initialHTTP,
					response.Body.String(),
				)
			}
			if testCase.initialHTTP != http.StatusAccepted {
				assertRuntimeErrorResponse(
					t,
					response,
					testCase.initialHTTP,
					contentgenerated.ErrPublicationRejected.Error(),
				)
				assertNoPublicationWrites(t, authorID)
				return
			}

			receipt := decodeTestObject(t, response)
			if receipt["state"] != testCase.initialState {
				t.Fatalf("receipt state=%v want=%s", receipt["state"], testCase.initialState)
			}
			postID := asTestString(receipt["postId"])
			if postID == "" {
				t.Fatalf("publication receipt has no postId: %+v", receipt)
			}
			if testCase.initialState == "published" {
				assertPublicPostCount(t, postID, 1)
				return
			}

			assertPublicPostCount(t, postID, 0)
			assertPostReadStatus(
				t,
				harness.handler,
				postID,
				authorID,
				http.StatusOK,
			)
			assertPostReadStatus(
				t,
				harness.handler,
				postID,
				"another-persona",
				http.StatusNotFound,
			)
			submissionRelay := postapp.NewOutboxRelay(
				harness.store,
				harness.store,
				moderationapp.NewPostSubmissionModerationHandler(testModerationFacades),
				fmt.Sprintf("text-safety-submission-%d", index),
			)
			if delivered, err := submissionRelay.Drain(
				context.Background(),
				10,
			); err != nil || delivered != 1 {
				t.Fatalf("open moderation case: delivered=%d err=%v", delivered, err)
			}
			caseSlice, err := testModerationFacades.GetCurrentPostModerationCase(
				context.Background(),
				moderationapp.GetCurrentPostModerationCaseQuery{PostID: postID},
			)
			if err != nil || caseSlice.Status != moderationmodel.StatusPending {
				t.Fatalf("pending moderation case=%+v err=%v", caseSlice, err)
			}
			reviewerID := fmt.Sprintf("operator-text-safety-%d", index)
			if _, err := testModerationFacades.ReviewPostModerationCase(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					fmt.Sprintf("review-text-safety-%d", index),
				),
				moderationapp.ReviewPostModerationCaseCommand{
					PostID: postID, CaseID: caseSlice.ID, ReviewerID: reviewerID,
				},
			); err != nil {
				t.Fatalf("review moderation case: %v", err)
			}
			if _, err := testModerationFacades.DecidePostModerationCase(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					fmt.Sprintf("decide-text-safety-%d", index),
				),
				moderationapp.DecidePostModerationCaseCommand{
					PostID:         postID,
					CaseID:         caseSlice.ID,
					ReviewerID:     reviewerID,
					Decision:       testCase.terminalDecision,
					DecisionReason: "integration decision",
				},
			); err != nil {
				t.Fatalf("decide moderation case: %v", err)
			}
			decisionRelay := moderationapp.NewOutboxRelay(
				testModerationStore,
				testModerationStore,
				postapp.NewPostModerationDecisionHandler(harness.service),
				fmt.Sprintf("text-safety-post-lifecycle-%d", index),
			)
			if delivered, err := decisionRelay.Drain(
				context.Background(),
				10,
			); err != nil || delivered != 3 {
				t.Fatalf("apply moderation decision: delivered=%d err=%v", delivered, err)
			}
			var stored struct {
				Status           string `bson:"status"`
				ModerationStatus string `bson:"moderationStatus"`
			}
			if err := mongoDB.Collection("posts").FindOne(
				context.Background(),
				bson.M{"_id": postID},
			).Decode(&stored); err != nil {
				t.Fatalf("load moderated Post: %v", err)
			}
			if stored.Status != testCase.terminalState ||
				stored.ModerationStatus != string(testCase.terminalDecision) {
				t.Fatalf("moderated Post state mismatch: %+v", stored)
			}
			if testCase.terminalState == "published" {
				assertPublicPostCount(t, postID, 1)
				assertPostReadStatus(
					t,
					harness.handler,
					postID,
					"another-persona",
					http.StatusOK,
				)
			} else {
				assertPublicPostCount(t, postID, 0)
				assertPostReadStatus(
					t,
					harness.handler,
					postID,
					authorID,
					http.StatusOK,
				)
				assertPostReadStatus(
					t,
					harness.handler,
					postID,
					"another-persona",
					http.StatusNotFound,
				)
			}
		})
	}
}

func newTextPublicationHTTPHarness(
	t *testing.T,
	rateGate postports.PublicationRateGate,
	safetyGate postports.PublicationSafetyGate,
) textPublicationHTTPHarness {
	t.Helper()
	store := newMongoPostStore(
		requireMongoDB(t).Collection("posts"),
	)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure Post indexes: %v", err)
	}
	service := postapp.NewPostService(
		postapp.BindDataPorts(store),
		postapp.WithPublicationAdmission(rateGate, safetyGate),
	)
	reader := persistence.NewMongoPostQueryReader(
		requireMongoDB(t).Collection("posts"),
	)
	query := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail:     reader,
		Author:     reader,
		Tombstones: store,
	})
	return textPublicationHTTPHarness{
		handler: contenthttp.NewContentHandler(
			nil,
			postapp.BindFacades(service),
			query,
			nil,
			nil,
			nil,
			nil,
		).Routes(),
		store:   store,
		service: service,
	}
}

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-006
func TestTextPublicationSemanticMentionProjectionRoundTripThroughHTTP(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	harness := newTextPublicationHTTPHarness(
		t,
		postgovernance.NewRedisPublicationRateGate(
			requireTestRouter(t).Scene("general"),
		),
		testsupport.FixedPublicationSafetyGate{
			Decision: postports.PublicationSafetyAllow,
		},
	)
	authorID := "persona-text-publication-mentions"
	response := publishTextThroughHarness(
		t,
		harness.handler,
		authorID,
		"intent-semantic-mentions",
		"draft-semantic-mentions",
		map[string]any{
			"contentType": "micro",
			"body":        "九寨沟的秋天值得专程去一次",
			"visibility":  "public",
			"semanticMentions": []map[string]any{
				{
					"mentionId": "m_entity_published",
					"kind":      "entity",
					"status":    "published",
					"targetRef": "/entity/地点/景区/九寨沟",
				},
				{
					"mentionId": "m_tag_published",
					"kind":      "tag",
					"status":    "published",
					"targetRef": "tag:topic:川西秋色",
				},
				{
					"mentionId": "m_entity_pending",
					"kind":      "entity",
					"status":    "pending",
					"targetRef": "/entity/地点/景区/黄龙",
				},
			},
		},
	)
	if response.Code != http.StatusAccepted {
		t.Fatalf(
			"mention publication status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
	receipt := decodeTestObject(t, response)
	postID := asTestString(receipt["postId"])
	if postID == "" {
		t.Fatalf("publication receipt has no postId: %+v", receipt)
	}

	// 公开读回：只有 published mention 进入 entityRefs/tagRefs 投影；
	// pending mention 不得伪装成事实标签。
	request := authenticatedPublicationRequest(
		t,
		http.MethodGet,
		"/content/posts/"+postID,
		authorID,
		nil,
	)
	readback := httptest.NewRecorder()
	harness.handler.ServeHTTP(readback, request)
	if readback.Code != http.StatusOK {
		t.Fatalf("GetPost status=%d body=%s", readback.Code, readback.Body.String())
	}
	detail := decodeTestObject(t, readback)
	entityRefs, _ := detail["entityRefs"].([]any)
	tagRefs, _ := detail["tagRefs"].([]any)
	if len(entityRefs) != 1 || asTestString(entityRefs[0]) != "/entity/地点/景区/九寨沟" {
		t.Fatalf("entityRefs=%v want published mention only", entityRefs)
	}
	if len(tagRefs) != 1 || asTestString(tagRefs[0]) != "tag:topic:川西秋色" {
		t.Fatalf("tagRefs=%v want published mention only", tagRefs)
	}
	mentions, _ := detail["semanticMentions"].([]any)
	if len(mentions) != 3 {
		t.Fatalf("semanticMentions=%v want all three author mentions retained", mentions)
	}
}

func publishTextThroughHarness(
	t *testing.T,
	handler http.Handler,
	authorID string,
	intentID string,
	draftID string,
	payload map[string]any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload["publishIntentId"] = intentID
	payload["localDraftId"] = draftID
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("encode publication request: %v", err)
	}
	request := authenticatedPublicationRequest(
		t,
		http.MethodPost,
		"/content/posts:publish",
		authorID,
		strings.NewReader(string(encoded)),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", intentID)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func assertPostReadStatus(
	t *testing.T,
	handler http.Handler,
	postID string,
	viewerID string,
	expected int,
) {
	t.Helper()
	request := authenticatedPublicationRequest(
		t,
		http.MethodGet,
		"/content/posts/"+postID,
		viewerID,
		nil,
	)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != expected {
		t.Fatalf(
			"GetPost viewer=%s status=%d want=%d body=%s",
			viewerID,
			response.Code,
			expected,
			response.Body.String(),
		)
	}
}

func authenticatedPublicationRequest(
	t *testing.T,
	method string,
	path string,
	personaID string,
	body *strings.Reader,
) *http.Request {
	t.Helper()
	var request *http.Request
	if body == nil {
		request = httptest.NewRequest(method, path, nil)
	} else {
		request = httptest.NewRequest(method, path, body)
	}
	request.Header.Set("X-Client-User-Id", personaID)
	request.Header.Set("X-Client-Persona-Id", personaID)
	principal := rtauth.Principal{
		Claims: rtauth.Claims{Subject: personaID, Persona: personaID},
		Actor: rtoperation.ActorContext{
			AccountID: personaID,
			PersonaID: personaID,
		},
	}
	return request.WithContext(
		rtauth.WithPrincipal(request.Context(), principal),
	)
}

func assertRuntimeErrorResponse(
	t *testing.T,
	response *httptest.ResponseRecorder,
	expectedHTTP int,
	expectedCode string,
) {
	t.Helper()
	if response.Code != expectedHTTP {
		t.Fatalf(
			"runtime error HTTP=%d want=%d body=%s",
			response.Code,
			expectedHTTP,
			response.Body.String(),
		)
	}
	failure := decodeTestObject(t, response)
	if failure["code"] != expectedCode {
		t.Fatalf("runtime error code=%v want=%s", failure["code"], expectedCode)
	}
}

func decodeTestObject(
	t *testing.T,
	response *httptest.ResponseRecorder,
) map[string]any {
	t.Helper()
	var result map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v body=%s", err, response.Body.String())
	}
	return result
}

func assertNoPublicationWrites(t *testing.T, authorID string) {
	t.Helper()
	for collection, filter := range map[string]bson.M{
		"posts":                 {"authorId": authorID},
		"content_outbox":        {"aggregateId": bson.M{"$ne": ""}},
		"post_command_receipts": {"aggregateId": bson.M{"$ne": ""}},
	} {
		count, err := mongoDB.Collection(collection).CountDocuments(
			context.Background(),
			filter,
		)
		if err != nil {
			t.Fatalf("count %s: %v", collection, err)
		}
		if count != 0 {
			t.Fatalf("rejected publication wrote %d document(s) to %s", count, collection)
		}
	}
}

func assertPublicPostCount(t *testing.T, postID string, expected int64) {
	t.Helper()
	count, err := mongoDB.Collection("posts").CountDocuments(
		context.Background(),
		bson.M{
			"_id":              postID,
			"status":           "published",
			"moderationStatus": "approved",
		},
	)
	if err != nil || count != expected {
		t.Fatalf("public Post count=%d want=%d err=%v", count, expected, err)
	}
}
