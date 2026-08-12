// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
// readiness_case: execute-persisted-graphql-query-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

func TestPersistedQueryIngressOverHTTPExecutesOnlyRegisteredOwnerReader(t *testing.T) {
	entry := integrationRegistryEntry()
	registry, err := domain.NewRegistry([]domain.Entry{entry})
	if err != nil {
		t.Fatal(err)
	}
	reader := &boundOwnerReader{}
	service, err := application.NewService("beta", registry, exactBindingAuthorizer{}, reader, nil)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(httpadapter.NewHandler(service))
	defer server.Close()

	response := postJSON(t, server.URL, map[string]any{
		"operationName": "ContentPostDetail",
		"variables":     map[string]any{"postId": "post-1", "input": map[string]any{"itemCount": 10}},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": entry.SHA256Hash},
		},
	})
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(response.Body)
		t.Fatalf("status=%d body=%s", response.StatusCode, body)
	}
	if reader.calls != 1 || reader.postID != "post-1" {
		t.Fatalf("owner reader calls=%d postId=%q", reader.calls, reader.postID)
	}

	mutation := postJSON(t, server.URL, map[string]any{
		"query": "mutation DeletePost { deletePost }",
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": entry.SHA256Hash},
		},
	})
	defer mutation.Body.Close()
	if mutation.StatusCode != http.StatusBadRequest {
		body, _ := io.ReadAll(mutation.Body)
		t.Fatalf("mutation status=%d body=%s", mutation.StatusCode, body)
	}
	if reader.calls != 1 {
		t.Fatalf("query text reached owner reader; calls=%d", reader.calls)
	}
}

func TestVariableCostAndExecutionUsageAreEnforcedAcrossHTTPBoundary(t *testing.T) {
	entry := integrationRegistryEntry()
	registry, err := domain.NewRegistry([]domain.Entry{entry})
	if err != nil {
		t.Fatal(err)
	}
	reader := &boundOwnerReader{}
	service, err := application.NewService("beta", registry, exactBindingAuthorizer{}, reader, nil)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(httpadapter.NewHandler(service))
	defer server.Close()

	overVariableBudget := postJSON(t, server.URL, map[string]any{
		"variables": map[string]any{"input": map[string]any{"itemCount": 26}},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": entry.SHA256Hash},
		},
	})
	defer overVariableBudget.Body.Close()
	if overVariableBudget.StatusCode != http.StatusBadRequest {
		body, _ := io.ReadAll(overVariableBudget.Body)
		t.Fatalf("variable cost status=%d body=%s", overVariableBudget.StatusCode, body)
	}
	if reader.calls != 0 {
		t.Fatalf("over-budget variables reached owner reader; calls=%d", reader.calls)
	}

	reader.usageOverride = application.ExecutionUsage{
		OwnerCalls: 2, BatchKeys: 1, ResponseBytes: 0,
	}
	overExecutionBudget := postJSON(t, server.URL, map[string]any{
		"variables": map[string]any{"input": map[string]any{"itemCount": 10}},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{"version": 1, "sha256Hash": entry.SHA256Hash},
		},
	})
	defer overExecutionBudget.Body.Close()
	if overExecutionBudget.StatusCode != http.StatusServiceUnavailable {
		body, _ := io.ReadAll(overExecutionBudget.Body)
		t.Fatalf("execution usage status=%d body=%s", overExecutionBudget.StatusCode, body)
	}
}

func integrationRegistryEntry() domain.Entry {
	plan := domain.CostPlan{
		BaseComplexity: 100,
		ListMultipliers: []domain.ListMultiplier{
			{VariablePath: "input.itemCount", Coefficient: 4, DefaultValue: 1, MaximumValue: 25},
		},
		MaxOwnerCalls:    1,
		MaxBatchKeys:     25,
		MaxResponseBytes: 4096,
	}
	digest, err := plan.Digest()
	if err != nil {
		panic(err)
	}
	worstCase, err := plan.WorstCaseComplexity()
	if err != nil {
		panic(err)
	}
	return domain.Entry{
		SHA256Hash:           "c5a236c3bb412b5652af458e20aa6620357d2ba62f242a562be638182fdb5369",
		OperationName:        "ContentPostDetail",
		OperationType:        domain.OperationTypeQuery,
		CanonicalOperationID: "content.post.GetPost",
		ObjectIDs:            []string{"content.post"},
		Authorization: domain.AuthorizationBinding{
			Principal: "public", OwnershipPolicy: "visibility_filtered",
		},
		CostModelVersion: domain.CostModelVersionV1,
		CostPlanDigest:   digest,
		Cost: domain.CostBudget{
			Depth: 2, TopLevelFields: 1, Complexity: worstCase,
			VariablesMaxBytes: 1024, PageSizeMax: 100,
			MaxOwnerCalls: 1, MaxBatchKeys: 25, MaxResponseBytes: 4096,
			SLORef: "slo:gateway_graphql_read_execute",
		},
		CostPlan:    plan,
		ExecutorKey: "content.post.getPost",
	}
}

func postJSON(t *testing.T, endpoint string, body map[string]any) *http.Response {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	return response
}

type exactBindingAuthorizer struct{}

func (exactBindingAuthorizer) Authorize(_ context.Context, entry domain.Entry) error {
	if entry.CanonicalOperationID != "content.post.GetPost" ||
		len(entry.ObjectIDs) != 1 || entry.ObjectIDs[0] != "content.post" {
		return context.Canceled
	}
	return nil
}

type boundOwnerReader struct {
	calls         int
	postID        string
	usageOverride application.ExecutionUsage
}

func (reader *boundOwnerReader) Execute(
	_ context.Context,
	entry domain.Entry,
	variables map[string]any,
) (application.ExecutionResult, error) {
	reader.calls++
	reader.postID, _ = variables["postId"].(string)
	data, _ := json.Marshal(map[string]any{
		"contentPostDetail": map[string]any{
			"postId": reader.postID, "contentType": "article", "status": "published",
		},
	})
	if entry.ExecutorKey != "content.post.getPost" {
		return application.ExecutionResult{}, context.Canceled
	}
	usage := reader.usageOverride
	if usage == (application.ExecutionUsage{}) {
		usage = application.ExecutionUsage{
			OwnerCalls: 1, BatchKeys: 1, ResponseBytes: len(data),
		}
	} else if usage.ResponseBytes == 0 {
		usage.ResponseBytes = len(data)
	}
	return application.ExecutionResult{Data: data, Usage: usage}, nil
}
