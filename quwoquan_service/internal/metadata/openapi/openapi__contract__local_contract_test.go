package openapi

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func TestGenerateCoversEveryTransportOperation(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Operations: []ast.Operation{
			commandOperation(
				"integration.payment.HandlePaymentCallback",
				"HandlePaymentCallback",
				"integration",
				"integration.payment",
				"POST",
				"/callbacks/payments/{provider}",
				"PaymentCallbackRequest",
				"",
			),
			queryOperation(
				"content.post.GetPost",
				"GetPost",
				"content",
				"content.post",
				"/content/content/posts/{postId}",
				"PostView",
				"object",
			),
			commandOperation(
				"content.post.RebuildPostIndex",
				"RebuildPostIndex",
				"content",
				"content.post",
				"POST",
				"/internal/content/content/posts/{postId}:rebuild-index",
				"RebuildPostIndexRequest",
				"RebuildPostIndexResult",
			),
			queryOperation(
				"content.post.Health",
				"Health",
				"content",
				"content.post",
				"/health",
				"HealthResult",
				"object",
			),
		},
	}

	snapshots, err := Generate(contractGraph)
	if err != nil {
		t.Fatalf("generate OpenAPI snapshots: %v", err)
	}
	if got, want := len(snapshots), 2; got != want {
		t.Fatalf("snapshot count = %d, want %d", got, want)
	}

	content := decodeSnapshot(t, snapshots[0])
	if got, want := content["openapi"], "3.0.3"; got != want {
		t.Fatalf("OpenAPI version = %v, want %s", got, want)
	}
	if got, want := snapshots[0].RelativePath, "content/openapi.yaml"; got != want {
		t.Fatalf("first snapshot path = %q, want %q", got, want)
	}
	assertOperationBinding(
		t,
		content,
		"/content/content/posts/{postId}",
		"get",
		"GetPost",
		"content.post",
		"persona_or_device",
		"query",
	)
	assertPathParameter(
		t,
		content,
		"/content/content/posts/{postId}",
		"get",
		"postId",
	)
	assertOperationBinding(
		t,
		content,
		"/internal/content/content/posts/{postId}:rebuild-index",
		"post",
		"RebuildPostIndex",
		"content.post",
		"persona",
		"command",
	)
	if _, exists := content["paths"].(map[string]any)["/health"]; exists {
		t.Fatal("non-domain health operation must not enter domain OpenAPI")
	}

	integration := decodeSnapshot(t, snapshots[1])
	assertOperationBinding(
		t,
		integration,
		"/callbacks/payments/{provider}",
		"post",
		"HandlePaymentCallback",
		"integration.payment",
		"persona",
		"command",
	)
	assertPathParameter(
		t,
		integration,
		"/callbacks/payments/{provider}",
		"post",
		"provider",
	)
}

func TestGenerateModelsRuntimeSessionUpgradeWithoutAggregateCommand(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Operations: []ast.Operation{{
			ID:               "realtime.connection.WebSocketUpgrade",
			LocalID:          "WebSocketUpgrade",
			Domain:           "realtime",
			ObjectID:         "realtime.connection",
			Method:           "GET",
			PathTemplate:     "/realtime/ws",
			Kind:             ast.OperationKindSession,
			KindExplicit:     true,
			Facet:            "ConnectionSessionFacet",
			FacadeMethod:     "openWebSocket",
			SessionOwner:     "Connection",
			ActorRequirement: "account",
			ResponseBodyKind: "upgrade",
		}},
	}

	snapshots, err := Generate(contractGraph)
	if err != nil {
		t.Fatalf("generate OpenAPI snapshots: %v", err)
	}
	document := decodeSnapshot(t, snapshots[0])
	operation := operationAt(t, document, "/realtime/ws", "get")
	application := operation["x-application"].(map[string]any)
	if got, want := application["kind"], "session"; got != want {
		t.Fatalf("session kind = %v, want %s", got, want)
	}
	if got, want := application["sessionOwner"], "Connection"; got != want {
		t.Fatalf("session owner = %v, want %s", got, want)
	}
	if _, exists := operation["requestBody"]; exists {
		t.Fatal("session upgrade must not synthesize a command request body")
	}
	if _, exists := operation["responses"].(map[string]any)["101"]; !exists {
		t.Fatal("session upgrade must expose HTTP 101")
	}
}

