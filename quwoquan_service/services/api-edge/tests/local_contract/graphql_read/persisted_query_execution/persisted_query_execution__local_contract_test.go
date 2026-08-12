// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
// readiness_case: execute-persisted-graphql-query-local
package local_contract

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	httpadapter "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

func TestRegistryRejectsMutationAndOverBudgetEntries(t *testing.T) {
	mutation := validRegistryEntry()
	mutation.OperationType = "mutation"
	if _, err := domain.NewRegistry([]domain.Entry{mutation}); err == nil {
		t.Fatal("mutation must never enter the persisted read registry")
	}

	overBudget := validRegistryEntry()
	overBudget.Cost.Depth = domain.MaxDepth + 1
	if _, err := domain.NewRegistry([]domain.Entry{overBudget}); err == nil {
		t.Fatal("query above the canonical depth limit must fail at registry load")
	}
}

func TestRegistryCostThresholdsRequireExactExceptionsAndHardLimits(t *testing.T) {
	testCases := []struct {
		name   string
		mutate func(*domain.Entry)
		valid  bool
	}{
		{
			name: "depth four requires exception",
			mutate: func(entry *domain.Entry) {
				entry.Cost.Depth = 4
			},
		},
		{
			name: "depth five accepts exception",
			mutate: func(entry *domain.Entry) {
				entry.Cost.Depth = 5
				entry.Cost.DepthExceptionRef = "approval:graphql-depth-content-post"
			},
			valid: true,
		},
		{
			name: "depth six is a hard rejection",
			mutate: func(entry *domain.Entry) {
				entry.Cost.Depth = 6
				entry.Cost.DepthExceptionRef = "approval:graphql-depth-content-post"
			},
		},
		{
			name: "top level four requires exception",
			mutate: func(entry *domain.Entry) {
				entry.Cost.TopLevelFields = 4
			},
		},
		{
			name: "top level five accepts exception",
			mutate: func(entry *domain.Entry) {
				entry.Cost.TopLevelFields = 5
				entry.Cost.TopLevelExceptionRef = "approval:graphql-top-level-content-post"
			},
			valid: true,
		},
		{
			name: "top level six is a hard rejection",
			mutate: func(entry *domain.Entry) {
				entry.Cost.TopLevelFields = 6
				entry.Cost.TopLevelExceptionRef = "approval:graphql-top-level-content-post"
			},
		},
		{
			name: "complexity above five hundred requires exception",
			mutate: func(entry *domain.Entry) {
				setConstantCostPlan(entry, 501)
			},
		},
		{
			name: "complexity one thousand accepts exception",
			mutate: func(entry *domain.Entry) {
				setConstantCostPlan(entry, 1000)
				entry.Cost.ComplexityExceptionRef = "approval:graphql-complexity-content-post"
			},
			valid: true,
		},
		{
			name: "complexity above one thousand is a hard rejection",
			mutate: func(entry *domain.Entry) {
				setConstantCostPlan(entry, 1001)
				entry.Cost.ComplexityExceptionRef = "approval:graphql-complexity-content-post"
			},
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			entry := validRegistryEntry()
			testCase.mutate(&entry)
			_, err := domain.NewRegistry([]domain.Entry{entry})
			if testCase.valid && err != nil {
				t.Fatalf("valid exception-bound entry rejected: %v", err)
			}
			if !testCase.valid && err == nil {
				t.Fatal("entry outside the canonical cost policy must be rejected")
			}
		})
	}
}

func TestRegistryRecomputesSignedCostPlanDigestAndWorstCase(t *testing.T) {
	entry := validRegistryEntry()
	entry.CostPlanDigest = "sha256:" + strings.Repeat("f", 64)
	if _, err := domain.NewRegistry([]domain.Entry{entry}); err == nil {
		t.Fatal("registry must reject a costPlanDigest not derived from canonical JSON")
	}

	entry = validRegistryEntry()
	entry.Cost.Complexity++
	if _, err := domain.NewRegistry([]domain.Entry{entry}); err == nil {
		t.Fatal("registry must reject a worst-case complexity not derived from the plan")
	}

	entry = validRegistryEntry()
	entry.Cost.MaxOwnerCalls++
	if _, err := domain.NewRegistry([]domain.Entry{entry}); err == nil {
		t.Fatal("registry must reject execution limits that drift from the signed plan")
	}
}

