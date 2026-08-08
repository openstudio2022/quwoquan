package codegen

import (
	"bytes"
	"fmt"
	"go/format"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"text/template"
	"unicode"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/codegen/eventconstants"
)

type DomainGeneratorOption func(*domainGeneratorConfig)

type domainGeneratorConfig struct {
	typedEnums          bool
	resolveSliceEntity  bool
	skipViewEntities    bool
	goFieldIDSuffix     bool
	businessObjectsOnly bool
	objectFirstRoot     bool
}

func WithTypedEnums() DomainGeneratorOption {
	return func(config *domainGeneratorConfig) {
		config.typedEnums = true
	}
}

func WithSliceEntityRefs() DomainGeneratorOption {
	return func(config *domainGeneratorConfig) {
		config.resolveSliceEntity = true
	}
}

func WithSkipViewEntities() DomainGeneratorOption {
	return func(config *domainGeneratorConfig) {
		config.skipViewEntities = true
	}
}

func WithGoFieldIDSuffix() DomainGeneratorOption {
	return func(config *domainGeneratorConfig) {
		config.goFieldIDSuffix = true
	}
}

// WithBusinessObjectEntitiesOnly prevents transport DTOs, command receipts,
// outbox records, checkpoints and inbox rows from leaking into generated
// contract model packages. An entity is eligible only when object.yaml owns it
// as the aggregate root or one of its bounded members.
func WithBusinessObjectEntitiesOnly() DomainGeneratorOption {
	return func(config *domainGeneratorConfig) {
		config.businessObjectsOnly = true
	}
}

// WithObjectFirstRoot emits domain/model and domain/event relative to an
// already-resolved <domain>/<context>/<object> source root.
func WithObjectFirstRoot() DomainGeneratorOption {
	return func(config *domainGeneratorConfig) {
		config.objectFirstRoot = true
	}
}

type DomainGenerator struct {
	source    *Source
	outputDir string
	config    domainGeneratorConfig
}

func NewDomainGenerator(
	source *Source,
	outputDir string,
	options ...DomainGeneratorOption,
) *DomainGenerator {
	var config domainGeneratorConfig
	for _, option := range options {
		option(&config)
	}
	return &DomainGenerator{
		source:    source,
		outputDir: outputDir,
		config:    config,
	}
}

func (generator *DomainGenerator) GenerateDomainModel(
	aggregateName string,
) error {
	data, err := generator.buildTemplateData(aggregateName)
	if err != nil {
		return err
	}
	return renderDomainFile(
		goModelTemplate,
		data,
		filepath.Join(generator.outputDir, data.DomainModelPath, data.SnakeName+".go"),
	)
}

func (generator *DomainGenerator) GenerateDomainEvents(
	aggregateName string,
) error {
	data, err := generator.buildTemplateData(aggregateName)
	if err != nil {
		return err
	}
	return renderDomainFile(
		goEventsTemplate,
		data,
		filepath.Join(generator.outputDir, path.Dir(data.DomainModelPath), "event", "events.go"),
	)
}

// GenerateObjectEvents is the repository-wide orchestrator entrypoint. Unlike
// the legacy aggregate-name method, it resolves one exact canonical object and
// cannot select a same-named aggregate from another domain.
func (generator *DomainGenerator) GenerateObjectEvents(objectID string) error {
	object, err := generator.findObjectByID(objectID)
	if err != nil {
		return err
	}
	data, err := generator.buildObjectTemplateData(object)
	if err != nil {
		return err
	}
	return renderDomainFile(
		goEventsTemplate,
		data,
		filepath.Join(generator.outputDir, path.Dir(data.DomainModelPath), "event", "events.go"),
	)
}

type fieldsDocument struct {
	Entity       string                          `yaml:"entity"`
	Fields       []domainField                   `yaml:"fields"`
	Entities     map[string]domainEntityDocument `yaml:"entities"`
	Members      map[string]domainEntityDocument `yaml:"members"`
	ValueObjects map[string]domainEntityDocument `yaml:"value_objects"`
	Types        map[string]domainEntityDocument `yaml:"types"`
	Enums        map[string]localEnumDocument    `yaml:"enums"`
}

type localEnumDocument struct {
	Values []string `yaml:"values"`
}

