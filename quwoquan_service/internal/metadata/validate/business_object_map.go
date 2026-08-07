package validate

import (
	"encoding/json"
	"fmt"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

var businessObjectStorageFieldRoles = []string{
	"authoritative_state",
	"owned_value",
	"append_only_fact",
	"projection",
	"transport_only",
}

type fieldsDocument struct {
	Entity   string                  `json:"entity"`
	Fields   []fieldDocument         `json:"fields"`
	Entities map[string]entityFields `json:"entities"`
	Members  map[string]entityFields `json:"members"`
}

type entityFields struct {
	Fields []fieldDocument `json:"fields"`
}

type fieldDocument struct {
	Name string `json:"name"`
}

type registeredBoundary struct {
	Domain  string
	Context string
	Object  ast.BusinessObjectBoundary
}

type registeredMember struct {
	OwnerID string
	Context string
	Kind    ast.ObjectKind
}

func validateBusinessObjectMaps(contractGraph *graph.ContractGraph) []Issue {
	if len(contractGraph.BusinessObjectMaps) == 0 {
		return []Issue{issue(
			"CONTRACT.OBJECT_REGISTRY.MISSING",
			"",
			"commercial ContractGraph must register every bounded context and business object",
		)}
	}
	documents := make(map[string]ast.SourceDocument, len(contractGraph.Documents))
	for _, document := range contractGraph.Documents {
		documents[document.Path] = document
	}
	canonicalObjects := make(
		map[string]ast.Object,
		len(contractGraph.Objects),
	)
	for _, object := range contractGraph.Objects {
		canonicalObjects[domainObjectKey(object.Domain, object.Name)] = object
	}
	operationsByLocalID := make(map[string]ast.Operation, len(contractGraph.Operations))
	for _, operation := range contractGraph.Operations {
		operationsByLocalID[operation.LocalID] = operation
	}

	var issues []Issue
	mapsByDomain := make(map[string]ast.BusinessObjectMap, len(contractGraph.BusinessObjectMaps))
	boundaries := map[string]registeredBoundary{}
	contextIDs := map[string]string{}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		if previous, exists := mapsByDomain[objectMap.Domain]; exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.DUPLICATE_DOMAIN",
				objectMap.SourcePath,
				"domain %q is also registered by %s",
				objectMap.Domain,
				previous.SourcePath,
			))
		} else {
			mapsByDomain[objectMap.Domain] = objectMap
		}
		for _, context := range objectMap.BoundedContexts {
			if previous, exists := contextIDs[context.ContextID]; exists {
				issues = append(issues, issue(
					"CONTRACT.BOUNDED_CONTEXT.DUPLICATE_ID",
					objectMap.SourcePath,
					"context_id %q is also declared by %s",
					context.ContextID,
					previous,
				))
			} else {
				contextIDs[context.ContextID] = objectMap.SourcePath
			}
		}
		for _, object := range objectMap.Objects {
			canonicalID := canonicalObjectID(objectMap.Domain, object.CanonicalObject)
			if previous, exists := boundaries[canonicalID]; exists {
				issues = append(issues, issue(
					"CONTRACT.OBJECT_REGISTRY.DUPLICATE_OBJECT",
					objectMap.SourcePath,
					"canonical object %q is already registered by %s/%s",
					canonicalID,
					previous.Domain,
					previous.Context,
				))
				continue
			}
			boundaries[canonicalID] = registeredBoundary{
				Domain:  objectMap.Domain,
				Context: object.BoundedContext,
				Object:  object,
			}
		}
	}
	members := map[string]registeredMember{}
	for _, object := range contractGraph.Objects {
		ownerID := canonicalObjectID(object.Domain, object.Name)
		owner, exists := boundaries[ownerID]
		if !exists {
			continue
		}
		for _, member := range object.Members {
			memberID := canonicalObjectID(object.Domain, member.Name)
			if previous, duplicate := members[memberID]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.MEMBER.DUPLICATE_ID",
					object.SourcePath,
					"aggregate member %q is owned by both %q and %q",
					memberID,
					previous.OwnerID,
					ownerID,
				))
				continue
			}
			members[memberID] = registeredMember{
				OwnerID: ownerID,
				Context: owner.Context,
				Kind:    member.Kind,
			}
		}
	}
	for _, object := range contractGraph.Objects {
		objectMap, exists := mapsByDomain[object.Domain]
		if !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.UNREGISTERED_DOMAIN",
				object.SourcePath,
				"domain %q has ContractGraph objects but no derived object index",
				object.Domain,
			))
			continue
		}
		if _, exists := boundaries[canonicalObjectID(object.Domain, object.Name)]; !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.UNREGISTERED_OBJECT",
				objectMap.SourcePath,
				"object %q is absent from the canonical object registry",
				canonicalObjectID(object.Domain, object.Name),
			))
		}
	}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		issues = append(
			issues,
			validateBusinessObjectMap(
				objectMap,
				documents,
				canonicalObjects,
				boundaries,
				members,
				operationsByLocalID,
			)...,
		)
	}
	for index := range issues {
		if issues[index].SubjectID == "" {
			issues[index].SubjectID = "object-registry"
		}
	}
	return issues
}

