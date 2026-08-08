package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validateEventGovernance(contractGraph *graph.ContractGraph) []Issue {
	entities := map[string]struct{}{}
	objectsByID := map[string]ast.Object{}
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
		objectsByID[object.ID] = object
		entities[object.Name] = struct{}{}
	}
	for _, projection := range contractGraph.Projections {
		entities[projection.ReadModel] = struct{}{}
	}
	var issues []Issue
	producedEvents := map[string][]ast.EventDefinition{}
	wireTypeOwners := map[string]string{}
	fieldVisibility := map[string]map[string][]string{}
	for _, packet := range contractGraph.Governance.Objects {
		if packet.Privacy != nil {
			fieldVisibility[packet.ObjectID] = map[string][]string{}
			for _, policy := range packet.Privacy.Document.FieldVisibility {
				fieldVisibility[packet.ObjectID][strings.TrimSpace(policy.Field)] =
					append([]string(nil), policy.Visibility...)
			}
		}
		for _, event := range packet.Events {
			eventRef := ast.CanonicalEventRef(packet.ObjectID, event.Name)
			producedEvents[eventRef] = append(producedEvents[eventRef], event)
			wireType := strings.TrimSpace(event.WireEventType)
			if event.DeliverySemantics == "transactional_outbox" {
				if wireType == "" {
					issues = append(issues, issue(
						"CONTRACT.EVENT.MISSING_WIRE_EVENT_TYPE",
						event.SourcePath,
						"transactional_outbox event_ref %q must declare its actual wire_event_type",
						eventRef,
					))
				} else if previous, duplicate := wireTypeOwners[wireType]; duplicate {
					issues = append(issues, issue(
						"CONTRACT.EVENT.DUPLICATE_WIRE_EVENT_TYPE",
						event.SourcePath,
						"wire_event_type %q is owned by both %q and %q",
						wireType,
						previous,
						eventRef,
					))
				} else {
					wireTypeOwners[wireType] = eventRef
				}
			} else if wireType != "" {
				issues = append(issues, issue(
					"CONTRACT.EVENT.UNEXPECTED_WIRE_EVENT_TYPE",
					event.SourcePath,
					"event_ref %q declares wire_event_type but delivery_semantics is %q, not transactional_outbox",
					eventRef,
					event.DeliverySemantics,
				))
			}
		}
	}
	for eventRef, producers := range producedEvents {
		if len(producers) <= 1 {
			continue
		}
		issues = append(issues, issue(
			"CONTRACT.EVENT.DUPLICATE_PRODUCER",
			producers[0].SourcePath,
			"canonical event_ref %q is declared more than once",
			eventRef,
		))
	}
	reverseConsumers := graph.BuildEventConsumerIndex(contractGraph.Objects)
	for _, object := range contractGraph.Objects {
		lifecycle := object.Lifecycle
		if lifecycle == nil {
			continue
		}
		consumerRef := ast.CanonicalConsumerRef(object)
		if len(lifecycle.SourceEvents) > 0 && len(lifecycle.EventConsumers) == 0 {
			issues = append(issues, issue(
				"CONTRACT.EVENT.LIFECYCLE_HANDLER_MISSING",
				object.SourcePath,
				"consumer object %q declares lifecycle.source_events without lifecycle.event_consumers",
				consumerRef,
			))
		}
		if len(lifecycle.EventConsumers) > 0 && len(lifecycle.SourceEvents) == 0 {
			issues = append(issues, issue(
				"CONTRACT.EVENT.LIFECYCLE_SOURCE_EVENTS_MISSING",
				object.SourcePath,
				"consumer object %q declares lifecycle.event_consumers without lifecycle.source_events",
				consumerRef,
			))
		}
		seenHandlers := map[string]struct{}{}
		for _, consumer := range lifecycle.EventConsumers {
			if _, duplicate := seenHandlers[consumer.Name]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.EVENT.DUPLICATE_LIFECYCLE_HANDLER",
					object.SourcePath,
					"consumer object %q declares handler %q more than once",
					consumerRef,
					consumer.Name,
				))
			}
			seenHandlers[consumer.Name] = struct{}{}
		}
		seenSources := map[string]struct{}{}
		for _, sourceEvent := range lifecycle.SourceEvents {
			sourceEvent = strings.TrimSpace(sourceEvent)
			if _, duplicate := seenSources[sourceEvent]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.EVENT.DUPLICATE_SOURCE_EVENT",
					object.SourcePath,
					"consumer_ref %q declares source event %q more than once",
					consumerRef,
					sourceEvent,
				))
				continue
			}
			seenSources[sourceEvent] = struct{}{}
			if !ast.IsCanonicalEventRef(sourceEvent) {
				issues = append(issues, issue(
					"CONTRACT.EVENT.INVALID_SOURCE_REF",
					object.SourcePath,
					"consumer_ref %q source event %q must be <objectId>.<PascalCaseEventName>",
					consumerRef,
					sourceEvent,
				))
				continue
			}
			if len(producedEvents[sourceEvent]) == 0 {
				issues = append(issues, issue(
					"CONTRACT.EVENT.SOURCE_WITHOUT_PRODUCER",
					object.SourcePath,
					"consumer_ref %q references event_ref %q but ContractGraph has no producer",
					consumerRef,
					sourceEvent,
				))
				continue
			}
		}
	}
	clientWSTypeOwners := map[string]string{}
	for _, packet := range contractGraph.Governance.Objects {
		for _, event := range packet.Events {
			eventRef := ast.CanonicalEventRef(packet.ObjectID, event.Name)
			consumers := reverseConsumers[eventRef]
			producer := objectsByID[packet.ObjectID]
			if event.ClientWSType != "" {
				if previous, duplicate := clientWSTypeOwners[event.ClientWSType]; duplicate {
					issues = append(issues, issue(
						"CONTRACT.EVENT.DUPLICATE_CLIENT_WS_TYPE",
						event.SourcePath,
						"client_ws_type %q is owned by both %q and %q",
						event.ClientWSType,
						previous,
						eventRef,
					))
				} else {
					clientWSTypeOwners[event.ClientWSType] = eventRef
				}
			}
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
			payloadFields := map[string]struct{}{}
			for _, field := range event.PayloadFields {
				payloadFields[strings.TrimSpace(field)] = struct{}{}
			}
			for field := range event.ClientPayloadDefaults {
				if _, exists := payloadFields[field]; exists {
					continue
				}
				issues = append(issues, issue(
					"CONTRACT.EVENT.CLIENT_DEFAULT_UNKNOWN_FIELD",
					event.SourcePath,
					"event_ref %q client_payload_defaults key %q is absent from payload_fields",
					eventRef,
					field,
				))
			}
			for _, field := range event.PayloadFields {
				visibility, governed := fieldVisibility[packet.ObjectID][strings.TrimSpace(field)]
				if !governed {
					continue
				}
				for _, consumerID := range consumers {
					consumer, exists := objectsByID[consumerID]
					if exists && eventPayloadVisibilityAllowsConsumer(
						visibility,
						producer,
						consumer,
					) {
						continue
					}
					issues = append(issues, issue(
						"CONTRACT.EVENT.PAYLOAD_FIELD_VISIBILITY_MISMATCH",
						event.SourcePath,
						"event_ref %q payload field %q is consumed by %q outside field_visibility %v",
						eventRef,
						field,
						consumerID,
						visibility,
					))
				}
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
			// 精确取值，不做子串匹配。子串匹配（`strings.Contains(channel, "outbox")`）
			// 只在 `channel` 那个无值域字段上成立：它靠「凡是含 outbox 字样的都算」把
			// `transactional_outbox` 与 6 处 `outbox` 笔误一并罩住，代价是任何 topic 名或
			// 拼写变体都能改变判定结果。值域收敛后判定只认受控取值。
			requiresConsumer := ast.RequiresNamedConsumer(event.DeliverySemantics)
			forbidsConsumer := ast.ForbidsNamedConsumer(event.DeliverySemantics)
			// 未知取值 fail-safe 到「要求 consumer」侧：schema 的 enum 已让未知取值
			// 不可能通过校验，但绕过 schema 的调用路径不得因此白拿一个达标。
			if ast.ClassifyEventDelivery(event.DeliverySemantics) == ast.EventDeliveryUnrecognized {
				requiresConsumer = true
			}
			if requiresConsumer && len(consumers) == 0 {
				issues = append(issues, issue(
					"CONTRACT.EVENT.OUTBOX_WITHOUT_CONSUMER",
					event.SourcePath,
					"event_ref %q declares delivery_semantics %q but has no reverse consumer edge; "+
						"a relay with no recipient is unfinished wiring, and an event whose "+
						"obligation ends at durable append must declare transactional_event_log",
					eventRef,
					event.DeliverySemantics,
				))
			}
			if len(consumers) == 0 && event.NoConsumerReason == "" {
				issues = append(issues, issue(
					"CONTRACT.EVENT.MISSING_NO_CONSUMER_REASON",
					event.SourcePath,
					"event %q without consumers must declare no_consumer_reason",
					event.Name,
				))
			}
			if forbidsConsumer && len(consumers) > 0 {
				issues = append(issues, issue(
					"CONTRACT.EVENT.EVENT_LOG_WITH_CONSUMER",
					event.SourcePath,
					"event %q declares transactional_event_log but has consumers %s; "+
						"a consumed event must declare transactional_outbox instead of "+
						"washing a broken delivery path into \"no delivery needed\"",
					event.Name,
					strings.Join(consumers, ", "),
				))
			}
			if len(consumers) > 0 && event.NoConsumerReason != "" {
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

func eventPayloadVisibilityAllowsConsumer(
	visibility []string,
	producer ast.Object,
	consumer ast.Object,
) bool {
	for _, raw := range visibility {
		value := strings.TrimSpace(raw)
		switch value {
		case "all", "first_party_service_internal":
			return true
		case "self":
			if consumer.ID == producer.ID {
				return true
			}
		case "platform-ops":
			if consumer.Domain == "ops" {
				return true
			}
		default:
			const suffix = "-service-internal"
			if strings.HasSuffix(value, suffix) &&
				consumer.Domain == strings.TrimSuffix(value, suffix) {
				return true
			}
		}
	}
	return false
}