type domainEntityDocument struct {
	Fields []domainField `yaml:"fields"`
}

type domainField struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	ObjectRef   string   `yaml:"object_ref"`
	EnumRef     string   `yaml:"enum_ref"`
	Constraints []string `yaml:"constraints"`
}

type eventsDocument struct {
	Events []domainEvent `yaml:"events"`
}

type domainEvent struct {
	Name              string   `yaml:"name"`
	DeliverySemantics string   `yaml:"delivery_semantics"`
	WireEventType     string   `yaml:"wire_event_type"`
	ClientWsType      string   `yaml:"client_ws_type"`
	Description       string   `yaml:"description"`
	PayloadEntity     string   `yaml:"payload_entity"`
	PayloadFields     []string `yaml:"payload_fields"`
}

type sharedTypesDocument struct {
	Types map[string]domainEntityDocument `yaml:"types"`
	Enums map[string][]string             `yaml:"enums"`
}

type domainTemplateData struct {
	PackageName     string
	AggregateRoot   string
	SnakeName       string
	DomainModelPath string
	Entities        []domainEntityData
	EnumTypes       []domainEnumTypeData
	Events          []domainEventData
}

type domainEnumTypeData struct {
	Name   string
	Values []domainEnumValueData
}

type domainEnumValueData struct {
	ConstName string
	WireValue string
}

type domainEntityData struct {
	Name   string
	IsRoot bool
	Fields []domainFieldData
}

type domainFieldData struct {
	GoName  string
	GoType  string
	JSONTag string
	BSONTag string
}

type domainEventData struct {
	Name         string
	WireValue    string
	ClientWsType string
}

func (generator *DomainGenerator) buildTemplateData(
	aggregateName string,
) (domainTemplateData, error) {
	object, err := generator.findObject(aggregateName)
	if err != nil {
		return domainTemplateData{}, err
	}
	return generator.buildObjectTemplateData(object)
}

func (generator *DomainGenerator) buildObjectTemplateData(
	object ast.Object,
) (domainTemplateData, error) {
	aggregateName := object.Name
	objectDir := path.Dir(object.SourcePath)
	var fields fieldsDocument
	if err := generator.source.Decode(
		path.Join(objectDir, "fields.yaml"),
		&fields,
	); err != nil {
		return domainTemplateData{}, err
	}
	if len(fields.Entities) == 0 && len(fields.Fields) > 0 {
		entityName := strings.TrimSpace(fields.Entity)
		if entityName == "" {
			entityName = object.Name
		}
		fields.Entities = map[string]domainEntityDocument{
			entityName: {Fields: fields.Fields},
		}
	}
	if fields.Entities == nil {
		fields.Entities = make(map[string]domainEntityDocument)
	}
	for name, member := range fields.Members {
		fields.Entities[name] = member
	}
	sharedTypes, err := generator.sharedValueTypes()
	if err != nil {
		return domainTemplateData{}, err
	}
	referencedValueObjects := includeReferencedOwnedTypes(&fields, sharedTypes)

	data := domainTemplateData{
		PackageName:     strings.ToLower(aggregateName),
		AggregateRoot:   aggregateName,
		SnakeName:       CamelToSnake(aggregateName),
		DomainModelPath: generator.domainModelOutputPath(object),
	}
	entityNames := make([]string, 0, len(fields.Entities))
	registeredEntities, err := generator.registeredBusinessEntities(object, path.Join(objectDir, "fields.yaml"))
	if err != nil {
		return domainTemplateData{}, err
	}
	for name := range fields.Entities {
		if generator.config.businessObjectsOnly {
			if _, registered := registeredEntities[name]; !registered {
				if _, valueObject := referencedValueObjects[name]; !valueObject {
					continue
				}
			}
		}
		if generator.config.skipViewEntities &&
			strings.HasSuffix(name, "View") {
			continue
		}
		entityNames = append(entityNames, name)
	}
	sort.Strings(entityNames)
	entitySet := make(map[string]struct{}, len(entityNames))
	for _, name := range entityNames {
		entitySet[name] = struct{}{}
	}

	if generator.config.typedEnums {
		data.EnumTypes, err = generator.collectEnumTypes(fields, entityNames)
		if err != nil {
			return domainTemplateData{}, err
		}
	}
	for _, entityName := range entityNames {
		entity := fields.Entities[entityName]
		entityData := domainEntityData{
			Name:   entityName,
			IsRoot: entityName == aggregateName,
		}
		for _, field := range entity.Fields {
			jsonTag := field.Name
			if field.Name == "_id" {
				jsonTag = "id"
			}
			goType, err := generator.fieldGoType(field, entitySet)
			if err != nil {
				return domainTemplateData{}, fmt.Errorf(
					"%s.%s from %s: %w",
					entityName,
					field.Name,
					path.Join(objectDir, "fields.yaml"),
					err,
				)
			}
			entityData.Fields = append(
				entityData.Fields,
				domainFieldData{
					GoName:  generator.fieldGoName(field.Name),
					GoType:  goType,
					JSONTag: jsonTag,
					BSONTag: field.Name,
				},
			)
		}
		data.Entities = append(data.Entities, entityData)
	}

	eventsPath := path.Join(objectDir, "events.yaml")
	if generator.source.Has(eventsPath) {
		var events eventsDocument
		if err := generator.source.Decode(eventsPath, &events); err != nil {
			return domainTemplateData{}, err
		}
		for _, event := range events.Events {
			wireValue, wireErr := domainEventWireValue(event)
			if wireErr != nil {
				return domainTemplateData{}, fmt.Errorf("%s: %w", eventsPath, wireErr)
			}
			data.Events = append(
				data.Events,
				domainEventData{
					Name:         event.Name,
					WireValue:    wireValue,
					ClientWsType: strings.TrimSpace(event.ClientWsType),
				},
			)
		}
	}
	return data, nil
}

