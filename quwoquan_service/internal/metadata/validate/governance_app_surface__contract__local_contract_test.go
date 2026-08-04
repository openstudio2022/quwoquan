package validate

import (
	"encoding/json"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func TestAppSurfaceGovernanceRejectsSecondTruthAndUntypedOperations(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{{
		ID:           "home",
		Owner:        "content",
		OperationIDs: []string{"GetPost", "GetPost"},
	}})
	operation := &contractGraph.Operations[0]
	operation.RequestEntity = ""
	operation.RequestBodyKind = ""
	operation.ResponseEntity = ""
	operation.ResponseBody = "PostView"
	operation.ResponseBodyKind = "ack"
	operation.ClientContract = nil
	operation.ClientContractExplicit = true
	operation.ErrorCodes = nil

	issues := validateAppSurfaceGovernance(contractGraph)
	for _, code := range []string{
		"CONTRACT.APP_SURFACE.DUPLICATE_OPERATION",
		"CONTRACT.APP_SURFACE.CLIENT_CONTRACT_SECOND_TRUTH",
		"CONTRACT.APP_SURFACE.REQUEST_ENTITY_REQUIRED",
		"CONTRACT.APP_SURFACE.REQUEST_BODY_KIND_REQUIRED",
		"CONTRACT.APP_SURFACE.RESPONSE_ENTITY_REQUIRED",
		"CONTRACT.APP_SURFACE.CLIENT_ABI_UNRESOLVED",
		"CONTRACT.APP_SURFACE.ERROR_CONTRACT_REQUIRED",
	} {
		if !appSurfaceIssueCodePresent(issues, code) {
			t.Fatalf("missing issue %s in %+v", code, issues)
		}
	}
}

func TestAppSurfaceGovernanceRejectsAmbiguousResponseOwner(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{{
		ID:           "home",
		Owner:        "content",
		OperationIDs: []string{"GetPost"},
	}})
	for index := range contractGraph.Governance.Types {
		if contractGraph.Governance.Types[index].Name == "PostView" {
			contractGraph.Governance.Types[index].ObjectID = "entity.homepage"
		}
	}
	contractGraph.Governance.Types = append(
		contractGraph.Governance.Types,
		ast.TypeDefinition{Name: "PostView", ObjectID: "search.search_index_view"},
	)

	issues := validateAppSurfaceGovernance(contractGraph)
	if !appSurfaceIssueCodePresent(
		issues,
		"CONTRACT.APP_SURFACE.RESPONSE_ENTITY_OWNER",
	) {
		t.Fatalf("missing ambiguous response owner issue in %+v", issues)
	}
}

func TestAppSurfaceGovernanceRejectsUnknownAmbiguousAndForeignRequestOwners(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{
		{ID: "unknown", Owner: "app", OperationIDs: []string{"Missing"}},
		{ID: "ambiguous", Owner: "app", OperationIDs: []string{"GetPost"}},
		{ID: "content", Owner: "content", OperationIDs: []string{"GetPost"}},
	})
	contractGraph.Operations = append(contractGraph.Operations, ast.Operation{
		ID:      "search.search_request_fact.GetPost",
		LocalID: "GetPost",
		Domain:  "search",
	})
	contractGraph.Governance.Types = nil

	issues := validateAppSurfaceGovernance(contractGraph)
	for _, code := range []string{
		"CONTRACT.APP_SURFACE.UNKNOWN_OPERATION",
		"CONTRACT.APP_SURFACE.AMBIGUOUS_OPERATION",
		"CONTRACT.APP_SURFACE.REQUEST_ENTITY_OWNER",
	} {
		if !appSurfaceIssueCodePresent(issues, code) {
			t.Fatalf("missing issue %s in %+v", code, issues)
		}
	}
}

func TestAppSurfaceGovernanceAcceptsBlockedOperationWithCompleteTypedABI(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{{
		ID:           "home",
		Owner:        "content",
		OperationIDs: []string{"GetPost"},
	}})
	contractGraph.Operations[0].Commercial = ast.CommercialBinding{
		Status:      "blocked",
		BlockReason: "environment evidence is pending",
	}

	if issues := validateAppSurfaceGovernance(contractGraph); len(issues) != 0 {
		t.Fatalf("complete blocked App operation issues = %+v", issues)
	}
	gotSurfaces, gotReferences, gotOperations, err := appSurfaceContractCounts(contractGraph)
	if err != nil {
		t.Fatal(err)
	}
	if gotSurfaces != 1 || gotReferences != 1 || gotOperations != 1 {
		t.Fatalf(
			"surface counts = %d/%d/%d, want 1/1/1",
			gotSurfaces,
			gotReferences,
			gotOperations,
		)
	}
}

func TestAppSurfaceGovernanceRequiresBindingsInObjectLocalRequestEntity(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{{
		ID:           "home",
		Owner:        "content",
		OperationIDs: []string{"GetPost"},
	}})
	contractGraph.Operations[0].RequestBindings = &ast.RequestBindings{
		Path: []ast.RequestBinding{{Name: "postId", Field: "missingPostId"}},
	}

	issues := validateAppSurfaceGovernance(contractGraph)
	if !appSurfaceIssueCodePresent(
		issues,
		"CONTRACT.APP_SURFACE.REQUEST_BINDING_OWNER",
	) {
		t.Fatalf("missing object-local request binding issue in %+v", issues)
	}
}

