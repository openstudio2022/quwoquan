package codegen

import (
	"bytes"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"strings"
	"text/template"

	"quwoquan_service/runtime/registry"
)

// Generator drives code generation from the EntityRegistry.
type Generator struct {
	reg       *registry.EntityRegistry
	outputDir string
	templates map[string]*template.Template
}

// NewGenerator creates a code generator.
func NewGenerator(reg *registry.EntityRegistry, outputDir string) *Generator {
	g := &Generator{
		reg:       reg,
		outputDir: outputDir,
		templates: make(map[string]*template.Template),
	}
	g.registerBuiltinTemplates()
	return g
}

// GenerateAll generates code for all aggregates in the registry.
func (g *Generator) GenerateAll() error {
	for _, name := range g.reg.ListAggregates() {
		if err := g.GenerateForAggregate(name); err != nil {
			return fmt.Errorf("generate %s: %w", name, err)
		}
	}
	return nil
}

// GenerateForAggregate generates all artifacts for one aggregate/entity.
func (g *Generator) GenerateForAggregate(name string) error {
	agg, err := g.reg.GetAggregate(name)
	if err != nil {
		return err
	}

	data := g.buildTemplateData(name, agg)

	targets := []struct {
		tmplName string
		subDir   string
		fileName string
	}{
		{"go_model", filepath.Join("domain", data.PackageName, "model"), data.SnakeName + ".go"},
		{"go_repository_iface", filepath.Join("domain", data.PackageName, "repository"), "repository.go"},
		{"go_events", filepath.Join("domain", data.PackageName, "event"), "events.go"},
	}

	for _, t := range targets {
		if err := g.renderToFile(t.tmplName, data, t.subDir, t.fileName); err != nil {
			return fmt.Errorf("render %s: %w", t.tmplName, err)
		}
	}

	return nil
}

type templateData struct {
	PackageName   string
	AggregateRoot string
	SnakeName     string
	Domain        string
	Backend       string
	Entities      []entityData
	Events        []eventData
	HasCache      bool
	CacheTTL      int
}

type entityData struct {
	Name   string
	IsRoot bool
	Fields []fieldData
}

type fieldData struct {
	Name        string
	GoName      string
	GoType      string
	JSONTag     string
	BSONTag     string
	IsPK        bool
	IsRequired  bool
}

type eventData struct {
	Name          string
	Description   string
	PayloadEntity string
	PayloadFields []string
}

func (g *Generator) buildTemplateData(name string, agg *registry.AggregateEntry) templateData {
	td := templateData{
		PackageName:   strings.ToLower(name),
		AggregateRoot: name,
		SnakeName:     toSnake(name),
		Domain:        agg.Spec.Domain,
		Backend:       agg.Spec.StorageBackend,
		HasCache:      agg.Spec.CacheLayer != "" && agg.Spec.CacheLayer != "none",
		CacheTTL:      agg.Spec.CacheTTLSeconds,
	}

	for entityName, entityDef := range agg.Fields.Entities {
		isRoot := entityName == name
		var fields []fieldData
		for _, f := range entityDef.Fields {
			fields = append(fields, fieldData{
				Name:       f.Name,
				GoName:     toPascal(f.Name),
				GoType:     yamlTypeToGo(f.Type),
				JSONTag:    f.Name,
				BSONTag:    f.Name,
				IsPK:       containsStr(f.Constraints, "PK"),
				IsRequired: containsStr(f.Constraints, "NOT_NULL"),
			})
		}
		td.Entities = append(td.Entities, entityData{
			Name:   entityName,
			IsRoot: isRoot,
			Fields: fields,
		})
	}

	for _, e := range agg.Events.Events {
		td.Events = append(td.Events, eventData{
			Name:          e.Name,
			Description:   e.Description,
			PayloadEntity: e.PayloadEntity,
			PayloadFields: e.PayloadFields,
		})
	}

	return td
}

func (g *Generator) renderToFile(tmplName string, data templateData, subDir, fileName string) error {
	tmpl, ok := g.templates[tmplName]
	if !ok {
		return fmt.Errorf("template %q not registered", tmplName)
	}

	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		return fmt.Errorf("execute template %q: %w", tmplName, err)
	}

	formatted, err := format.Source(buf.Bytes())
	if err != nil {
		formatted = buf.Bytes()
	}

	dir := filepath.Join(g.outputDir, subDir)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("mkdir %s: %w", dir, err)
	}

	path := filepath.Join(dir, fileName)
	return os.WriteFile(path, formatted, 0644)
}

func (g *Generator) registerBuiltinTemplates() {
	g.templates["go_model"] = template.Must(template.New("go_model").Parse(goModelTemplate))
	g.templates["go_repository_iface"] = template.Must(template.New("go_repository_iface").Parse(goRepositoryTemplate))
	g.templates["go_events"] = template.Must(template.New("go_events").Parse(goEventsTemplate))
}

func yamlTypeToGo(t string) string {
	switch t {
	case "string", "ObjectId":
		return "string"
	case "int", "integer":
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

func toPascal(s string) string {
	if s == "" {
		return s
	}
	if s == "_id" {
		return "ID"
	}
	parts := strings.FieldsFunc(s, func(r rune) bool { return r == '_' || r == '-' })
	var result strings.Builder
	for _, p := range parts {
		if len(p) > 0 {
			result.WriteString(strings.ToUpper(p[:1]))
			result.WriteString(p[1:])
		}
	}
	return result.String()
}

func toSnake(s string) string {
	var result strings.Builder
	for i, r := range s {
		if r >= 'A' && r <= 'Z' {
			if i > 0 {
				result.WriteByte('_')
			}
			result.WriteRune(r + 32)
		} else {
			result.WriteRune(r)
		}
	}
	return result.String()
}

func containsStr(ss []string, target string) bool {
	for _, s := range ss {
		if s == target {
			return true
		}
	}
	return false
}
