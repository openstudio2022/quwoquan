package server

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

const testOperatorToken = "provider-substitute-test-operator-token"

var (
	testConfigurationDigest = canonicalTestSHA256("provider-substitute:alpha-config")
	testRuntimeDigest       = canonicalTestSHA256("provider-substitute:alpha-runtime")
)

type testClock struct {
	mu  sync.Mutex
	now time.Time
}

func newTestClock() *testClock {
	return &testClock{now: time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)}
}

func (clock *testClock) Now() time.Time {
	clock.mu.Lock()
	defer clock.mu.Unlock()
	return clock.now
}

func (clock *testClock) Advance(duration time.Duration) {
	clock.mu.Lock()
	clock.now = clock.now.Add(duration)
	clock.mu.Unlock()
}

func canonicalTestSHA256(payload string) string {
	return fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(payload)))
}

func TestServerRejectsProdAndInvalidRuntimeIdentity(t *testing.T) {
	valid := Config{
		Environment:              "alpha",
		ConfigurationDigest:      testConfigurationDigest,
		RuntimeCompositionDigest: testRuntimeDigest,
		OperatorToken:            testOperatorToken,
	}
	tests := []struct {
		name   string
		mutate func(*Config)
	}{
		{name: "prod", mutate: func(cfg *Config) { cfg.Environment = "prod" }},
		{name: "short operator", mutate: func(cfg *Config) { cfg.OperatorToken = "short" }},
		{name: "missing config digest", mutate: func(cfg *Config) { cfg.ConfigurationDigest = "" }},
		{name: "non canonical config digest", mutate: func(cfg *Config) { cfg.ConfigurationDigest = "sha256:abc" }},
		{name: "missing runtime digest", mutate: func(cfg *Config) { cfg.RuntimeCompositionDigest = "" }},
		{name: "uppercase runtime digest", mutate: func(cfg *Config) { cfg.RuntimeCompositionDigest = strings.ToUpper(testRuntimeDigest) }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			cfg := valid
			test.mutate(&cfg)
			if _, err := New(cfg); err == nil {
				t.Fatal("invalid substitute configuration must fail closed")
			}
		})
	}
}

