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
)

type DomainGeneratorOption func(*domainGeneratorConfig)

type domainGeneratorConfig struct {
	typedEnums          bool
	resolveSliceEntity  bool
	skipViewEntities    bool
	goFieldIDSuffix     bool
	businessObjectsOnly bool
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
// domain model packages. An entity is eligible only when business_object_map
// registers it as a governed business object for the same fields document.
func WithBusinessObjectEntitiesOnly() DomainGeneratorOption {
	return func(config *domainGeneratorConfig) {
		config.businessObjectsOnly = true
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

type fieldsDocument struct {
	Entity   string                          `yaml:"entity"`
	Fields   []domainField                   `yaml:"fields"`
	Entities map[string]domainEntityDocument `yaml:"entities"`
}

type domainEntityDocument struct {
	Fields []domainField `yaml:"fields"`
}

type domainField struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	EnumRef     string   `yaml:"enum_ref"`
	Constraints []string `yaml:"constraints"`
}

type eventsDocument struct {
	Events []domainEvent `yaml:"events"`
}

type domainEvent struct {
	Name          string   `yaml:"name"`
	Description   string   `yaml:"description"`
	PayloadEntity string   `yaml:"payload_entity"`
	PayloadFields []string `yaml:"payload_fields"`
}

type sharedTypesDocument struct {
	Enums map[string][]string `yaml:"enums"`
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
	Name string
}

func (generator *DomainGenerator) buildTemplateData(
	aggregateName string,
) (domainTemplateData, error) {
	object, err := generator.findObject(aggregateName)
	if err != nil {
		return domainTemplateData{}, err
	}
	objectDir := path.Dir(object.SourcePath)
	var fields fieldsDocument
	if err := generator.source.Decode(
		path.Join(objectDir, "fields.yaml"),
		&fields,
	); err != nil {
		return domainTemplateData{}, err
	}
	if len(fields.Entities) == 0 && fields.Entity != "" {
		fields.Entities = map[string]domainEntityDocument{
			fields.Entity: {Fields: fields.Fields},
		}
	}

	data := domainTemplateData{
		PackageName:     strings.ToLower(aggregateName),
		AggregateRoot:   aggregateName,
		SnakeName:       CamelToSnake(aggregateName),
		DomainModelPath: domainModelOutputPath(object),
	}
	entityNames := make([]string, 0, len(fields.Entities))
	registeredEntities, err := generator.registeredBusinessEntities(object, path.Join(objectDir, "fields.yaml"))
	if err != nil {
		return domainTemplateData{}, err
	}
	for name := range fields.Entities {
		if generator.config.businessObjectsOnly {
			if _, registered := registeredEntities[name]; !registered {
				continue
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
			entityData.Fields = append(
				entityData.Fields,
				domainFieldData{
					GoName:  generator.fieldGoName(field.Name),
					GoType:  generator.fieldGoType(field, entitySet),
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
			data.Events = append(
				data.Events,
				domainEventData{Name: event.Name},
			)
		}
	}
	return data, nil
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
	return registered, nil
}

func domainModelOutputPath(object ast.Object) string {
	configured := path.Clean(strings.TrimSpace(object.DDDLayer.DomainModel))
	if configured == "." || configured == "" {
		return path.Join("domain", strings.ToLower(object.Name), "model")
	}
	configured = strings.TrimPrefix(configured, "./")
	configured = strings.TrimPrefix(configured, "internal/")
	return configured
}

func (generator *DomainGenerator) findObject(name string) (ast.Object, error) {
	for _, object := range generator.source.Graph().Objects {
		if object.Name == name {
			return object, nil
		}
	}
	return ast.Object{}, fmt.Errorf("business object %q not found", name)
}

func (generator *DomainGenerator) collectEnumTypes(
	fields fieldsDocument,
	entityNames []string,
) ([]domainEnumTypeData, error) {
	var shared sharedTypesDocument
	if err := generator.source.Decode("_shared/types.yaml", &shared); err != nil {
		return nil, err
	}
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
	result := make([]domainEnumTypeData, 0, len(names))
	for _, name := range names {
		values, exists := shared.Enums[name]
		if !exists {
			return nil, fmt.Errorf("enum %q is not declared in _shared/types.yaml", name)
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
) string {
	fieldType := strings.TrimSpace(field.Type)
	if strings.HasPrefix(fieldType, "[]") {
		inner := strings.TrimSpace(strings.TrimPrefix(fieldType, "[]"))
		if inner == "string" {
			return "[]string"
		}
		if generator.config.resolveSliceEntity {
			if _, exists := entityNames[inner]; exists {
				return "[]" + inner
			}
		}
	}
	if fieldType == "enum" && generator.config.typedEnums && field.EnumRef != "" {
		return field.EnumRef
	}
	return metadataTypeToGo(fieldType)
}

func metadataTypeToGo(value string) string {
	switch value {
	case "string", "ObjectId":
		return "string"
	case "int64", "int", "integer":
		return "int64"
	case "float", "float64", "double":
		return "float64"
	case "bool", "boolean":
		return "bool"
	case "datetime", "timestamp":
		return "time.Time"
	case "enum":
		return "string"
	case "json", "map", "object":
		return "map[string]any"
	case "array", "list":
		return "[]any"
	case "GeoPoint":
		return "GeoPoint"
	default:
		return "any"
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

// GeoPoint represents a geographic coordinate.
type GeoPoint struct {
	Latitude  float64 ` + "`json:\"latitude\" bson:\"latitude\"`" + `
	Longitude float64 ` + "`json:\"longitude\" bson:\"longitude\"`" + `
}

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
	{{.Name}} = "{{.Name}}"
{{- end}}
)
{{end}}
`