func TestCostPlanDigestAndVariableEvaluationUseCanonicalModel(t *testing.T) {
	plan := domain.CostPlan{
		BaseComplexity: 100,
		ListMultipliers: []domain.ListMultiplier{
			{VariablePath: "input.itemCount", Coefficient: 4, DefaultValue: 1, MaximumValue: 25},
		},
		MaxOwnerCalls: 1, MaxBatchKeys: 25, MaxResponseBytes: 4096,
	}
	digest, err := plan.Digest()
	if err != nil {
		t.Fatal(err)
	}
	canonicalJSON := []byte(`{"baseComplexity":100,"listMultipliers":[{"variablePath":"input.itemCount","coefficient":4,"defaultValue":1,"maximumValue":25}],"maxOwnerCalls":1,"maxBatchKeys":25,"maxResponseBytes":4096}`)
	sum := sha256.Sum256(canonicalJSON)
	if digest != "sha256:"+hex.EncodeToString(sum[:]) {
		t.Fatalf("digest=%s does not bind canonical JSON", digest)
	}
	missingValueComplexity, err := plan.Evaluate(map[string]any{})
	if err != nil || missingValueComplexity != 100 {
		t.Fatalf("missing variable uses default: complexity=%d err=%v", missingValueComplexity, err)
	}
	actualComplexity, err := plan.Evaluate(map[string]any{
		"input": map[string]any{"itemCount": json.Number("10")},
	})
	if err != nil || actualComplexity != 136 {
		t.Fatalf("actual complexity=%d err=%v", actualComplexity, err)
	}
}

func TestProdRejectsUnsignedRegistryBeforeServingTraffic(t *testing.T) {
	registry, err := domain.NewRegistry([]domain.Entry{validRegistryEntry()})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := application.NewService(
		"prod", registry, &contractAuthorizer{}, &contractExecutor{}, nil,
	); err == nil {
		t.Fatal("prod must reject a registry not loaded through signature verification")
	}
}

func TestSignedRegistryBindsCandidateSchemaAndExactPayload(t *testing.T) {
	candidateDigest := "sha256:" + strings.Repeat("1", 64)
	schemaDigest := "sha256:" + strings.Repeat("2", 64)
	payload, err := json.Marshal(map[string]any{
		"candidateDigest": candidateDigest,
		"schemaDigest":    schemaDigest,
		"entries":         []domain.Entry{validRegistryEntry()},
	})
	if err != nil {
		t.Fatal(err)
	}
	secret := []byte("local-contract-signature-key")
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write(payload)
	signature := mac.Sum(nil)
	payloadSum := sha256.Sum256(payload)
	envelope, err := json.Marshal(map[string]any{
		"keyId":         "release-signing-2026",
		"payloadSha256": "sha256:" + hex.EncodeToString(payloadSum[:]),
		"payload":       base64.StdEncoding.EncodeToString(payload),
		"signature":     base64.StdEncoding.EncodeToString(signature),
	})
	if err != nil {
		t.Fatal(err)
	}
	registry, err := domain.LoadSignedRegistry(
		context.Background(), strings.NewReader(string(envelope)),
		candidateDigest, schemaDigest, hmacContractVerifier{secret: secret},
	)
	if err != nil {
		t.Fatalf("load signed registry: %v", err)
	}
	if !registry.IsSignedRelease() || registry.Source().CandidateDigest != candidateDigest {
		t.Fatalf("signed source=%+v", registry.Source())
	}
	if _, err := application.NewService(
		"prod", registry, &contractAuthorizer{}, &contractExecutor{}, nil,
	); err != nil {
		t.Fatalf("verified registry must be accepted in prod composition: %v", err)
	}
}