func validateBusinessObjectMap(
	objectMap ast.BusinessObjectMap,
	documents map[string]ast.SourceDocument,
	canonicalObjects map[string]ast.Object,
	boundaries map[string]registeredBoundary,
	members map[string]registeredMember,
	operationsByLocalID map[string]ast.Operation,
) []Issue {
	var issues []Issue
	sourcePath := objectMap.SourcePath
	contexts := map[string]ast.BoundedContextRegistration{}
	for _, context := range objectMap.BoundedContexts {
		if _, exists := contexts[context.Name]; exists {
			issues = append(issues, issue(
				"CONTRACT.BOUNDED_CONTEXT.DUPLICATE",
				sourcePath,
				"bounded context %q is declared more than once",
				context.Name,
			))
		}
		contexts[context.Name] = context
		issues = append(issues, validateContextPolicy(sourcePath, objectMap.Domain, context)...)
	}
	seenCanonicalObjects := map[string]struct{}{}
	sourceEntities := map[string]string{}
	for _, object := range objectMap.Objects {
		if _, exists := contexts[object.BoundedContext]; !exists {
			issues = append(issues, issue(
				"CONTRACT.BOUNDED_CONTEXT.UNKNOWN_OBJECT_CONTEXT",
				sourcePath,
				"object %q references unregistered bounded context %q",
				object.CanonicalObject,
				object.BoundedContext,
			))
		}
		issues = append(issues, validateObjectAccess(sourcePath, object)...)
		issues = append(issues, validateObjectSemantics(
			sourcePath,
			objectMap.Domain,
			object,
			documents,
			canonicalObjects,
			operationsByLocalID,
		)...)
		issues = append(issues, validateObjectRelationships(
			sourcePath,
			objectMap.Domain,
			object,
			boundaries,
			members,
		)...)
		issues = append(issues, validateProjectionSourceRelationship(
			sourcePath,
			object,
		)...)
		issues = append(issues, validateCounterSources(
			sourcePath,
			object,
			boundaries,
			members,
		)...)
		if _, exists := seenCanonicalObjects[object.CanonicalObject]; exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.DUPLICATE_CANONICAL_OBJECT",
				sourcePath,
				"canonical object %q is declared more than once",
				object.CanonicalObject,
			))
		}
		seenCanonicalObjects[object.CanonicalObject] = struct{}{}

		declared, exists := canonicalObjects[domainObjectKey(
			objectMap.Domain,
			object.CanonicalObject,
		)]
		if !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.UNKNOWN_CANONICAL_OBJECT",
				sourcePath,
				"canonical object %q is absent from ContractGraph",
				object.CanonicalObject,
			))
		} else {
			if declared.Kind != object.ObjectKind {
				issues = append(issues, issue(
					"CONTRACT.OBJECT_MAP.KIND_MISMATCH",
					sourcePath,
					"object %q map kind %q differs from canonical kind %q",
					object.CanonicalObject,
					object.ObjectKind,
					declared.Kind,
				))
			}
			if strings.TrimSpace(declared.AggregateOwner) !=
				strings.TrimSpace(object.AggregateOwner) {
				issues = append(issues, issue(
					"CONTRACT.OBJECT_MAP.AGGREGATE_OWNER_MISMATCH",
					sourcePath,
					"object %q map aggregate owner %q differs from canonical owner %q",
					object.CanonicalObject,
					object.AggregateOwner,
					declared.AggregateOwner,
				))
			}
			if strings.TrimSpace(declared.StorageBackend) !=
				strings.TrimSpace(object.StorageBackend) {
				issues = append(issues, issue(
					"CONTRACT.OBJECT_MAP.STORAGE_MISMATCH",
					sourcePath,
					"object %q map storage %q differs from canonical storage %q",
					object.CanonicalObject,
					object.StorageBackend,
					declared.StorageBackend,
				))
			}
		}

		if object.SourceDocument == "" && object.SourceEntity == "" {
			if mappedFieldCount(object.FieldRoles) != 0 ||
				requiresFieldSource(object.ObjectKind) {
				issues = append(issues, issue(
					"CONTRACT.OBJECT_MAP.FIELD_SOURCE_MISSING",
					sourcePath,
					"object %q requires a source document/entity",
					object.CanonicalObject,
				))
			}
			continue
		}
		if object.SourceDocument == "" || object.SourceEntity == "" {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.FIELD_SOURCE_INCOMPLETE",
				sourcePath,
				"object %q must declare both source_document and source_entity",
				object.CanonicalObject,
			))
			continue
		}

		sourceKey := object.SourceDocument + "\x00" + object.SourceEntity
		if previous, exists := sourceEntities[sourceKey]; exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.DUPLICATE_SOURCE_ENTITY",
				sourcePath,
				"%s#%s is mapped by both %q and %q",
				object.SourceDocument,
				object.SourceEntity,
				previous,
				object.CanonicalObject,
			))
		}
		sourceEntities[sourceKey] = object.CanonicalObject

		sourceFields, err := loadSourceFields(
			documents,
			object.SourceDocument,
			object.SourceEntity,
		)
		if err != nil {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_MAP.UNKNOWN_FIELD_SOURCE",
				sourcePath,
				"object %q: %v",
				object.CanonicalObject,
				err,
			))
			continue
		}
		issues = append(
			issues,
			validateMappedFields(sourcePath, object, sourceFields)...,
		)
		issues = append(
			issues,
			validateIdentityFields(sourcePath, object, sourceFields)...,
		)
	}
	return issues
}

