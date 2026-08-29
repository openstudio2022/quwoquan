package main

import (
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestRenderEmitsSameDerivedPolicyCountForGoAndDart(t *testing.T) {
	operations := []ast.Operation{
		{
			ID:     "content.post.GetPost",
			Domain: "content",
			Privacy: ast.PrivacyPolicy{
				RequestClassification:  "PUBLIC",
				ResponseClassification: "PUBLIC",
				LogPolicy:              "redacted",
			},
			Telemetry: ast.TelemetryPolicy{Metric: "content.post.get"},
		},
		{
			ID:     "entity.homepage.GetHomepage",
			Domain: "entity",
			Privacy: ast.PrivacyPolicy{
				RequestClassification:  "PUBLIC",
				ResponseClassification: "PUBLIC",
				LogPolicy:              "redacted",
			},
			Telemetry: ast.TelemetryPolicy{Metric: "entity.homepage.get"},
		},
	}

	goOutput := render(operations)
	dartOutput := renderDart(operations)
	if !strings.Contains(goOutput, "const generatedOperationPrivacyPolicyCount = 2") {
		t.Fatalf("Go count must be derived from the same operation slice:\n%s", goOutput)
	}
	if !strings.Contains(dartOutput, "const int generatedOperationPrivacyPolicyCount = 2;") {
		t.Fatalf("Dart count must be derived from the same operation slice:\n%s", dartOutput)
	}
}