func domainEventWireValue(event domainEvent) (string, error) {
	return eventconstants.WireValue(
		event.Name,
		event.DeliverySemantics,
		event.WireEventType,
	)
}

// includeReferencedOwnedTypes promotes only named owned values reachable from
// the generated aggregate/member graph. `types` is the canonical fields.yaml
// vocabulary used by transport codegen; object_ref identifies the named type
// when the wire shape is `object`. Unreachable request/response DTOs stay out of
// domain packages.
//
// sharedTypes carries `_shared/types.yaml` `types:` so a cross-service value
// object keeps a single wire owner there instead of being copied into every
// consuming object's fields.yaml. Resolution order is local-first, mirroring how
// collectEnumTypes resolves shared enums.
func includeReferencedOwnedTypes(
	fields *fieldsDocument,
	sharedTypes map[string]domainEntityDocument,
) map[string]struct{} {
	result := make(map[string]struct{})
	for {
		changed := false
		for _, entity := range fields.Entities {
			for _, field := range entity.Fields {
				candidate := strings.TrimSpace(field.ObjectRef)
				if candidate == "" {
					candidate = strings.TrimSpace(field.Type)
				}
				if strings.HasPrefix(candidate, "[]") {
					candidate = strings.TrimSpace(strings.TrimPrefix(candidate, "[]"))
				}
				valueObject, exists := fields.ValueObjects[candidate]
				if !exists {
					valueObject, exists = fields.Types[candidate]
				}
				if !exists {
					valueObject, exists = sharedTypes[candidate]
				}
				if !exists {
					continue
				}
				if _, included := result[candidate]; included {
					continue
				}
				fields.Entities[candidate] = valueObject
				result[candidate] = struct{}{}
				changed = true
			}
		}
		if !changed {
			return result
		}
	}
}

// sharedValueTypes returns the `types:` roster from _shared/types.yaml, the
// single wire owner for cross-service value objects.
func (generator *DomainGenerator) sharedValueTypes() (
	map[string]domainEntityDocument,
	error,
) {
	if generator.source == nil {
		return nil, nil
	}
	if !generator.source.Has("_shared/types.yaml") {
		return nil, nil
	}
	var shared sharedTypesDocument
	if err := generator.source.Decode("_shared/types.yaml", &shared); err != nil {
		return nil, fmt.Errorf("decode _shared/types.yaml: %w", err)
	}
	return shared.Types, nil
}