func validateContextPolicy(
	sourcePath string,
	domain string,
	context ast.BoundedContextRegistration,
) []Issue {
	var issues []Issue
	if context.Name == "" {
		issues = append(issues, issue(
			"CONTRACT.BOUNDED_CONTEXT.MISSING_NAME",
			sourcePath,
			"bounded context name is required",
		))
	}
	expectedContextID := strings.TrimSpace(domain) + "." + snakeCase(context.Name)
	if context.ContextID != expectedContextID {
		issues = append(issues, issue(
			"CONTRACT.BOUNDED_CONTEXT.UNSTABLE_ID",
			sourcePath,
			"bounded context %q context_id must be %q, got %q",
			context.Name,
			expectedContextID,
			context.ContextID,
		))
	}
	if !oneOf(context.Role, "core", "supporting", "generic") {
		issues = append(issues, issue(
			"CONTRACT.BOUNDED_CONTEXT.INVALID_ROLE",
			sourcePath,
			"bounded context %q has invalid role %q",
			context.Name,
			context.Role,
		))
	}
	policy := context.AccessPolicy
	if policy.Commands != "aggregate_facade_only" ||
		policy.Queries != "named_reader_slice_only" ||
		policy.ChildObjects != "aggregate_root_only" ||
		policy.CrossContext != "public_contract_only" {
		issues = append(issues, issue(
			"CONTRACT.BOUNDED_CONTEXT.INVALID_ACCESS_POLICY",
			sourcePath,
			"bounded context %q must enforce aggregate_facade_only, named_reader_slice_only, aggregate_root_only and public_contract_only",
			context.Name,
		))
	}
	return issues
}