func TestGenerateHonorsExplicitBodylessPostCommand(t *testing.T) {
	operation := commandOperation(
		"ops.experiment_assignment_fact.AssignExperimentVariant",
		"AssignExperimentVariant",
		"ops",
		"ops.experiment_assignment_fact",
		"POST",
		"/ops/product_ops/experiments/{experimentId}/assignment",
		"",
		"ExperimentAssignmentFact",
	)
	operation.RequestBodyKind = "none"

	snapshots, err := Generate(&graph.ContractGraph{Operations: []ast.Operation{operation}})
	if err != nil {
		t.Fatalf("generate bodyless command: %v", err)
	}
	document := decodeSnapshot(t, snapshots[0])
	rendered := operationAt(t, document, operation.PathTemplate, "post")
	if _, exists := rendered["requestBody"]; exists {
		t.Fatal("request_body_kind=none must not generate requestBody")
	}
}

func TestGenerateExposesTypedIdempotencyAndConcurrencyHeaders(t *testing.T) {
	operation := commandOperation(
		"social.circle_group.UpdateCircleGroup",
		"UpdateCircleGroup",
		"circle",
		"social.circle_group",
		"PATCH",
		"/circles/groups/{groupId}",
		"UpdateCircleGroupRequest",
		"CircleGroup",
	)
	operation.Reliability.Idempotency = "required"
	operation.Concurrency.VersionPrecondition = ast.VersionPreconditionIfMatch

	snapshots, err := Generate(&graph.ContractGraph{
		Operations: []ast.Operation{operation},
	})
	if err != nil {
		t.Fatalf("generate typed header contract: %v", err)
	}
	document := decodeSnapshot(t, snapshots[0])
	assertPathParameter(t, document, operation.PathTemplate, "patch", "groupId")
	assertHeaderParameter(
		t,
		document,
		operation.PathTemplate,
		"patch",
		"Idempotency-Key",
		true,
	)
	assertHeaderParameter(
		t,
		document,
		operation.PathTemplate,
		"patch",
		"If-Match",
		true,
	)
}

func TestGenerateRequiredAuthNeverAdvertisesAnonymousAccess(t *testing.T) {
	operation := commandOperation(
		"ops.experiment_assignment_fact.AssignExperimentVariant",
		"AssignExperimentVariant",
		"ops",
		"ops.experiment_assignment_fact",
		"POST",
		"/ops/product_ops/experiments/{experimentId}/assignment",
		"",
		"ExperimentAssignmentFact",
	)
	operation.ActorRequirement = "persona_or_device"
	operation.AuthMode = "required"
	operation.RequestBodyKind = "none"

	snapshots, err := Generate(&graph.ContractGraph{Operations: []ast.Operation{operation}})
	if err != nil {
		t.Fatalf("generate required-auth command: %v", err)
	}
	document := decodeSnapshot(t, snapshots[0])
	rendered := operationAt(t, document, operation.PathTemplate, "post")
	security := rendered["security"].([]any)
	if got, want := len(security), 1; got != want {
		t.Fatalf("required auth security alternatives = %d, want %d: %#v", got, want, security)
	}
	if _, exists := security[0].(map[string]any)["bearerAuth"]; !exists {
		t.Fatalf("required auth must use bearerAuth: %#v", security)
	}
}

