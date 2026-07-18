package load

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

type businessObjectMapWire struct {
	Domain          string                           `json:"domain"`
	DecisionRefs    []string                         `json:"decision_refs"`
	BoundedContexts []boundedContextRegistrationWire `json:"bounded_contexts"`
	Objects         []businessObjectBoundaryWire     `json:"objects"`
}

type businessObjectBoundaryWire struct {
	CanonicalObject      string                   `json:"canonical_object"`
	BoundedContext       string                   `json:"bounded_context"`
	ObjectKind           ast.ObjectKind           `json:"object_kind"`
	AggregateOwner       *string                  `json:"aggregate_owner"`
	Identity             objectIdentityWire       `json:"identity"`
	InvariantRefs        []string                 `json:"invariant_refs"`
	MemberBounds         map[string]int           `json:"member_bounds"`
	StorageRole          string                   `json:"storage_role"`
	StorageBackend       *string                  `json:"storage_backend"`
	MutationEntrypoints  []string                 `json:"mutation_entrypoints"`
	EventConsumers       []string                 `json:"event_consumers"`
	LifecycleRefs        []string                 `json:"lifecycle_refs"`
	SourceDocument       *string                  `json:"source_document"`
	SourceEntity         *string                  `json:"source_entity"`
	Access               objectAccessPolicyWire   `json:"access"`
	Relationships        []objectRelationshipWire `json:"relationships"`
	FieldRoles           map[string][]string      `json:"field_roles"`
	LocalIdentityReasons map[string]string        `json:"local_identity_reasons"`
}

type objectIdentityWire struct {
	Fields        []string `json:"fields"`
	VersionSource string   `json:"version_source"`
	VersionField  *string  `json:"version_field"`
}

type boundedContextRegistrationWire struct {
	ContextID    string                  `json:"context_id"`
	Name         string                  `json:"name"`
	Role         string                  `json:"role"`
	AccessPolicy contextAccessPolicyWire `json:"access_policy"`
}

