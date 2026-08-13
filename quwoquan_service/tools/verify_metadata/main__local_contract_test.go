package main

import (
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestInvocationRequestShapeUsesOneCanonicalRequestEntity(t *testing.T) {
	t.Parallel()

	fields := requestInvocationFieldsDocument{
		Types: map[string]requestInvocationEntity{
			"BodylessQuery": {
				Fields: []requestInvocationField{
					{Name: "objectId"},
					{Name: "cursor"},
					{Name: "revision"},
					{Name: "accountId"},
				},
			},
			"BodyCommand": {
				Fields: []requestInvocationField{
					{Name: "objectId"},
					{Name: "title"},
				},
			},
		},
	}
	testCases := []struct {
		name      string
		operation serviceOperationEntityDocument
		wantIssue string
	}{
		{
			name: "bodyless invocation is fully position-bound",
			operation: serviceOperationEntityDocument{
				Operation:       "GetObject",
				RequestEntity:   "BodylessQuery",
				RequestBodyKind: "none",
				RequestBindings: requestInvocationBindings{
					Path: []requestInvocationBinding{
						{Name: "objectId", Field: "objectId"},
					},
					Query: []requestInvocationBinding{
						{Name: "cursor", Field: "cursor"},
					},
					Header: []requestInvocationBinding{
						{Name: "If-Match", Field: "revision"},
					},
					Injected: []requestInvocationBinding{
						{Name: "accountId", Field: "accountId"},
					},
				},
			},
		},
		{
			name: "bodyless invocation rejects an unbound field",
			operation: serviceOperationEntityDocument{
				Operation:       "GetObject",
				RequestEntity:   "BodylessQuery",
				RequestBodyKind: "none",
				RequestBindings: requestInvocationBindings{
					Path: []requestInvocationBinding{
						{Name: "objectId", Field: "objectId"},
					},
				},
			},
			wantIssue: "request_body_kind=none leaves",
		},
		{
			name: "body operation keeps unbound fields in the body",
			operation: serviceOperationEntityDocument{
				Operation:       "UpdateObject",
				RequestEntity:   "BodyCommand",
				RequestBodyKind: "object",
				RequestBindings: requestInvocationBindings{
					Path: []requestInvocationBinding{
						{Name: "objectId", Field: "objectId"},
					},
				},
			},
		},
		{
			name: "body operation rejects a fully position-bound entity",
			operation: serviceOperationEntityDocument{
				Operation:       "UpdateObject",
				RequestEntity:   "BodyCommand",
				RequestBodyKind: "object",
				RequestBindings: requestInvocationBindings{
					Path: []requestInvocationBinding{
						{Name: "objectId", Field: "objectId"},
					},
					Query: []requestInvocationBinding{
						{Name: "title", Field: "title"},
					},
				},
			},
			wantIssue: "has no body fields",
		},
		{
			name: "binding must reference the request entity",
			operation: serviceOperationEntityDocument{
				Operation:       "UpdateObject",
				RequestEntity:   "BodyCommand",
				RequestBodyKind: "object",
				RequestBindings: requestInvocationBindings{
					Header: []requestInvocationBinding{
						{Name: "X-Missing", Field: "missing"},
					},
				},
			},
			wantIssue: "is absent from request_entity",
		},
		{
			name: "request entity must exist",
			operation: serviceOperationEntityDocument{
				Operation:       "MissingObject",
				RequestEntity:   "MissingRequest",
				RequestBodyKind: "none",
			},
			wantIssue: "is absent from fields.yaml",
		},
		{
			name: "bodyless invocation still requires one request entity",
			operation: serviceOperationEntityDocument{
				Operation:       "MissingRequestEntity",
				RequestBodyKind: "none",
			},
			wantIssue: "requires request_entity",
		},
		{
			name: "one field cannot have two canonical positions",
			operation: serviceOperationEntityDocument{
				Operation:       "DuplicateBinding",
				RequestEntity:   "BodyCommand",
				RequestBodyKind: "object",
				RequestBindings: requestInvocationBindings{
					Path: []requestInvocationBinding{
						{Name: "objectId", Field: "objectId"},
					},
					Header: []requestInvocationBinding{
						{Name: "X-Object-Id", Field: "objectId"},
					},
				},
			},
			wantIssue: "bound to both path and header",
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			issues := validateInvocationRequestShape(
				testCase.operation,
				"Object",
				fields,
			)
			if testCase.wantIssue == "" {
				if len(issues) != 0 {
					t.Fatalf("unexpected issues: %v", issues)
				}
				return
			}
			if !containsIssue(issues, testCase.wantIssue) {
				t.Fatalf("issues %v do not contain %q", issues, testCase.wantIssue)
			}
		})
	}
}

func containsIssue(issues []string, target string) bool {
	for _, issue := range issues {
		if strings.Contains(issue, target) {
			return true
		}
	}
	return false
}

func TestControlPlaneOperationScopesFollowCanonicalPrincipalAuthority(t *testing.T) {
	t.Parallel()

	if controlPlaneOperationRequiresScopes("public") {
		t.Fatal("canonical public principal must retain actor and ownership authority without inventing an operator scope")
	}
	for _, principal := range []string{"", "operator", "service", "owner"} {
		if !controlPlaneOperationRequiresScopes(principal) {
			t.Fatalf("principal %q must remain scope-bound in the control plane", principal)
		}
	}
}

func TestRepositoryMetadataUsesObjectFirstSingleTrack(t *testing.T) {
	metadataDir := contractsview.Build(t)
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile metadata: %v", err)
	}
	v := &validator{metadataDir: metadataDir, source: source}
	v.run()
	if len(v.errors) != 0 {
		t.Fatalf("metadata validation errors: %v", v.errors)
	}

	objects, err := filepath.Glob(filepath.Join(metadataDir, "*", "*", "*", "object.yaml"))
	if err != nil {
		t.Fatalf("scan object metadata: %v", err)
	}
	wantObjects := len(source.Graph().Objects)
	if len(objects) != wantObjects {
		t.Fatalf("independent object roots = %d, want %d", len(objects), wantObjects)
	}
	for _, pattern := range []string{
		filepath.Join(metadataDir, "*", "business_object_map.yaml"),
		filepath.Join(metadataDir, "*", "*", "*", "readiness.yaml"),
		filepath.Join(metadataDir, "*", "*", "*", "aggregate.yaml"),
		filepath.Join(metadataDir, "*", "*", "*", "entity.yaml"),
	} {
		matches, globErr := filepath.Glob(pattern)
		if globErr != nil {
			t.Fatalf("scan forbidden metadata: %v", globErr)
		}
		if len(matches) != 0 {
			t.Fatalf("forbidden metadata remains: %v", matches)
		}
	}
}
