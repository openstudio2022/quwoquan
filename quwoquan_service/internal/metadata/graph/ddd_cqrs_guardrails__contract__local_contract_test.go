package graph_test

import (
	"path/filepath"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/metadata/validate"
)

func TestAggregateRejectsNestedAggregateRoot(t *testing.T) {
	t.Parallel()

	contractGraph := &graph.ContractGraph{Objects: []ast.Object{{
		ID:           "assistant.assistant_run",
		Domain:       "assistant",
		Name:         "AssistantRun",
		Kind:         ast.ObjectKindAggregateRoot,
		KindExplicit: true,
		SourcePath:   "assistant/assistant_run/aggregate.yaml",
		Members: []ast.Member{{
			Name:           "AssistantConversation",
			Kind:           ast.ObjectKindAggregateRoot,
			Cardinality:    "1:1",
			AggregateOwner: "AssistantConversation",
		}},
	}}}
	issues := validate.Run(contractGraph, validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.MEMBER.INVALID_KIND") {
		t.Fatalf("nested aggregate root was accepted: %+v", issues)
	}
}

func TestObjectRegistryRejectsCrossContextChildAccess(t *testing.T) {
	t.Parallel()

	contextPolicy := ast.ContextAccessPolicy{
		Commands:     "aggregate_facade_only",
		Queries:      "named_reader_slice_only",
		ChildObjects: "aggregate_root_only",
		CrossContext: "public_contract_only",
	}
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "content.post", Domain: "content", Name: "Post", Kind: ast.ObjectKindAggregateRoot, KindExplicit: true, SourcePath: "content/post/aggregate.yaml"},
			{ID: "content.asset_variant", Domain: "content", Name: "AssetVariant", Kind: ast.ObjectKindOwnedEntity, KindExplicit: true, AggregateOwner: "MediaAsset", SourcePath: "content/media/fields.yaml"},
		},
		BusinessObjectMaps: []ast.BusinessObjectMap{{
			Domain:     "content",
			SourcePath: "content/business_object_map.yaml",
			BoundedContexts: []ast.BoundedContextRegistration{
				{Name: "Content", Role: "core", AccessPolicy: contextPolicy},
				{Name: "Media", Role: "supporting", AccessPolicy: contextPolicy},
			},
			Objects: []ast.BusinessObjectBoundary{
				{
					CanonicalObject: "Post",
					BoundedContext:  "Content",
					ObjectKind:      ast.ObjectKindAggregateRoot,
					Access:          ast.ObjectAccessPolicy{Commands: "aggregate_facade", Queries: "named_reader", CrossContext: "public_contract_only"},
					Relationships: []ast.ObjectRelationship{{
						Name: "assetVariant", TargetObject: "content.AssetVariant", Kind: "reference", Cardinality: "N:1", Consistency: "eventual", Access: "aggregate_root", OnDelete: "retain",
					}},
				},
				{
					CanonicalObject: "AssetVariant",
					BoundedContext:  "Media",
					ObjectKind:      ast.ObjectKindOwnedEntity,
					AggregateOwner:  "MediaAsset",
					Access:          ast.ObjectAccessPolicy{Commands: "via_aggregate_root", Queries: "via_aggregate_projection", CrossContext: "forbidden"},
				},
			},
		}},
	}
	issues := validate.Run(contractGraph, validate.ProfileCommercial)
	for _, code := range []string{
		"CONTRACT.RELATIONSHIP.DIRECT_CHILD_ACCESS",
		"CONTRACT.RELATIONSHIP.CROSS_CONTEXT_DIRECT_ACCESS",
	} {
		if !hasIssueCode(issues, code) {
			t.Fatalf("expected %s, got %+v", code, issues)
		}
	}
}

