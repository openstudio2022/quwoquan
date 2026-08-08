package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#open-011
func TestFieldPrivacyCatalogDerivesOnlyObjectAuthoredPolicies(t *testing.T) {
	truncate := 100
	source := contractcodegen.NewSourceFromGraph("contracts/metadata", &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "user.user_account", Name: "UserAccount"},
			{ID: "content.post", Name: "Post"},
		},
		Governance: ast.MetadataGovernance{
			Fields: []ast.FieldDefinition{
				{ObjectID: "user.user_account", Entity: "UserAccount", Name: "phone", Classification: "PII"},
				{ObjectID: "user.user_account", Entity: "UserAccount", Name: "region", Classification: "PII"},
				{ObjectID: "user.user_account", Entity: "UserAccount", Name: "internalNote", Classification: "SENSITIVE"},
				{ObjectID: "content.post", Entity: "Post", Name: "title", Classification: "PUBLIC"},
				{ObjectID: "content.post", Entity: "Post", Name: "mediaUrls", Classification: "PUBLIC"},
				{ObjectID: "content.post", Entity: "Post", Name: "moderationStatus", Classification: "PUBLIC"},
			},
			Objects: []ast.ObjectGovernance{
				{
					ObjectID: "user.user_account",
					Privacy: &ast.PrivacyDefinition{Document: ast.PrivacyDocument{
						AppLogPolicy: []ast.PrivacyAppLogPolicy{
							{Field: "phone", Classification: ast.PrivacyClassificationPII, AppLog: ast.PrivacyAppLogDrop},
							{Field: "region", Classification: ast.PrivacyClassificationPII, AppLog: ast.PrivacyAppLogMask, MaskStrategy: "city_level_only"},
						},
					}},
				},
				{
					ObjectID: "content.post",
					Privacy: &ast.PrivacyDefinition{Document: ast.PrivacyDocument{
						AppLogPolicy: []ast.PrivacyAppLogPolicy{
							{Field: "title", Classification: ast.PrivacyClassificationPublic, AppLog: ast.PrivacyAppLogTruncate, TruncateChars: &truncate},
							{Field: "mediaUrls", Classification: ast.PrivacyClassificationPublic, AppLog: ast.PrivacyAppLogCountOnly},
						},
						FieldVisibility: []ast.PrivacyFieldVisibility{{
							Field: "moderationStatus",
							Visibility: []string{
								"platform-ops",
								"first_party_service_internal",
							},
						}},
					}},
				},
			},
		},
	})

	policies := deriveFieldPrivacyPolicies(source)
	if len(policies) != 6 {
		t.Fatalf("derived policies = %d, want 6", len(policies))
	}
	wantOrder := []string{
		"content.post.mediaUrls:count_only",
		"content.post.moderationStatus:drop",
		"content.post.title:truncate",
		"user.user_account.internalNote:drop",
		"user.user_account.phone:drop",
		"user.user_account.region:mask",
	}
	for index, policy := range policies {
		got := policy.ObjectID + "." + policy.Field + ":" + policy.Action
		if got != wantOrder[index] {
			t.Fatalf("policy[%d] = %q, want %q", index, got, wantOrder[index])
		}
	}
	if policies[2].TruncateChars != 100 || policies[5].MaskStrategy != "city_level_only" {
		t.Fatalf("derived policy parameters drifted: %#v", policies)
	}
	if policies[1].Explicit || policies[1].Action != "drop" {
		t.Fatalf("undeclared root field is not default-denied: %#v", policies[1])
	}
	if got := strings.Join(policies[1].Visibility, ","); got != "first_party_service_internal,platform-ops" {
		t.Fatalf("moderationStatus visibility = %q", got)
	}
	if policies[1].Classification != "PUBLIC" || policies[1].Action != "drop" {
		t.Fatalf("visibility changed the independent classification/log action axes: %#v", policies[1])
	}
	if policies[3].Explicit || policies[3].Action != "drop" {
		t.Fatalf("undeclared root field is not default-denied: %#v", policies[3])
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#open-011
func TestFieldPrivacyPoliciesReachEveryCatalogAndBothRuntimeRedactors(t *testing.T) {
	value := catalog{FieldPrivacyPolicies: []fieldPrivacyPolicy{
		{ObjectID: "content.post", Field: "title", Classification: "PUBLIC", Action: "truncate", TruncateChars: 100, Explicit: true, Visibility: []string{"app"}},
		{ObjectID: "content.post", Field: "moderationStatus", Classification: "PUBLIC", Action: "allow", Explicit: true, Visibility: []string{"first_party_service_internal", "platform-ops"}},
		{ObjectID: "user.user_account", Field: "phone", Classification: "PII", Action: "drop", Explicit: true},
	}}
	outputs := map[string]string{
		"go":         renderGo(value),
		"dart":       renderDart(value),
		"python":     renderPython(value),
		"typescript": renderTypeScript(value),
	}
	for name, output := range outputs {
		for _, token := range []string{"content.post", "title", "truncate", "moderationStatus", "first_party_service_internal", "platform-ops", "user.user_account", "phone", "drop"} {
			if !strings.Contains(output, token) {
				t.Fatalf("%s catalog is missing derived token %q", name, token)
			}
		}
	}

	goOutput := outputs["go"]
	if !strings.Contains(goOutput, "registerCatalogFieldPrivacyPolicies") {
		t.Fatal("Go catalog does not register the derived policy with the runtime redactor")
	}
	appRedactor := renderAppLogRedactor()
	for _, token := range []string{
		"RuntimeLogCatalog.fieldPrivacyPolicies",
		"_visibilityAllowsApp(policy.visibility)",
		"audience == 'app' || audience == 'all'",
		"case 'drop':",
		"case 'mask':",
		"case 'truncate':",
		"case 'count_only':",
		"case 'drop_if_gt_100chars':",
	} {
		if !strings.Contains(appRedactor, token) {
			t.Fatalf("generated App redactor is missing runtime policy consumption %q", token)
		}
	}
	if strings.Contains(appRedactor, "_sensitiveKeyTokens") {
		t.Fatal("generated App redactor retains a handwritten sensitive-token truth source")
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#open-011
func TestAppLogRedactorOwnerAndCurrentRuntimeHaveNoHandwrittenTokenRoster(t *testing.T) {
	repoRoot := filepath.Clean(filepath.Join("..", "..", ".."))
	want := filepath.Join(
		repoRoot,
		"quwoquan_app",
		"lib",
		"runtime",
		"observability",
		"app_log_redactor.dart",
	)
	if got := appLogRedactorOutputPath(repoRoot); got != want {
		t.Fatalf("App log redactor target = %q, want %q", got, want)
	}
	current, err := os.ReadFile(want)
	if err != nil {
		t.Fatal(err)
	}
	text := string(current)
	if !strings.Contains(text, "RuntimeLogCatalog.forbiddenAttributeKeys") {
		t.Fatal("current App redactor does not consume the generated runtime catalog")
	}
	if strings.Contains(text, "_sensitiveKeyTokens") {
		t.Fatal("current App redactor still owns a handwritten sensitive-token roster")
	}
	service, err := os.ReadFile(filepath.Join(repoRoot, "quwoquan_app", "lib", "runtime", "observability", "app_log_service.dart"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(service), "operationId: context.operationId") {
		t.Fatal("App log service does not pass object identity into field privacy redaction")
	}
}
