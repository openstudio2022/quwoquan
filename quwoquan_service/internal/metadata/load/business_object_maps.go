package load

import (
	"encoding/json"
	"fmt"
	"path"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

// businessObjectMaps remains a ContractGraph projection for existing validators
// and generators. It is derived exclusively from object-first packets; there is
// no writable business_object_map.yaml registry.
type contextDocument struct {
	Role   string                  `json:"role"`
	Access contextAccessPolicyWire `json:"access"`
}

type contextAccessPolicyWire struct {
	Commands     string `json:"commands"`
	Queries      string `json:"queries"`
	ChildObjects string `json:"child_objects"`
	CrossContext string `json:"cross_context"`
}

type objectDocument struct {
	Kind                 ast.ObjectKind           `json:"kind"`
	Identity             objectIdentityWire       `json:"identity"`
	Access               objectAccessPolicyWire   `json:"access"`
	Relationships        []objectRelationshipWire `json:"relationships"`
	BusinessRules        []any                    `json:"business_rules"`
	Lifecycle            any                      `json:"lifecycle"`
	LocalIdentityReasons map[string]string        `json:"local_identity_reasons"`
}

type objectIdentityWire struct {
	Fields        []string `json:"fields"`
	VersionSource string   `json:"version_source"`
	VersionField  string   `json:"version_field"`
}

type objectAccessPolicyWire struct {
	Commands     string `json:"commands"`
	Queries      string `json:"queries"`
	CrossContext string `json:"cross_context"`
}

type objectRelationshipWire struct {
	Name            string   `json:"name"`
	TargetObject    string   `json:"target_object"`
	TargetObjects   []string `json:"target_objects"`
	ReferenceFields []string `json:"reference_fields"`
	Kind            string   `json:"kind"`
	Cardinality     string   `json:"cardinality"`
	Consistency     string   `json:"consistency"`
	Access          string   `json:"access"`
	OnDelete        string   `json:"on_delete"`
}

type fieldsPacket struct {
	Fields []fieldDeclaration `json:"fields"`
}

type fieldDeclaration struct {
	Name      string `json:"name"`
	Role      string `json:"role"`
	Reference bool   `json:"reference"`
}

type storageDocument struct {
	Backend string `json:"backend"`
	Role    string `json:"role"`
}

type eventsDocument struct {
	Subscriptions []string `json:"subscriptions"`
}

func deriveBusinessObjectMaps(catalog *ast.Catalog, errs *[]error) {
	documents := make(map[string]ast.SourceDocument, len(catalog.Documents))
	for _, document := range catalog.Documents {
		documents[document.Path] = document
	}
	operationsByObject := map[string][]ast.Operation{}
	for _, operation := range catalog.Operations {
		operationsByObject[operation.ObjectID] = append(
			operationsByObject[operation.ObjectID],
			operation,
		)
	}

	mapsByDomain := map[string]*ast.BusinessObjectMap{}
	contextsSeen := map[string]map[string]struct{}{}
	for _, object := range catalog.Objects {
		segments := strings.Split(object.SourcePath, "/")
		if len(segments) != 4 {
			*errs = append(*errs, fmt.Errorf(
				"%s: cannot derive domain/context/object from path",
				object.SourcePath,
			))
			continue
		}
		domainSegment, contextSegment := segments[0], segments[1]
		objectDir := path.Dir(object.SourcePath)
		contextPath := path.Join(domainSegment, contextSegment, "context.yaml")

		objectWire, ok := decodeDerivedDocument[objectDocument](
			documents,
			object.SourcePath,
			errs,
		)
		if !ok {
			continue
		}
		contextWire, ok := decodeDerivedDocument[contextDocument](
			documents,
			contextPath,
			errs,
		)
		if !ok {
			continue
		}

		objectMap := mapsByDomain[domainSegment]
		if objectMap == nil {
			objectMap = &ast.BusinessObjectMap{
				Domain:     domainSegment,
				SourcePath: domainSegment + "/**/object.yaml",
			}
			mapsByDomain[domainSegment] = objectMap
			contextsSeen[domainSegment] = map[string]struct{}{}
		}
		contextName := pascalCaseIdentifier(contextSegment)
		contextID := domainSegment + "." + contextSegment
		if _, exists := contextsSeen[domainSegment][contextID]; !exists {
			objectMap.BoundedContexts = append(
				objectMap.BoundedContexts,
				ast.BoundedContextRegistration{
					ContextID: contextID,
					Name:      contextName,
					Role:      strings.TrimSpace(contextWire.Role),
					AccessPolicy: ast.ContextAccessPolicy{
						Commands: strings.TrimSpace(
							contextWire.Access.Commands,
						),
						Queries: strings.TrimSpace(
							contextWire.Access.Queries,
						),
						ChildObjects: strings.TrimSpace(
							contextWire.Access.ChildObjects,
						),
						CrossContext: strings.TrimSpace(
							contextWire.Access.CrossContext,
						),
					},
				},
			)
			contextsSeen[domainSegment][contextID] = struct{}{}
		}

		fieldRoles := cloneFieldRoles(nil)
		fieldsPath := path.Join(objectDir, "fields.yaml")
		if fields, exists := documents[fieldsPath]; exists {
			var packet fieldsPacket
			if err := json.Unmarshal(fields.Content, &packet); err != nil {
				*errs = append(*errs, fmt.Errorf("%s: decode fields: %w", fieldsPath, err))
				continue
			}
			for index, field := range packet.Fields {
				name := strings.TrimSpace(field.Name)
				role := strings.TrimSpace(field.Role)
				if name == "" || role == "" {
					*errs = append(*errs, fmt.Errorf(
						"%s: fields[%d] must declare name and role",
						fieldsPath,
						index,
					))
					continue
				}
				fieldRoles[role] = append(fieldRoles[role], name)
				if field.Reference {
					fieldRoles["reference"] = append(fieldRoles["reference"], name)
				}
			}
		}

		storagePath := path.Join(objectDir, "storage.yaml")
		var storage storageDocument
		if document, exists := documents[storagePath]; exists {
			if err := json.Unmarshal(document.Content, &storage); err != nil {
				*errs = append(*errs, fmt.Errorf("%s: decode storage: %w", storagePath, err))
				continue
			}
		}
		if strings.TrimSpace(storage.Role) == "" {
			storage.Role = storageRoleForKind(objectWire.Kind)
		}
		eventsPath := path.Join(objectDir, "events.yaml")
		var events eventsDocument
		if document, exists := documents[eventsPath]; exists {
			if err := json.Unmarshal(document.Content, &events); err != nil {
				*errs = append(*errs, fmt.Errorf("%s: decode events: %w", eventsPath, err))
				continue
			}
		}

		mutationEntrypoints := make([]string, 0)
		for _, operation := range operationsByObject[object.ID] {
			if operation.Kind != ast.OperationKindQuery {
				mutationEntrypoints = append(mutationEntrypoints, operation.LocalID)
			}
		}
		memberBounds := map[string]int{}
		for _, member := range object.Members {
			if member.MaxCardinality > 0 {
				memberBounds[member.Name] = member.MaxCardinality
			}
		}
		relationships := make([]ast.ObjectRelationship, 0, len(objectWire.Relationships))
		for _, relationship := range objectWire.Relationships {
			relationships = append(relationships, ast.ObjectRelationship{
				Name:            strings.TrimSpace(relationship.Name),
				TargetObject:    strings.TrimSpace(relationship.TargetObject),
				TargetObjects:   normalizedStrings(relationship.TargetObjects),
				ReferenceFields: normalizedStrings(relationship.ReferenceFields),
				Kind:            strings.TrimSpace(relationship.Kind),
				Cardinality:     strings.TrimSpace(relationship.Cardinality),
				Consistency:     strings.TrimSpace(relationship.Consistency),
				Access:          strings.TrimSpace(relationship.Access),
				OnDelete:        strings.TrimSpace(relationship.OnDelete),
			})
		}
		invariantRefs := []string{}
		if len(objectWire.BusinessRules) > 0 {
			invariantRefs = append(invariantRefs, object.SourcePath+"#business_rules")
		}
		lifecycleRefs := []string{}
		if objectWire.Lifecycle != nil {
			lifecycleRefs = append(lifecycleRefs, object.SourcePath+"#lifecycle")
		}
		sourceDocument := ""
		sourceEntity := ""
		if _, exists := documents[fieldsPath]; exists {
			sourceDocument = fieldsPath
			sourceEntity = object.Name
		}
		objectMap.Objects = append(objectMap.Objects, ast.BusinessObjectBoundary{
			CanonicalObject: object.Name,
			BoundedContext:  contextName,
			ObjectKind:      objectWire.Kind,
			Identity: ast.ObjectIdentity{
				Fields:        normalizedStrings(objectWire.Identity.Fields),
				VersionSource: strings.TrimSpace(objectWire.Identity.VersionSource),
				VersionField:  strings.TrimSpace(objectWire.Identity.VersionField),
			},
			InvariantRefs:       invariantRefs,
			MemberBounds:        memberBounds,
			StorageRole:         strings.TrimSpace(storage.Role),
			StorageBackend:      strings.TrimSpace(storage.Backend),
			MutationEntrypoints: mutationEntrypoints,
			EventConsumers:      normalizedStrings(events.Subscriptions),
			LifecycleRefs:       lifecycleRefs,
			SourceDocument:      sourceDocument,
			SourceEntity:        sourceEntity,
			Access: ast.ObjectAccessPolicy{
				Commands:     strings.TrimSpace(objectWire.Access.Commands),
				Queries:      strings.TrimSpace(objectWire.Access.Queries),
				CrossContext: strings.TrimSpace(objectWire.Access.CrossContext),
			},
			Relationships:        relationships,
			FieldRoles:           fieldRoles,
			LocalIdentityReasons: cloneStringMap(objectWire.LocalIdentityReasons),
		})
	}

	domains := make([]string, 0, len(mapsByDomain))
	for domain := range mapsByDomain {
		domains = append(domains, domain)
	}
	sort.Strings(domains)
	for _, domain := range domains {
		catalog.BusinessObjectMaps = append(catalog.BusinessObjectMaps, *mapsByDomain[domain])
	}
}

func storageRoleForKind(kind ast.ObjectKind) string {
	switch kind {
	case ast.ObjectKindAggregateRoot:
		return "authoritative"
	case ast.ObjectKindAppendOnlyFact:
		return "append_only"
	case ast.ObjectKindProjection:
		return "projection"
	case ast.ObjectKindExternalReference:
		return "external"
	case ast.ObjectKindRuntimeSession:
		return "runtime"
	default:
		return ""
	}
}

func decodeDerivedDocument[T any](
	documents map[string]ast.SourceDocument,
	documentPath string,
	errs *[]error,
) (T, bool) {
	var result T
	document, exists := documents[documentPath]
	if !exists {
		*errs = append(*errs, fmt.Errorf("%s: required derived source is missing", documentPath))
		return result, false
	}
	if err := json.Unmarshal(document.Content, &result); err != nil {
		*errs = append(*errs, fmt.Errorf("%s: decode derived source: %w", documentPath, err))
		return result, false
	}
	return result, true
}

func cloneFieldRoles(roles map[string][]string) map[string][]string {
	cloned := map[string][]string{
		"authoritative_state": {},
		"owned_value":         {},
		"reference":           {},
		"append_only_fact":    {},
		"projection":          {},
		"transport_only":      {},
	}
	for role, fields := range roles {
		cloned[role] = append([]string{}, fields...)
	}
	return cloned
}

func normalizedStrings(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func cloneStringMap(values map[string]string) map[string]string {
	result := make(map[string]string, len(values))
	for key, value := range values {
		result[strings.TrimSpace(key)] = strings.TrimSpace(value)
	}
	return result
}
