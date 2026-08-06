package load

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

// loadMetadataGovernance builds the typed, compiler-only view used by
// cross-document governance checks. All YAML decoding remains in the loader;
// validators and generators consume this normalized representation.
func loadMetadataGovernance(metadataDir string, catalog *ast.Catalog) error {
	var loadErrors []error
	governance := ast.MetadataGovernance{}

	globalEnums, globalTypes, err := loadSharedDefinitions(
		metadataDir,
		filepath.Join(metadataDir, "_shared", "types.yaml"),
		ast.EnumOwnerGlobal,
		"",
	)
	if err != nil {
		loadErrors = append(loadErrors, err)
	} else {
		governance.Enums = append(governance.Enums, globalEnums...)
		governance.Types = append(governance.Types, globalTypes...)
	}
	globalFields, err := loadSharedTypeFields(
		metadataDir,
		filepath.Join(metadataDir, "_shared", "types.yaml"),
		"",
	)
	if err != nil {
		loadErrors = append(loadErrors, err)
	} else {
		governance.Fields = append(governance.Fields, globalFields...)
	}
	seenServiceShared := map[string]struct{}{}
	for _, object := range catalog.Objects {
		if _, seen := seenServiceShared[object.Domain]; !seen {
			seenServiceShared[object.Domain] = struct{}{}
			for _, filename := range []string{"enums.yaml", "types.yaml"} {
				sharedPath := filepath.Join(
					metadataDir,
					object.Domain,
					"_shared",
					filename,
				)
				enums, types, sharedErr := loadSharedDefinitions(
					metadataDir,
					sharedPath,
					ast.EnumOwnerService,
					object.Domain,
				)
				if sharedErr != nil {
					loadErrors = append(loadErrors, sharedErr)
					continue
				}
				governance.Enums = append(governance.Enums, enums...)
				governance.Types = append(governance.Types, types...)
				fields, fieldsErr := loadSharedTypeFields(
					metadataDir,
					sharedPath,
					object.Domain,
				)
				if fieldsErr != nil {
					loadErrors = append(loadErrors, fieldsErr)
				} else {
					governance.Fields = append(governance.Fields, fields...)
				}
			}
		}

		packet, packetEnums, packetTypes, packetErr := loadObjectGovernance(
			metadataDir,
			object,
		)
		if packetErr != nil {
			loadErrors = append(loadErrors, packetErr)
			continue
		}
		governance.Objects = append(governance.Objects, packet)
		governance.Enums = append(governance.Enums, packetEnums...)
		governance.Types = append(governance.Types, packetTypes...)
		governance.Fields = append(governance.Fields, packet.Fields...)
	}

	references, err := loadEnumReferences(metadataDir)
	if err != nil {
		loadErrors = append(loadErrors, err)
	} else {
		governance.EnumReferences = references
	}
	sortMetadataGovernance(&governance)
	catalog.Governance = governance
	if len(loadErrors) > 0 {
		return errors.Join(loadErrors...)
	}
	return nil
}

