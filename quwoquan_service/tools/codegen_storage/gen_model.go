package main

import (
	"bytes"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"strings"
	"text/template"

	"quwoquan_service/internal/metadata/codegen"
)

type modelData struct {
	Package     string
	EntityName  string
	MetaSource  string
	Fields      []modelFieldData
	NestedTypes []nestedTypeData
	NeedsTime   bool
	NeedsJSON   bool
}

type modelFieldData struct {
	GoName  string
	GoType  string
	JSONTag string
	DBTag   string
}

type nestedTypeData struct {
	Name        string
	Description string
	Fields      []modelFieldData
}

func generateModels(ctx *genContext) error {
	backend := ctx.storage.Backend
	if len(ctx.storage.Tables) > 0 && backend == "" {
		backend = "postgres"
	}
	if len(ctx.storage.Collections) > 0 && backend == "" {
		backend = "mongodb"
	}

	generated := make(map[string]bool)

	if backend == "postgres" || len(ctx.storage.Tables) > 0 {
		for tableName, table := range ctx.storage.Tables {
			if !table.InfrastructureOnly && strings.TrimSpace(table.Entity) == "" {
				return fmt.Errorf(
					"table %s has no entity; mark infrastructure_only when the model is handwritten",
					tableName,
				)
			}
		}
		for _, table := range ctx.storage.Tables {
			if table.InfrastructureOnly {
				continue
			}
			if generated[table.Entity] {
				continue
			}
			if err := generatePGModel(ctx, table.Entity, table); err != nil {
				return fmt.Errorf("gen model %s: %w", table.Entity, err)
			}
			generated[table.Entity] = true
		}
	}

	if backend == "mongodb" || len(ctx.storage.Collections) > 0 {
		for _, coll := range ctx.storage.Collections {
			if generated[coll.Entity] {
				continue
			}
			if err := generateMongoModel(ctx, coll.Entity); err != nil {
				return fmt.Errorf("gen model %s: %w", coll.Entity, err)
			}
			generated[coll.Entity] = true
		}
	}

	return nil
}

func generatePGModel(ctx *genContext, entityName string, table TableDef) error {
	dir := filepath.Join(ctx.outputDir(), "contract", ctx.source.domainPath())
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	entityFields := ctx.fields.Entities[entityName]
	fieldMap := make(map[string]FieldDef)
	for _, f := range entityFields.Fields {
		fieldMap[f.Name] = f
	}

	var fields []modelFieldData
	needsTime := false
	needsJSON := false
	nested := newNestedCollector(ctx)

	for _, col := range table.Columns {
		camelName := codegen.SnakeToCamel(col.Name)
		goName := codegen.SnakeToGoName(col.Name)

		field := fieldMap[camelName]
		goType := resolveGoType(ctx, nested, entityName, camelName, field, col)

		jsonTag := camelName
		if field.APIExposure == "drop" {
			jsonTag = "-"
		}

		if strings.Contains(goType, "time.Time") {
			needsTime = true
		}
		if strings.Contains(goType, "json.") {
			needsJSON = true
		}

		fields = append(fields, modelFieldData{
			GoName:  goName,
			GoType:  goType,
			JSONTag: jsonTag,
			DBTag:   fmt.Sprintf(`db:"%s"`, col.Name),
		})
	}

	nestedTypes, nestedNeedsTime := nested.materialize()
	return writeModel(ctx, entityName, dir, fields, nestedTypes, needsTime || nestedNeedsTime, needsJSON)
}

