package validate

import (
	"fmt"
	"regexp"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	contractopenapi "quwoquan_service/internal/metadata/openapi"
)

var (
	typedBindingIdentifier        = regexp.MustCompile(`^[A-Z][A-Za-z0-9]*$`)
	runtimeFacadeMethodIdentifier = regexp.MustCompile(`^[a-z][A-Za-z0-9]*$`)
)

type Profile string

const (
	ProfileBaseline   Profile = "baseline"
	ProfileCommercial Profile = "commercial"
)

type Issue struct {
	Code       string `json:"code"`
	SubjectID  string `json:"subjectId,omitempty"`
	SourcePath string `json:"sourcePath,omitempty"`
	Message    string `json:"message"`
}

func Run(contractGraph *graph.ContractGraph, profile Profile) []Issue {
	issues := make([]Issue, 0)
	objectIDs := map[string]string{}
	objectsByID := map[string]ast.Object{}
	objectsByDomainName := map[string]ast.Object{}
	identityByDomainName := map[string]ast.ObjectIdentity{}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		for _, object := range objectMap.Objects {
			identityByDomainName[domainObjectKey(
				objectMap.Domain,
				object.CanonicalObject,
			)] = object.Identity
		}
	}
	for _, object := range contractGraph.Objects {
		if previous, exists := objectIDs[object.ID]; exists {
			issues = append(issues, issue(
				"CONTRACT.DUPLICATE.OBJECT_ID",
				object.SourcePath,
				"object id %q is also declared by %s", object.ID, previous,
			))
		} else {
			objectIDs[object.ID] = object.SourcePath
		}
		objectsByID[object.ID] = object
		objectsByDomainName[domainObjectKey(object.Domain, object.Name)] = object
		if profile == ProfileCommercial {
			issues = append(
				issues,
				bindIssueSubject(object.ID, validateCommercialObject(object))...,
			)
		}
	}

	operationIDs := map[string]string{}
	transportKeys := map[string]string{}
	// DEC-011: HTTP 与非 HTTP runtime ingress 是互斥入口。事件消费是
	// object.yaml.lifecycle 的内部事实，不再借 runtime entrypoint 形成第二入口。
	operationsByObject := map[string][]ast.Operation{}
	for _, operation := range contractGraph.Operations {
		operationsByObject[operation.ObjectID] = append(
			operationsByObject[operation.ObjectID], operation,
		)
		if previous, exists := operationIDs[operation.ID]; exists {
			issues = append(issues, issue(
				"CONTRACT.DUPLICATE.OPERATION_ID",
				operation.SourcePath,
				"operation id %q is also declared by %s", operation.ID, previous,
			))
		} else {
			operationIDs[operation.ID] = operation.SourcePath
		}
		if _, exists := objectIDs[operation.ObjectID]; !exists {
			issues = append(issues, issue(
				"CONTRACT.REFERENCE.UNKNOWN_OBJECT",
				operation.SourcePath,
				"operation %q references unknown object %q", operation.ID, operation.ObjectID,
			))
		}
		if !allowedMethod(operation.Method) {
			issues = append(issues, issue(
				"CONTRACT.TRANSPORT.INVALID_METHOD",
				operation.SourcePath,
				"operation %q uses unsupported method %q", operation.ID, operation.Method,
			))
		}
		if !allowedPath(operation.PathTemplate) {
			issues = append(issues, issue(
				"CONTRACT.TRANSPORT.INVALID_PATH",
				operation.SourcePath,
				"operation %q path %q must be an unversioned resource path without version segments",
				operation.ID,
				operation.PathTemplate,
			))
		}
		if operation.Transport != "json" && operation.Transport != "sse" {
			issues = append(issues, issue(
				"CONTRACT.TRANSPORT.INVALID_KIND",
				operation.SourcePath,
				"operation %q uses unsupported transport %q", operation.ID, operation.Transport,
			))
		}
		if operation.Transport == "sse" {
			if operation.Method != "GET" || operation.RequestBodyKind != "none" {
				issues = append(issues, issue(
					"CONTRACT.TRANSPORT.INVALID_SSE_SHAPE",
					operation.SourcePath,
					"SSE operation %q must use GET with request_body_kind none", operation.ID,
				))
			}
			if operation.ResponseAdmission == nil || operation.ResponseAdmission.MaximumBodyBytes < 1024 {
				issues = append(issues, issue(
					"CONTRACT.TRANSPORT.SSE_FRAME_BUDGET_REQUIRED",
					operation.SourcePath,
					"SSE operation %q must declare response_admission.maximum_body_bytes as its per-frame bound", operation.ID,
				))
			}
			if operation.Streaming == nil {
				issues = append(issues, issue(
					"CONTRACT.TRANSPORT.SSE_POLICY_REQUIRED",
					operation.SourcePath,
					"SSE operation %q must declare resume and terminal fields", operation.ID,
				))
			} else {
				resumeBindingFound := false
				if operation.RequestBindings != nil {
					for _, binding := range operation.RequestBindings.Query {
						if binding.Name == operation.Streaming.ResumeRequestField {
							resumeBindingFound = true
							break
						}
					}
				}
				if !resumeBindingFound {
					issues = append(issues, issue(
						"CONTRACT.TRANSPORT.SSE_RESUME_BINDING_REQUIRED",
						operation.SourcePath,
						"SSE operation %q resume field %q must be a canonical query binding",
						operation.ID,
						operation.Streaming.ResumeRequestField,
					))
				}
			}
		} else if operation.Streaming != nil {
			issues = append(issues, issue(
				"CONTRACT.TRANSPORT.STREAMING_POLICY_FORBIDDEN",
				operation.SourcePath,
				"non-SSE operation %q cannot declare streaming policy", operation.ID,
			))
		}
		issues = append(issues, streamBudgetIssues(operation)...)
		issues = append(issues, successStatusIssues(operation)...)
		transportKey := operation.Method + " " + operation.PathTemplate
		if previous, exists := transportKeys[transportKey]; exists {
			issues = append(issues, issue(
				"CONTRACT.DUPLICATE.TRANSPORT",
				operation.SourcePath,
				"%s is owned by both %s and %s", transportKey, previous, operation.ID,
			))
		} else {
			transportKeys[transportKey] = operation.ID
		}
		if profile == ProfileCommercial {
			issues = append(
				issues,
				validateRequestBindings(operation)...,
			)
			issues = append(
				issues,
				validateCommercialOperation(
					operation,
					objectsByID,
					objectsByDomainName,
					identityByDomainName,
				)...,
			)
		}
	}
	runtimeEntrypointIDs := map[string]string{}
	runtimeEntrypointKeys := map[string]string{}
	for _, entrypoint := range contractGraph.RuntimeEntrypoints {
		if previous, exists := runtimeEntrypointIDs[entrypoint.ID]; exists {
			issues = append(issues, issue(
				"CONTRACT.DUPLICATE.RUNTIME_ENTRYPOINT_ID",
				entrypoint.SourcePath,
				"runtime entrypoint id %q is also declared by %s",
				entrypoint.ID,
				previous,
			))
		} else {
			runtimeEntrypointIDs[entrypoint.ID] = entrypoint.SourcePath
		}
		object, exists := objectsByID[entrypoint.ObjectID]
		if !exists {
			issues = append(issues, issue(
				"CONTRACT.REFERENCE.UNKNOWN_RUNTIME_ENTRYPOINT_OWNER",
				entrypoint.SourcePath,
				"runtime entrypoint %q references unknown object %q",
				entrypoint.ID,
				entrypoint.ObjectID,
			))
		} else {
			for _, sourceObject := range entrypoint.SourceObjects {
				sourceDomain, sourceName, sourceOK := strings.Cut(sourceObject, ".")
				_, sourceExists := objectsByDomainName[domainObjectKey(sourceDomain, sourceName)]
				if !sourceOK || !sourceExists {
					issues = append(issues, issue(
						"CONTRACT.RUNTIME_ENTRYPOINT.UNKNOWN_SOURCE_OBJECT",
						entrypoint.SourcePath,
						"runtime entrypoint %q references unknown source object %q",
						entrypoint.ID,
						sourceObject,
					))
				}
			}
		}
		if operations := operationsByObject[entrypoint.ObjectID]; len(operations) != 0 {
			issues = append(issues, issue(
				"CONTRACT.RUNTIME_ENTRYPOINT.HTTP_DUAL_TRACK",
				entrypoint.SourcePath,
				"object %q must not own both HTTP api_routes and runtime_entrypoints; internal event consumption belongs to object lifecycle",
				entrypoint.ObjectID,
			))
		}
		key := entrypoint.ObjectID + "\x00" + entrypoint.RuntimeKind + "\x00" + entrypoint.Phase
		if previous, exists := runtimeEntrypointKeys[key]; exists {
			issues = append(issues, issue(
				"CONTRACT.DUPLICATE.RUNTIME_ENTRYPOINT",
				entrypoint.SourcePath,
				"runtime entrypoint %q duplicates the object/kind/phase owned by %s",
				entrypoint.ID,
				previous,
			))
		} else {
			runtimeEntrypointKeys[key] = entrypoint.ID
		}
		issues = append(
			issues,
			validateRuntimeEntrypoint(entrypoint, object)...,
		)
	}
	projectionIDs := map[string]string{}
	for _, projection := range contractGraph.Projections {
		if previous, exists := projectionIDs[projection.ID]; exists {
			issues = append(issues, issue(
				"CONTRACT.DUPLICATE.PROJECTION_ID",
				projection.SourcePath,
				"projection id %q is also declared by %s", projection.ID, previous,
			))
		} else {
			projectionIDs[projection.ID] = projection.SourcePath
		}
		if _, exists := objectIDs[projection.ObjectID]; !exists {
			issues = append(issues, issue(
				"CONTRACT.REFERENCE.UNKNOWN_PROJECTION_OWNER",
				projection.SourcePath,
				"projection %q references unknown object %q", projection.ID, projection.ObjectID,
			))
		}
	}
	if profile == ProfileCommercial {
		issues = append(issues, validateBusinessObjectMaps(contractGraph)...)
		issues = append(issues, validateMetadataGovernance(contractGraph)...)
	}

	sortIssues(issues)
	return issues
}