func TestAppSurfaceGovernanceRequiresExplicitUniqueCrossObjectResponseOwner(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{{
		ID:           "home",
		Owner:        "content",
		OperationIDs: []string{"GetPost"},
	}})
	for index := range contractGraph.Governance.Types {
		if contractGraph.Governance.Types[index].Name == "PostView" {
			contractGraph.Governance.Types[index].ObjectID = "entity.homepage"
		}
	}
	contractGraph.Objects = append(contractGraph.Objects, ast.Object{
		ID:     "entity.homepage",
		Domain: "entity",
		Name:   "Homepage",
	})

	issues := validateAppSurfaceGovernance(contractGraph)
	if !appSurfaceIssueCodePresent(
		issues,
		"CONTRACT.APP_SURFACE.CROSS_OBJECT_RESPONSE_REF_REQUIRED",
	) {
		t.Fatalf("missing cross-object response ref issue in %+v", issues)
	}

	contractGraph.Operations[0].ResponseEntityRef = "entity.Homepage"
	issues = validateAppSurfaceGovernance(contractGraph)
	if appSurfaceIssueCodePresent(
		issues,
		"CONTRACT.APP_SURFACE.CROSS_OBJECT_RESPONSE_REF_REQUIRED",
	) {
		t.Fatalf("canonical cross-object response ref rejected: %+v", issues)
	}
}

func TestAppSurfaceGovernanceAcceptsCanonicalObjectRootResponseOwner(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{{
		ID:           "home",
		Owner:        "content",
		OperationIDs: []string{"GetPost"},
	}})
	contractGraph.Operations[0].ResponseEntity = "Post"
	contractGraph.Operations[0].ClientContract.ResponseType = "Post"
	contractGraph.Operations[0].ClientContract.ResponseDecoder = "decodePost"
	contractGraph.Governance.Types = []ast.TypeDefinition{{
		Name:     "GetPostQuery",
		ObjectID: "content.post",
	}}

	if issues := validateAppSurfaceGovernance(contractGraph); len(issues) != 0 {
		t.Fatalf("canonical object root response rejected: %+v", issues)
	}
}

func TestAppSurfaceGovernanceRejectsClientAliasAndAmbiguousErrorOwner(t *testing.T) {
	contractGraph := appSurfaceTestGraph(t, []appSurfaceContract{{
		ID:           "home",
		Owner:        "content",
		OperationIDs: []string{"GetPost"},
	}})
	contractGraph.Operations[0].ClientContract.ResponseType = "PostViewAlias"
	contractGraph.Operations[0].ClientContract.ResponseDecoder = "decodePostViewAlias"
	duplicate := contractGraph.Governance.Objects[0].Errors[0]
	duplicate.ObjectID = "content.comment"
	duplicate.SourcePath = "content/content/comment/errors.yaml"
	contractGraph.Governance.Objects = append(
		contractGraph.Governance.Objects,
		ast.ObjectGovernance{
			ObjectID: "content.comment",
			Errors:   []ast.ErrorDefinition{duplicate},
		},
	)

	issues := validateAppSurfaceGovernance(contractGraph)
	for _, code := range []string{
		"CONTRACT.APP_SURFACE.CLIENT_ABI_NOT_DERIVED",
		"CONTRACT.APP_SURFACE.ERROR_OWNER",
	} {
		if !appSurfaceIssueCodePresent(issues, code) {
			t.Fatalf("missing issue %s in %+v", code, issues)
		}
	}
}

func appSurfaceTestGraph(
	t *testing.T,
	surfaces []appSurfaceContract,
) *graph.ContractGraph {
	t.Helper()
	payload, err := json.Marshal(appSurfaceContractDocument{Surfaces: surfaces})
	if err != nil {
		t.Fatal(err)
	}
	return &graph.ContractGraph{
		Objects: []ast.Object{{
			ID:     "content.post",
			Domain: "content",
			Name:   "Post",
		}},
		Operations: []ast.Operation{{
			ID:               "content.post.GetPost",
			LocalID:          "GetPost",
			Domain:           "content",
			ObjectID:         "content.post",
			RequestEntity:    "GetPostQuery",
			RequestBodyKind:  "none",
			ResponseEntity:   "PostView",
			ResponseBodyKind: "object",
			SourcePath:       "content/content/post/operations.yaml",
			ErrorCodes:       []string{"CONTENT.USER.post_not_found"},
			ClientContract: &ast.ClientContract{
				DartImport:      "../content/content_operation_contracts.g.dart",
				ResponseType:    "PostView",
				ResponseDecoder: "decodePostView",
			},
		}},
		Documents: []ast.SourceDocument{{
			Path:    appSurfaceSourcePath,
			Content: payload,
		}},
		Governance: ast.MetadataGovernance{
			Objects: []ast.ObjectGovernance{{
				ObjectID: "content.post",
				Errors: []ast.ErrorDefinition{{
					ObjectID:   "content.post",
					Code:       "CONTENT.USER.post_not_found",
					SourcePath: "content/content/post/errors.yaml",
				}},
			}},
			Types: []ast.TypeDefinition{
				{Name: "GetPostQuery", ObjectID: "content.post"},
				{Name: "PostView", ObjectID: "content.post"},
			},
			Fields: []ast.FieldDefinition{{
				ObjectID: "content.post",
				Entity:   "GetPostQuery",
				Name:     "postId",
			}},
		},
	}
}

func appSurfaceIssueCodePresent(issues []Issue, code string) bool {
	for _, candidate := range issues {
		if candidate.Code == code {
			return true
		}
	}
	return false
}
