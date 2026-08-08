package validate

import (
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// validateAuthoritativeFieldOwnership rejects a business-state name owned by
// aggregate roots in two bounded contexts of the same domain. Bounded-context
// local identity, lifecycle timestamps and concurrency fields are deliberately
// excluded: equal technical names there describe independent local facts, not
// competing business truth.
func validateAuthoritativeFieldOwnership(contractGraph *graph.ContractGraph) []Issue {
	type owner struct {
		object  string
		context string
		source  string
	}
	owners := map[string][]owner{}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		for _, object := range objectMap.Objects {
			// process_manager 与 aggregate_root 同为权威状态所有者，同一 domain 的
			// 两个上下文不得各自持有同名业务状态。
			if object.ObjectKind != ast.ObjectKindAggregateRoot &&
				object.ObjectKind != ast.ObjectKindProcessManager {
				continue
			}
			for _, field := range object.FieldRoles["authoritative_state"] {
				field = strings.TrimSpace(field)
				if !isCrossContextBusinessStateName(field) {
					continue
				}
				key := objectMap.Domain + "\x00" + field
				owners[key] = append(owners[key], owner{
					object:  object.CanonicalObject,
					context: object.BoundedContext,
					source:  object.SourceDocument,
				})
			}
		}
	}

	var issues []Issue
	for key, candidates := range owners {
		contexts := map[string]struct{}{}
		for _, candidate := range candidates {
			contexts[candidate.context] = struct{}{}
		}
		if len(contexts) < 2 {
			continue
		}
		parts := strings.SplitN(key, "\x00", 2)
		field := parts[1]
		labels := make([]string, 0, len(candidates))
		for _, candidate := range candidates {
			labels = append(labels, candidate.context+"/"+candidate.object)
		}
		sort.Strings(labels)
		issues = append(issues, issue(
			"CONTRACT.FIELD.CROSS_CONTEXT_AUTHORITATIVE_DUPLICATE",
			candidates[0].source,
			"domain %q authoritative field %q is owned by aggregate roots in multiple bounded contexts: %s",
			parts[0],
			field,
			strings.Join(labels, ", "),
		))
	}
	return issues
}

func isCrossContextBusinessStateName(field string) bool {
	field = strings.TrimSpace(field)
	if field == "" || isIdentityLikeField(field) || strings.HasSuffix(field, "At") ||
		strings.HasSuffix(field, "Digest") {
		return false
	}
	switch field {
	case "version", "status", "state", "type", "source", "channel", "isActive":
		return false
	default:
		return true
	}
}
