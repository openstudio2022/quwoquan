// spec_ref: specs/feature-tree/runtime/runtime-testinfra/performance-load-harness/spec.md#gwt-001
package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func testProfile(baseURL string, operations []operationProfile) loadProfile {
	return loadProfile{
		Schema:        profileSchema,
		BaseURL:       baseURL,
		Concurrency:   2,
		RequestsPerOp: 20,
		TimeoutMs:     2000,
		Operations:    operations,
	}
}

func TestRunProfilePassesWithinDeclaredSLO(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer server.Close()

	profile := testProfile(server.URL, []operationProfile{{
		OperationID:            "chat-service/chat/conversation#ListConversations",
		Method:                 http.MethodGet,
		Path:                   "/chat/conversations",
		SLOLatencyP95Ms:        1500,
		SLOAvailabilityPercent: 99.0,
	}})
	report, err := runProfile(profile, server.Client())
	if err != nil {
		t.Fatalf("runProfile: %v", err)
	}
	if report.Verdict != verdictPass {
		t.Fatalf("expected pass verdict, got %s (%+v)", report.Verdict, report.Operations)
	}
	result := report.Operations[0]
	if result.Samples != 20 || result.Failures != 0 {
		t.Fatalf("expected 20 clean samples, got %+v", result)
	}
	if result.P95Ms <= 0 || result.P95Ms > 1500 {
		t.Fatalf("p95 out of expected range: %+v", result)
	}
}

func TestRunProfileFailsWhenLatencyBudgetExceeded(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(30 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	profile := testProfile(server.URL, []operationProfile{{
		OperationID:            "content-service/content/post#ListFeed",
		Method:                 http.MethodGet,
		Path:                   "/content/feed",
		SLOLatencyP95Ms:        5,
		SLOAvailabilityPercent: 99.0,
	}})
	report, err := runProfile(profile, server.Client())
	if err != nil {
		t.Fatalf("runProfile: %v", err)
	}
	if report.Verdict != verdictFail {
		t.Fatalf("expected fail verdict, got %s", report.Verdict)
	}
	reasons := strings.Join(report.Operations[0].FailureReasons, "; ")
	if !strings.Contains(reasons, "latency_p95_ms") {
		t.Fatalf("expected latency failure reason, got %q", reasons)
	}
}

func TestRunProfileFailsWhenAvailabilityBelowSLO(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	profile := testProfile(server.URL, []operationProfile{{
		OperationID:            "user-service/user/account_session#GetSession",
		Method:                 http.MethodGet,
		Path:                   "/user/session",
		SLOLatencyP95Ms:        1500,
		SLOAvailabilityPercent: 99.9,
	}})
	report, err := runProfile(profile, server.Client())
	if err != nil {
		t.Fatalf("runProfile: %v", err)
	}
	result := report.Operations[0]
	if result.Verdict != verdictFail || result.Failures != result.Samples {
		t.Fatalf("expected availability failure, got %+v", result)
	}
	if result.AvailabilityPercent != 0 {
		t.Fatalf("expected 0%% availability, got %v", result.AvailabilityPercent)
	}
}

func TestRunProfileReportsNoSLOWithoutFabricatingVerdict(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	profile := testProfile(server.URL, []operationProfile{{
		OperationID: "tag-service/tag/tag_tree#GetTree",
		Method:      http.MethodGet,
		Path:        "/tags/tree",
	}})
	report, err := runProfile(profile, server.Client())
	if err != nil {
		t.Fatalf("runProfile: %v", err)
	}
	if report.Verdict != verdictNoSLO || report.Operations[0].Verdict != verdictNoSLO {
		t.Fatalf("expected no_slo verdict, got %+v", report)
	}
}

func TestValidateProfileRejectsMutationsByDefault(t *testing.T) {
	profile := testProfile("http://127.0.0.1:1", []operationProfile{{
		OperationID: "chat-service/chat/message#SendMessage",
		Method:      http.MethodPost,
		Path:        "/chat/messages",
	}})
	if err := validateProfile(profile); err == nil {
		t.Fatal("expected mutation rejection for POST without allowMutations")
	}
	profile.AllowMutations = true
	if err := validateProfile(profile); err != nil {
		t.Fatalf("allowMutations profile should validate: %v", err)
	}
}

func TestValidateProfileRejectsWrongSchema(t *testing.T) {
	profile := testProfile("http://127.0.0.1:1", []operationProfile{{
		OperationID: "x", Method: http.MethodGet, Path: "/x",
	}})
	profile.Schema = "other"
	if err := validateProfile(profile); err == nil {
		t.Fatal("expected schema rejection")
	}
}