// sortedMappingKeys 是 YAML mapping 展开成 slice 时的唯一顺序来源。mappingFromNode 返回
// Go map，`range` 顺序被运行时刻意随机化，任何直接展开都会把随机顺序带进 governance
// slice，再经下游非稳定排序泄漏成非确定性产物。装配处按 key 收敛，产物就不依赖下游排序键
// 是否恰好全序。
func sortedMappingKeys(mapping map[string]*yaml.Node) []string {
	keys := make([]string, 0, len(mapping))
	for key := range mapping {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func sortMetadataGovernance(governance *ast.MetadataGovernance) {
	sort.Slice(governance.Objects, func(left, right int) bool {
		return governance.Objects[left].ObjectID < governance.Objects[right].ObjectID
	})
	for index := range governance.Objects {
		packet := &governance.Objects[index]
		sort.Slice(packet.Fields, func(left, right int) bool {
			if packet.Fields[left].Entity != packet.Fields[right].Entity {
				return packet.Fields[left].Entity < packet.Fields[right].Entity
			}
			return packet.Fields[left].Name < packet.Fields[right].Name
		})
		sort.Slice(packet.Errors, func(left, right int) bool {
			return packet.Errors[left].Code < packet.Errors[right].Code
		})
		sort.Slice(packet.Events, func(left, right int) bool {
			return packet.Events[left].Name < packet.Events[right].Name
		})
	}
	sort.Slice(governance.Enums, func(left, right int) bool {
		first := governance.Enums[left]
		second := governance.Enums[right]
		return strings.Join([]string{
			string(first.OwnerLevel), first.Domain, first.ObjectID, first.Name, first.SourcePath,
		}, "\x00") < strings.Join([]string{
			string(second.OwnerLevel), second.Domain, second.ObjectID, second.Name, second.SourcePath,
		}, "\x00")
	})
	sort.Slice(governance.EnumReferences, func(left, right int) bool {
		first := governance.EnumReferences[left]
		second := governance.EnumReferences[right]
		return strings.Join([]string{
			first.Domain, first.ObjectID, first.Name, first.SourcePath,
		}, "\x00") < strings.Join([]string{
			second.Domain, second.ObjectID, second.Name, second.SourcePath,
		}, "\x00")
	})
	sort.Slice(governance.Types, func(left, right int) bool {
		first := governance.Types[left]
		second := governance.Types[right]
		return strings.Join([]string{
			string(first.OwnerLevel), first.Domain, first.ObjectID, first.Name, first.SourcePath,
		}, "\x00") < strings.Join([]string{
			string(second.OwnerLevel), second.Domain, second.ObjectID, second.Name, second.SourcePath,
		}, "\x00")
	})
	sort.Slice(governance.Fields, func(left, right int) bool {
		first := governance.Fields[left]
		second := governance.Fields[right]
		return strings.Join([]string{
			first.Domain, first.ObjectID, first.Entity, first.Name, first.SourcePath,
		}, "\x00") < strings.Join([]string{
			second.Domain, second.ObjectID, second.Entity, second.Name, second.SourcePath,
		}, "\x00")
	})
}

func loadSharedTypeFields(
	metadataDir string,
	path string,
	domain string,
) ([]ast.FieldDefinition, error) {
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, err
	}
	types := top["types"]
	if types == nil || types.Kind != yaml.MappingNode {
		return nil, nil
	}
	mapping, err := mappingFromNode(types)
	if err != nil {
		return nil, fmt.Errorf("%s: types: %w", path, err)
	}
	sourcePath := relativePath(metadataDir, path)
	var result []ast.FieldDefinition
	for _, name := range sortedMappingKeys(mapping) {
		definitionMap, mapErr := mappingFromNode(mapping[name])
		if mapErr != nil {
			continue
		}
		fields, fieldsErr := decodeFields(
			definitionMap["fields"],
			ast.Object{Domain: domain},
			strings.TrimSpace(name),
			sourcePath,
		)
		if fieldsErr != nil {
			return nil, fmt.Errorf("%s: types.%s.fields: %w", path, name, fieldsErr)
		}
		result = append(result, fields...)
	}
	return result, nil
}

func loadSharedDefinitions(
	metadataDir string,
	path string,
	owner ast.EnumOwnerLevel,
	domain string,
) ([]ast.EnumDefinition, []ast.TypeDefinition, error) {
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, nil, nil
	} else if err != nil {
		return nil, nil, err
	}
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, nil, err
	}
	sourcePath := relativePath(metadataDir, path)
	enums, err := decodeEnumDefinitions(
		top["enums"],
		owner,
		domain,
		"",
		sourcePath,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("%s: enums: %w", path, err)
	}
	var types []ast.TypeDefinition
	if node := top["types"]; node != nil && node.Kind == yaml.MappingNode {
		mapping, mapErr := mappingFromNode(node)
		if mapErr != nil {
			return nil, nil, fmt.Errorf("%s: types: %w", path, mapErr)
		}
		for _, name := range sortedMappingKeys(mapping) {
			if trimmed := strings.TrimSpace(name); trimmed != "" {
				types = append(types, ast.TypeDefinition{
					Name:       trimmed,
					OwnerLevel: owner,
					Domain:     domain,
					SourcePath: sourcePath,
				})
			}
		}
	}
	return enums, types, nil
}