func validateObjectSemantics(
	sourcePath string,
	domain string,
	object ast.BusinessObjectBoundary,
	documents map[string]ast.SourceDocument,
	canonicalObjects map[string]ast.Object,
	operationsByLocalID map[string]ast.Operation,
) []Issue {
	var issues []Issue
	expectedStorageRole := map[ast.ObjectKind]string{
		ast.ObjectKindAggregateRoot:  "authoritative",
		ast.ObjectKindOwnedEntity:    "owned",
		ast.ObjectKindValueObject:    "owned",
		ast.ObjectKindAppendOnlyFact: "append_only",
		// saga 的 checkpoint 存储 seam 与聚合存储同为持久权威存储，共用同一 role。
		ast.ObjectKindProcessManager:    "authoritative",
		ast.ObjectKindProjection:        "projection",
		ast.ObjectKindExternalReference: "external",
		ast.ObjectKindRuntimeSession:    "runtime",
	}[object.ObjectKind]
	if object.StorageRole != expectedStorageRole {
		issues = append(issues, issue(
			"CONTRACT.OBJECT_REGISTRY.STORAGE_ROLE_MISMATCH",
			sourcePath,
			"object %q kind %q requires storage_role %q, got %q",
			object.CanonicalObject,
			object.ObjectKind,
			expectedStorageRole,
			object.StorageRole,
		))
	}
	expectedVersionSources := map[ast.ObjectKind][]string{
		ast.ObjectKindAggregateRoot:     {"field", "store_commit"},
		ast.ObjectKindOwnedEntity:       {"owner"},
		ast.ObjectKindValueObject:       {"owner"},
		ast.ObjectKindAppendOnlyFact:    {"immutable"},
		ast.ObjectKindProcessManager:    {"checkpoint"},
		ast.ObjectKindProjection:        {"checkpoint"},
		ast.ObjectKindExternalReference: {"external"},
		ast.ObjectKindRuntimeSession:    {"session"},
	}[object.ObjectKind]
	if !oneOf(object.Identity.VersionSource, expectedVersionSources...) {
		issues = append(issues, issue(
			"CONTRACT.OBJECT_REGISTRY.VERSION_POLICY_MISMATCH",
			sourcePath,
			"object %q kind %q requires identity.version_source in %v, got %q",
			object.CanonicalObject,
			object.ObjectKind,
			expectedVersionSources,
			object.Identity.VersionSource,
		))
	}
	// process_manager 与 aggregate_root 同为状态所有者：两者都必须有入口、不变式与
	// 生命周期绑定。saga 的生命周期绑定尤其不可省，它就是那台状态机本身。
	if oneOf(object.ObjectKind, ast.ObjectKindAggregateRoot, ast.ObjectKindProcessManager) {
		if len(object.MutationEntrypoints) == 0 && len(object.EventConsumers) == 0 &&
			object.Access.Commands != "cli_facade" {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.ZERO_ENTRYPOINT_ROOT",
				sourcePath,
				"object %q kind %q must declare a command or typed event consumer",
				object.CanonicalObject,
				object.ObjectKind,
			))
		}
		if len(object.InvariantRefs) == 0 {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.MISSING_INVARIANT_REF",
				sourcePath,
				"object %q kind %q must bind its invariant specification",
				object.CanonicalObject,
				object.ObjectKind,
			))
		}
		if len(object.LifecycleRefs) == 0 {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.MISSING_LIFECYCLE_REF",
				sourcePath,
				"object %q kind %q must bind its lifecycle specification",
				object.CanonicalObject,
				object.ObjectKind,
			))
		}
	}
	for _, ref := range object.InvariantRefs {
		if err := validateSpecificationRef(documents, ref); err != nil {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.INVALID_INVARIANT_REF",
				sourcePath,
				"aggregate root %q invariant ref %q is invalid: %v",
				object.CanonicalObject,
				ref,
				err,
			))
		}
	}
	for _, ref := range object.LifecycleRefs {
		if err := validateSpecificationRef(documents, ref); err != nil {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.INVALID_LIFECYCLE_REF",
				sourcePath,
				"aggregate root %q lifecycle ref %q is invalid: %v",
				object.CanonicalObject,
				ref,
				err,
			))
		}
	}
	if oneOf(object.ObjectKind, ast.ObjectKindOwnedEntity, ast.ObjectKindValueObject, ast.ObjectKindProjection, ast.ObjectKindExternalReference) &&
		len(object.MutationEntrypoints) != 0 {
		issues = append(issues, issue(
			"CONTRACT.OBJECT_REGISTRY.FORBIDDEN_MUTATION_ENTRYPOINT",
			sourcePath,
			"object %q kind %q cannot expose mutation entrypoints",
			object.CanonicalObject,
			object.ObjectKind,
		))
	}
	for _, entrypoint := range object.MutationEntrypoints {
		operation, exists := operationsByLocalID[entrypoint]
		if !exists {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.UNKNOWN_MUTATION_ENTRYPOINT",
				sourcePath,
				"object %q references unknown mutation entrypoint %q",
				object.CanonicalObject,
				entrypoint,
			))
			continue
		}
		if operation.Domain != domain || operation.Kind == ast.OperationKindQuery {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.INVALID_MUTATION_ENTRYPOINT",
				sourcePath,
				"object %q mutation entrypoint %q must be a command/session in domain %q",
				object.CanonicalObject,
				entrypoint,
				domain,
			))
			continue
		}
		declared, exists := canonicalObjects[domainObjectKey(domain, object.CanonicalObject)]
		if exists && operation.ObjectID != declared.ID {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.MUTATION_OWNER_MISMATCH",
				sourcePath,
				"entrypoint %q is registered to %q but its operation packet is %q",
				entrypoint,
				declared.ID,
				operation.ObjectID,
			))
		}
	}
	if declared, exists := canonicalObjects[domainObjectKey(domain, object.CanonicalObject)]; exists {
		registeredEntrypoints := make(map[string]struct{}, len(object.MutationEntrypoints))
		for _, entrypoint := range object.MutationEntrypoints {
			registeredEntrypoints[entrypoint] = struct{}{}
		}
		for _, operation := range operationsByLocalID {
			if operation.ObjectID != declared.ID || operation.Kind == ast.OperationKindQuery {
				continue
			}
			if _, registered := registeredEntrypoints[operation.LocalID]; !registered {
				issues = append(issues, issue(
					"CONTRACT.OBJECT_REGISTRY.UNREGISTERED_MUTATION_ENTRYPOINT",
					sourcePath,
					"object %q operation %q is not registered as a mutation entrypoint",
					object.CanonicalObject,
					operation.LocalID,
				))
			}
		}
	}
	if declared, exists := canonicalObjects[domainObjectKey(domain, object.CanonicalObject)]; exists {
		expectedBounds := map[string]int{}
		for _, member := range declared.Members {
			if member.MaxCardinality > 0 {
				expectedBounds[member.Name] = member.MaxCardinality
			}
		}
		if !equalIntMaps(expectedBounds, object.MemberBounds) {
			issues = append(issues, issue(
				"CONTRACT.OBJECT_REGISTRY.MEMBER_BOUNDS_MISMATCH",
				sourcePath,
				"object %q member_bounds must equal aggregate member bounds: want %v got %v",
				object.CanonicalObject,
				expectedBounds,
				object.MemberBounds,
			))
		}
	}
	return issues
}