func generateMongoModel(ctx *genContext, entityName string) error {
	dir := filepath.Join(ctx.outputDir(), "contract", ctx.source.domainPath())
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	entityFields := ctx.fields.Entities[entityName]
	if len(entityFields.Fields) == 0 {
		var flat struct {
			Fields []FieldDef `yaml:"fields"`
		}
		if ctx.fields.Entity == entityName {
			entityFields = EntityFieldsDef{Fields: ctx.fields.Entities[entityName].Fields}
		}
		if len(entityFields.Fields) == 0 {
			_ = flat
			return fmt.Errorf("no fields found for mongo entity %s", entityName)
		}
	}

	var fields []modelFieldData
	needsTime := false
	nested := newNestedCollector(ctx)

	for _, f := range entityFields.Fields {
		goName := codegen.CamelToGoName(f.Name)
		notNull := hasConstraint(f.Constraints, "NOT_NULL") || hasConstraint(f.Constraints, "PK")
		goType := fieldTypeToGoType(nested, f.Name, f.Type, notNull)

		jsonTag := f.Name
		if f.Name == "_id" {
			jsonTag = "id"
		}
		if f.APIExposure == "drop" {
			jsonTag = "-"
		}

		if strings.Contains(goType, "time.Time") {
			needsTime = true
		}

		fields = append(fields, modelFieldData{
			GoName:  goName,
			GoType:  goType,
			JSONTag: jsonTag,
			DBTag:   fmt.Sprintf(`bson:"%s"`, f.Name),
		})
	}

	nestedTypes, nestedNeedsTime := nested.materialize()
	return writeModel(ctx, entityName, dir, fields, nestedTypes, needsTime || nestedNeedsTime, false)
}

func writeModel(
	ctx *genContext,
	entityName, dir string,
	fields []modelFieldData,
	nestedTypes []nestedTypeData,
	needsTime, needsJSON bool,
) error {
	data := modelData{
		Package:     "model",
		EntityName:  entityName,
		MetaSource:  ctx.source.Metadata,
		Fields:      fields,
		NestedTypes: nestedTypes,
		NeedsTime:   needsTime,
		NeedsJSON:   needsJSON,
	}

	tmpl, err := template.New("model").Parse(modelTemplate)
	if err != nil {
		return fmt.Errorf("parse model template: %w", err)
	}

	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		return fmt.Errorf("execute model template: %w", err)
	}

	formatted, err := format.Source(buf.Bytes())
	if err != nil {
		formatted = buf.Bytes()
	}

	fileName := codegen.CamelToSnake(entityName) + ".g.go"
	path := filepath.Join(dir, fileName)
	fmt.Printf("  model: %s/%s\n", filepath.ToSlash(ctx.source.domainPath()), fileName)
	return os.WriteFile(path, formatted, 0644)
}

func resolveGoType(
	ctx *genContext,
	nested *nestedCollector,
	entityName, camelName string,
	field FieldDef,
	col ColumnDef,
) string {
	if overrides, ok := ctx.source.TypeOverrides[entityName]; ok {
		if goType, ok := overrides[camelName]; ok {
			return goType
		}
	}

	notNull := col.IsNotNull() || col.IsPrimaryKey()

	if field.Type != "" {
		return fieldTypeToGoType(nested, camelName, field.Type, notNull)
	}

	return sqlTypeToGoModel(col.Type, camelName, notNull)
}

// nestedCollector turns composite field types into generated structs. Composite
// types are discovered lazily while fields are walked, and a composite may
// reference another composite, so materialize keeps draining the queue until it
// stops growing.
type nestedCollector struct {
	ctx   *genContext
	queue []string
	seen  map[string]bool
}

func newNestedCollector(ctx *genContext) *nestedCollector {
	return &nestedCollector{ctx: ctx, seen: make(map[string]bool)}
}

func (n *nestedCollector) require(typeName string) bool {
	if n == nil {
		return false
	}
	if _, ok := n.ctx.compositeType(typeName); !ok {
		return false
	}
	if !n.seen[typeName] {
		n.seen[typeName] = true
		n.queue = append(n.queue, typeName)
	}
	return true
}