func validateRuntimeEntrypoint(
	entrypoint ast.RuntimeEntrypoint,
	object ast.Object,
) []Issue {
	var issues []Issue
	if !typedBindingIdentifier.MatchString(entrypoint.LocalID) {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_NAME",
			entrypoint.SourcePath,
			"runtime entrypoint %q name must be a typed identifier",
			entrypoint.ID,
		))
	}
	expectedPhase := map[string]string{
		"middleware":    "post_authorization_pre_owner_proxy",
		"projector":     "event_projection",
		"event_handler": "event_command",
		"subscription":  "event_ingest",
		"internal_port": "transactional_append",
		"external_port": "outbound_invocation",
	}[entrypoint.RuntimeKind]
	if expectedPhase == "" {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_KIND",
			entrypoint.SourcePath,
			"runtime entrypoint %q has unsupported kind %q",
			entrypoint.ID,
			entrypoint.RuntimeKind,
		))
	} else if entrypoint.Phase != expectedPhase {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_PHASE",
			entrypoint.SourcePath,
			"runtime entrypoint %q kind %q requires phase %q, got %q",
			entrypoint.ID,
			entrypoint.RuntimeKind,
			expectedPhase,
			entrypoint.Phase,
		))
	}
	expectedObjectKind := map[string]ast.ObjectKind{
		"middleware":    ast.ObjectKindRuntimeSession,
		"projector":     ast.ObjectKindProjection,
		"event_handler": ast.ObjectKindAggregateRoot,
		"subscription":  ast.ObjectKindAppendOnlyFact,
		"internal_port": ast.ObjectKindAppendOnlyFact,
		"external_port": ast.ObjectKindExternalReference,
	}[entrypoint.RuntimeKind]
	if expectedObjectKind != "" && object.Kind != expectedObjectKind {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_OWNER_KIND",
			entrypoint.SourcePath,
			"runtime entrypoint %q kind %q requires object kind %q, got %q",
			entrypoint.ID,
			entrypoint.RuntimeKind,
			expectedObjectKind,
			object.Kind,
		))
	}
	if entrypoint.RuntimeKind == "middleware" &&
		entrypoint.ApplicationKind != ast.OperationKindSession {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_APPLICATION_KIND",
			entrypoint.SourcePath,
			"runtime entrypoint %q middleware application.kind must be session",
			entrypoint.ID,
		))
	}
	if entrypoint.RuntimeKind != "middleware" &&
		entrypoint.RuntimeKind != "external_port" &&
		entrypoint.ApplicationKind != ast.OperationKindCommand {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_APPLICATION_KIND",
			entrypoint.SourcePath,
			"runtime entrypoint %q kind %q application.kind must be command",
			entrypoint.ID,
			entrypoint.RuntimeKind,
		))
	}
	if !typedBindingIdentifier.MatchString(entrypoint.Facet) ||
		!hasTypedEntrypointSuffix(entrypoint.Facet) {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_FACADE",
			entrypoint.SourcePath,
			"runtime entrypoint %q facet %q must be a typed Facade/Projector/Appender/Port identifier",
			entrypoint.ID,
			entrypoint.Facet,
		))
	}
	if !runtimeFacadeMethodIdentifier.MatchString(entrypoint.FacadeMethod) {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_METHOD",
			entrypoint.SourcePath,
			"runtime entrypoint %q method %q must be a lower-camel identifier",
			entrypoint.ID,
			entrypoint.FacadeMethod,
		))
	}
	if entrypoint.ObjectOwner == "" || entrypoint.ObjectOwner != object.Name {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_OBJECT_OWNER",
			entrypoint.SourcePath,
			"runtime entrypoint %q object_owner %q must equal canonical owner %q",
			entrypoint.ID,
			entrypoint.ObjectOwner,
			object.Name,
		))
	}
	if entrypoint.RuntimeKind == "projector" || entrypoint.RuntimeKind == "event_handler" ||
		entrypoint.RuntimeKind == "subscription" {
		if !runtimeEntrypointHasLifecycleConsumer(entrypoint, object) {
			issues = append(issues, issue(
				"CONTRACT.RUNTIME_ENTRYPOINT.LIFECYCLE_CONSUMER_MISSING",
				entrypoint.SourcePath,
				"runtime entrypoint %q must bind an object.lifecycle.event_consumers handler; event facts are not authored in operations",
				entrypoint.ID,
			))
		}
	}
	if (entrypoint.RuntimeKind == "internal_port" || entrypoint.RuntimeKind == "external_port") &&
		entrypoint.Idempotency == "" {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.MISSING_IDEMPOTENCY",
			entrypoint.SourcePath,
			"runtime entrypoint %q must declare one idempotency identity",
			entrypoint.ID,
		))
	}
	return bindIssueSubject(entrypoint.ID, issues)
}

