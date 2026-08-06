// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/unified-entry-security/rate-limit-protection/spec.md#gwt-001
// readiness_case: shared-admission-local
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
)

func TestBucketKeyIsBoundedOpaqueAndSharedAcrossRolloutStages(t *testing.T) {
	subject := domain.Subject{Kind: "persona", ID: "persona-sensitive-value"}
	operationID := "content.post.CreatePost"

	stable, err := domain.BucketKey("prod", subject, operationID)
	if err != nil {
		t.Fatalf("stable key: %v", err)
	}
	gray, err := domain.BucketKey("prod", subject, operationID)
	if err != nil {
		t.Fatalf("gray key: %v", err)
	}
	if stable != gray {
		t.Fatalf("stable and gray must share one authoritative bucket: %q != %q", stable, gray)
	}
	if len(stable) > domain.MaxAdmissionKey {
		t.Fatalf("key length=%d exceeds %d", len(stable), domain.MaxAdmissionKey)
	}
	for _, forbidden := range []string{subject.ID, operationID, "stable", "gray"} {
		if strings.Contains(stable, forbidden) {
			t.Fatalf("key leaks or partitions by %q: %q", forbidden, stable)
		}
	}
	alpha, err := domain.BucketKey("alpha", subject, operationID)
	if err != nil {
		t.Fatalf("alpha key: %v", err)
	}
	if alpha == stable {
		t.Fatal("different environments must not share admission state")
	}
}

func TestBucketKeySeparatesSubjectsAndCanonicalOperations(t *testing.T) {
	personaFeed, err := domain.BucketKey(
		"prod",
		domain.Subject{Kind: "persona", ID: "persona-1"},
		"content.post.GetFeed",
	)
	if err != nil {
		t.Fatal(err)
	}
	otherPersonaFeed, err := domain.BucketKey(
		"prod",
		domain.Subject{Kind: "persona", ID: "persona-2"},
		"content.post.GetFeed",
	)
	if err != nil {
		t.Fatal(err)
	}
	personaPost, err := domain.BucketKey(
		"prod",
		domain.Subject{Kind: "persona", ID: "persona-1"},
		"content.post.GetPost",
	)
	if err != nil {
		t.Fatal(err)
	}
	if personaFeed == otherPersonaFeed || personaFeed == personaPost || otherPersonaFeed == personaPost {
		t.Fatalf(
			"subject and operation buckets must be isolated: %q %q %q",
			personaFeed,
			otherPersonaFeed,
			personaPost,
		)
	}
}

func TestPolicyRejectsUnboundedTTL(t *testing.T) {
	policy := domain.Policy{
		Limit:        1,
		Window:       domain.MaxWindow + time.Millisecond,
		StateFailure: domain.FailurePolicyFailClosed,
	}
	if err := policy.Validate(); err == nil {
		t.Fatal("policy window above the canonical TTL ceiling must fail")
	}
}

func TestExactOperationPolicyOverridesGenericKindPolicy(t *testing.T) {
	store := &stubStore{}
	policies := application.PolicySet{
		ByOperationKind: map[string]domain.Policy{
			"command": {Limit: 10, Window: time.Minute, StateFailure: domain.FailurePolicyFailClosed},
			"query":   {Limit: 20, Window: time.Minute, StateFailure: domain.FailurePolicyFailClosed},
			"session": {Limit: 30, Window: time.Minute, StateFailure: domain.FailurePolicyFailClosed},
		},
		ByOperationID: map[string]domain.Policy{
			"content.post.GetFeed": {
				Limit:        400,
				Window:       time.Second,
				StateFailure: domain.FailurePolicyFailClosed,
			},
		},
	}
	service, err := application.NewService("prod", store, policies, nil)
	if err != nil {
		t.Fatal(err)
	}
	descriptor := testDescriptor()
	descriptor.CanonicalOperationID = "content.post.GetFeed"
	descriptor.OperationKind = "query"
	if _, err := service.Admit(
		context.Background(),
		domain.Subject{Kind: "persona", ID: "persona-1"},
		descriptor,
	); err != nil {
		t.Fatal(err)
	}
	if len(store.limits) != 1 || store.limits[0] != 400 || store.windows[0] != time.Second {
		t.Fatalf("exact operation policy was not authoritative: limits=%v windows=%v", store.limits, store.windows)
	}
}

func TestAdmissionStateFailureExecutesTheDeclaredPolicyWithoutLocalFallback(t *testing.T) {
	descriptor := testDescriptor()
	stateFailure := errors.New("redis unavailable")

	for _, testCase := range []struct {
		name          string
		failurePolicy domain.FailurePolicy
		wantAllowed   bool
		wantError     bool
		wantOutcome   string
	}{
		{
			name:          "fail closed",
			failurePolicy: domain.FailurePolicyFailClosed,
			wantAllowed:   false,
			wantError:     true,
			wantOutcome:   "state_unavailable_denied",
		},
		{
			name:          "explicit fail open",
			failurePolicy: domain.FailurePolicyFailOpen,
			wantAllowed:   true,
			wantError:     false,
			wantOutcome:   "state_unavailable_allowed",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := &stubStore{err: stateFailure}
			observer := &captureObserver{}
			service := newTestService(t, store, testCase.failurePolicy, observer)
			decision, err := service.Admit(
				context.Background(),
				domain.Subject{Kind: "persona", ID: "persona-1"},
				descriptor,
			)
			if decision.Allowed != testCase.wantAllowed {
				t.Fatalf("allowed=%v want=%v", decision.Allowed, testCase.wantAllowed)
			}
			if (err != nil) != testCase.wantError {
				t.Fatalf("err=%v wantError=%v", err, testCase.wantError)
			}
			if testCase.wantError && !errors.Is(err, application.ErrSharedStateUnavailable) {
				t.Fatalf("error=%v does not preserve shared-state sentinel", err)
			}
			if store.calls != 1 {
				t.Fatalf("authoritative store calls=%d want=1", store.calls)
			}
			if observer.outcome != testCase.wantOutcome ||
				observer.failurePolicy != string(testCase.failurePolicy) {
				t.Fatalf("observer=%+v", observer)
			}
		})
	}
}