func validateSpecificationRef(
	documents map[string]ast.SourceDocument,
	ref string,
) error {
	path, fragment, hasFragment := strings.Cut(strings.TrimSpace(ref), "#")
	if path == "" || !hasFragment || strings.Trim(fragment, "/") == "" {
		return fmt.Errorf("expected metadata/path.yaml#non-empty/anchor")
	}
	document, exists := documents[path]
	if !exists {
		return fmt.Errorf("document does not exist")
	}
	var value any
	if err := json.Unmarshal(document.Content, &value); err != nil {
		return fmt.Errorf("decode normalized document: %w", err)
	}
	current := value
	for _, segment := range strings.Split(strings.Trim(fragment, "/"), "/") {
		mapping, ok := current.(map[string]any)
		if !ok {
			return fmt.Errorf("anchor segment %q is not a mapping", segment)
		}
		current, exists = mapping[segment]
		if !exists {
			return fmt.Errorf("anchor segment %q does not exist", segment)
		}
	}
	switch typed := current.(type) {
	case nil:
		return fmt.Errorf("anchor is null")
	case string:
		if strings.TrimSpace(typed) == "" {
			return fmt.Errorf("anchor is empty")
		}
	case []any:
		if len(typed) == 0 {
			return fmt.Errorf("anchor is empty")
		}
	case map[string]any:
		if len(typed) == 0 {
			return fmt.Errorf("anchor is empty")
		}
	}
	return nil
}