func hasTypedEntrypointSuffix(value string) bool {
	for _, suffix := range []string{
		"Facade", "Projector", "Projection", "Appender", "Consumer", "Port",
		"Coordinator", "Recorder", "Orchestrator", "Handler",
	} {
		if strings.HasSuffix(value, suffix) {
			return true
		}
	}
	return false
}

// All 执行 ContractGraph 交叉校验，并在 commercial profile 下强制消费版本化 schema。
func All(contractGraph *graph.ContractGraph, profile Profile, metadataDir string) ([]Issue, error) {
	issues := Run(contractGraph, profile)
	if profile == ProfileCommercial {
		issues = append(
			issues,
			validateOpenAPISnapshots(contractGraph, metadataDir)...,
		)
		schemaIssues, err := MetadataSchemas(metadataDir)
		if err != nil {
			return nil, err
		}
		issues = append(issues, schemaIssues...)
	}
	sortIssues(issues)
	return issues, nil
}

func validateOpenAPISnapshots(
	contractGraph *graph.ContractGraph,
	metadataDir string,
) []Issue {
	snapshots, err := contractopenapi.Generate(contractGraph)
	if err != nil {
		return []Issue{issue(
			"CONTRACT.OPENAPI.GENERATION_FAILED",
			"",
			"%v",
			err,
		)}
	}
	drifts, err := contractopenapi.CompareDirectory(metadataDir, snapshots)
	if err != nil {
		return []Issue{issue(
			"CONTRACT.OPENAPI.INVALID_ARTIFACT",
			"",
			"%v",
			err,
		)}
	}
	issues := make([]Issue, 0, len(drifts))
	for _, drift := range drifts {
		code := "CONTRACT.OPENAPI.STALE_SNAPSHOT"
		switch drift.Kind {
		case contractopenapi.DriftMissing:
			code = "CONTRACT.OPENAPI.MISSING_SNAPSHOT"
		case contractopenapi.DriftOrphan:
			code = "CONTRACT.OPENAPI.ORPHAN_SNAPSHOT"
		}
		issues = append(issues, issue(
			code,
			drift.RelativePath,
			"generated OpenAPI snapshot is %s; run qwq-contract generate-openapi",
			drift.Kind,
		))
	}
	return issues
}

