// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-001
package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	httpadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/http"

	"gopkg.in/yaml.v3"
)

type connectionOperationContract struct {
	Operation       string `yaml:"operation"`
	RequestBindings struct {
		Query []struct {
			Name     string `yaml:"name"`
			Field    string `yaml:"field"`
			Required *bool  `yaml:"required"`
		} `yaml:"query"`
	} `yaml:"request_bindings"`
	Authorization struct {
		Principal       string `yaml:"principal"`
		OwnershipPolicy string `yaml:"ownership_policy"`
	} `yaml:"authorization"`
	Reliability struct {
		TimeoutMilliseconds int    `yaml:"timeout_ms"`
		RetryMode           string `yaml:"retry_mode"`
		MaxAttempts         int    `yaml:"max_attempts"`
	} `yaml:"reliability"`
	ErrorCodes []string `yaml:"error_codes"`
	Privacy    struct {
		RequestClassification  string `yaml:"request_classification"`
		ResponseClassification string `yaml:"response_classification"`
	} `yaml:"privacy"`
	Telemetry struct {
		Metric string `yaml:"metric"`
		Trace  bool   `yaml:"trace"`
	} `yaml:"telemetry"`
	Security struct {
		AuthMode        string `yaml:"auth_mode"`
		Principal       string `yaml:"principal"`
		TokenTransport  string `yaml:"token_transport"`
		AnonymousPolicy string `yaml:"anonymous_policy"`
		Visibility      string `yaml:"visibility"`
	} `yaml:"security"`
}

func TestConnectionOperationPoliciesAreSingleTrack(t *testing.T) {
	serviceRoot := realtimeGatewayServiceRoot(t)
	data, err := os.ReadFile(filepath.Join(
		serviceRoot,
		"contracts",
		"realtime",
		"connection",
		"operations.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		APIRoutes []connectionOperationContract `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	operations := make(map[string]connectionOperationContract, len(document.APIRoutes))
	for _, operation := range document.APIRoutes {
		if _, exists := operations[operation.Operation]; exists {
			t.Fatalf("duplicate operation %q", operation.Operation)
		}
		operations[operation.Operation] = operation
	}

	issueTicket := requireConnectionOperation(t, operations, "IssueConnectionTicket")
	assertNoAutomaticRetry(t, issueTicket)

	webSocket := requireConnectionOperation(t, operations, "WebSocketUpgrade")
	assertNoAutomaticRetry(t, webSocket)
	if webSocket.Security.TokenTransport != "query_ticket" ||
		webSocket.Security.AuthMode != "required" ||
		webSocket.Security.AnonymousPolicy != "deny" ||
		webSocket.Authorization.OwnershipPolicy != "ticket_self" ||
		len(webSocket.RequestBindings.Query) != 1 ||
		webSocket.RequestBindings.Query[0].Name != "ticket" ||
		webSocket.RequestBindings.Query[0].Field != "ticket" ||
		webSocket.RequestBindings.Query[0].Required == nil ||
		!*webSocket.RequestBindings.Query[0].Required {
		t.Fatalf("WebSocket ticket policy drifted: %+v", webSocket)
	}

	longPoll := requireConnectionOperation(t, operations, "LongPoll")
	if longPoll.Security.AuthMode != "required" ||
		longPoll.Security.Principal != "account" ||
		longPoll.Security.TokenTransport != "bearer" ||
		longPoll.Security.AnonymousPolicy != "deny" ||
		longPoll.Authorization.OwnershipPolicy != "connection_self" ||
		longPoll.Reliability.TimeoutMilliseconds != 30000 {
		t.Fatalf("LongPoll bearer/self/timeout policy drifted: %+v", longPoll)
	}

	config := requireConnectionOperation(t, operations, "GetRealtimeConfig")
	if config.Security.AuthMode != "public" ||
		config.Security.Visibility != "public" ||
		config.Authorization.Principal != "public" {
		t.Fatalf("GetRealtimeConfig must remain public: %+v", config)
	}

	for _, name := range []string{"HealthCheck", "ReadinessCheck", "Metrics"} {
		probe := requireConnectionOperation(t, operations, name)
		if probe.Security.Visibility != "internal" ||
			probe.Security.AuthMode != "public" ||
			probe.Security.AnonymousPolicy != "allow" ||
			probe.Authorization.OwnershipPolicy != "internal_probe" ||
			probe.Privacy.RequestClassification != "INTERNAL" ||
			probe.Privacy.ResponseClassification != "INTERNAL" ||
			probe.Reliability.RetryMode != "none" ||
			probe.Reliability.MaxAttempts != 1 ||
			len(probe.ErrorCodes) == 0 ||
			probe.Telemetry.Metric == "" ||
			!probe.Telemetry.Trace {
			t.Fatalf("%s internal probe policy drifted: %+v", name, probe)
		}
	}
	readiness := requireConnectionOperation(t, operations, "ReadinessCheck")
	if len(readiness.ErrorCodes) != 1 ||
		readiness.ErrorCodes[0] != "REALTIME.SYSTEM.readiness_unavailable" {
		t.Fatalf("readiness errors=%v", readiness.ErrorCodes)
	}
}

func TestReadinessUnavailableUsesCanonicalTypedError(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	request.Header.Set("X-Request-Id", "realtime-readiness-contract")
	response := httptest.NewRecorder()

	httpadapter.WriteReadinessUnavailable(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var body rterr.ErrorResponse
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Code != "REALTIME.SYSTEM.readiness_unavailable" ||
		body.RequestID != "realtime-readiness-contract" ||
		body.Recovery.Action != "retry" ||
		body.Recovery.AfterSeconds != 1 {
		t.Fatalf("typed readiness response=%+v", body)
	}
}

func assertNoAutomaticRetry(
	t *testing.T,
	operation connectionOperationContract,
) {
	t.Helper()
	if operation.Reliability.RetryMode != "none" ||
		operation.Reliability.MaxAttempts != 1 {
		t.Fatalf(
			"%s must be a single attempt, got retry=%q maxAttempts=%d",
			operation.Operation,
			operation.Reliability.RetryMode,
			operation.Reliability.MaxAttempts,
		)
	}
}

func requireConnectionOperation(
	t *testing.T,
	operations map[string]connectionOperationContract,
	name string,
) connectionOperationContract {
	t.Helper()
	operation, ok := operations[name]
	if !ok {
		t.Fatalf("operation %q missing", name)
	}
	return operation
}

func realtimeGatewayServiceRoot(t *testing.T) string {
	t.Helper()
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
}
