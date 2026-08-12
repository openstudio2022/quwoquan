package local_contract

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	admissionapp "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	admissiondomain "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
	rollouthttp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/adapters/inbound/http"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	graphread "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
	graphapp "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	graphdomain "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	ownerinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
	registryinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/registry"
)

func TestRuntimeExecutesSignedGetPostAfterSharedAdmission(t *testing.T) {
	quota := &graphQLQuotaStore{}
	admission, err := admissionapp.NewService("beta", quota, graphQLAdmissionPolicies(), nil)
	if err != nil {
		t.Fatal(err)
	}
	rollout, err := rolloutapp.NewEvaluator(rolloutdomain.Policy{}, nil, nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	ownerCalls := 0
	owner := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		ownerCalls++
		if quota.calls != 1 {
			t.Errorf("owner reached before shared admission; calls=%d", quota.calls)
		}
		if request.Method != http.MethodPost || request.URL.Path != "/internal/graphql" ||
			request.Header.Get("X-Contract-Graph-SHA256") == "" ||
			request.Header.Get("Authorization") != "Bearer graphql-local-contract" {
			t.Errorf("owner request method/path/header drifted: %s %s", request.Method, request.URL.Path)
		}
		response.Header().Set("Content-Type", "application/json")
		response.Header().Set("X-Contract-Graph-SHA256", operationsecurity.ContractGraphSHA256)
		payload := baseOwnerPost("post-1", "signed query")
		payload["body"] = "body"
		payload["summary"] = "summary"
		payload["authorId"] = "persona-1"
		payload["authorDisplayName"] = "Author"
		payload["coverUrl"] = "https://media.invalid/cover.jpg"
		_ = json.NewEncoder(response).Encode(map[string]any{
			"data": map[string]any{"contentPostDetailBase": payload},
		})
	}))
	defer owner.Close()

	entry := validGraphQLRuntimeEntry()
	registryPath, publicKeys := writeSignedGraphQLRegistry(t, entry)
	config := graphread.Config{
		Enabled:               true,
		RegistryFile:          registryPath,
		CandidateDigest:       "sha256:" + strings.Repeat("1", 64),
		SchemaDigest:          "sha256:" + strings.Repeat("2", 64),
		TrustedPublicKeysJSON: publicKeys,
		OwnerTimeoutMS:        1000,
	}
	minimum, err := rollouthttp.MinimumBuildMiddleware(
		rolloutapp.MinimumBuildPolicy{
			SourceDigest: "sha256:" + strings.Repeat("3", 64),
			Mode:         "enforce",
			Platforms:    map[string]uint64{"android": 1, "ios": 1, "web": 1},
		},
		map[string]struct{}{},
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	resolver := &graphQLNetworkAttributeResolver{}
	observer := &graphQLRolloutObserver{}
	registryLoader := newGraphQLRegistryLoader(t, publicKeys)
	ownerOrigin, err := url.Parse(owner.URL)
	if err != nil {
		t.Fatal(err)
	}
	ownerExecutor, err := ownerinfra.NewContentPostQueryExecutor(
		ownerOrigin,
		nil,
		&http.Client{Timeout: time.Second},
		operationsecurity.ContractGraphSHA256,
		graphQLServiceCredential{},
	)
	if err != nil {
		t.Fatal(err)
	}
	runtime, err := graphread.NewRuntime(context.Background(), graphread.Options{
		Environment:     "beta",
		Config:          config,
		RegistryLoader:  registryLoader,
		OwnerExecutor:   ownerExecutor,
		Admission:       admission,
		Rollout:         rollout,
		RolloutObserver: observer,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := runtime.Ready(context.Background()); err != nil {
		t.Fatalf("signed runtime readiness: %v", err)
	}
	handler := graphread.RequestMetadataMiddleware(
		"X-Edge-Client-IP",
		resolver,
		runtime.Handler(),
	)
	handler = rollouthttp.MinimumBuildForAuthenticatedClients(minimum, handler)
	handler = rtauth.Middleware(rtauth.MiddlewareConfig{})(handler)

	payload := map[string]any{
		"operationName": "ContentPostDetailBase",
		"variables":     map[string]any{"postId": "post-1"},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": entry.SHA256Hash},
		},
	}
	response := executeGraphQLRuntimeRequest(t, handler, payload)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if quota.calls != 1 || ownerCalls != 1 {
		t.Fatalf("admission=%d owner=%d", quota.calls, ownerCalls)
	}
	if resolver.calls != 1 {
		t.Fatalf("trusted network resolver calls=%d, want 1", resolver.calls)
	}
	if len(observer.observations) != 1 ||
		observer.observations[0].Region != "guangdong" ||
		observer.observations[0].Carrier != "telecom" {
		t.Fatalf("rollout observation=%+v", observer.observations)
	}
	if strings.Contains(response.Body.String(), "embedding") ||
		strings.Contains(response.Body.String(), "moderationStatus") {
		t.Fatalf("owner-only fields leaked: %s", response.Body.String())
	}

	queryText := payload
	queryText["query"] = "mutation DeletePost { deletePost }"
	rejected := executeGraphQLRuntimeRequest(t, handler, queryText)
	if rejected.Code != http.StatusBadRequest || quota.calls != 1 || ownerCalls != 1 {
		t.Fatalf(
			"query text status=%d admission=%d owner=%d",
			rejected.Code,
			quota.calls,
			ownerCalls,
		)
	}
}

func TestRuntimeAuthorizesGatewayOwnedPersistedSearchOperation(t *testing.T) {
	quota := &graphQLQuotaStore{}
	admission, err := admissionapp.NewService("beta", quota, graphQLAdmissionPolicies(), nil)
	if err != nil {
		t.Fatal(err)
	}
	rollout, err := rolloutapp.NewEvaluator(rolloutdomain.Policy{}, nil, nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	entry := validSearchPageRuntimeEntry()
	registryPath, publicKeys := writeSignedGraphQLRegistry(t, entry)
	runtime, err := graphread.NewRuntime(context.Background(), graphread.Options{
		Environment: "beta",
		Config: graphread.Config{
			Enabled:               true,
			RegistryFile:          registryPath,
			CandidateDigest:       "sha256:" + strings.Repeat("1", 64),
			SchemaDigest:          "sha256:" + strings.Repeat("2", 64),
			TrustedPublicKeysJSON: publicKeys,
			OwnerTimeoutMS:        1000,
		},
		RegistryLoader:  newGraphQLRegistryLoader(t, publicKeys),
		OwnerExecutor:   graphQLExecutorStub{},
		Admission:       admission,
		Rollout:         rollout,
		RolloutObserver: &graphQLRolloutObserver{},
	})
	if err != nil {
		t.Fatalf("gateway-owned persisted query runtime: %v", err)
	}
	if err := runtime.Ready(context.Background()); err != nil {
		t.Fatalf("gateway-owned persisted query readiness: %v", err)
	}
}

func newGraphQLRegistryLoader(
	t *testing.T,
	publicKeysJSON string,
) *registryinfra.SignedFileLoader {
	t.Helper()
	publicKeys := map[string]string{}
	if err := json.Unmarshal([]byte(publicKeysJSON), &publicKeys); err != nil {
		t.Fatal(err)
	}
	verifier, err := registryinfra.NewEd25519SignatureVerifier(publicKeys)
	if err != nil {
		t.Fatal(err)
	}
	loader, err := registryinfra.NewSignedFileLoader(verifier)
	if err != nil {
		t.Fatal(err)
	}
	return loader
}

func TestConfigFailsClosedOnDisabledInputsAndDigestDrift(t *testing.T) {
	disabled := graphread.Config{RegistryFile: "registry.json"}
	if err := graphread.ValidateAndResolveConfig(
		&disabled,
		"/release/config.yaml",
		false,
		"",
	); err == nil {
		t.Fatal("disabled GraphQL accepted release inputs")
	}

	directory := t.TempDir()
	schema := []byte("schema { query: Query }\ntype Query { ping: String }\n")
	schemaPath := filepath.Join(directory, "schema.graphqls")
	registryPath := filepath.Join(directory, "registry.json")
	if err := os.WriteFile(schemaPath, schema, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(registryPath, []byte("{}"), 0o600); err != nil {
		t.Fatal(err)
	}
	config := graphread.Config{
		Enabled:               true,
		RegistryFile:          registryPath,
		SchemaFile:            schemaPath,
		SchemaDigest:          fmt.Sprintf("sha256:%x", sha256.Sum256(schema)),
		CandidateDigest:       "sha256:" + strings.Repeat("1", 64),
		TrustedPublicKeysJSON: `{"release-key":"value"}`,
		OwnerTimeoutMS:        1000,
	}
	if err := graphread.ValidateAndResolveConfig(
		&config,
		filepath.Join(directory, "config.yaml"),
		false,
		"",
	); err != nil {
		t.Fatalf("valid GraphQL config: %v", err)
	}
	config.SchemaDigest = "sha256:" + strings.Repeat("0", 64)
	if err := graphread.ValidateAndResolveConfig(
		&config,
		filepath.Join(directory, "config.yaml"),
		false,
		"",
	); err == nil || !strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("schema drift was not rejected: %v", err)
	}
}

func TestRuntimeFailsClosedWhenCompositionPortsAreMissing(t *testing.T) {
	config := graphread.Config{Enabled: true}
	_, err := graphread.NewRuntime(context.Background(), graphread.Options{
		Environment: "beta",
		Config:      config,
	})
	if err == nil || !strings.Contains(err.Error(), "signed registry loader is required") {
		t.Fatalf("missing registry loader was not rejected: %v", err)
	}

	_, publicKeys := writeSignedGraphQLRegistry(t, validGraphQLRuntimeEntry())
	_, err = graphread.NewRuntime(context.Background(), graphread.Options{
		Environment:    "beta",
		Config:         config,
		RegistryLoader: newGraphQLRegistryLoader(t, publicKeys),
	})
	if err == nil || !strings.Contains(err.Error(), "owner executor is required") {
		t.Fatalf("missing owner executor was not rejected: %v", err)
	}

	unsignedRegistry, err := graphdomain.NewRegistry([]graphdomain.Entry{
		validGraphQLRuntimeEntry(),
	})
	if err != nil {
		t.Fatal(err)
	}
	_, err = graphread.NewRuntime(context.Background(), graphread.Options{
		Environment:    "beta",
		Config:         config,
		RegistryLoader: graphQLRegistryLoaderStub{registry: unsignedRegistry},
		OwnerExecutor:  graphQLExecutorStub{},
	})
	if err == nil || !strings.Contains(err.Error(), "unverified release") {
		t.Fatalf("unsigned registry port result was not rejected: %v", err)
	}
}

type graphQLQuotaStore struct{ calls int }

type graphQLNetworkAttributeResolver struct{ calls int }

type graphQLRolloutObserver struct {
	observations []rolloutapp.DecisionObservation
}

type graphQLRegistryLoaderStub struct {
	registry *graphdomain.Registry
}

type graphQLExecutorStub struct{}

type graphQLServiceCredential struct{}

func (graphQLServiceCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer graphql-local-contract", nil
}

func (loader graphQLRegistryLoaderStub) Load(
	context.Context,
	string,
	string,
	string,
) (*graphdomain.Registry, error) {
	return loader.registry, nil
}

func (graphQLExecutorStub) Execute(
	context.Context,
	graphdomain.Entry,
	map[string]any,
) (graphapp.ExecutionResult, error) {
	data := json.RawMessage(`{"contentPost":{"postId":"post-1"}}`)
	return graphapp.ExecutionResult{
		Data: data,
		Usage: graphapp.ExecutionUsage{
			OwnerCalls: 1, BatchKeys: 1, ResponseBytes: len(data),
		},
	}, nil
}

func (resolver *graphQLNetworkAttributeResolver) Resolve(net.IP) rolloutapp.NetworkAttributes {
	resolver.calls++
	return rolloutapp.NetworkAttributes{Region: "guangdong", Carrier: "telecom"}
}

func (observer *graphQLRolloutObserver) ObserveDecision(value rolloutapp.DecisionObservation) {
	observer.observations = append(observer.observations, value)
}

func (store *graphQLQuotaStore) Consume(
	context.Context,
	string,
	int64,
	time.Duration,
) (admissionapp.QuotaResult, error) {
	store.calls++
	return admissionapp.QuotaResult{Allowed: true, Remaining: 99, RetryAfter: time.Second}, nil
}

func (*graphQLQuotaStore) Ping(context.Context) error { return nil }
func (*graphQLQuotaStore) Close() error               { return nil }

func graphQLAdmissionPolicies() admissionapp.PolicySet {
	policy := admissiondomain.Policy{
		Limit: 100, Window: time.Minute, StateFailure: admissiondomain.FailurePolicyFailClosed,
	}
	return admissionapp.PolicySet{ByOperationKind: map[string]admissiondomain.Policy{
		"command": policy, "query": policy, "session": policy,
	}}
}

func validGraphQLRuntimeEntry() graphdomain.Entry {
	plan := graphdomain.CostPlan{
		BaseComplexity: 56, ListMultipliers: []graphdomain.ListMultiplier{},
		MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 64 * 1024,
	}
	digest, err := plan.Digest()
	if err != nil {
		panic(err)
	}
	return graphdomain.Entry{
		SHA256Hash:           "3c1481366f84401aa2d89280925d5943bf040f7c94cf757fb5cc219f00a7f71b",
		OperationName:        "ContentPostDetailBase",
		OperationType:        graphdomain.OperationTypeQuery,
		CanonicalOperationID: "content.post.GetPost",
		ObjectIDs:            []string{"content.post"},
		Authorization: graphdomain.AuthorizationBinding{
			Principal: "public", OwnershipPolicy: "visibility_filtered",
		},
		CostModelVersion: graphdomain.CostModelVersionV1,
		CostPlanDigest:   digest,
		Cost: graphdomain.CostBudget{
			Depth: 3, TopLevelFields: 1, Complexity: 56,
			VariablesMaxBytes: 1024, PageSizeMax: 1,
			MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 64 * 1024,
			SLORef: "slo:gateway_graphql_read_detail",
		},
		CostPlan:    plan,
		ExecutorKey: "content.post.getPost",
	}
}

func validSearchPageRuntimeEntry() graphdomain.Entry {
	entry := validGraphQLRuntimeEntry()
	entry.SHA256Hash = "894a7b1541100c4ffa20e446d7969aa6bb1c6aa385d025cc2a8c7b625ba50d58"
	entry.OperationName = "SearchPage"
	entry.CanonicalOperationID = "gateway.persisted_query_execution.SearchPage"
	entry.ObjectIDs = []string{"gateway.persisted_query_execution"}
	entry.Authorization.OwnershipPolicy = "public_search_discovery"
	entry.ExecutorKey = "search.searchIndexView.searchPage"
	return entry
}

func writeSignedGraphQLRegistry(t *testing.T, entry graphdomain.Entry) (string, string) {
	t.Helper()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(map[string]any{
		"candidateDigest": "sha256:" + strings.Repeat("1", 64),
		"schemaDigest":    "sha256:" + strings.Repeat("2", 64),
		"entries":         []graphdomain.Entry{entry},
	})
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := json.Marshal(map[string]any{
		"keyId":         "release-key",
		"payloadSha256": fmt.Sprintf("sha256:%x", sha256.Sum256(payload)),
		"payload":       base64.StdEncoding.EncodeToString(payload),
		"signature":     base64.StdEncoding.EncodeToString(ed25519.Sign(privateKey, payload)),
	})
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "registry.signed.json")
	if err := os.WriteFile(path, envelope, 0o600); err != nil {
		t.Fatal(err)
	}
	keys, _ := json.Marshal(map[string]string{
		"release-key": base64.StdEncoding.EncodeToString(publicKey),
	})
	return path, string(keys)
}

func executeGraphQLRuntimeRequest(
	t *testing.T,
	handler http.Handler,
	payload map[string]any,
) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/graphql", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-Device-Platform", "android")
	request.Header.Set("X-Client-App-Build", "1")
	request.Header.Set("X-Edge-Client-IP", "127.0.0.1")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}