func runtimeEntrypointHasLifecycleConsumer(
	entrypoint ast.RuntimeEntrypoint,
	object ast.Object,
) bool {
	if object.Lifecycle == nil || len(object.Lifecycle.SourceEvents) == 0 {
		return false
	}
	for _, consumer := range object.Lifecycle.EventConsumers {
		if consumer.Name == entrypoint.LocalID && consumer.Kind == entrypoint.RuntimeKind &&
			consumer.Facet == entrypoint.Facet && consumer.Method == entrypoint.FacadeMethod {
			return true
		}
	}
	return false
}

func validateCommercialObject(object ast.Object) []Issue {
	var issues []Issue
	if !object.KindExplicit {
		issues = append(issues, issue(
			"CONTRACT.OBJECT.KIND_NOT_EXPLICIT",
			object.SourcePath,
			"object %q must declare object_kind", object.ID,
		))
	}
	if object.Kind == ast.ObjectKindOwnedEntity && object.AggregateOwner == "" {
		issues = append(issues, issue(
			"CONTRACT.OBJECT.MISSING_AGGREGATE_OWNER",
			object.SourcePath,
			"owned entity %q must declare aggregate_owner", object.ID,
		))
	}
	if object.Kind == ast.ObjectKindOwnedEntity && object.StorageBackend != "" {
		issues = append(issues, issue(
			"CONTRACT.OBJECT.OWNED_ENTITY_HAS_STORE",
			object.SourcePath,
			"owned entity %q must be persisted through aggregate %q, not storage_backend %q",
			object.ID,
			object.AggregateOwner,
			object.StorageBackend,
		))
	}
	for _, member := range object.Members {
		if member.Kind == "" {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.KIND_NOT_EXPLICIT",
				object.SourcePath,
				"member %s.%s must declare object_kind", object.ID, member.Name,
			))
		}
		if member.Cardinality == "1:N" && member.MaxCardinality <= 0 {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.UNBOUNDED_COLLECTION",
				object.SourcePath,
				"member %s.%s is 1:N without max_cardinality; split it or declare a finite bound", object.ID, member.Name,
			))
		}
		if member.Kind != ast.ObjectKindOwnedEntity &&
			member.Kind != ast.ObjectKindValueObject {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.INVALID_KIND",
				object.SourcePath,
				"member %s.%s has kind %q; aggregate members may only be owned_entity or value_object",
				object.ID,
				member.Name,
				member.Kind,
			))
		}
		if member.Kind == ast.ObjectKindOwnedEntity &&
			member.AggregateOwner != object.Name {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.INVALID_AGGREGATE_OWNER",
				object.SourcePath,
				"owned member %s.%s must declare aggregate_owner %q, got %q",
				object.ID,
				member.Name,
				object.Name,
				member.AggregateOwner,
			))
		}
	}
	if object.Lifecycle != nil {
		for _, consumer := range object.Lifecycle.EventConsumers {
			expectedKind := map[string]ast.ObjectKind{
				"projector":     ast.ObjectKindProjection,
				"event_handler": ast.ObjectKindAggregateRoot,
				"subscription":  ast.ObjectKindAppendOnlyFact,
			}[consumer.Kind]
			if expectedKind != "" && object.Kind != expectedKind {
				issues = append(issues, issue(
					"CONTRACT.EVENT.LIFECYCLE_CONSUMER_INVALID_OWNER_KIND",
					object.SourcePath,
					"lifecycle consumer %q kind %q requires object kind %q, got %q",
					consumer.Name,
					consumer.Kind,
					expectedKind,
					object.Kind,
				))
			}
			if !typedBindingIdentifier.MatchString(consumer.Name) ||
				!typedBindingIdentifier.MatchString(consumer.Facet) ||
				!hasTypedEntrypointSuffix(consumer.Facet) {
				issues = append(issues, issue(
					"CONTRACT.EVENT.LIFECYCLE_CONSUMER_INVALID_BINDING",
					object.SourcePath,
					"lifecycle consumer %q must bind a typed production facet",
					consumer.Name,
				))
			}
			if !runtimeFacadeMethodIdentifier.MatchString(consumer.Method) {
				issues = append(issues, issue(
					"CONTRACT.EVENT.LIFECYCLE_CONSUMER_INVALID_METHOD",
					object.SourcePath,
					"lifecycle consumer %q method %q must be lower camel case",
					consumer.Name,
					consumer.Method,
				))
			}
		}
	}
	return issues
}