func (n *nestedCollector) materialize() ([]nestedTypeData, bool) {
	if n == nil {
		return nil, false
	}
	var result []nestedTypeData
	needsTime := false
	for cursor := 0; cursor < len(n.queue); cursor++ {
		typeName := n.queue[cursor]
		definition, ok := n.ctx.compositeType(typeName)
		if !ok {
			continue
		}
		var fields []modelFieldData
		for _, f := range definition.Fields {
			notNull := !f.Nullable && !hasConstraint(f.Constraints, "NULLABLE")
			goType := fieldTypeToGoType(n, f.Name, f.Type, notNull)
			if strings.Contains(goType, "time.Time") {
				needsTime = true
			}
			fields = append(fields, modelFieldData{
				GoName:  codegen.CamelToGoName(f.Name),
				GoType:  goType,
				JSONTag: f.Name,
				DBTag:   fmt.Sprintf(`bson:"%s"`, f.Name),
			})
		}
		result = append(result, nestedTypeData{
			Name:        typeName,
			Description: firstLine(definition.Description),
			Fields:      fields,
		})
	}
	return result, needsTime
}

func firstLine(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	if idx := strings.IndexByte(trimmed, '\n'); idx >= 0 {
		return strings.TrimSpace(trimmed[:idx])
	}
	return trimmed
}

func fieldTypeToGoType(nested *nestedCollector, fieldName, fieldType string, notNull bool) string {
	if nested.require(fieldType) {
		if notNull {
			return fieldType
		}
		return "*" + fieldType
	}
	switch fieldType {
	case "string", "enum":
		return "string"
	case "bool":
		return "bool"
	case "int":
		if strings.HasSuffix(fieldName, "Count") {
			return "int64"
		}
		return "int"
	case "int64":
		return "int64"
	case "timestamp":
		if !notNull {
			return "*time.Time"
		}
		return "time.Time"
	case "date":
		if !notNull {
			return "*string"
		}
		return "string"
	case "time":
		if !notNull {
			return "*string"
		}
		return "string"
	case "jsonb":
		return "json.RawMessage"
	case "string[]", "[]string":
		return "[]string"
	default:
		return "string"
	}
}

func sqlTypeToGoModel(sqlType, fieldName string, notNull bool) string {
	upper := strings.ToUpper(sqlType)
	switch {
	case upper == "DATE":
		if !notNull {
			return "*string"
		}
		return "string"
	case upper == "TIME":
		if !notNull {
			return "*string"
		}
		return "string"
	case strings.HasPrefix(upper, "TIMESTAMP"):
		if !notNull {
			return "*time.Time"
		}
		return "time.Time"
	case upper == "BOOLEAN", upper == "BOOL":
		return "bool"
	case upper == "INTEGER", upper == "INT", upper == "BIGINT":
		if strings.HasSuffix(fieldName, "Count") || strings.HasSuffix(fieldName, "count") {
			return "int64"
		}
		return "int"
	case upper == "JSONB", upper == "JSON":
		return "json.RawMessage"
	default:
		return "string"
	}
}

const modelTemplate = `// Code generated by codegen_storage from contracts/metadata/{{.MetaSource}}. DO NOT EDIT.
package {{.Package}}
{{if or .NeedsTime .NeedsJSON}}
import (
{{- if .NeedsTime}}
	"time"
{{- end}}
{{- if .NeedsJSON}}
	"encoding/json"
{{- end}}
)
{{end}}
{{- range .NestedTypes}}
{{if .Description}}// {{.Name}} {{.Description}}
{{end -}}
type {{.Name}} struct {
{{- range .Fields}}
	{{.GoName}} {{.GoType}} ` + "`" + `json:"{{.JSONTag}}" {{.DBTag}}` + "`" + `
{{- end}}
}

{{end -}}
type {{.EntityName}} struct {
{{- range .Fields}}
	{{.GoName}} {{.GoType}} ` + "`" + `json:"{{.JSONTag}}" {{.DBTag}}` + "`" + `
{{- end}}
}
`