type contextAccessPolicyWire struct {
	Commands     string `json:"commands"`
	Queries      string `json:"queries"`
	ChildObjects string `json:"child_objects"`
	CrossContext string `json:"cross_context"`
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

func loadBusinessObjectMaps(catalog *ast.Catalog, errs *[]error) {
	for _, document := range catalog.Documents {
		if filepath.Base(document.Path) != "business_object_map.yaml" {
			continue
		}
		var wire businessObjectMapWire
		var envelope map[string]json.RawMessage
		if err := json.Unmarshal(document.Content, &envelope); err != nil {
			*errs = append(
				*errs,
				fmt.Errorf("%s: decode business object map envelope: %w", document.Path, err),
			)
			continue
		}
		for _, retiredField := range []string{"version", "schemaVersion", "registryRevision"} {
			if _, exists := envelope[retiredField]; exists {
				*errs = append(
					*errs,
					fmt.Errorf(
						"%s: retired Registry field %q is forbidden",
						document.Path,
						retiredField,
					),
				)
				continue
			}
		}
		if err := json.Unmarshal(document.Content, &wire); err != nil {
			*errs = append(
				*errs,
				fmt.Errorf("%s: decode business object map: %w", document.Path, err),
			)
			continue
		}
		objectMap := ast.BusinessObjectMap{
			Domain:          strings.TrimSpace(wire.Domain),
			DecisionRefs:    append([]string(nil), wire.DecisionRefs...),
			BoundedContexts: make([]ast.BoundedContextRegistration, 0, len(wire.BoundedContexts)),
			SourcePath:      document.Path,
			Objects: make(
				[]ast.BusinessObjectBoundary,
				0,
				len(wire.Objects),
			),
		}
		for _, boundedContext := range wire.BoundedContexts {
			objectMap.BoundedContexts = append(
				objectMap.BoundedContexts,
				ast.BoundedContextRegistration{
					ContextID: strings.TrimSpace(boundedContext.ContextID),
					Name:      strings.TrimSpace(boundedContext.Name),
					Role:      strings.TrimSpace(boundedContext.Role),
					AccessPolicy: ast.ContextAccessPolicy{
						Commands:     strings.TrimSpace(boundedContext.AccessPolicy.Commands),
						Queries:      strings.TrimSpace(boundedContext.AccessPolicy.Queries),
						ChildObjects: strings.TrimSpace(boundedContext.AccessPolicy.ChildObjects),
						CrossContext: strings.TrimSpace(boundedContext.AccessPolicy.CrossContext),
					},
				},
			)
		}
		for _, object := range wire.Objects {
			relationships := make([]ast.ObjectRelationship, 0, len(object.Relationships))
			for _, relationship := range object.Relationships {
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
			objectMap.Objects = append(
				objectMap.Objects,
				ast.BusinessObjectBoundary{
					CanonicalObject: strings.TrimSpace(object.CanonicalObject),
					BoundedContext:  strings.TrimSpace(object.BoundedContext),
					ObjectKind:      object.ObjectKind,
					AggregateOwner:  dereferenceString(object.AggregateOwner),
					Identity: ast.ObjectIdentity{
						Fields:        normalizedStrings(object.Identity.Fields),
						VersionSource: strings.TrimSpace(object.Identity.VersionSource),
						VersionField:  dereferenceString(object.Identity.VersionField),
					},
					InvariantRefs:       normalizedStrings(object.InvariantRefs),
					MemberBounds:        cloneIntMap(object.MemberBounds),
					StorageRole:         strings.TrimSpace(object.StorageRole),
					StorageBackend:      dereferenceString(object.StorageBackend),
					MutationEntrypoints: normalizedStrings(object.MutationEntrypoints),
					EventConsumers:      normalizedStrings(object.EventConsumers),
					LifecycleRefs:       normalizedStrings(object.LifecycleRefs),
					SourceDocument:      dereferenceString(object.SourceDocument),
					SourceEntity:        dereferenceString(object.SourceEntity),
					Access: ast.ObjectAccessPolicy{
						Commands:     strings.TrimSpace(object.Access.Commands),
						Queries:      strings.TrimSpace(object.Access.Queries),
						CrossContext: strings.TrimSpace(object.Access.CrossContext),
					},
					Relationships:        relationships,
					FieldRoles:           cloneFieldRoles(object.FieldRoles),
					LocalIdentityReasons: cloneStringMap(object.LocalIdentityReasons),
				},
			)
		}
		catalog.BusinessObjectMaps = append(catalog.BusinessObjectMaps, objectMap)
	}
}

func mergeBusinessObjectBoundaries(catalog *ast.Catalog, errs *[]error) {
	objectsByDomainName := make(map[string]int, len(catalog.Objects))
	objectIDs := make(map[string]struct{}, len(catalog.Objects))
	for index, object := range catalog.Objects {
		key := object.Domain + "\x00" + object.Name
		objectsByDomainName[key] = index
		objectIDs[object.ID] = struct{}{}
	}
	for _, objectMap := range catalog.BusinessObjectMaps {
		for _, boundary := range objectMap.Objects {
			key := objectMap.Domain + "\x00" + boundary.CanonicalObject
			if _, exists := objectsByDomainName[key]; exists {
				continue
			}
			id := objectMap.Domain + "." + snakeCaseIdentifier(
				boundary.CanonicalObject,
			)
			if _, exists := objectIDs[id]; exists {
				*errs = append(
					*errs,
					fmt.Errorf(
						"%s: canonical object %q conflicts with object id %q",
						objectMap.SourcePath,
						boundary.CanonicalObject,
						id,
					),
				)
				continue
			}
			catalog.Objects = append(catalog.Objects, ast.Object{
				ID:             id,
				Domain:         objectMap.Domain,
				Name:           boundary.CanonicalObject,
				Kind:           boundary.ObjectKind,
				KindExplicit:   true,
				AggregateOwner: boundary.AggregateOwner,
				StorageBackend: boundary.StorageBackend,
				SourcePath:     objectMap.SourcePath,
			})
			objectsByDomainName[key] = len(catalog.Objects) - 1
			objectIDs[id] = struct{}{}
		}
	}
}

func dereferenceString(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}

func cloneFieldRoles(
	roles map[string][]string,
) map[string][]string {
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
		result = append(result, strings.TrimSpace(value))
	}
	return result
}

func cloneIntMap(values map[string]int) map[string]int {
	result := make(map[string]int, len(values))
	for key, value := range values {
		result[strings.TrimSpace(key)] = value
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

func snakeCaseIdentifier(value string) string {
	var result strings.Builder
	for index, current := range value {
		if current >= 'A' && current <= 'Z' {
			if index > 0 {
				result.WriteByte('_')
			}
			result.WriteRune(current + ('a' - 'A'))
			continue
		}
		result.WriteRune(current)
	}
	return result.String()
}