func validateCommercialOperation(
	operation ast.Operation,
	objectsByID map[string]ast.Object,
	objectsByDomainName map[string]ast.Object,
	identityByDomainName map[string]ast.ObjectIdentity,
) []Issue {
	var issues []Issue
	blocked := false
	if !operation.Commercial.Explicit {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.COMMERCIAL_STATUS_NOT_EXPLICIT",
			operation.SourcePath,
			"operation %q must explicitly declare commercial.status",
			operation.ID,
		))
	}
	switch operation.Commercial.Status {
	case "blocked":
		blocked = true
		if strings.TrimSpace(operation.Commercial.BlockReason) == "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.MISSING_COMMERCIAL_BLOCK_REASON",
				operation.SourcePath,
				"blocked operation %q must declare a fail-closed reason",
				operation.ID,
			))
		}
		if strings.TrimSpace(operation.Commercial.GapID) == "" ||
			strings.TrimSpace(operation.Commercial.TargetStory) == "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.MISSING_COMMERCIAL_GAP_BINDING",
				operation.SourcePath,
				"blocked operation %q must declare commercial.gap_id and target_story",
				operation.ID,
			))
		}
		if strings.TrimSpace(operation.Commercial.GapID) == "APP_CLOUD_OBJECT_MIGRATION" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.GENERIC_COMMERCIAL_GAP_FORBIDDEN",
				operation.SourcePath,
				"blocked operation %q must bind an object-packet-specific commercial gap",
				operation.ID,
			))
		}
	case "ready":
		// Continue with the complete commercial and DDD contract below.
	default:
		return bindIssueSubject(
			operation.ID,
			append(issues, issue(
				"CONTRACT.OPERATION.INVALID_COMMERCIAL_STATUS",
				operation.SourcePath,
				"operation %q commercial status %q must be ready or blocked",
				operation.ID,
				operation.Commercial.Status,
			)),
		)
	}
	if !operation.KindExplicit {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.KIND_NOT_EXPLICIT",
			operation.SourcePath,
			"operation %q must declare application.kind", operation.ID,
		))
	}
	if operation.Facet == "" || operation.FacadeMethod == "" {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_FACADE_BINDING",
			operation.SourcePath,
			"operation %q must declare application.facet and application.method", operation.ID,
		))
	}
	switch operation.Kind {
	case ast.OperationKindCommand:
		expectedMutationTarget := operation.AggregateOwner
		if expectedMutationTarget == "" {
			expectedMutationTarget = operation.AppendSink
		}
		if expectedMutationTarget == "" {
			expectedMutationTarget = operation.LifecycleOwner
		}
		if operation.MutationTarget == "" || operation.InvariantTarget == "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.MISSING_SEMANTIC_TARGET",
				operation.SourcePath,
				"command %q must declare application.mutation_target and application.invariant_target",
				operation.ID,
			))
		}
		if expectedMutationTarget != "" &&
			(operation.MutationTarget != expectedMutationTarget || operation.InvariantTarget != expectedMutationTarget) {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.SEMANTIC_TARGET_MISMATCH",
				operation.SourcePath,
				"command %q mutation/invariant target must both equal canonical owner %q",
				operation.ID,
				expectedMutationTarget,
			))
		}
		commandOwnerCount := 0
		for _, owner := range []string{
			operation.AggregateOwner,
			operation.AppendSink,
			operation.LifecycleOwner,
		} {
			if owner != "" {
				commandOwnerCount++
			}
		}
		if commandOwnerCount == 0 {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.MISSING_COMMAND_TARGET",
				operation.SourcePath,
				"command %q must declare exactly one application.aggregate_owner, application.append_sink, or application.lifecycle_owner",
				operation.ID,
			))
		}
		if commandOwnerCount > 1 {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.AMBIGUOUS_COMMAND_TARGET",
				operation.SourcePath,
				"command %q must declare only one of aggregate_owner, append_sink, or lifecycle_owner",
				operation.ID,
			))
		}
		if operation.Reader != "" || operation.Slice != "" || operation.SessionOwner != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_COMMAND_BINDING",
				operation.SourcePath,
				"command %q must not declare reader, slice, or session_owner",
				operation.ID,
			))
		}
		if operation.AggregateOwner != "" {
			owner, exists := objectsByDomainName[domainObjectKey(
				operation.Domain,
				operation.AggregateOwner,
			)]
			if !exists {
				issues = append(issues, issue(
					"CONTRACT.REFERENCE.UNKNOWN_AGGREGATE_OWNER",
					operation.SourcePath,
					"command %q references unknown aggregate owner %q", operation.ID, operation.AggregateOwner,
				))
			} else {
				if owner.Kind != ast.ObjectKindAggregateRoot {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.INVALID_COMMAND_OWNER_KIND",
						operation.SourcePath,
						"command %q aggregate owner %q has kind %q, want aggregate_root",
						operation.ID,
						owner.ID,
						owner.Kind,
					))
				}
				if owner.ID != operation.ObjectID {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.CROSS_OBJECT_COMMAND_OWNER",
						operation.SourcePath,
						"command %q is declared by %q but owned by %q; move it to the canonical owner packet",
						operation.ID,
						operation.ObjectID,
						owner.ID,
					))
				}
			}
		}
		if operation.AppendSink != "" {
			sink, exists := objectsByDomainName[domainObjectKey(
				operation.Domain,
				operation.AppendSink,
			)]
			if !exists {
				issues = append(issues, issue(
					"CONTRACT.REFERENCE.UNKNOWN_APPEND_SINK",
					operation.SourcePath,
					"command %q references unknown append sink %q",
					operation.ID,
					operation.AppendSink,
				))
			} else {
				if sink.Kind != ast.ObjectKindAppendOnlyFact {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.INVALID_APPEND_SINK_KIND",
						operation.SourcePath,
						"command %q append sink %q has kind %q, want append_only_fact",
						operation.ID,
						sink.ID,
						sink.Kind,
					))
				}
				if sink.ID != operation.ObjectID {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.CROSS_OBJECT_APPEND_SINK",
						operation.SourcePath,
						"command %q is declared by %q but appends to %q; move it to the canonical fact packet",
						operation.ID,
						operation.ObjectID,
						sink.ID,
					))
				}
				if operation.Method != "POST" {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.FACT_MUTATION_FORBIDDEN",
						operation.SourcePath,
						"append-only fact command %q must use POST append/dedupe semantics, not %s",
						operation.ID,
						operation.Method,
					))
				}
			}
		}
		if operation.LifecycleOwner != "" {
			owner, exists := objectsByDomainName[domainObjectKey(
				operation.Domain,
				operation.LifecycleOwner,
			)]
			if !exists {
				issues = append(issues, issue(
					"CONTRACT.REFERENCE.UNKNOWN_LIFECYCLE_OWNER",
					operation.SourcePath,
					"command %q references unknown lifecycle owner %q",
					operation.ID,
					operation.LifecycleOwner,
				))
			} else {
				if owner.ID != operation.ObjectID {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.CROSS_OBJECT_LIFECYCLE_OWNER",
						operation.SourcePath,
						"command %q is declared by %q but recovers lifecycle owner %q; move it to the canonical owner packet",
						operation.ID,
						operation.ObjectID,
						owner.ID,
					))
				}
				if owner.Lifecycle == nil || len(owner.Lifecycle.SourceEvents) == 0 ||
					len(owner.Lifecycle.EventConsumers) == 0 {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.LIFECYCLE_OWNER_WITHOUT_CONSUMER",
						operation.SourcePath,
						"command %q lifecycle owner %q must declare lifecycle.source_events and lifecycle.event_consumers",
						operation.ID,
						owner.ID,
					))
				}
				if operation.Method != "POST" {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.LIFECYCLE_RECOVERY_METHOD",
						operation.SourcePath,
						"lifecycle recovery command %q must use POST",
						operation.ID,
					))
				}
			}
		}
	case ast.OperationKindQuery:
		if operation.MutationTarget != "" || operation.InvariantTarget != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.QUERY_SEMANTIC_TARGET_FORBIDDEN",
				operation.SourcePath,
				"query %q must not declare mutation or invariant targets",
				operation.ID,
			))
		}
		if operation.AggregateOwner != "" || operation.AppendSink != "" ||
			operation.LifecycleOwner != "" || operation.SessionOwner != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_QUERY_BINDING",
				operation.SourcePath,
				"query %q must not declare aggregate_owner, append_sink, lifecycle_owner, or session_owner",
				operation.ID,
			))
		}
		if operation.Reader == "" || operation.Slice == "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.MISSING_QUERY_BINDING",
				operation.SourcePath,
				"query %q must declare application.reader and application.slice", operation.ID,
			))
		} else {
			if !typedBindingIdentifier.MatchString(operation.Reader) ||
				!strings.HasSuffix(operation.Reader, "Reader") {
				issues = append(issues, issue(
					"CONTRACT.OPERATION.INVALID_QUERY_READER",
					operation.SourcePath,
					"query %q reader %q must be a typed *Reader identifier",
					operation.ID,
					operation.Reader,
				))
			}
			if !typedBindingIdentifier.MatchString(operation.Slice) ||
				operation.Slice == "Map" ||
				operation.Slice == "Object" ||
				operation.Slice == "Dynamic" {
				issues = append(issues, issue(
					"CONTRACT.OPERATION.INVALID_QUERY_SLICE",
					operation.SourcePath,
					"query %q slice %q must be a concrete typed identifier",
					operation.ID,
					operation.Slice,
				))
			}
		}
	case ast.OperationKindSession:
		if operation.MutationTarget != "" || operation.InvariantTarget != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.SESSION_SEMANTIC_TARGET_FORBIDDEN",
				operation.SourcePath,
				"session operation %q must not declare mutation or invariant targets",
				operation.ID,
			))
		}
		if operation.AggregateOwner != "" ||
			operation.AppendSink != "" ||
			operation.LifecycleOwner != "" ||
			operation.Reader != "" ||
			operation.Slice != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_SESSION_BINDING",
				operation.SourcePath,
				"session operation %q must not declare aggregate_owner, append_sink, lifecycle_owner, or query reader/slice",
				operation.ID,
			))
		}
		if operation.SessionOwner == "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.MISSING_SESSION_OWNER",
				operation.SourcePath,
				"session operation %q must declare application.session_owner",
				operation.ID,
			))
		} else if owner, exists := objectsByDomainName[domainObjectKey(
			operation.Domain,
			operation.SessionOwner,
		)]; !exists {
			issues = append(issues, issue(
				"CONTRACT.REFERENCE.UNKNOWN_SESSION_OWNER",
				operation.SourcePath,
				"session operation %q references unknown session owner %q",
				operation.ID,
				operation.SessionOwner,
			))
		} else {
			if owner.Kind != ast.ObjectKindRuntimeSession {
				issues = append(issues, issue(
					"CONTRACT.OPERATION.INVALID_SESSION_OWNER_KIND",
					operation.SourcePath,
					"session operation %q owner %q has kind %q, want runtime_session",
					operation.ID,
					owner.ID,
					owner.Kind,
				))
			}
			if owner.ID != operation.ObjectID {
				issues = append(issues, issue(
					"CONTRACT.OPERATION.CROSS_OBJECT_SESSION_OWNER",
					operation.SourcePath,
					"session operation %q is declared by %q but owned by %q",
					operation.ID,
					operation.ObjectID,
					owner.ID,
				))
			}
		}
	}
	if declared, exists := objectsByID[operation.ObjectID]; exists &&
		declared.Kind == ast.ObjectKindProjection &&
		operation.Kind == ast.OperationKindCommand {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.PROJECTION_COMMAND_FORBIDDEN",
			operation.SourcePath,
			"projection %q cannot declare command %q",
			declared.ID,
			operation.ID,
		))
	}
	switch operation.Concurrency.VersionPrecondition {
	case ast.VersionPreconditionNone:
		// The default is server-owned concurrency. Callers must not send a
		// resource version unless the operation explicitly opts into If-Match.
	case ast.VersionPreconditionIfMatch:
		if operation.Kind != ast.OperationKindCommand ||
			operation.AggregateOwner == "" ||
			operation.AppendSink != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_VERSION_PRECONDITION_TARGET",
				operation.SourcePath,
				"operation %q may use if_match only for an aggregate-root command",
				operation.ID,
			))
			break
		}
		ownerKey := domainObjectKey(
			operation.Domain,
			operation.AggregateOwner,
		)
		_, ownerExists := objectsByDomainName[ownerKey]
		identity, identityExists := identityByDomainName[ownerKey]
		if !ownerExists || !identityExists ||
			(identity.VersionSource != "field" &&
				identity.VersionSource != "store_commit") {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_VERSION_PRECONDITION_SOURCE",
				operation.SourcePath,
				"operation %q if_match owner must use field or store_commit version source",
				operation.ID,
			))
		}
	default:
		issues = append(issues, issue(
			"CONTRACT.OPERATION.INVALID_VERSION_PRECONDITION",
			operation.SourcePath,
			"operation %q version_precondition %q must be if_match or omitted",
			operation.ID,
			operation.Concurrency.VersionPrecondition,
		))
	}
	if operation.ActorRequirement == "" || operation.ActorRequirement == "unspecified" {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_ACTOR",
			operation.SourcePath,
			"operation %q must declare actor requirement", operation.ID,
		))
	}
	if blocked {
		return bindIssueSubject(operation.ID, issues)
	}
	if operation.AuthMode == "deny" {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_AUTH_MODE",
			operation.SourcePath,
			"commercial-ready operation %q must declare auth/security.auth_mode",
			operation.ID,
		))
	}
	if operation.Principal == "" || operation.OwnershipPolicy == "" {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_AUTHORIZATION",
			operation.SourcePath,
			"commercial-ready operation %q must declare authorization principal and ownership_policy",
			operation.ID,
		))
	}
	if operation.Reliability.TimeoutMilliseconds <= 0 ||
		operation.Reliability.Cancellation == "" ||
		operation.Reliability.RetryMode == "" ||
		operation.Reliability.MaxAttempts <= 0 ||
		operation.Reliability.Idempotency == "" {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_RELIABILITY",
			operation.SourcePath,
			"commercial-ready operation %q must declare timeout/cancellation/retry/max_attempts/idempotency",
			operation.ID,
		))
	}
	if pagination := operation.Pagination; pagination != nil {
		if pagination.DefaultItems <= 0 || pagination.MaximumItems <= 0 {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_PAGINATION_BUDGET",
				operation.SourcePath,
				"operation %q pagination default_items and maximum_items must be positive",
				operation.ID,
			))
		} else if pagination.DefaultItems > pagination.MaximumItems {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_PAGINATION_BUDGET",
				operation.SourcePath,
				"operation %q pagination default_items must not exceed maximum_items",
				operation.ID,
			))
		}
	}
	if responseAdmission := operation.ResponseAdmission; responseAdmission != nil &&
		responseAdmission.MaximumBodyBytes < 1024 {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.INVALID_RESPONSE_ADMISSION_BUDGET",
			operation.SourcePath,
			"operation %q response maximum_body_bytes must be at least 1024",
			operation.ID,
		))
	}
	unsafeMethod := operation.Method == "POST" ||
		operation.Method == "PUT" ||
		operation.Method == "PATCH" ||
		operation.Method == "DELETE"
	if operation.Reliability.RetryMode == "none" &&
		operation.Reliability.MaxAttempts > 1 {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.INVALID_RETRY_BUDGET",
			operation.SourcePath,
			"operation %q retry_mode none requires max_attempts=1",
			operation.ID,
		))
	}
	if unsafeMethod &&
		operation.Reliability.MaxAttempts > 1 &&
		operation.Reliability.Idempotency == "none" {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.UNSAFE_RETRY_WITHOUT_IDEMPOTENCY",
			operation.SourcePath,
			"operation %q retries an unsafe method without a stable idempotency key",
			operation.ID,
		))
	}
	if len(operation.ErrorCodes) == 0 {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_ERROR_CODES",
			operation.SourcePath,
			"commercial-ready operation %q must declare error_codes",
			operation.ID,
		))
	}
	if operation.Privacy.RequestClassification == "" ||
		operation.Privacy.ResponseClassification == "" ||
		operation.Privacy.LogPolicy == "" {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_PRIVACY",
			operation.SourcePath,
			"commercial-ready operation %q must declare request/response classification and log policy",
			operation.ID,
		))
	}
	if operation.Telemetry.Metric == "" || !operation.Telemetry.Trace {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_TELEMETRY",
			operation.SourcePath,
			"commercial-ready operation %q must declare metric and trace=true",
			operation.ID,
		))
	}
	if operation.SLO.LatencyP95Milliseconds <= 0 ||
		operation.SLO.AvailabilityPercent <= 0 {
		issues = append(issues, issue(
			"CONTRACT.OPERATION.MISSING_SLO",
			operation.SourcePath,
			"commercial-ready operation %q must declare latency_p95_ms and availability_percent",
			operation.ID,
		))
	}
	if operation.ClientContract != nil {
		issues = append(issues, validateClientContract(operation)...)
	}
	return bindIssueSubject(operation.ID, issues)
}

