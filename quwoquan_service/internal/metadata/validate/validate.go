package validate

import (
	"fmt"
	"regexp"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	contractopenapi "quwoquan_service/internal/metadata/openapi"
)

var typedBindingIdentifier = regexp.MustCompile(`^[A-Z][A-Za-z0-9]*$`)

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
	for _, operation := range contractGraph.Operations {
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
				"operation %q path %q must use /v1, /internal/v1 or /callbacks/v1", operation.ID, operation.PathTemplate,
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
				validateCommercialOperation(
					operation,
					objectsByID,
					objectsByDomainName,
				)...,
			)
		}
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
	}

	sortIssues(issues)
	return issues
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
		contract.RequestType == "" ||
		contract.ResponseType == "" ||
		contract.RequestEncoder == "" ||
		contract.ResponseDecoder == "" {
		return []Issue{issue(
			"CONTRACT.OPERATION.INVALID_CLIENT_CONTRACT",
			operation.SourcePath,
			"operation %q client_contract must declare import, request/response types and codecs",
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
	case "/health", "/healthz", "/metrics":
		return true
	}
	for _, prefix := range []string{"/v1/", "/internal/v1/", "/callbacks/v1/"} {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}

func issue(code, sourcePath, format string, args ...any) Issue {
	return Issue{
		Code:       code,
		SourcePath: sourcePath,
		Message:    fmt.Sprintf(format, args...),
	}
}