func loadObjectGovernance(
	metadataDir string,
	object ast.Object,
) (ast.ObjectGovernance, []ast.EnumDefinition, []ast.TypeDefinition, error) {
	objectPath := filepath.Join(metadataDir, filepath.FromSlash(object.SourcePath))
	objectDir := filepath.Dir(objectPath)
	packet := ast.ObjectGovernance{
		ObjectID:   object.ID,
		Domain:     object.Domain,
		SourcePath: object.SourcePath,
		Lifecycle:  object.Lifecycle,
	}

	fieldsPath := filepath.Join(objectDir, "fields.yaml")
	fields, declaredTypes, enums, err := loadFieldsGovernance(
		metadataDir,
		fieldsPath,
		object,
	)
	if err != nil {
		return packet, nil, nil, err
	}
	packet.Fields = fields
	packet.DeclaredTypes = declaredTypes

	errors, err := loadErrorsGovernance(metadataDir, objectDir, object)
	if err != nil {
		return packet, nil, nil, err
	}
	packet.Errors = errors
	events, err := loadEventsGovernance(metadataDir, objectDir, object)
	if err != nil {
		return packet, nil, nil, err
	}
	packet.Events = events
	privacy, err := loadPrivacyGovernance(metadataDir, objectDir, object)
	if err != nil {
		return packet, nil, nil, err
	}
	packet.Privacy = privacy

	typeDefinitions := make([]ast.TypeDefinition, 0, len(declaredTypes))
	for _, name := range declaredTypes {
		typeDefinitions = append(typeDefinitions, ast.TypeDefinition{
			Name:       name,
			OwnerLevel: ast.EnumOwnerObject,
			Domain:     object.Domain,
			ObjectID:   object.ID,
			SourcePath: relativePath(metadataDir, fieldsPath),
		})
	}
	return packet, enums, typeDefinitions, nil
}

func loadPrivacyGovernance(
	metadataDir string,
	objectDir string,
	object ast.Object,
) (*ast.PrivacyDefinition, error) {
	privacyPath := filepath.Join(objectDir, "privacy.yaml")
	if _, err := os.Stat(privacyPath); errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	document, err := loadPrivacyDocument(privacyPath)
	if err != nil {
		return nil, err
	}
	return &ast.PrivacyDefinition{
		ObjectID:   object.ID,
		Document:   document,
		SourcePath: relativePath(metadataDir, privacyPath),
	}, nil
}

func decodeLifecycle(
	node *yaml.Node,
	sourcePath string,
) (*ast.LifecycleDefinition, error) {
	mapping, err := mappingFromNode(node)
	if err != nil {
		return nil, err
	}
	immutable := false
	if value := mapping["immutable"]; value != nil {
		if err := value.Decode(&immutable); err != nil {
			return nil, fmt.Errorf("immutable: %w", err)
		}
	}
	eventConsumers, err := decodeLifecycleEventConsumers(mapping["event_consumers"])
	if err != nil {
		return nil, fmt.Errorf("event_consumers: %w", err)
	}
	return &ast.LifecycleDefinition{
		States:         stringSequence(mapping["states"]),
		StateField:     strings.TrimSpace(scalarString(mapping["state_field"])),
		Immutable:      immutable,
		SourceEvents:   trimStrings(stringSequence(mapping["source_events"])),
		Checkpoint:     strings.TrimSpace(scalarString(mapping["checkpoint"])),
		Rebuild:        strings.TrimSpace(scalarString(mapping["rebuild"])),
		Tombstone:      strings.TrimSpace(scalarString(mapping["tombstone"])),
		Idempotency:    strings.TrimSpace(scalarString(mapping["idempotency"])),
		EventConsumers: eventConsumers,
		SourcePath:     sourcePath,
	}, nil
}