func bindIssueSubject(subjectID string, issues []Issue) []Issue {
	for index := range issues {
		if issues[index].SubjectID == "" {
			issues[index].SubjectID = subjectID
		}
	}
	return issues
}

func successStatusIssues(operation ast.Operation) []Issue {
	status := operation.SuccessStatus
	if status == 0 {
		return nil
	}
	responseKind := strings.TrimSpace(operation.ResponseBodyKind)
	responseEntity := strings.TrimSpace(operation.ResponseEntity)
	if status != 200 && status != 201 && status != 202 && status != 204 {
		return []Issue{issue(
			"CONTRACT.OPERATION.INVALID_SUCCESS_STATUS",
			operation.SourcePath,
			"operation %q success_status must be one of 200, 201, 202 or 204",
			operation.ID,
		)}
	}
	if responseKind == "upgrade" {
		return []Issue{issue(
			"CONTRACT.OPERATION.SUCCESS_STATUS_FORBIDDEN",
			operation.SourcePath,
			"upgrade operation %q has protocol status 101 and cannot declare success_status",
			operation.ID,
		)}
	}
	if responseKind == "ack" && status != 204 {
		return []Issue{issue(
			"CONTRACT.OPERATION.SUCCESS_STATUS_BODY_MISMATCH",
			operation.SourcePath,
			"ack operation %q must use success_status 204; use response_body_kind object for a typed receipt",
			operation.ID,
		)}
	}
	if status == 204 && responseEntity != "" {
		return []Issue{issue(
			"CONTRACT.OPERATION.SUCCESS_STATUS_BODY_MISMATCH",
			operation.SourcePath,
			"operation %q cannot combine success_status 204 with response_entity %q",
			operation.ID,
			responseEntity,
		)}
	}
	if status != 204 && responseKind != "page" && responseKind != "object" &&
		responseEntity == "" {
		return []Issue{issue(
			"CONTRACT.OPERATION.SUCCESS_STATUS_BODY_MISMATCH",
			operation.SourcePath,
			"operation %q success_status %d requires response_body_kind object/page and a typed response_entity",
			operation.ID,
			status,
		)}
	}
	return nil
}