func TestGenerateCarriesTypedAppendSinkWithoutAggregateOwner(t *testing.T) {
	operation := commandOperation(
		"ops.experiment_assignment_fact.AssignExperimentVariant",
		"AssignExperimentVariant",
		"ops",
		"ops.experiment_assignment_fact",
		"POST",
		"/ops/product_ops/experiments/{experimentId}/assignments",
		"AssignExperimentVariantRequest",
		"ExperimentAssignmentFact",
	)
	operation.AggregateOwner = ""
	operation.AppendSink = "ExperimentAssignmentFact"

	snapshots, err := Generate(&graph.ContractGraph{Operations: []ast.Operation{operation}})
	if err != nil {
		t.Fatalf("generate append sink OpenAPI: %v", err)
	}
	document := decodeSnapshot(t, snapshots[0])
	rendered := operationAt(
		t,
		document,
		"/ops/product_ops/experiments/{experimentId}/assignments",
		"post",
	)
	application := rendered["x-application"].(map[string]any)
	if got, want := application["appendSink"], "ExperimentAssignmentFact"; got != want {
		t.Fatalf("append sink = %v, want %s", got, want)
	}
	if _, exists := application["aggregateOwner"]; exists {
		t.Fatalf("append-only command must not expose aggregateOwner: %#v", application)
	}
}

func TestGenerateExpandsCommandAndQuerySchemasWithoutAnonymousMaps(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Operations: []ast.Operation{
			commandOperation(
				"content.post.PublishPost",
				"PublishPost",
				"content",
				"content.post",
				"POST",
				"/content/content/posts/{postId}:publish",
				"PublishPostRequest",
				"PublishPostResult",
			),
			queryOperation(
				"content.post.ListPosts",
				"ListPosts",
				"content",
				"content.post",
				"/content/content/posts",
				"PostCard",
				"page",
			),
			commandOperation(
				"content.post.MarkPostsVisited",
				"MarkPostsVisited",
				"content",
				"content.post",
				"POST",
				"/content/content/posts:mark-visited",
				"MarkPostsVisitedRequest",
				"",
			),
		},
	}
	contractGraph.Operations[2].ResponseBodyKind = "ack"

	snapshots, err := Generate(contractGraph)
	if err != nil {
		t.Fatalf("generate OpenAPI snapshots: %v", err)
	}
	document := decodeSnapshot(t, snapshots[0])

	publish := operationAt(
		t,
		document,
		"/content/content/posts/{postId}:publish",
		"post",
	)
	publishApplication := publish["x-application"].(map[string]any)
	if got, want := publishApplication["aggregateOwner"], "Post"; got != want {
		t.Fatalf("command aggregate owner = %v, want %s", got, want)
	}
	assertSchemaRef(
		t,
		publish["requestBody"].(map[string]any),
		"content",
		"#/components/schemas/PublishPostRequest",
	)
	publishResponse := publish["responses"].(map[string]any)["200"].(map[string]any)
	assertSchemaRef(
		t,
		publishResponse,
		"content",
		"#/components/schemas/PublishPostResult",
	)

	list := operationAt(t, document, "/content/content/posts", "get")
	listApplication := list["x-application"].(map[string]any)
	if got, want := listApplication["reader"], "ListPostsReader"; got != want {
		t.Fatalf("query reader = %v, want %s", got, want)
	}
	if got, want := listApplication["slice"], "ListPostsSlice"; got != want {
		t.Fatalf("query slice = %v, want %s", got, want)
	}
	listResponse := list["responses"].(map[string]any)["200"].(map[string]any)
	assertSchemaRef(
		t,
		listResponse,
		"content",
		"#/components/schemas/ListPostsPage",
	)

	schemas := document["components"].(map[string]any)["schemas"].(map[string]any)
	page := schemas["ListPostsPage"].(map[string]any)
	items := page["properties"].(map[string]any)["items"].(map[string]any)
	if got, want := items["items"].(map[string]any)["$ref"], "#/components/schemas/PostCard"; got != want {
		t.Fatalf("page item ref = %v, want %v", got, want)
	}
	postCard := schemas["PostCard"].(map[string]any)
	if got, want := postCard["x-contract-entity"], "PostCard"; got != want {
		t.Fatalf("placeholder entity = %v, want %v", got, want)
	}
	if _, exists := postCard["additionalProperties"]; exists {
		t.Fatal("placeholder schema must not use additionalProperties as a universal map")
	}

	ack := operationAt(t, document, "/content/content/posts:mark-visited", "post")
	if _, exists := ack["responses"].(map[string]any)["204"]; !exists {
		t.Fatal("ack command must generate a 204 response")
	}
}