func decodeLifecycleEventConsumers(
	node *yaml.Node,
) ([]ast.LifecycleEventConsumer, error) {
	if node == nil {
		return nil, nil
	}
	if node.Kind != yaml.SequenceNode || len(node.Content) == 0 {
		return nil, fmt.Errorf("must be a non-empty sequence")
	}
	result := make([]ast.LifecycleEventConsumer, 0, len(node.Content))
	for index, item := range node.Content {
		mapping, err := mappingFromNode(item)
		if err != nil {
			return nil, fmt.Errorf("[%d]: %w", index, err)
		}
		for key := range mapping {
			switch key {
			case "name", "kind", "facet", "method", "idempotency":
			default:
				return nil, fmt.Errorf("[%d]: unknown field %q", index, key)
			}
		}
		consumer := ast.LifecycleEventConsumer{
			Name:        strings.TrimSpace(scalarString(mapping["name"])),
			Kind:        strings.TrimSpace(scalarString(mapping["kind"])),
			Facet:       strings.TrimSpace(scalarString(mapping["facet"])),
			Method:      strings.TrimSpace(scalarString(mapping["method"])),
			Idempotency: strings.TrimSpace(scalarString(mapping["idempotency"])),
		}
		if consumer.Name == "" || consumer.Kind == "" || consumer.Facet == "" ||
			consumer.Method == "" || consumer.Idempotency == "" {
			return nil, fmt.Errorf("[%d]: name, kind, facet, method and idempotency are required", index)
		}
		result = append(result, consumer)
	}
	return result, nil
}

func loadFieldsGovernance(
	metadataDir string,
	path string,
	object ast.Object,
) ([]ast.FieldDefinition, []string, []ast.EnumDefinition, error) {
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, []string{object.Name}, nil, nil
	} else if err != nil {
		return nil, nil, nil, err
	}
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, nil, nil, err
	}
	if err := rejectNestedEnumDeclarations(top, path); err != nil {
		return nil, nil, nil, err
	}
	sourcePath := relativePath(metadataDir, path)
	rootEntity := strings.TrimSpace(scalarString(top["entity"]))
	if rootEntity == "" {
		rootEntity = object.Name
	}
	fields, err := decodeFields(
		top["fields"],
		object,
		rootEntity,
		sourcePath,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("%s: fields: %w", path, err)
	}
	declared := map[string]struct{}{object.Name: {}, rootEntity: {}}
	for _, section := range []string{"entities", "members", "types", "value_objects"} {
		node := top[section]
		if node == nil || node.Kind != yaml.MappingNode {
			continue
		}
		mapping, mapErr := mappingFromNode(node)
		if mapErr != nil {
			return nil, nil, nil, fmt.Errorf("%s: %s: %w", path, section, mapErr)
		}
		for _, key := range sortedMappingKeys(mapping) {
			name := strings.TrimSpace(key)
			if name == "" {
				continue
			}
			declared[name] = struct{}{}
			definitionMap, definitionErr := mappingFromNode(mapping[key])
			if definitionErr != nil {
				continue
			}
			nested, nestedErr := decodeFields(
				definitionMap["fields"],
				object,
				name,
				sourcePath,
			)
			if nestedErr != nil {
				return nil, nil, nil, fmt.Errorf(
					"%s: %s.%s.fields: %w",
					path,
					section,
					name,
					nestedErr,
				)
			}
			fields = append(fields, nested...)
		}
	}

	enums, err := decodeEnumDefinitions(
		top["enums"],
		ast.EnumOwnerObject,
		object.Domain,
		object.ID,
		sourcePath,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("%s: enums: %w", path, err)
	}
	declaredList := make([]string, 0, len(declared))
	for name := range declared {
		declaredList = append(declaredList, name)
	}
	sort.Strings(declaredList)
	return fields, declaredList, enums, nil
}