// streamBudgetIssues keeps the two timeout vocabularies from overlapping.
//
// A unary operation declares reliability.timeout_ms and nothing else: one
// budget describes its whole life. A streaming operation declares
// reliability.stream_budget and nothing else: handshake, idle and connection
// lifetime are independent limits, and enforcing any single one of them as
// "the timeout" is wrong in both directions — clamping the lifetime truncates
// healthy long work, while clamping idle at the lifetime value never detects a
// stalled producer. timeout_ms is therefore derived from max_duration_ms by
// load, not authored, so the connection ceiling stays one number.
func streamBudgetIssues(operation ast.Operation) []Issue {
	budget := operation.Reliability.StreamBudget
	isStreaming := strings.EqualFold(
		strings.TrimSpace(operation.Transport),
		"sse",
	) || strings.EqualFold(
		strings.TrimSpace(operation.ResponseBodyKind),
		"upgrade",
	)
	if !isStreaming {
		if budget == nil {
			return nil
		}
		return []Issue{issue(
			"CONTRACT.RELIABILITY.STREAM_BUDGET_FORBIDDEN",
			operation.SourcePath,
			"non-streaming operation %q cannot declare reliability.stream_budget; its whole-request bound is reliability.timeout_ms",
			operation.ID,
		)}
	}
	if budget == nil {
		return []Issue{issue(
			"CONTRACT.RELIABILITY.STREAM_BUDGET_REQUIRED",
			operation.SourcePath,
			"streaming operation %q must declare reliability.stream_budget handshake_ms/idle_ms/max_duration_ms; reliability.timeout_ms cannot bound a long-lived connection",
			operation.ID,
		)}
	}
	var issues []Issue
	if operation.Reliability.TimeoutExplicit {
		issues = append(issues, issue(
			"CONTRACT.RELIABILITY.STREAM_TIMEOUT_FORBIDDEN",
			operation.SourcePath,
			"streaming operation %q cannot author reliability.timeout_ms; it is derived from stream_budget.max_duration_ms",
			operation.ID,
		))
	}
	if budget.HandshakeMilliseconds <= 0 ||
		budget.IdleMilliseconds <= 0 ||
		budget.MaxDurationMilliseconds <= 0 {
		issues = append(issues, issue(
			"CONTRACT.RELIABILITY.INVALID_STREAM_BUDGET",
			operation.SourcePath,
			"streaming operation %q must declare positive handshake_ms, idle_ms and max_duration_ms",
			operation.ID,
		))
		return issues
	}
	// A bound that can never fire before the connection is closed anyway is a
	// dead clause, and a dead clause reads like enforcement without being it.
	if budget.HandshakeMilliseconds >= budget.MaxDurationMilliseconds ||
		budget.IdleMilliseconds >= budget.MaxDurationMilliseconds {
		issues = append(issues, issue(
			"CONTRACT.RELIABILITY.UNREACHABLE_STREAM_BUDGET",
			operation.SourcePath,
			"streaming operation %q must keep handshake_ms and idle_ms strictly below max_duration_ms, otherwise neither bound can ever fire",
			operation.ID,
		))
	}
	return issues
}