func TestGatewayRateLimitResponseKeepsRetryAfterAndTypedRecoveryIdentical(t *testing.T) {
	store := &stubStore{results: []application.QuotaResult{
		{Allowed: true, Remaining: 0, RetryAfter: 1500 * time.Millisecond},
		{Allowed: false, Remaining: 0, RetryAfter: 1500 * time.Millisecond},
	}}
	service := newTestService(t, store, domain.FailurePolicyFailClosed, nil)
	descriptor := testDescriptor()
	ownerReached := 0
	owner := http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		ownerReached++
		response.WriteHeader(http.StatusNoContent)
	})
	handler := httpadapter.AdmissionMiddleware(
		service,
		httpadapter.SubjectResolver{TrustedNetworkHeader: "X-Edge-Client-IP"},
	)(owner)
	handler = rtauth.RequireGeneratedOperationAuthorization(
		[]rtauth.OperationSecurityDescriptor{descriptor},
	)(handler)

	for attempt := 1; attempt <= 2; attempt++ {
		request := httptest.NewRequest(http.MethodGet, "/content/posts", nil)
		request.Header.Set("X-Edge-Client-IP", "203.0.113.10")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if attempt == 1 {
			if response.Code != http.StatusNoContent {
				t.Fatalf("first request status=%d body=%s", response.Code, response.Body.String())
			}
			continue
		}
		if response.Code != http.StatusTooManyRequests {
			t.Fatalf("second request status=%d body=%s", response.Code, response.Body.String())
		}
		var body rterr.ErrorResponse
		if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
			t.Fatalf("decode typed gateway error: %v", err)
		}
		if body.Code != "GATEWAY.USER.rate_limited" {
			t.Fatalf("code=%q", body.Code)
		}
		headerSeconds, err := strconv.Atoi(response.Header().Get("Retry-After"))
		if err != nil {
			t.Fatalf("Retry-After=%q: %v", response.Header().Get("Retry-After"), err)
		}
		if headerSeconds != body.Recovery.AfterSeconds ||
			body.Recovery.Action != "retry" ||
			body.Recovery.DisruptionLevel != "snackbar" {
			t.Fatalf("header=%d recovery=%+v", headerSeconds, body.Recovery)
		}
	}
	if ownerReached != 1 {
		t.Fatalf("owner reached=%d want=1", ownerReached)
	}
}

func testDescriptor() rtauth.OperationSecurityDescriptor {
	return rtauth.OperationSecurityDescriptor{
		CanonicalOperationID: "content.post.ListPosts",
		ContractGraphSHA256:  "api-edge-local-contract",
		Method:               http.MethodGet,
		PathTemplate:         "/content/posts",
		OperationKind:        "query",
		AuthMode:             "public",
		ActorRequirement:     "none",
		CommercialStatus:     "ready",
		TimeoutMilliseconds:  1000,
	}
}

func newTestService(
	t *testing.T,
	store application.AtomicQuotaStore,
	failurePolicy domain.FailurePolicy,
	observer application.Observer,
) *application.Service {
	t.Helper()
	policies := application.PolicySet{ByOperationKind: map[string]domain.Policy{}}
	for _, operationKind := range []string{"command", "query", "session"} {
		policies.ByOperationKind[operationKind] = domain.Policy{
			Limit:        1,
			Window:       time.Minute,
			StateFailure: failurePolicy,
		}
	}
	service, err := application.NewService("prod", store, policies, observer)
	if err != nil {
		t.Fatalf("new admission service: %v", err)
	}
	return service
}

type stubStore struct {
	results []application.QuotaResult
	err     error
	calls   int
	limits  []int64
	windows []time.Duration
}

func (store *stubStore) Consume(
	_ context.Context,
	_ string,
	limit int64,
	window time.Duration,
) (application.QuotaResult, error) {
	store.calls++
	store.limits = append(store.limits, limit)
	store.windows = append(store.windows, window)
	if store.err != nil {
		return application.QuotaResult{}, store.err
	}
	if len(store.results) == 0 {
		return application.QuotaResult{Allowed: true}, nil
	}
	index := store.calls - 1
	if index >= len(store.results) {
		index = len(store.results) - 1
	}
	return store.results[index], nil
}

func (*stubStore) Ping(context.Context) error { return nil }
func (*stubStore) Close() error               { return nil }

type captureObserver struct {
	outcome       string
	failurePolicy string
}

func (observer *captureObserver) RecordDecision(
	_ string,
	_ string,
	outcome string,
	failurePolicy string,
	_ time.Duration,
) {
	observer.outcome = outcome
	observer.failurePolicy = failurePolicy
}