func validateObjectAccess(
	sourcePath string,
	object ast.BusinessObjectBoundary,
) []Issue {
	commands := object.Access.Commands
	queries := object.Access.Queries
	crossContext := object.Access.CrossContext
	valid := false
	switch object.ObjectKind {
	case ast.ObjectKindAggregateRoot:
		valid = oneOf(commands, "aggregate_facade", "cli_facade") &&
			oneOf(queries, "named_reader", "none") &&
			oneOf(crossContext, "public_contract_only", "event_only")
	case ast.ObjectKindOwnedEntity, ast.ObjectKindValueObject:
		valid = commands == "via_aggregate_root" &&
			oneOf(queries, "via_aggregate_projection", "none") &&
			crossContext == "forbidden"
	case ast.ObjectKindProjection:
		valid = commands == "none" && queries == "named_reader" &&
			crossContext == "public_contract_only"
	case ast.ObjectKindExternalReference:
		valid = commands == "none" && queries == "external_port" &&
			crossContext == "public_contract_only"
	case ast.ObjectKindAppendOnlyFact:
		valid = commands == "append_only_sink" &&
			oneOf(queries, "named_reader", "none") &&
			oneOf(crossContext, "event_only", "public_contract_only")
	case ast.ObjectKindProcessManager:
		// 长流程编排器有专属命令面 process_facade，禁止复用 aggregate_facade：
		// 调用方看到的是流程推进/取消/恢复，不是聚合状态写入。
		// 对外经公开合同暴露的流程必须给出具名状态读取面；只经事件参与的内部
		// saga（cross_context=event_only）没有外部调用方，可以没有 reader。
		valid = commands == "process_facade" &&
			oneOf(crossContext, "public_contract_only", "event_only")
		if crossContext == "event_only" {
			valid = valid && oneOf(queries, "named_reader", "none")
		} else {
			valid = valid && queries == "named_reader"
		}
	case ast.ObjectKindRuntimeSession:
		valid = commands == "session_facade" &&
			oneOf(queries, "named_reader", "none") &&
			crossContext == "public_contract_only"
	}
	if valid {
		return nil
	}
	return []Issue{issue(
		"CONTRACT.OBJECT_REGISTRY.INVALID_ACCESS_POLICY",
		sourcePath,
		"object %q kind %q has invalid access commands=%q queries=%q cross_context=%q",
		object.CanonicalObject,
		object.ObjectKind,
		commands,
		queries,
		crossContext,
	)}
}