func (generator *DomainGenerator) registeredBusinessEntities(object ast.Object, fieldsPath string) (map[string]struct{}, error) {
	registered := make(map[string]struct{})
	rootFound := false
	for _, objectMap := range generator.source.Graph().BusinessObjectMaps {
		for _, boundary := range objectMap.Objects {
			if path.Clean(boundary.SourceDocument) != path.Clean(fieldsPath) || strings.TrimSpace(boundary.SourceEntity) == "" {
				continue
			}
			registered[boundary.SourceEntity] = struct{}{}
			if boundary.CanonicalObject == object.Name {
				rootFound = true
			}
		}
	}
	if generator.config.businessObjectsOnly && !rootFound {
		return nil, fmt.Errorf("business object %q has no source_entity registration for %s", object.Name, fieldsPath)
	}
	if rootFound {
		for _, member := range object.Members {
			if name := strings.TrimSpace(member.Name); name != "" {
				registered[name] = struct{}{}
			}
		}
	}
	return registered, nil
}

func (generator *DomainGenerator) domainModelOutputPath(object ast.Object) string {
	if generator.config.objectFirstRoot {
		return path.Join("contract", "model")
	}
	return path.Join("domain", strings.ToLower(object.Name), "model")
}

func (generator *DomainGenerator) findObject(name string) (ast.Object, error) {
	for _, object := range generator.source.Graph().Objects {
		if object.Name == name {
			return object, nil
		}
	}
	return ast.Object{}, fmt.Errorf("business object %q not found", name)
}

func (generator *DomainGenerator) findObjectByID(objectID string) (ast.Object, error) {
	for _, object := range generator.source.Graph().Objects {
		if object.ID == objectID {
			return object, nil
		}
	}
	return ast.Object{}, fmt.Errorf("business object %q not found", objectID)
}

func (generator *DomainGenerator) collectEnumTypes(
	fields fieldsDocument,
	entityNames []string,
) ([]domainEnumTypeData, error) {
	references := map[string]struct{}{}
	for _, entityName := range entityNames {
		for _, field := range fields.Entities[entityName].Fields {
			if strings.TrimSpace(field.Type) == "enum" && field.EnumRef != "" {
				references[field.EnumRef] = struct{}{}
			}
		}
	}
	names := make([]string, 0, len(references))
	for name := range references {
		names = append(names, name)
	}
	sort.Strings(names)
	var shared sharedTypesDocument
	for _, name := range names {
		if _, local := fields.Enums[name]; local {
			continue
		}
		if generator.source == nil {
			return nil, fmt.Errorf("enum %q requires a metadata source for shared type resolution", name)
		}
		if err := generator.source.Decode("_shared/types.yaml", &shared); err != nil {
			return nil, err
		}
		break
	}
	result := make([]domainEnumTypeData, 0, len(names))
	for _, name := range names {
		values, exists := shared.Enums[name]
		if local, localExists := fields.Enums[name]; localExists {
			values, exists = local.Values, true
		}
		if !exists {
			return nil, fmt.Errorf("enum %q is not declared in fields.yaml enums or _shared/types.yaml", name)
		}
		enumType := domainEnumTypeData{Name: name}
		for _, value := range values {
			enumType.Values = append(enumType.Values, domainEnumValueData{
				ConstName: enumConstName(name, value),
				WireValue: value,
			})
		}
		result = append(result, enumType)
	}
	return result, nil
}

func (generator *DomainGenerator) fieldGoName(name string) string {
	if generator.config.goFieldIDSuffix &&
		name != "_id" &&
		strings.HasSuffix(name, "Id") {
		return camelBaseToPascal(name[:len(name)-2]) + "ID"
	}
	if name == "_id" {
		return "ID"
	}
	return camelBaseToPascal(strings.ReplaceAll(name, "_", " "))
}