func TestProtocolRoutesHealthAndStrictOperatorAuthentication(t *testing.T) {
	server, _ := newTestServer(t)
	handler := server.Handler()

	health := perform(handler, http.MethodGet, "/healthz", nil, nil)
	if health.Code != http.StatusOK ||
		!strings.Contains(health.Body.String(), AdapterID) ||
		!strings.Contains(health.Body.String(), `"target":"alpha-local"`) ||
		!strings.Contains(health.Body.String(), testRuntimeDigest) ||
		!strings.Contains(health.Body.String(), `"idempotency_ledger"`) ||
		!strings.Contains(health.Body.String(), `"callback_channel_ordering"`) ||
		!strings.Contains(health.Body.String(), `"nonPromotable":true`) {
		t.Fatalf("health=%d %s", health.Code, health.Body.String())
	}

	model := perform(
		handler,
		http.MethodPost,
		"/v1/chat/completions",
		strings.NewReader(`{"messages":[{"role":"user","content":"hello"}]}`),
		nil,
	)
	if model.Code != http.StatusOK || !strings.Contains(model.Body.String(), "隔离协议替代链路") {
		t.Fatalf("model=%d %s", model.Code, model.Body.String())
	}

	location := perform(
		handler,
		http.MethodGet,
		"/map/place/v2/search?query=coffee&location=30.1,120.2",
		nil,
		nil,
	)
	if location.Code != http.StatusOK || !strings.Contains(location.Body.String(), "Nonprod Search POI") {
		t.Fatalf("location=%d %s", location.Code, location.Body.String())
	}

	authTests := []struct {
		name   string
		values []string
	}{
		{name: "missing"},
		{name: "wrong scheme", values: []string{"bearer " + testOperatorToken}},
		{name: "leading whitespace", values: []string{" Bearer " + testOperatorToken}},
		{name: "trailing whitespace", values: []string{"Bearer " + testOperatorToken + " "}},
		{name: "duplicate", values: []string{"Bearer " + testOperatorToken, "Bearer " + testOperatorToken}},
	}
	for _, test := range authTests {
		t.Run(test.name, func(t *testing.T) {
			headers := make(http.Header)
			for _, value := range test.values {
				headers.Add("Authorization", value)
			}
			response := perform(handler, http.MethodGet, "/control/readback", nil, headers)
			if response.Code != http.StatusUnauthorized {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}

	readback := performOperator(handler, http.MethodGet, "/control/readback", nil)
	if readback.Code != http.StatusOK ||
		!strings.Contains(readback.Body.String(), "assistant.model.generation/complete") ||
		strings.Contains(readback.Body.String(), testOperatorToken) {
		t.Fatalf("readback=%d %s", readback.Code, readback.Body.String())
	}
}

func TestFaultScenariosAreScopedBoundedAndRecoverable(t *testing.T) {
	tests := []struct {
		name       string
		scenario   string
		parameters FaultParameters
		status     int
		outcome    string
	}{
		{name: "validation", scenario: "validation", status: http.StatusBadRequest, outcome: "validation_rejected"},
		{name: "auth", scenario: "auth", status: http.StatusUnauthorized, outcome: "auth_rejected"},
		{name: "delay timeout", scenario: "delay_timeout", parameters: FaultParameters{DelayMillis: 25}, status: http.StatusGatewayTimeout, outcome: "timeout"},
		{name: "throttle", scenario: "throttle", parameters: FaultParameters{RetryAfterSeconds: 3}, status: http.StatusTooManyRequests, outcome: "throttled"},
		{name: "unavailable", scenario: "unavailable", status: http.StatusServiceUnavailable, outcome: "unavailable"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server, _ := newTestServer(t)
			handler := server.Handler()
			lease := acquireLease(t, handler, leasePayload(
				"assistant.weather.forecast",
				"forecast",
				test.scenario,
				test.parameters,
				"attempt:scenario-table",
				30,
				1,
			))
			faulted := perform(handler, http.MethodGet, "/weather/forecast", nil, nil)
			if faulted.Code != test.status {
				t.Fatalf("faulted=%d body=%s", faulted.Code, faulted.Body.String())
			}
			if test.scenario == "throttle" && faulted.Header().Get("Retry-After") != "3" {
				t.Fatalf("retry-after=%q", faulted.Header().Get("Retry-After"))
			}
			recovered := perform(handler, http.MethodGet, "/weather/forecast", nil, nil)
			if recovered.Code != http.StatusOK {
				t.Fatalf("recovered=%d body=%s", recovered.Code, recovered.Body.String())
			}
			state := readLease(t, handler, lease.LeaseID)
			if state.State != "exhausted" || state.CleanupReceipt == nil ||
				state.CleanupReceipt.Status != "restored" {
				t.Fatalf("lease did not restore: %+v", state)
			}
			readback := performOperator(handler, http.MethodGet, "/control/readback", nil)
			if !strings.Contains(readback.Body.String(), `"outcome":"`+test.outcome+`"`) {
				t.Fatalf("missing outcome in %s", readback.Body.String())
			}
		})
	}
}

func TestTransientFaultUsesRemainingFailuresAndMaxMatches(t *testing.T) {
	server, _ := newTestServer(t)
	handler := server.Handler()
	lease := acquireLease(t, handler, leasePayload(
		"assistant.weather.forecast",
		"forecast",
		"transient_then_success",
		FaultParameters{RemainingFailures: 2},
		"attempt:transient",
		30,
		3,
	))
	statuses := []int{
		http.StatusServiceUnavailable,
		http.StatusServiceUnavailable,
		http.StatusOK,
		http.StatusOK,
	}
	for index, expected := range statuses {
		response := perform(handler, http.MethodGet, "/weather/forecast", nil, nil)
		if response.Code != expected {
			t.Fatalf("call %d: status=%d body=%s", index+1, response.Code, response.Body.String())
		}
	}
	state := readLease(t, handler, lease.LeaseID)
	if state.State != "exhausted" || state.MatchedCount != 3 ||
		state.RemainingFailures != 0 || state.CleanupReceipt == nil {
		t.Fatalf("unexpected transient state: %+v", state)
	}
}

func TestFaultLeaseConflictCASAndExplicitRelease(t *testing.T) {
	server, _ := newTestServer(t)
	handler := server.Handler()
	payload := leasePayload(
		"assistant.public.search",
		"search",
		"unavailable",
		FaultParameters{},
		"attempt:owner-one",
		30,
		5,
	)
	lease := acquireLease(t, handler, payload)

	conflictPayload := payload
	conflictPayload["owner"] = "attempt:owner-two"
	conflict := acquireLeaseResponse(handler, conflictPayload)
	if conflict.Code != http.StatusConflict {
		t.Fatalf("scope conflict=%d %s", conflict.Code, conflict.Body.String())
	}

	otherScope := leasePayload(
		"assistant.weather.forecast",
		"forecast",
		"unavailable",
		FaultParameters{},
		"attempt:owner-two",
		30,
		5,
	)
	if response := acquireLeaseResponse(handler, otherScope); response.Code != http.StatusCreated {
		t.Fatalf("independent scope=%d %s", response.Code, response.Body.String())
	}

	stale := releaseLeaseResponse(handler, lease.LeaseID, "attempt:owner-one", lease.Version+1)
	if stale.Code != http.StatusConflict {
		t.Fatalf("stale CAS=%d %s", stale.Code, stale.Body.String())
	}
	wrongOwner := releaseLeaseResponse(handler, lease.LeaseID, "attempt:owner-two", lease.Version)
	if wrongOwner.Code != http.StatusConflict {
		t.Fatalf("wrong owner=%d %s", wrongOwner.Code, wrongOwner.Body.String())
	}
	released := releaseLeaseResponse(handler, lease.LeaseID, "attempt:owner-one", lease.Version)
	if released.Code != http.StatusOK ||
		!strings.Contains(released.Body.String(), `"state":"released"`) ||
		!strings.Contains(released.Body.String(), `"status":"restored"`) {
		t.Fatalf("release=%d %s", released.Code, released.Body.String())
	}
	secondRelease := releaseLeaseResponse(handler, lease.LeaseID, "attempt:owner-one", lease.Version)
	if secondRelease.Code != http.StatusConflict {
		t.Fatalf("second release=%d %s", secondRelease.Code, secondRelease.Body.String())
	}
	if response := acquireLeaseResponse(handler, payload); response.Code != http.StatusCreated {
		t.Fatalf("released scope must be reusable: %d %s", response.Code, response.Body.String())
	}
}

func TestFaultLeaseTTLAutomaticallyRestoresScope(t *testing.T) {
	server, clock := newTestServer(t)
	handler := server.Handler()
	lease := acquireLease(t, handler, leasePayload(
		"integration.location.lookup",
		"search",
		"unavailable",
		FaultParameters{},
		"attempt:ttl",
		1,
		5,
	))
	clock.Advance(2 * time.Second)

	recovered := perform(
		handler,
		http.MethodGet,
		"/map/place/v2/search?query=coffee&location=30.1,120.2",
		nil,
		nil,
	)
	if recovered.Code != http.StatusOK {
		t.Fatalf("expired lease must restore route: %d %s", recovered.Code, recovered.Body.String())
	}
	state := readLease(t, handler, lease.LeaseID)
	if state.State != "expired" || state.CleanupReceipt == nil ||
		state.CleanupReceipt.Reason != "expired" {
		t.Fatalf("expired lease state=%+v", state)
	}
}

func TestFaultLeaseRejectsInvalidIdentityScopeAndLegacyScenario(t *testing.T) {
	server, _ := newTestServer(t)
	handler := server.Handler()
	base := leasePayload(
		"assistant.public.search",
		"search",
		"unavailable",
		FaultParameters{},
		"attempt:validation",
		30,
		2,
	)
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{name: "environment", mutate: func(value map[string]any) { value["environment"] = "beta" }},
		{name: "target", mutate: func(value map[string]any) { value["target"] = "beta-local" }},
		{name: "configuration", mutate: func(value map[string]any) { value["configurationDigest"] = canonicalTestSHA256("other") }},
		{name: "runtime", mutate: func(value map[string]any) { value["runtimeCompositionDigest"] = canonicalTestSHA256("other") }},
		{name: "capability", mutate: func(value map[string]any) { value["capabilityId"] = "assistant.unknown" }},
		{name: "operation", mutate: func(value map[string]any) { value["operation"] = "quote" }},
		{name: "legacy timeout", mutate: func(value map[string]any) { value["scenario"] = "timeout" }},
		{name: "success without fault", mutate: func(value map[string]any) { value["scenario"] = "success" }},
		{name: "unsafe owner", mutate: func(value map[string]any) { value["owner"] = "operator@example.com" }},
		{name: "missing parameters", mutate: func(value map[string]any) { delete(value, "parameters") }},
		{name: "zero ttl", mutate: func(value map[string]any) { value["ttlSeconds"] = 0 }},
		{name: "zero matches", mutate: func(value map[string]any) { value["maxMatches"] = 0 }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			payload := cloneMap(base)
			test.mutate(payload)
			response := acquireLeaseResponse(handler, payload)
			if response.Code != http.StatusBadRequest {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}

	unknownField := cloneMap(base)
	unknownField["token"] = "must-not-be-accepted"
	if response := acquireLeaseResponse(handler, unknownField); response.Code != http.StatusBadRequest {
		t.Fatalf("unknown field=%d %s", response.Code, response.Body.String())
	}
	legacy := performOperator(
		handler,
		http.MethodPut,
		"/control/scenario",
		strings.NewReader(`{"scenario":"throttle"}`),
	)
	if legacy.Code != http.StatusNotFound {
		t.Fatalf("legacy global scenario endpoint must be retired: %d %s", legacy.Code, legacy.Body.String())
	}
}

func TestInvocationLedgerContainsOnlyDigestsAndCleanupReceipt(t *testing.T) {
	server, _ := newTestServer(t)
	handler := server.Handler()
	lease := acquireLease(t, handler, leasePayload(
		"identity.carrier.one_tap",
		"resolvePhone",
		"unavailable",
		FaultParameters{},
		"attempt:ledger",
		30,
		3,
	))
	requestSecret := "secret-carrier-token-13800138000"
	traceSecret := "00-secret-trace-value-01"
	headers := http.Header{
		"Content-Type": []string{"application/json"},
		"X-Request-Id": []string{"request-user@example.com"},
		"Traceparent":  []string{traceSecret},
	}
	faulted := perform(
		handler,
		http.MethodPost,
		"/carrier/resolve?phone=13800138000",
		strings.NewReader(`{"token":"`+requestSecret+`"}`),
		headers,
	)
	if faulted.Code != http.StatusServiceUnavailable {
		t.Fatalf("faulted=%d %s", faulted.Code, faulted.Body.String())
	}
	current := readLease(t, handler, lease.LeaseID)
	released := releaseLeaseResponse(handler, lease.LeaseID, "attempt:ledger", current.Version)
	if released.Code != http.StatusOK {
		t.Fatalf("cleanup=%d %s", released.Code, released.Body.String())
	}

	readback := performOperator(handler, http.MethodGet, "/control/readback", nil)
	body := readback.Body.String()
	for _, forbidden := range []string{
		requestSecret,
		traceSecret,
		"13800138000",
		"user@example.com",
		testOperatorToken,
	} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("readback leaked %q: %s", forbidden, body)
		}
	}
	var payload struct {
		Invocations []InvocationLedgerEntry `json:"invocations"`
		FaultLeases []FaultLease            `json:"faultLeases"`
	}
	if err := json.Unmarshal(readback.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if len(payload.Invocations) != 1 {
		t.Fatalf("invocations=%+v", payload.Invocations)
	}
	entry := payload.Invocations[0]
	if entry.LeaseID != lease.LeaseID ||
		entry.CapabilityID != "identity.carrier.one_tap" ||
		entry.Operation != "resolvePhone" ||
		entry.CallOrdinal != 1 ||
		!isSHA256Digest(entry.RequestDigest) ||
		!isSHA256Digest(entry.TraceDigest) ||
		entry.Outcome != "unavailable" {
		t.Fatalf("ledger entry=%+v", entry)
	}
	if len(payload.FaultLeases) != 1 || payload.FaultLeases[0].CleanupReceipt == nil ||
		payload.FaultLeases[0].CleanupReceipt.Status != "restored" {
		t.Fatalf("cleanup receipt=%+v", payload.FaultLeases)
	}
}

func newTestServer(t *testing.T) (*Server, *testClock) {
	t.Helper()
	clock := newTestClock()
	server, err := newServer(Config{
		Environment:              "alpha",
		ConfigurationDigest:      testConfigurationDigest,
		RuntimeCompositionDigest: testRuntimeDigest,
		OperatorToken:            testOperatorToken,
	}, clock.Now, clock.Advance)
	if err != nil {
		t.Fatal(err)
	}
	return server, clock
}

func leasePayload(
	capabilityID string,
	operation string,
	scenario string,
	parameters FaultParameters,
	owner string,
	ttlSeconds int,
	maxMatches uint64,
) map[string]any {
	return map[string]any{
		"environment":              "alpha",
		"target":                   "alpha-local",
		"configurationDigest":      testConfigurationDigest,
		"runtimeCompositionDigest": testRuntimeDigest,
		"capabilityId":             capabilityID,
		"operation":                operation,
		"scenario":                 scenario,
		"parameters":               parameters,
		"owner":                    owner,
		"ttlSeconds":               ttlSeconds,
		"maxMatches":               maxMatches,
	}
}

func cloneMap(source map[string]any) map[string]any {
	cloned := make(map[string]any, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}

func acquireLease(t *testing.T, handler http.Handler, payload map[string]any) FaultLease {
	t.Helper()
	response := acquireLeaseResponse(handler, payload)
	if response.Code != http.StatusCreated {
		t.Fatalf("acquire=%d %s", response.Code, response.Body.String())
	}
	var lease FaultLease
	if err := json.Unmarshal(response.Body.Bytes(), &lease); err != nil {
		t.Fatal(err)
	}
	if !faultLeaseIDPattern.MatchString(lease.LeaseID) || lease.Version != 1 ||
		lease.State != "active" {
		t.Fatalf("invalid acquired lease: %+v", lease)
	}
	return lease
}

func acquireLeaseResponse(handler http.Handler, payload map[string]any) *httptest.ResponseRecorder {
	encoded, err := json.Marshal(payload)
	if err != nil {
		panic(err)
	}
	return performOperator(
		handler,
		http.MethodPost,
		"/control/fault-leases",
		bytes.NewReader(encoded),
	)
}

func readLease(t *testing.T, handler http.Handler, leaseID string) FaultLease {
	t.Helper()
	response := performOperator(
		handler,
		http.MethodGet,
		"/control/fault-leases/"+leaseID,
		nil,
	)
	if response.Code != http.StatusOK {
		t.Fatalf("read lease=%d %s", response.Code, response.Body.String())
	}
	var lease FaultLease
	if err := json.Unmarshal(response.Body.Bytes(), &lease); err != nil {
		t.Fatal(err)
	}
	return lease
}

func releaseLeaseResponse(
	handler http.Handler,
	leaseID string,
	owner string,
	expectedVersion uint64,
) *httptest.ResponseRecorder {
	encoded, err := json.Marshal(map[string]any{
		"owner":           owner,
		"expectedVersion": expectedVersion,
	})
	if err != nil {
		panic(err)
	}
	return performOperator(
		handler,
		http.MethodDelete,
		"/control/fault-leases/"+leaseID,
		bytes.NewReader(encoded),
	)
}

func performOperator(
	handler http.Handler,
	method string,
	path string,
	body io.Reader,
) *httptest.ResponseRecorder {
	headers := http.Header{"Authorization": []string{"Bearer " + testOperatorToken}}
	return perform(handler, method, path, body, headers)
}

func perform(
	handler http.Handler,
	method string,
	path string,
	body io.Reader,
	headers http.Header,
) *httptest.ResponseRecorder {
	var request *http.Request
	if body == nil {
		request = httptest.NewRequest(method, path, nil)
	} else {
		request = httptest.NewRequest(method, path, body)
	}
	for key, values := range headers {
		for _, value := range values {
			request.Header.Add(key, value)
		}
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