// rejectNestedEnumDeclarations keeps enum ownership explicit. Object-owned
// enums may live only at the top-level `enums:` key of fields.yaml; an `enums:`
// block nested below entities/members/types/value_objects is ignored by every
// canonical resolver and would therefore be an undetectable second truth
// source.
func rejectNestedEnumDeclarations(
	top map[string]*yaml.Node,
	path string,
) error {
	for _, section := range []string{"entities", "members", "types", "value_objects"} {
		node := top[section]
		if node == nil || !containsMappingKey(node, "enums") {
			continue
		}
		return fmt.Errorf(
			"%s: %s contains a nested enums declaration; declare object-owned enums at top-level or move shared enums to the owning _shared catalog",
			path,
			section,
		)
	}
	return nil
}

func containsMappingKey(node *yaml.Node, expected string) bool {
	if node == nil {
		return false
	}
	if node.Kind == yaml.MappingNode {
		for index := 0; index+1 < len(node.Content); index += 2 {
			if strings.TrimSpace(node.Content[index].Value) == expected {
				return true
			}
			if containsMappingKey(node.Content[index+1], expected) {
				return true
			}
		}
		return false
	}
	for _, child := range node.Content {
		if containsMappingKey(child, expected) {
			return true
		}
	}
	return false
}

func decodeFields(
	node *yaml.Node,
	object ast.Object,
	entity string,
	sourcePath string,
) ([]ast.FieldDefinition, error) {
	if node == nil {
		return nil, nil
	}
	if node.Kind != yaml.SequenceNode {
		return nil, fmt.Errorf("must be a sequence")
	}
	result := make([]ast.FieldDefinition, 0, len(node.Content))
	for _, item := range node.Content {
		mapping, err := mappingFromNode(item)
		if err != nil {
			return nil, err
		}
		fieldType := strings.TrimSpace(scalarString(mapping["type"]))
		result = append(result, ast.FieldDefinition{
			ObjectID:       object.ID,
			Domain:         object.Domain,
			Entity:         entity,
			Name:           strings.TrimSpace(scalarString(mapping["name"])),
			Type:           fieldType,
			EnumRef:        strings.TrimSpace(scalarString(mapping["enum_ref"])),
			InlineValues:   stringSequence(mapping["values"]),
			SemanticType:   strings.TrimSpace(scalarString(mapping["semantic_type"])),
			Classification: strings.TrimSpace(scalarString(mapping["classification"])),
			LogPolicy:      strings.TrimSpace(scalarString(mapping["log_policy"])),
			SourcePath:     sourcePath,
		})
	}
	return result, nil
}

func decodeEnumDefinitions(
	node *yaml.Node,
	owner ast.EnumOwnerLevel,
	domain string,
	objectID string,
	sourcePath string,
) ([]ast.EnumDefinition, error) {
	if node == nil {
		return nil, nil
	}
	var result []ast.EnumDefinition
	appendDefinition := func(name string, valuesNode *yaml.Node) {
		name = strings.TrimSpace(name)
		if name == "" {
			return
		}
		result = append(result, ast.EnumDefinition{
			Name:       name,
			Values:     enumValues(valuesNode),
			OwnerLevel: owner,
			Domain:     domain,
			ObjectID:   objectID,
			SourcePath: sourcePath,
		})
	}
	switch node.Kind {
	case yaml.MappingNode:
		mapping, err := mappingFromNode(node)
		if err != nil {
			return nil, err
		}
		for _, name := range sortedMappingKeys(mapping) {
			definition := mapping[name]
			if definition.Kind == yaml.MappingNode {
				definitionMap, mapErr := mappingFromNode(definition)
				if mapErr != nil {
					return nil, mapErr
				}
				appendDefinition(name, definitionMap["values"])
				continue
			}
			appendDefinition(name, definition)
		}
	case yaml.SequenceNode:
		for _, item := range node.Content {
			mapping, err := mappingFromNode(item)
			if err != nil {
				return nil, err
			}
			appendDefinition(scalarString(mapping["name"]), mapping["values"])
		}
	default:
		return nil, fmt.Errorf("must be a mapping or sequence")
	}
	return result, nil
}

