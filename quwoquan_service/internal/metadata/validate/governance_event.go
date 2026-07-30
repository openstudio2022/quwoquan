package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validateEventGovernance(contractGraph *graph.ContractGraph) []Issue {
	entities := map[string]struct{}{}
	localEntityFields := map[string]map[string]struct{}{}
	for _, field := range contractGraph.Governance.Fields {
		entities[field.Entity] = struct{}{}
		key := field.ObjectID + "\x00" + field.Entity
		if localEntityFields[key] == nil {
			localEntityFields[key] = map[string]struct{}{}
		}
		localEntityFields[key][field.Name] = struct{}{}
	}
	for _, object := range contractGraph.Objects {
		entities[object.Name] = struct{}{}
	}
	for _, projection := range contractGraph.Projections {
		entities[projection.ReadModel] = struct{}{}
	}
	var issues []Issue
	producedEvents := map[string][]string{}
	for _, packet := range contractGraph.Governance.Objects {
		for _, event := range packet.Events {
			producedEvents[event.Name] = append(producedEvents[event.Name], packet.ObjectID)
		}
	}
	for name, producers := range producedEvents {
		if len(producers) <= 1 {
			continue
		}
		issues = append(issues, issue(
			"CONTRACT.EVENT.DUPLICATE_PRODUCER",
			"contracts/**/events.yaml",
			"event %q has multiple canonical producers: %s",
			name,
			strings.Join(producers, ", "),
		))
	}
	objectsByDomainName := map[string]ast.Object{}
	for _, object := range contractGraph.Objects {
		objectsByDomainName[object.Domain+"\x00"+object.Name] = object
	}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		for _, boundary := range objectMap.Objects {
			object, exists := objectsByDomainName[objectMap.Domain+"\x00"+boundary.CanonicalObject]
			if !exists {
				continue
			}
			for _, subscription := range boundary.EventConsumers {
				if len(producedEvents[subscription]) > 0 {
					continue
				}
				issues = append(issues, issue(
					"CONTRACT.EVENT.SUBSCRIPTION_WITHOUT_PRODUCER",
					strings.TrimSuffix(object.SourcePath, "object.yaml")+"events.yaml",
					"object %q subscribes to event %q but ContractGraph has no producer",
					object.ID,
					subscription,
				))
			}
		}
	}
	for _, packet := range contractGraph.Governance.Objects {
		for _, event := range packet.Events {
			if event.PayloadEntity == "" {
				issues = append(issues, issue(
					"CONTRACT.EVENT.MISSING_PAYLOAD_ENTITY",
					event.SourcePath,
					"event %q must declare payload_entity",
					event.Name,
				))
			} else if _, exists := entities[event.PayloadEntity]; !exists {
				issues = append(issues, issue(
					"CONTRACT.EVENT.UNKNOWN_PAYLOAD_ENTITY",
					event.SourcePath,
					"event %q references unknown payload_entity %q",
					event.Name,
					event.PayloadEntity,
				))
			}
			if declaredFields := localEntityFields[packet.ObjectID+"\x00"+event.PayloadEntity]; event.PayloadShape == "exact" &&
				len(declaredFields) > 0 && len(event.PayloadFields) > 0 {
				seen := map[string]struct{}{}
				for _, field := range event.PayloadFields {
					field = strings.TrimSpace(field)
					if _, duplicate := seen[field]; duplicate {
						issues = append(issues, issue(
							"CONTRACT.EVENT.DUPLICATE_PAYLOAD_FIELD",
							event.SourcePath,
							"event %q declares payload field %q more than once",
							event.Name,
							field,
						))
						continue
					}
					seen[field] = struct{}{}
					if _, exists := declaredFields[field]; !exists {
						issues = append(issues, issue(
							"CONTRACT.EVENT.UNKNOWN_PAYLOAD_FIELD",
							event.SourcePath,
							"event %q payload field %q is absent from %q",
							event.Name,
							field,
							event.PayloadEntity,
						))
					}
				}
				for field := range declaredFields {
					if _, exists := seen[field]; !exists {
						issues = append(issues, issue(
							"CONTRACT.EVENT.MISSING_PAYLOAD_FIELD",
							event.SourcePath,
							"event %q omits payload entity field %q from payload_fields",
							event.Name,
							field,
						))
					}
				}
			}
			outbox := strings.Contains(strings.ToLower(event.Channel), "outbox")
			if outbox && len(event.Consumers) == 0 {
				issues = append(issues, issue(
					"CONTRACT.EVENT.OUTBOX_WITHOUT_CONSUMER",
					event.SourcePath,
					"outbox event %q must declare at least one consumer",
					event.Name,
				))
			} else if !outbox && len(event.Consumers) == 0 &&
				event.NoConsumerReason == "" {
				issues = append(issues, issue(
					"CONTRACT.EVENT.MISSING_NO_CONSUMER_REASON",
					event.SourcePath,
					"event %q without consumers must declare no_consumer_reason",
					event.Name,
				))
			}
			if len(event.Consumers) > 0 && event.NoConsumerReason != "" {
				issues = append(issues, issue(
					"CONTRACT.EVENT.STALE_NO_CONSUMER_REASON",
					event.SourcePath,
					"event %q has consumers and must remove no_consumer_reason",
					event.Name,
				))
			}
		}
	}
	return issues
}
