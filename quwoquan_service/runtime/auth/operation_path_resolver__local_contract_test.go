package auth

import (
	"crypto/sha256"
	"fmt"
	"net/http"
	"testing"
)

func TestOperationPathTemplateResolverBoundsDynamicAndUnknownRoutes(t *testing.T) {
	resolver := NewOperationPathTemplateResolver([]OperationSecurityDescriptor{
		{
			CanonicalOperationID: "assistant.assistant_run.GetAssistantRun",
			ContractGraphSHA256:  fmt.Sprintf("sha256:%x", sha256.Sum256([]byte("operation-security:test-graph"))),
			Method:               http.MethodGet,
			PathTemplate:         "/assistant/runs/{runId}",
			OperationKind:        "query",
			AuthMode:             "required",
			Principal:            "persona",
			CommercialStatus:     "ready",
		},
	})
	request, err := http.NewRequest(
		http.MethodGet,
		"https://assistant.test/assistant/runs/arn_sensitive_123",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if got := resolver(request); got != "/assistant/runs/{runId}" {
		t.Fatalf("resolved route=%q", got)
	}

	unknown, err := http.NewRequest(
		http.MethodGet,
		"https://assistant.test/unregistered/arn_sensitive_123",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if got := resolver(unknown); got != "/_unmatched" {
		t.Fatalf("unknown route must be bounded, got=%q", got)
	}
}