func enumValues(node *yaml.Node) []string {
	if node == nil || node.Kind != yaml.SequenceNode {
		return nil
	}
	result := make([]string, 0, len(node.Content))
	for _, item := range node.Content {
		if item.Kind == yaml.ScalarNode {
			result = append(result, strings.TrimSpace(item.Value))
			continue
		}
		mapping, err := mappingFromNode(item)
		if err != nil {
			continue
		}
		value := strings.TrimSpace(scalarString(mapping["wire"]))
		if value == "" {
			value = strings.TrimSpace(scalarString(mapping["name"]))
		}
		result = append(result, value)
	}
	return result
}

func loadErrorsGovernance(
	metadataDir string,
	objectDir string,
	object ast.Object,
) ([]ast.ErrorDefinition, error) {
	path := filepath.Join(objectDir, "errors.yaml")
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, err
	}
	node := top["errors"]
	if node == nil || node.Kind != yaml.SequenceNode {
		return nil, nil
	}
	sourcePath := relativePath(metadataDir, path)
	result := make([]ast.ErrorDefinition, 0, len(node.Content))
	for _, item := range node.Content {
		mapping, mapErr := mappingFromNode(item)
		if mapErr != nil {
			return nil, fmt.Errorf("%s: errors: %w", path, mapErr)
		}
		var status *int
		if statusNode := mapping["http_status"]; statusNode != nil {
			value := 0
			if decodeErr := statusNode.Decode(&value); decodeErr != nil {
				return nil, fmt.Errorf("%s: http_status: %w", path, decodeErr)
			}
			status = &value
		}
		result = append(result, ast.ErrorDefinition{
			ObjectID:   object.ID,
			Code:       strings.TrimSpace(scalarString(mapping["code"])),
			HTTPStatus: status,
			EmittedBy:  decodeErrorEmissions(mapping["emitted_by"]),
			SourcePath: sourcePath,
		})
	}
	return result, nil
}

func decodeErrorEmissions(node *yaml.Node) []ast.ErrorEmission {
	if node == nil {
		return nil
	}
	if node.Kind == yaml.ScalarNode {
		return []ast.ErrorEmission{{Surface: strings.TrimSpace(node.Value)}}
	}
	if node.Kind != yaml.SequenceNode {
		return nil
	}
	result := make([]ast.ErrorEmission, 0, len(node.Content))
	for _, item := range node.Content {
		if item.Kind == yaml.ScalarNode {
			result = append(result, ast.ErrorEmission{
				Surface: strings.TrimSpace(item.Value),
			})
			continue
		}
		mapping, err := mappingFromNode(item)
		if err != nil {
			continue
		}
		operations := stringSequence(mapping["operations"])
		if operation := strings.TrimSpace(scalarString(mapping["operation"])); operation != "" {
			operations = append(operations, operation)
		}
		result = append(result, ast.ErrorEmission{
			Surface:    strings.TrimSpace(scalarString(mapping["surface"])),
			Operations: operations,
		})
	}
	return result
}

