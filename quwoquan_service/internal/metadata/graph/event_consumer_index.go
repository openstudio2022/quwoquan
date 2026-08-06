package graph

import (
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

// BuildEventConsumerIndex derives the reverse event graph from the only
// authored consumer edge: object.yaml.lifecycle.source_events[]. Producer
// contracts and operations/runtime_entrypoints never own or mirror this list.
func BuildEventConsumerIndex(
	objects []ast.Object,
) map[string][]string {
	sets := map[string]map[string]struct{}{}
	for _, object := range objects {
		lifecycle := object.Lifecycle
		if lifecycle == nil || len(lifecycle.EventConsumers) == 0 {
			continue
		}
		consumerRef := ast.CanonicalConsumerRef(object)
		if consumerRef == "" {
			continue
		}
		for _, sourceEvent := range lifecycle.SourceEvents {
			eventRef := strings.TrimSpace(sourceEvent)
			if eventRef == "" {
				continue
			}
			if sets[eventRef] == nil {
				sets[eventRef] = map[string]struct{}{}
			}
			sets[eventRef][consumerRef] = struct{}{}
		}
	}
	result := make(map[string][]string, len(sets))
	for eventRef, consumers := range sets {
		for consumerRef := range consumers {
			result[eventRef] = append(result[eventRef], consumerRef)
		}
		sort.Strings(result[eventRef])
	}
	return result
}