func TestObjectRegistryRequiresEveryDomain(t *testing.T) {
	t.Parallel()

	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "content.post", Domain: "content", Name: "Post", Kind: ast.ObjectKindAggregateRoot, KindExplicit: true, SourcePath: "content/post/aggregate.yaml"},
			{ID: "chat.conversation", Domain: "chat", Name: "Conversation", Kind: ast.ObjectKindAggregateRoot, KindExplicit: true, SourcePath: "messages/conversation/aggregate.yaml"},
		},
		BusinessObjectMaps: []ast.BusinessObjectMap{{
			Domain:     "content",
			SourcePath: "content/business_object_map.yaml",
			BoundedContexts: []ast.BoundedContextRegistration{{
				Name: "Content", Role: "core", AccessPolicy: ast.ContextAccessPolicy{Commands: "aggregate_facade_only", Queries: "named_reader_slice_only", ChildObjects: "aggregate_root_only", CrossContext: "public_contract_only"},
			}},
			Objects: []ast.BusinessObjectBoundary{{
				CanonicalObject: "Post",
				BoundedContext:  "Content",
				ObjectKind:      ast.ObjectKindAggregateRoot,
				Access:          ast.ObjectAccessPolicy{Commands: "aggregate_facade", Queries: "named_reader", CrossContext: "public_contract_only"},
			}},
		}},
	}
	issues := validate.Run(contractGraph, validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OBJECT_REGISTRY.UNREGISTERED_DOMAIN") {
		t.Fatalf("unregistered domain was accepted: %+v", issues)
	}
}

func TestCanonicalGraphRejectsSeparateAggregateAlias(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "content/report/entity.yaml"), `
domain: content
entity: Report
object_kind: separate_aggregate
description: report aggregate
storage_backend: postgres
`)
	if _, err := load.Load(metadataDir); err == nil {
		t.Fatal("separate_aggregate alias must be rejected by the metadata loader")
	}
}

func TestBlockedOperationStillRunsDDDStructuralValidation(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(
		t,
		filepath.Join(metadataDir, "content/post/aggregate.yaml"),
		commercialAggregate("content", "Post"),
	)
	writeFile(t, filepath.Join(metadataDir, "content/post/service.yaml"), `
service:
  name: content-service
  domain: content
  owner: test-team
api_routes:
  - method: POST
    path: /content/reports
    operation: CreateReport
    actor: persona
    commercial:
      status: blocked
      block_reason: report packet migration is pending
      gap_id: REPORT_PACKET_MIGRATION
      target_story: app-cloud-business-object-commercial-closure
    application:
      kind: command
      facet: ReportCommandFacade
      method: createReport
      aggregate_owner: Report
      mutation_target: Report
      invariant_target: Report
`)
	writeFile(t, filepath.Join(metadataDir, "content/report/entity.yaml"), `
domain: content
entity: Report
object_kind: aggregate_root
description: report aggregate
storage_backend: postgres
`)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.CROSS_OBJECT_COMMAND_OWNER") {
		t.Fatalf("blocked operation bypassed DDD validation: %+v", issues)
	}
}

func TestBusinessObjectMapRejectsKindStorageAndRoleDrift(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(
		t,
		filepath.Join(metadataDir, "content/post/aggregate.yaml"),
		commercialAggregate("content", "Post"),
	)
	writeFile(t, filepath.Join(metadataDir, "content/post/fields.yaml"), `
aggregate: Post
entities:
  Post:
    fields:
      - name: id
        type: string
`)
	writeFile(t, filepath.Join(metadataDir, "content/business_object_map.yaml"), `
domain: content
decision_refs: [DDD-OBJ-001]
bounded_contexts:
  - name: Content
    context_id: content.content
    role: core
    access_policy:
      commands: aggregate_facade_only
      queries: named_reader_slice_only
      child_objects: aggregate_root_only
      cross_context: public_contract_only
objects:
  - canonical_object: Post
    bounded_context: Content
    object_kind: projection
    identity:
      fields: [id]
      version_source: checkpoint
    invariant_refs: []
    member_bounds: {}
    storage_role: projection
    mutation_entrypoints: []
    event_consumers: [content.PostProjected.v1]
    lifecycle_refs: []
    storage_backend: postgres
    source_document: content/post/fields.yaml
    source_entity: Post
    access:
      commands: none
      queries: named_reader
      cross_context: public_contract_only
    relationships: []
    field_roles:
      authoritative_state: [id]
      owned_value: []
      reference: [id]
      append_only_fact: []
      projection: []
      transport_only: []
`)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	for _, code := range []string{
		"CONTRACT.OBJECT_MAP.KIND_MISMATCH",
		"CONTRACT.OBJECT_MAP.STORAGE_MISMATCH",
		"CONTRACT.OBJECT_MAP.INVALID_FIELD_ROLE",
		"CONTRACT.RELATIONSHIP.UNBOUND_REFERENCE_FIELD",
	} {
		if !hasIssueCode(issues, code) {
			t.Fatalf("expected %s, got %+v", code, issues)
		}
	}
}

