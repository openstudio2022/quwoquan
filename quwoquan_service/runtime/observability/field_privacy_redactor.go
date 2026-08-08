package runtimeobservability

import (
	"fmt"
	"reflect"
	"sort"
	"strings"
	"unicode/utf8"
)

// CatalogFieldPrivacyPolicy is the runtime projection of object-local
// privacy.yaml#app_log_policy. The generated catalog registers the complete
// list during init; runtime code never carries a handwritten field roster.
type CatalogFieldPrivacyPolicy struct {
	ObjectID       string
	Field          string
	Classification string
	Action         string
	MaskStrategy   string
	TruncateChars  int
	Explicit       bool
	Visibility     []string
}

var catalogFieldPrivacyPolicies []CatalogFieldPrivacyPolicy

func registerCatalogFieldPrivacyPolicies(values []CatalogFieldPrivacyPolicy) {
	catalogFieldPrivacyPolicies = cloneCatalogFieldPrivacyPolicies(values)
	sort.Slice(catalogFieldPrivacyPolicies, func(left, right int) bool {
		return catalogFieldPrivacyPolicies[left].ObjectID+"\x00"+
			catalogFieldPrivacyPolicies[left].Field <
			catalogFieldPrivacyPolicies[right].ObjectID+"\x00"+
				catalogFieldPrivacyPolicies[right].Field
	})
}

// CatalogFieldPrivacyPolicies returns an immutable snapshot for drift tests and
// runtime diagnostics. Callers cannot mutate the enforcement registry.
func CatalogFieldPrivacyPolicies() []CatalogFieldPrivacyPolicy {
	return cloneCatalogFieldPrivacyPolicies(catalogFieldPrivacyPolicies)
}

func redactCatalogFieldPrivacyAttribute(
	objectID string,
	key string,
	value any,
) (any, bool) {
	policy, ok := catalogFieldPrivacyPolicyFor(objectID, key)
	if !ok {
		return value, true
	}
	if !catalogFieldVisibilityAllowsFirstPartyServiceInternal(policy.Visibility) {
		return nil, false
	}
	switch policy.Action {
	case "allow":
		return value, true
	case "drop":
		return nil, false
	case "mask":
		return coarseCatalogFieldMask(value, policy.MaskStrategy), true
	case "truncate":
		return truncateCatalogFieldText(fmt.Sprint(value), policy.TruncateChars), true
	case "count_only":
		return catalogFieldValueCount(value), true
	case "drop_if_gt_100chars":
		text := fmt.Sprint(value)
		if utf8.RuneCountInString(text) > 100 {
			return nil, false
		}
		return text, true
	default:
		// Unknown generated actions fail closed even if a stale runtime somehow
		// bypasses generator validation.
		return nil, false
	}
}

func cloneCatalogFieldPrivacyPolicies(
	values []CatalogFieldPrivacyPolicy,
) []CatalogFieldPrivacyPolicy {
	result := append([]CatalogFieldPrivacyPolicy(nil), values...)
	for index := range result {
		result[index].Visibility = append([]string(nil), result[index].Visibility...)
	}
	return result
}

func catalogFieldVisibilityAllowsFirstPartyServiceInternal(
	visibility []string,
) bool {
	if len(visibility) == 0 {
		return true
	}
	for _, audience := range visibility {
		if audience == "all" || audience == "first_party_service_internal" {
			return true
		}
	}
	return false
}

func catalogFieldPrivacyPolicyFor(
	objectID string,
	key string,
) (CatalogFieldPrivacyPolicy, bool) {
	normalized := normalizeRuntimeLogKey(key)
	var fallback CatalogFieldPrivacyPolicy
	found := false
	for _, policy := range catalogFieldPrivacyPolicies {
		if normalizeRuntimeLogKey(policy.Field) != normalized {
			continue
		}
		if objectID != "" && policy.ObjectID == objectID {
			return policy, true
		}
		if objectID == "" && !policy.Explicit {
			continue
		}
		if !found || catalogFieldPrivacyPolicyRank(policy) > catalogFieldPrivacyPolicyRank(fallback) ||
			(catalogFieldPrivacyPolicyRank(policy) == catalogFieldPrivacyPolicyRank(fallback) &&
				policy.Action == "truncate" &&
				policy.TruncateChars < fallback.TruncateChars) {
			fallback = policy
			found = true
		}
	}
	return fallback, found
}

func catalogFieldPrivacyPolicyRank(policy CatalogFieldPrivacyPolicy) int {
	switch policy.Action {
	case "drop":
		return 6
	case "drop_if_gt_100chars":
		return 5
	case "mask":
		return 4
	case "count_only":
		return 3
	case "truncate":
		return 2
	case "allow":
		return 1
	default:
		return 7
	}
}

func coarseCatalogFieldMask(value any, strategy string) any {
	mapValue, ok := value.(map[string]any)
	if !ok {
		return "***"
	}
	allowed := map[string]struct{}{
		"country": {}, "countryName": {}, "province": {}, "provinceName": {},
	}
	if strategy == "city_level_only" {
		allowed["city"] = struct{}{}
		allowed["cityName"] = struct{}{}
	}
	result := map[string]any{}
	for key, item := range mapValue {
		if _, keep := allowed[key]; keep {
			result[key] = redactRuntimeLogText(fmt.Sprint(item))
		}
	}
	if len(result) == 0 {
		return "***"
	}
	return result
}

func truncateCatalogFieldText(value string, maxRunes int) string {
	if maxRunes <= 0 {
		return ""
	}
	runes := []rune(redactRuntimeLogText(value))
	if len(runes) <= maxRunes {
		return string(runes)
	}
	return string(runes[:maxRunes]) + "…"
}

func catalogFieldValueCount(value any) int {
	if value == nil {
		return 0
	}
	reflected := reflect.ValueOf(value)
	switch reflected.Kind() {
	case reflect.Array, reflect.Chan, reflect.Map, reflect.Slice, reflect.String:
		return reflected.Len()
	default:
		return 0
	}
}

func runtimeLogObjectID(operationID string) string {
	parts := strings.Split(strings.TrimSpace(operationID), ".")
	if len(parts) < 3 {
		return ""
	}
	return parts[0] + "." + parts[1]
}