func validateObjectRelationships(
	sourcePath string,
	domain string,
	object ast.BusinessObjectBoundary,
	boundaries map[string]registeredBoundary,
	members map[string]registeredMember,
) []Issue {
	var issues []Issue
	seen := map[string]struct{}{}
	boundReferenceFields := map[string]string{}
	for _, relationship := range object.Relationships {
		if _, exists := seen[relationship.Name]; exists {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.DUPLICATE_NAME",
				sourcePath,
				"object %q relationship %q is declared more than once",
				object.CanonicalObject,
				relationship.Name,
			))
		}
		seen[relationship.Name] = struct{}{}
		for _, field := range relationship.ReferenceFields {
			if previous, exists := boundReferenceFields[field]; exists {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.DUPLICATE_FIELD_BINDING",
					sourcePath,
					"object %q reference field %q is bound by both %q and %q",
					object.CanonicalObject,
					field,
					previous,
					relationship.Name,
				))
			}
			boundReferenceFields[field] = relationship.Name
		}
		if !oneOf(relationship.Kind, "owned", "reference", "event_source", "projection_source", "external") ||
			!oneOf(relationship.Cardinality, "1:1", "1:N", "N:1", "N:N") ||
			!oneOf(relationship.Consistency, "strong", "eventual", "runtime") ||
			!oneOf(relationship.Access, "aggregate_root", "command_facade", "named_reader", "event", "external_port", "none") ||
			!oneOf(relationship.OnDelete, "cascade", "restrict", "tombstone", "retain", "detach") {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.INVALID_POLICY",
				sourcePath,
				"object %q relationship %q has an invalid kind/cardinality/consistency/access/on_delete policy",
				object.CanonicalObject,
				relationship.Name,
			))
		}
		targetIDs := append([]string{}, relationship.TargetObjects...)
		if relationship.TargetObject != "" {
			targetIDs = append(targetIDs, relationship.TargetObject)
		}
		if len(targetIDs) == 0 ||
			(relationship.TargetObject != "" && len(relationship.TargetObjects) != 0) {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.INVALID_TARGET_SET",
				sourcePath,
				"object %q relationship %q must declare exactly one of target_object or target_objects",
				object.CanonicalObject,
				relationship.Name,
			))
			continue
		}
		if relationship.Kind == "owned" {
			if len(relationship.ReferenceFields) != 0 {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.OWNED_REFERENCE_FIELD",
					sourcePath,
					"owned relationship %s.%s cannot bind reference fields",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			if len(targetIDs) != 1 {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.POLYMORPHIC_OWNERSHIP",
					sourcePath,
					"owned relationship %s.%s must have exactly one target",
					object.CanonicalObject,
					relationship.Name,
				))
				continue
			}
			target, exists := members[targetIDs[0]]
			if !exists {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.UNKNOWN_TARGET",
					sourcePath,
					"object %q relationship %q references unknown target %q",
					object.CanonicalObject,
					relationship.Name,
					targetIDs[0],
				))
				continue
			}
			ownerID := canonicalObjectID(domain, object.CanonicalObject)
			if object.ObjectKind != ast.ObjectKindAggregateRoot ||
				target.Context != object.BoundedContext || target.OwnerID != ownerID ||
				!oneOf(target.Kind, ast.ObjectKindOwnedEntity, ast.ObjectKindValueObject) ||
				relationship.Consistency != "strong" ||
				relationship.Access != "aggregate_root" ||
				!oneOf(relationship.OnDelete, "cascade", "restrict") {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.INVALID_OWNERSHIP",
					sourcePath,
					"owned relationship %s.%s must stay inside one aggregate and use strong aggregate_root access",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			continue
		}
		if len(relationship.ReferenceFields) == 0 {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.MISSING_FIELD_BINDING",
				sourcePath,
				"relationship %s.%s must bind at least one concrete reference field",
				object.CanonicalObject,
				relationship.Name,
			))
		}
		for _, targetID := range targetIDs {
			if member, isMember := members[targetID]; isMember {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.DIRECT_CHILD_ACCESS",
					sourcePath,
					"relationship %s.%s targets aggregate member %q owned by %q",
					object.CanonicalObject,
					relationship.Name,
					targetID,
					member.OwnerID,
				))
				continue
			}
			target, exists := boundaries[targetID]
			if !exists {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.UNKNOWN_TARGET",
					sourcePath,
					"object %q relationship %q references unknown target %q",
					object.CanonicalObject,
					relationship.Name,
					targetID,
				))
				continue
			}
			sameContext := target.Domain == domain && target.Context == object.BoundedContext
			if !sameContext && relationship.Access == "aggregate_root" {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.CROSS_CONTEXT_DIRECT_ACCESS",
					sourcePath,
					"cross-context relationship %s.%s must use command_facade, named_reader, event or external_port",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			if !sameContext && relationship.Consistency == "strong" {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.CROSS_CONTEXT_STRONG_CONSISTENCY",
					sourcePath,
					"cross-context relationship %s.%s cannot claim strong consistency",
					object.CanonicalObject,
					relationship.Name,
				))
			}
			if relationship.Kind == "external" &&
				(target.Object.ObjectKind != ast.ObjectKindExternalReference ||
					relationship.Access != "external_port") {
				issues = append(issues, issue(
					"CONTRACT.RELATIONSHIP.INVALID_EXTERNAL_ACCESS",
					sourcePath,
					"external relationship %s.%s must target external_reference through external_port",
					object.CanonicalObject,
					relationship.Name,
				))
			}
		}
	}
	declaredReferenceFields := map[string]struct{}{}
	for _, field := range object.FieldRoles["reference"] {
		declaredReferenceFields[field] = struct{}{}
	}
	for field := range declaredReferenceFields {
		if _, exists := boundReferenceFields[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.UNBOUND_REFERENCE_FIELD",
				sourcePath,
				"object %q reference field %q has no relationship binding",
				object.CanonicalObject,
				field,
			))
		}
	}
	for field, relationship := range boundReferenceFields {
		if _, exists := declaredReferenceFields[field]; !exists {
			issues = append(issues, issue(
				"CONTRACT.RELATIONSHIP.UNKNOWN_REFERENCE_FIELD",
				sourcePath,
				"object %q relationship %q binds non-reference field %q",
				object.CanonicalObject,
				relationship,
				field,
			))
		}
	}
	return issues
}

