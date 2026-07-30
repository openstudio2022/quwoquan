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
	operationCountByObject := map[string]int{}
	for _, operation := range contractGraph.Operations {
		operationCountByObject[operation.ObjectID]++
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
		} else if object.Kind != ast.ObjectKindRuntimeSession {
			issues = append(issues, issue(
				"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_OWNER_KIND",
				entrypoint.SourcePath,
				"runtime entrypoint %q owner %q has kind %q, want runtime_session",
				entrypoint.ID,
				entrypoint.ObjectID,
				object.Kind,
			))
		}
		if operationCountByObject[entrypoint.ObjectID] != 0 {
			issues = append(issues, issue(
				"CONTRACT.RUNTIME_ENTRYPOINT.HTTP_DUAL_TRACK",
				entrypoint.SourcePath,
				"object %q must own either HTTP api_routes or runtime_entrypoints, not both",
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
	if entrypoint.RuntimeKind != "middleware" {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_KIND",
			entrypoint.SourcePath,
			"runtime entrypoint %q kind %q must be middleware",
			entrypoint.ID,
			entrypoint.RuntimeKind,
		))
	}
	if entrypoint.Phase != "post_authorization_pre_owner_proxy" {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_PHASE",
			entrypoint.SourcePath,
			"runtime entrypoint %q phase %q must be post_authorization_pre_owner_proxy",
			entrypoint.ID,
			entrypoint.Phase,
		))
	}
	if entrypoint.ApplicationKind != ast.OperationKindSession {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_APPLICATION_KIND",
			entrypoint.SourcePath,
			"runtime entrypoint %q application.kind %q must be session",
			entrypoint.ID,
			entrypoint.ApplicationKind,
		))
	}
	if !typedBindingIdentifier.MatchString(entrypoint.Facet) ||
		!strings.HasSuffix(entrypoint.Facet, "Facade") {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_FACADE",
			entrypoint.SourcePath,
			"runtime entrypoint %q facet %q must be a typed *Facade identifier",
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
	if entrypoint.SessionOwner == "" || entrypoint.SessionOwner != object.Name {
		issues = append(issues, issue(
			"CONTRACT.RUNTIME_ENTRYPOINT.INVALID_SESSION_OWNER",
			entrypoint.SourcePath,
			"runtime entrypoint %q session_owner %q must equal canonical owner %q",
			entrypoint.ID,
			entrypoint.SessionOwner,
			object.Name,
		))
	}
	return bindIssueSubject(entrypoint.ID, issues)
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
		if operation.AggregateOwner == "" && operation.AppendSink == "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.MISSING_COMMAND_TARGET",
				operation.SourcePath,
				"command %q must declare exactly one application.aggregate_owner or application.append_sink",
				operation.ID,
			))
		}
		if operation.AggregateOwner != "" && operation.AppendSink != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.AMBIGUOUS_COMMAND_TARGET",
				operation.SourcePath,
				"command %q must not declare aggregate_owner and append_sink together",
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
	case ast.OperationKindQuery:
		if operation.MutationTarget != "" || operation.InvariantTarget != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.QUERY_SEMANTIC_TARGET_FORBIDDEN",
				operation.SourcePath,
				"query %q must not declare mutation or invariant targets",
				operation.ID,
			))
		}
		if operation.AggregateOwner != "" || operation.AppendSink != "" || operation.SessionOwner != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_QUERY_BINDING",
				operation.SourcePath,
				"query %q must not declare aggregate_owner, append_sink, or session_owner",
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
			operation.Reader != "" ||
			operation.Slice != "" {
			issues = append(issues, issue(
				"CONTRACT.OPERATION.INVALID_SESSION_BINDING",
				operation.SourcePath,
				"session operation %q must not declare aggregate_owner, append_sink, or query reader/slice",
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
