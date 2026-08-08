package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

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
				if !oneOf(owner.Kind, commandOwnerKinds...) {
					issues = append(issues, issue(
						"CONTRACT.OPERATION.INVALID_COMMAND_OWNER_KIND",
						operation.SourcePath,
						"command %q aggregate owner %q has kind %q, want one of %v",
						operation.ID,
						owner.ID,
						owner.Kind,
						commandOwnerKinds,
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