func validateProjectionSourceRelationship(
	sourcePath string,
	object ast.BusinessObjectBoundary,
) []Issue {
	if object.ObjectKind != ast.ObjectKindProjection {
		return nil
	}
	for _, relationship := range object.Relationships {
		if relationship.Kind == "projection_source" {
			return nil
		}
	}
	return []Issue{issue(
		"CONTRACT.PROJECTION.MISSING_SOURCE_RELATIONSHIP",
		sourcePath,
		"projection object %q must declare at least one projection_source relationship",
		object.CanonicalObject,
	)}
}

func validateCounterSources(
	sourcePath string,
	object ast.BusinessObjectBoundary,
	boundaries map[string]registeredBoundary,
	members map[string]registeredMember,
) []Issue {
	var issues []Issue
	for counter, source := range object.CounterSources {
		parts := strings.Split(strings.TrimSpace(source), ".")
		if len(parts) < 2 || strings.TrimSpace(parts[0]) == "" || strings.TrimSpace(parts[1]) == "" {
			issues = append(issues, issue(
				"CONTRACT.COUNTER_SOURCE.INVALID_REFERENCE",
				sourcePath,
				"object %q counter %q has invalid source %q; expected domain.Object or domain.Object.fact",
				object.CanonicalObject,
				counter,
				source,
			))
			continue
		}
		for _, qualifier := range parts[2:] {
			if strings.TrimSpace(qualifier) == "" {
				issues = append(issues, issue(
					"CONTRACT.COUNTER_SOURCE.INVALID_REFERENCE",
					sourcePath,
					"object %q counter %q has invalid source %q; qualifiers cannot be empty",
					object.CanonicalObject,
					counter,
					source,
				))
				break
			}
		}
		targetID := strings.TrimSpace(parts[0]) + "." + strings.TrimSpace(parts[1])
		if member, exists := members[targetID]; exists {
			issues = append(issues, issue(
				"CONTRACT.COUNTER_SOURCE.DIRECT_CHILD_ACCESS",
				sourcePath,
				"object %q counter %q targets aggregate member %q owned by %q",
				object.CanonicalObject,
				counter,
				targetID,
				member.OwnerID,
			))
			continue
		}
		if _, exists := boundaries[targetID]; !exists {
			issues = append(issues, issue(
				"CONTRACT.COUNTER_SOURCE.UNKNOWN_TARGET",
				sourcePath,
				"object %q counter %q references unknown source object %q",
				object.CanonicalObject,
				counter,
				targetID,
			))
		}
	}
	return issues
}

func canonicalObjectID(domain, object string) string {
	return strings.TrimSpace(domain) + "." + strings.TrimSpace(object)
}

func oneOf[T comparable](value T, allowed ...T) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}