func loadEventsGovernance(
	metadataDir string,
	objectDir string,
	object ast.Object,
) ([]ast.EventDefinition, error) {
	path := filepath.Join(objectDir, "events.yaml")
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, err
	}
	node := top["events"]
	if node == nil || node.Kind != yaml.SequenceNode {
		return nil, nil
	}
	sourcePath := relativePath(metadataDir, path)
	result := make([]ast.EventDefinition, 0, len(node.Content))
	for _, item := range node.Content {
		mapping, mapErr := mappingFromNode(item)
		if mapErr != nil {
			return nil, fmt.Errorf("%s: events: %w", path, mapErr)
		}
		clientPayloadDefaults, defaultsErr := scalarStringMapping(
			mapping["client_payload_defaults"],
		)
		if defaultsErr != nil {
			return nil, fmt.Errorf(
				"%s: event %q client_payload_defaults: %w",
				path,
				scalarString(mapping["name"]),
				defaultsErr,
			)
		}
		result = append(result, ast.EventDefinition{
			ObjectID:              object.ID,
			Name:                  strings.TrimSpace(scalarString(mapping["name"])),
			DeliverySemantics:     strings.TrimSpace(scalarString(mapping["delivery_semantics"])),
			Topic:                 strings.TrimSpace(scalarString(mapping["topic"])),
			PayloadEntity:         strings.TrimSpace(scalarString(mapping["payload_entity"])),
			PayloadShape:          strings.TrimSpace(scalarString(mapping["payload_shape"])),
			PayloadFields:         stringSequence(mapping["payload_fields"]),
			ClientWSType:          strings.TrimSpace(scalarString(mapping["client_ws_type"])),
			ClientPayloadDefaults: clientPayloadDefaults,
			NoConsumerReason:      strings.TrimSpace(scalarString(mapping["no_consumer_reason"])),
			SourcePath:            sourcePath,
		})
	}
	return result, nil
}

func scalarStringMapping(node *yaml.Node) (map[string]string, error) {
	if node == nil {
		return nil, nil
	}
	mapping, err := mappingFromNode(node)
	if err != nil {
		return nil, err
	}
	result := make(map[string]string, len(mapping))
	for _, key := range sortedMappingKeys(mapping) {
		value := scalarString(mapping[key])
		if value == "" {
			return nil, fmt.Errorf("%q must map to a non-empty string", key)
		}
		result[strings.TrimSpace(key)] = value
	}
	return result, nil
}

func loadEnumReferences(metadataDir string) ([]ast.EnumReference, error) {
	var result []ast.EnumReference
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if entry.Name() == ".git" || entry.Name() == "test_fixtures" {
				return filepath.SkipDir
			}
			return nil
		}
		if filepath.Ext(entry.Name()) != ".yaml" && filepath.Ext(entry.Name()) != ".yml" {
			return nil
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var document yaml.Node
		if err := yaml.Unmarshal(data, &document); err != nil {
			return fmt.Errorf("%s: %w", path, err)
		}
		relative := relativePath(metadataDir, path)
		domain, objectID := governanceScope(relative)
		collectEnumReferences(
			&document,
			func(name string) {
				result = append(result, ast.EnumReference{
					Name:       name,
					Domain:     domain,
					ObjectID:   objectID,
					SourcePath: relative,
				})
			},
		)
		return nil
	})
	return result, err
}

func governanceScope(relative string) (string, string) {
	parts := strings.Split(filepath.ToSlash(relative), "/")
	if len(parts) == 0 || strings.HasPrefix(parts[0], "_") {
		return "", ""
	}
	domain := parts[0]
	if len(parts) >= 4 && parts[1] != "_shared" {
		return domain, domain + "." + strings.ReplaceAll(parts[2], "-", "_")
	}
	return domain, ""
}

func collectEnumReferences(node *yaml.Node, appendReference func(string)) {
	if node == nil {
		return
	}
	if node.Kind == yaml.MappingNode {
		for index := 0; index+1 < len(node.Content); index += 2 {
			key := node.Content[index]
			value := node.Content[index+1]
			if key.Value == "enum_ref" && value.Kind == yaml.ScalarNode {
				if name := strings.TrimSpace(value.Value); name != "" {
					appendReference(name)
				}
			}
			collectEnumReferences(value, appendReference)
		}
		return
	}
	for _, child := range node.Content {
		collectEnumReferences(child, appendReference)
	}
}