func TestQueryBindingRejectsWeakReaderAndSliceNames(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(
		t,
		filepath.Join(metadataDir, "content/post/aggregate.yaml"),
		commercialAggregate("content", "Post"),
	)
	writeFile(t, filepath.Join(metadataDir, "content/post/service.yaml"), `
service:
  name: content-service
  domain: content
  owner: test-team
api_routes:
  - method: GET
    path: /content/posts/{postId}
    operation: GetPost
    actor: persona_or_device
    commercial:
      status: blocked
      block_reason: post query migration is pending
      gap_id: POST_QUERY_MIGRATION
      target_story: app-cloud-business-object-commercial-closure
    application:
      kind: query
      facet: PostQueryFacade
      method: getPost
      reader: map
      slice: Map
`)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	for _, code := range []string{
		"CONTRACT.OPERATION.INVALID_QUERY_READER",
		"CONTRACT.OPERATION.INVALID_QUERY_SLICE",
	} {
		if !hasIssueCode(issues, code) {
			t.Fatalf("expected %s, got %+v", code, issues)
		}
	}
}

func TestSessionOperationRequiresSamePacketRuntimeSessionOwner(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "realtime/connection/entity.yaml"), `
domain: realtime
entity: Connection
object_kind: runtime_session
description: transient realtime connection
storage_backend: redis
`)
	writeFile(t, filepath.Join(metadataDir, "realtime/connection/service.yaml"), `
service:
  name: realtime-gateway
  domain: realtime
  owner: test-team
  commercial_defaults:
    status: blocked
    block_reason: session implementation is pending
    gap_id: REALTIME_SESSION_MIGRATION
    target_story: app-cloud-business-object-commercial-closure
api_routes:
  - method: GET
    path: /realtime/ws
    operation: WebSocketUpgrade
    actor: account
    application:
      kind: session
      facet: ConnectionSessionFacet
      method: openWebSocket
      session_owner: Connection
`)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	for _, code := range []string{
		"CONTRACT.OPERATION.MISSING_SESSION_OWNER",
		"CONTRACT.OPERATION.INVALID_SESSION_OWNER_KIND",
		"CONTRACT.OPERATION.CROSS_OBJECT_SESSION_OWNER",
		"CONTRACT.OPERATION.INVALID_SESSION_BINDING",
	} {
		if hasIssueCode(issues, code) {
			t.Fatalf("valid runtime session emitted %s: %+v", code, issues)
		}
	}
}

func TestSessionOperationRejectsAggregateOwnerKind(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(
		t,
		filepath.Join(metadataDir, "realtime/connection/aggregate.yaml"),
		commercialAggregate("realtime", "Connection"),
	)
	writeFile(t, filepath.Join(metadataDir, "realtime/connection/service.yaml"), `
service:
  name: realtime-gateway
  domain: realtime
  owner: test-team
  commercial_defaults:
    status: blocked
    block_reason: invalid session owner fixture
    gap_id: REALTIME_SESSION_MIGRATION
    target_story: app-cloud-business-object-commercial-closure
api_routes:
  - method: GET
    path: /realtime/ws
    operation: WebSocketUpgrade
    actor: account
    application:
      kind: session
      facet: ConnectionSessionFacet
      method: openWebSocket
      session_owner: Connection
`)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.INVALID_SESSION_OWNER_KIND") {
		t.Fatalf("aggregate owner was accepted as runtime session: %+v", issues)
	}
}