func TestGenerateIsDeterministicAcrossInputOrder(t *testing.T) {
	operations := []ast.Operation{
		queryOperation(
			"user.profile.GetProfile",
			"GetProfile",
			"user",
			"user.profile",
			"/users/{personaId}",
			"ProfileView",
			"object",
		),
		commandOperation(
			"user.profile.UpdateProfile",
			"UpdateProfile",
			"user",
			"user.profile",
			"PATCH",
			"/users/{personaId}",
			"UpdateProfileRequest",
			"ProfileView",
		),
	}

	first, err := Generate(&graph.ContractGraph{Operations: operations})
	if err != nil {
		t.Fatalf("first generate: %v", err)
	}
	second, err := Generate(&graph.ContractGraph{
		Operations: []ast.Operation{operations[1], operations[0]},
	})
	if err != nil {
		t.Fatalf("second generate: %v", err)
	}
	if len(first) != 1 || len(second) != 1 {
		t.Fatalf("unexpected snapshot counts: %d and %d", len(first), len(second))
	}
	if !bytes.Equal(first[0].Content, second[0].Content) {
		t.Fatal("OpenAPI output changed when ContractGraph operation order changed")
	}
}

func TestCompareDirectoryRejectsStaleAndOrphanSnapshots(t *testing.T) {
	metadataDir := t.TempDir()
	contractGraph := &graph.ContractGraph{
		Operations: []ast.Operation{
			queryOperation(
				"content.post.GetPost",
				"GetPost",
				"content",
				"content.post",
				"/content/content/posts/{postId}",
				"PostView",
				"object",
			),
		},
	}
	snapshots, err := Generate(contractGraph)
	if err != nil {
		t.Fatalf("generate OpenAPI snapshots: %v", err)
	}
	if err := WriteDirectory(metadataDir, snapshots); err != nil {
		t.Fatalf("write generated snapshots: %v", err)
	}
	if drifts, err := CompareDirectory(metadataDir, snapshots); err != nil {
		t.Fatalf("check current snapshots: %v", err)
	} else if len(drifts) != 0 {
		t.Fatalf("fresh snapshots reported drift: %+v", drifts)
	}

	if err := os.WriteFile(
		filepath.Join(metadataDir, "content", "openapi.yaml"),
		[]byte("openapi: 3.0.3\npaths: {}\n"),
		0o644,
	); err != nil {
		t.Fatalf("make content snapshot stale: %v", err)
	}
	orphanPath := filepath.Join(metadataDir, "unexpected", "openapi.yaml")
	if err := os.MkdirAll(filepath.Dir(orphanPath), 0o755); err != nil {
		t.Fatalf("mkdir orphan domain: %v", err)
	}
	if err := os.WriteFile(
		orphanPath,
		[]byte("openapi: 3.0.3\npaths: {}\n"),
		0o644,
	); err != nil {
		t.Fatalf("write orphan snapshot: %v", err)
	}

	drifts, err := CompareDirectory(metadataDir, snapshots)
	if err != nil {
		t.Fatalf("compare stale snapshots: %v", err)
	}
	assertDriftKind(t, drifts, DriftStale, "content/openapi.yaml")
	assertDriftKind(t, drifts, DriftOrphan, "unexpected/openapi.yaml")

	if err := WriteDirectory(metadataDir, snapshots); err != nil {
		t.Fatalf("replace stale and orphan snapshots: %v", err)
	}
	if _, err := os.Stat(orphanPath); !os.IsNotExist(err) {
		t.Fatalf("orphan snapshot still exists after generation: %v", err)
	}
	if drifts, err := CompareDirectory(metadataDir, snapshots); err != nil {
		t.Fatalf("check replaced snapshots: %v", err)
	} else if len(drifts) != 0 {
		t.Fatalf("replacement left snapshot drift: %+v", drifts)
	}
	temporaryFiles, err := filepath.Glob(
		filepath.Join(metadataDir, "content", ".openapi.yaml.tmp-*"),
	)
	if err != nil {
		t.Fatalf("glob staged snapshots: %v", err)
	}
	if len(temporaryFiles) != 0 {
		t.Fatalf("atomic write left temporary files: %v", temporaryFiles)
	}
}