func (generator *DomainGenerator) fieldGoType(
	field domainField,
	entityNames map[string]struct{},
) (string, error) {
	fieldType := strings.TrimSpace(field.Type)
	if objectRef := strings.TrimSpace(field.ObjectRef); objectRef != "" {
		if _, exists := entityNames[objectRef]; exists {
			return objectRef, nil
		}
	}
	if strings.HasPrefix(fieldType, "[]") {
		inner := strings.TrimSpace(strings.TrimPrefix(fieldType, "[]"))
		if inner == "" {
			return "", fmt.Errorf("array type %q has no element type", fieldType)
		}
		if _, exists := entityNames[inner]; exists {
			if !generator.config.resolveSliceEntity {
				return "", fmt.Errorf(
					"array element %q is a named entity; enable slice entity references",
					inner,
				)
			}
			return "[]" + inner, nil
		}
		innerType, err := metadataTypeToGo(inner)
		if err != nil {
			return "", fmt.Errorf("array element: %w", err)
		}
		return "[]" + innerType, nil
	}
	if fieldType == "enum" && generator.config.typedEnums && field.EnumRef != "" {
		return field.EnumRef, nil
	}
	if fieldType == "enum" && generator.config.typedEnums {
		return "", fmt.Errorf("typed enum field requires enum_ref")
	}
	if _, exists := entityNames[fieldType]; exists {
		return fieldType, nil
	}
	return metadataTypeToGo(fieldType)
}

func metadataTypeToGo(value string) (string, error) {
	switch value {
	case "string", "ObjectId", "uuid", "url":
		return "string", nil
	case "int64", "int", "integer", "long":
		return "int64", nil
	case "int32":
		return "int32", nil
	case "float", "float64", "double":
		return "float64", nil
	case "float32":
		return "float32", nil
	case "bool", "boolean":
		return "bool", nil
	case "date", "datetime", "timestamp":
		return "time.Time", nil
	case "enum":
		return "string", nil
	case "json", "jsonb", "map", "object":
		return "map[string]any", nil
	case "bytes", "binary":
		return "[]byte", nil
	case "array", "list", "embedded_list":
		return "", fmt.Errorf("collection type %q must declare an explicit []T element type", value)
	default:
		return "", fmt.Errorf("unsupported metadata type %q", value)
	}
}

func camelBaseToPascal(value string) string {
	parts := strings.FieldsFunc(value, func(current rune) bool {
		return current == '_' || current == '-' || unicode.IsSpace(current)
	})
	var result strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		result.WriteString(strings.ToUpper(part[:1]))
		result.WriteString(part[1:])
	}
	return result.String()
}

func enumConstName(typeName, wireValue string) string {
	var result strings.Builder
	result.WriteString(typeName)
	for _, part := range strings.Split(wireValue, "_") {
		if part == "" {
			continue
		}
		runes := []rune(part)
		result.WriteRune(unicode.ToUpper(runes[0]))
		result.WriteString(string(runes[1:]))
	}
	return result.String()
}

func renderDomainFile(
	templateSource string,
	data domainTemplateData,
	outputPath string,
) error {
	compiled, err := template.New("domain").Parse(templateSource)
	if err != nil {
		return err
	}
	var buffer bytes.Buffer
	if err := compiled.Execute(&buffer, data); err != nil {
		return err
	}
	formatted, err := format.Source(buffer.Bytes())
	if err != nil {
		return fmt.Errorf("format %s: %w", outputPath, err)
	}
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return err
	}
	return os.WriteFile(outputPath, formatted, 0o644)
}

const goModelTemplate = `// Code generated by internal/metadata/codegen. DO NOT EDIT.
package {{.PackageName}}

import "time"

var _ = time.Now
{{range $type := .EnumTypes}}
// {{$type.Name}} enumerates allowed wire values for {{$type.Name}}.
type {{$type.Name}} string

const (
{{range $type.Values}}
	{{.ConstName}} {{$type.Name}} = "{{.WireValue}}"
{{end}}
)
{{end}}
{{range .Entities}}
// {{.Name}} domain model.
type {{.Name}} struct {
{{- range .Fields}}
	{{.GoName}} {{.GoType}} ` + "`" + `json:"{{.JSONTag}}" bson:"{{.BSONTag}}"` + "`" + `
{{- end}}
}
{{end}}
`

const goEventsTemplate = `// Code generated by internal/metadata/codegen. DO NOT EDIT.
package event
{{if .Events}}
// Event type constants for {{.AggregateRoot}}.
const (
{{- range .Events}}
	{{.Name}} = "{{.WireValue}}"
{{- end}}
)
{{end}}
// ClientRealtimeWireTypes contains only events explicitly exposed by
// client_ws_type. Server-only domain events never enter realtime client fanout.
var ClientRealtimeWireTypes = map[string]string{
{{- range .Events}}{{if .ClientWsType}}
	{{.Name}}: "{{.ClientWsType}}",
{{- end}}{{end}}
}
`