func TestKnownPersistedQueryExecutesExactRegistryBinding(t *testing.T) {
	authorizer := &contractAuthorizer{}
	executor := &contractExecutor{data: json.RawMessage(`{"contentPostDetail":{"postId":"post-1"}}`)}
	handler := newContractHandler(t, authorizer, executor)

	response := serveGraphQL(t, handler, map[string]any{
		"operationName": "ContentPostDetail",
		"variables": map[string]any{
			"postId": "post-1",
		},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{
				"version": 1, "sha256Hash": validRegistryEntry().SHA256Hash,
			},
		},
	})
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if authorizer.calls != 1 || executor.calls != 1 {
		t.Fatalf("authorizer=%d executor=%d", authorizer.calls, executor.calls)
	}
	if authorizer.entry.CanonicalOperationID != "content.post.GetPost" ||
		fmt.Sprint(authorizer.entry.ObjectIDs) != "[content.post]" ||
		authorizer.entry.Authorization.OwnershipPolicy != "visibility_filtered" {
		t.Fatalf("registry binding drifted: %+v", authorizer.entry)
	}
	if executor.variables["postId"] != "post-1" {
		t.Fatalf("executor variables=%v", executor.variables)
	}
	var body struct {
		Data map[string]any `json:"data"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if _, ok := body.Data["contentPostDetail"]; !ok {
		t.Fatalf("GraphQL data=%v", body.Data)
	}
}

func TestQueryTextMutationAndAPQMissNeverRegisterOnline(t *testing.T) {
	executor := &contractExecutor{data: json.RawMessage(`{"unexpected":true}`)}
	handler := newContractHandler(t, &contractAuthorizer{}, executor)
	unknownHash := strings.Repeat("0", 64)

	withQueryText := serveGraphQL(t, handler, map[string]any{
		"query": "mutation ChangeState { changeState }",
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": unknownHash},
		},
	})
	assertRuntimeError(t, withQueryText, http.StatusBadRequest, "GATEWAY.USER.graphql_request_invalid")

	miss := serveGraphQL(t, handler, map[string]any{
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": unknownHash},
		},
	})
	assertRuntimeError(t, miss, http.StatusBadRequest, "GATEWAY.USER.persisted_query_unknown")
	if executor.calls != 0 {
		t.Fatalf("unknown/mutation requests reached executor %d times", executor.calls)
	}
}

func TestVariablesAndPaginationLimitsFailBeforeAuthorizationAndExecution(t *testing.T) {
	for _, testCase := range []struct {
		name      string
		variables map[string]any
	}{
		{name: "registered variable byte budget", variables: map[string]any{"postId": strings.Repeat("x", 2048)}},
		{name: "global page maximum", variables: map[string]any{"input": map[string]any{"limit": 101}}},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			authorizer := &contractAuthorizer{}
			executor := &contractExecutor{data: json.RawMessage(`{"unexpected":true}`)}
			handler := newContractHandler(t, authorizer, executor)
			response := serveGraphQL(t, handler, map[string]any{
				"variables": testCase.variables,
				"extensions": map[string]any{
					"persistedQuery": map[string]any{
						"version": 1, "sha256Hash": validRegistryEntry().SHA256Hash,
					},
				},
			})
			assertRuntimeError(t, response, http.StatusBadRequest, "GATEWAY.USER.graphql_request_invalid")
			if authorizer.calls != 0 || executor.calls != 0 {
				t.Fatalf("rejected cost reached authorizer=%d executor=%d", authorizer.calls, executor.calls)
			}
		})
	}
}

func TestVariableCostPlanRejectsNonIntegerAndOverMaximumBeforeAuthorization(t *testing.T) {
	entry := validRegistryEntry()
	entry.CostPlan = domain.CostPlan{
		BaseComplexity: 100,
		ListMultipliers: []domain.ListMultiplier{
			{VariablePath: "input.itemCount", Coefficient: 4, DefaultValue: 1, MaximumValue: 25},
		},
		MaxOwnerCalls:    1,
		MaxBatchKeys:     25,
		MaxResponseBytes: 4096,
	}
	syncCostPlan(&entry)

	for _, variables := range []map[string]any{
		{"input": map[string]any{"itemCount": 26}},
		{"input": map[string]any{"itemCount": 1.5}},
		{"input": map[string]any{"itemCount": "25"}},
	} {
		authorizer := &contractAuthorizer{}
		executor := &contractExecutor{data: json.RawMessage(`{"unexpected":true}`)}
		handler := newContractHandlerForEntry(t, entry, authorizer, executor)
		response := serveGraphQL(t, handler, map[string]any{
			"variables": variables,
			"extensions": map[string]any{
				"persistedQuery": map[string]any{
					"version": 1, "sha256Hash": entry.SHA256Hash,
				},
			},
		})
		assertRuntimeError(t, response, http.StatusBadRequest, "GATEWAY.USER.graphql_request_invalid")
		if authorizer.calls != 0 || executor.calls != 0 {
			t.Fatalf("variable cost rejection reached authorizer=%d executor=%d", authorizer.calls, executor.calls)
		}
	}
}

func TestExecutionUsageOverSignedBudgetFailsBeforeResponse(t *testing.T) {
	defaultData := json.RawMessage(`{"contentPostDetail":{"postId":"post-1"}}`)
	largeData := json.RawMessage(`{"payload":"` + strings.Repeat("x", 4096) + `"}`)
	for _, testCase := range []struct {
		name      string
		data      json.RawMessage
		usage     application.ExecutionUsage
		omitUsage bool
	}{
		{
			name: "owner calls exceed signed plan",
			data: defaultData,
			usage: application.ExecutionUsage{
				OwnerCalls: 2, BatchKeys: 1, ResponseBytes: len(defaultData),
			},
		},
		{
			name: "batch keys exceed signed plan",
			data: defaultData,
			usage: application.ExecutionUsage{
				OwnerCalls: 1, BatchKeys: 2, ResponseBytes: len(defaultData),
			},
		},
		{
			name: "reported response bytes differ from encoded data",
			data: defaultData,
			usage: application.ExecutionUsage{
				OwnerCalls: 1, BatchKeys: 1, ResponseBytes: len(defaultData) + 1,
			},
		},
		{
			name: "response bytes exceed signed plan",
			data: largeData,
			usage: application.ExecutionUsage{
				OwnerCalls: 1, BatchKeys: 1, ResponseBytes: len(largeData),
			},
		},
		{
			name:      "executor omits typed usage",
			data:      defaultData,
			omitUsage: true,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			authorizer := &contractAuthorizer{}
			executor := &contractExecutor{
				data: testCase.data, usage: testCase.usage, preserveZeroUsage: testCase.omitUsage,
			}
			handler := newContractHandler(t, authorizer, executor)
			response := serveGraphQL(t, handler, map[string]any{
				"extensions": map[string]any{
					"persistedQuery": map[string]any{
						"version": 1, "sha256Hash": validRegistryEntry().SHA256Hash,
					},
				},
			})
			assertRuntimeError(t, response, http.StatusServiceUnavailable, "GATEWAY.MIDDLEWARE.graphql_owner_unavailable")
			if authorizer.calls != 1 || executor.calls != 1 {
				t.Fatalf("usage gate calls authorizer=%d executor=%d", authorizer.calls, executor.calls)
			}
		})
	}
}

func TestRegistryAuthorizationFailureDoesNotReachOwner(t *testing.T) {
	executor := &contractExecutor{data: json.RawMessage(`{"unexpected":true}`)}
	handler := newContractHandler(t, &contractAuthorizer{err: errors.New("principal mismatch")}, executor)
	response := serveGraphQL(t, handler, map[string]any{
		"extensions": map[string]any{
			"persistedQuery": map[string]any{
				"version": 1, "sha256Hash": validRegistryEntry().SHA256Hash,
			},
		},
	})
	assertRuntimeError(t, response, http.StatusForbidden, "GATEWAY.USER.graphql_query_forbidden")
	if executor.calls != 0 {
		t.Fatalf("forbidden query reached owner executor %d times", executor.calls)
	}
}

func validRegistryEntry() domain.Entry {
	entry := domain.Entry{
		SHA256Hash:           "c5a236c3bb412b5652af458e20aa6620357d2ba62f242a562be638182fdb5369",
		OperationName:        "ContentPostDetail",
		OperationType:        domain.OperationTypeQuery,
		CanonicalOperationID: "content.post.GetPost",
		ObjectIDs:            []string{"content.post"},
		Authorization: domain.AuthorizationBinding{
			Principal: "public", OwnershipPolicy: "visibility_filtered",
		},
		CostModelVersion: domain.CostModelVersionV1,
		Cost: domain.CostBudget{
			Depth: 2, TopLevelFields: 1, Complexity: 13,
			VariablesMaxBytes: 1024, PageSizeMax: 100,
			MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 4096,
			SLORef: "slo:gateway_graphql_read_execute",
		},
		CostPlan: domain.CostPlan{
			BaseComplexity:   13,
			ListMultipliers:  []domain.ListMultiplier{},
			MaxOwnerCalls:    1,
			MaxBatchKeys:     1,
			MaxResponseBytes: 4096,
		},
		ExecutorKey: "content.post.getPost",
	}
	syncCostPlan(&entry)
	return entry
}

func setConstantCostPlan(entry *domain.Entry, complexity int) {
	entry.CostPlan.BaseComplexity = complexity
	entry.CostPlan.ListMultipliers = []domain.ListMultiplier{}
	syncCostPlan(entry)
}

func syncCostPlan(entry *domain.Entry) {
	digest, err := entry.CostPlan.Digest()
	if err != nil {
		panic(err)
	}
	worstCase, err := entry.CostPlan.WorstCaseComplexity()
	if err != nil {
		panic(err)
	}
	entry.CostModelVersion = domain.CostModelVersionV1
	entry.CostPlanDigest = digest
	entry.Cost.Complexity = worstCase
	entry.Cost.MaxOwnerCalls = entry.CostPlan.MaxOwnerCalls
	entry.Cost.MaxBatchKeys = entry.CostPlan.MaxBatchKeys
	entry.Cost.MaxResponseBytes = entry.CostPlan.MaxResponseBytes
}

func newContractHandler(
	t *testing.T,
	authorizer application.Authorizer,
	executor application.Executor,
) http.Handler {
	t.Helper()
	return newContractHandlerForEntry(t, validRegistryEntry(), authorizer, executor)
}

func newContractHandlerForEntry(
	t *testing.T,
	entry domain.Entry,
	authorizer application.Authorizer,
	executor application.Executor,
) http.Handler {
	t.Helper()
	registry, err := domain.NewRegistry([]domain.Entry{entry})
	if err != nil {
		t.Fatal(err)
	}
	service, err := application.NewService("alpha", registry, authorizer, executor, nil)
	if err != nil {
		t.Fatal(err)
	}
	return httpadapter.NewHandler(service)
}

func serveGraphQL(t *testing.T, handler http.Handler, body map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/graphql", strings.NewReader(string(payload)))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Request-Id", "graphql-local-contract")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func assertRuntimeError(t *testing.T, response *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	if response.Code != status {
		t.Fatalf("status=%d want=%d body=%s", response.Code, status, response.Body.String())
	}
	var body rterr.ErrorResponse
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode runtime error: %v", err)
	}
	if body.Code != code {
		t.Fatalf("code=%q want=%q body=%s", body.Code, code, response.Body.String())
	}
}

type contractAuthorizer struct {
	err   error
	calls int
	entry domain.Entry
}

func (authorizer *contractAuthorizer) Authorize(_ context.Context, entry domain.Entry) error {
	authorizer.calls++
	authorizer.entry = entry
	return authorizer.err
}

type contractExecutor struct {
	err               error
	data              json.RawMessage
	calls             int
	entry             domain.Entry
	variables         map[string]any
	usage             application.ExecutionUsage
	preserveZeroUsage bool
}

func (executor *contractExecutor) Execute(
	_ context.Context,
	entry domain.Entry,
	variables map[string]any,
) (application.ExecutionResult, error) {
	executor.calls++
	executor.entry = entry
	executor.variables = variables
	usage := executor.usage
	if usage == (application.ExecutionUsage{}) && executor.err == nil && !executor.preserveZeroUsage {
		usage = application.ExecutionUsage{
			OwnerCalls: 1, BatchKeys: 1, ResponseBytes: len(executor.data),
		}
	}
	return application.ExecutionResult{Data: executor.data, Usage: usage}, executor.err
}

type hmacContractVerifier struct {
	secret []byte
}

func (verifier hmacContractVerifier) Verify(
	_ context.Context,
	_ string,
	payload []byte,
	signature []byte,
) error {
	mac := hmac.New(sha256.New, verifier.secret)
	_, _ = mac.Write(payload)
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return errors.New("signature mismatch")
	}
	return nil
}