func validateClientContract(operation ast.Operation) []Issue {
	contract := operation.ClientContract
	if contract == nil {
		return nil
	}
	if contract.DartImport == "" ||
		contract.ResponseType == "" ||
		contract.ResponseDecoder == "" {
		return []Issue{issue(
			"CONTRACT.OPERATION.INVALID_CLIENT_CONTRACT",
			operation.SourcePath,
			"operation %q client_contract must declare response import, type and decoder; request ABI is generated from request_entity",
			operation.ID,
		)}
	}
	return nil
}

func domainObjectKey(domain, name string) string {
	return strings.TrimSpace(domain) + "\x00" + strings.TrimSpace(name)
}

func allowedMethod(method string) bool {
	switch method {
	case "GET", "POST", "PUT", "PATCH", "DELETE":
		return true
	default:
		return false
	}
}

func allowedPath(path string) bool {
	switch path {
	case "/health", "/healthz", "/metrics", "/livez", "/startupz":
		return true
	}
	if path == "" || path[0] != '/' {
		return false
	}
	for _, segment := range strings.Split(strings.Trim(path, "/"), "/") {
		if isAPIVersionSegment(segment) {
			return false
		}
	}
	if strings.HasPrefix(path, "/internal/") || strings.HasPrefix(path, "/callbacks/") {
		return len(path) > len("/internal/") && path != "/internal/" && path != "/callbacks/"
	}
	second := path[1]
	return (second >= 'a' && second <= 'z') || (second >= 'A' && second <= 'Z')
}

func isAPIVersionSegment(segment string) bool {
	if len(segment) < 2 || segment[0] != 'v' {
		return false
	}
	for i := 1; i < len(segment); i++ {
		if segment[i] < '0' || segment[i] > '9' {
			return false
		}
	}
	return true
}

func issue(code, sourcePath, format string, args ...any) Issue {
	return Issue{
		Code:       code,
		SourcePath: sourcePath,
		Message:    fmt.Sprintf(format, args...),
	}
}
