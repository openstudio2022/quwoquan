package codegen

import (
	"bytes"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"text/template"
	"unicode"

	"quwoquan_service/runtime/registry"
)

// Generator drives code generation from the EntityRegistry.
type Generator struct {
	reg       *registry.EntityRegistry
	outputDir string
	cfg       generatorConfig
	templates map[string]*template.Template
}

// NewGenerator creates a code generator with optional behavior overrides.
func NewGenerator(reg *registry.EntityRegistry, outputDir string, opts ...GeneratorOption) *Generator {
	var cfg generatorConfig
	for _, o := range opts {
		o(&cfg)
	}
	g := &Generator{
		reg:       reg,
		outputDir: outputDir,
		cfg:       cfg,
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

	data, err := g.buildTemplateData(name, agg)
	if err != nil {
		return err
	}

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

// GenerateDomainModelOnly writes only the Go domain model file for the aggregate root package
// (does not emit repository or event stubs). Used when repository interfaces are curated manually.
func (g *Generator) GenerateDomainModelOnly(aggregateName string) error {
	agg, err := g.reg.GetAggregate(aggregateName)
	if err != nil {
		return err
	}
	data, err := g.buildTemplateData(aggregateName, agg)
	if err != nil {
		return err
	}
	subDir := filepath.Join("domain", data.PackageName, "model")
	fileName := data.SnakeName + ".go"
	return g.renderToFile("go_model", data, subDir, fileName)
}

type templateData struct {
	PackageName   string
	AggregateRoot string
	SnakeName     string
	Domain        string
	Backend       string
	Entities      []entityData
	EnumTypes     []enumTypeData
	Events        []eventData
	HasCache      bool
	CacheTTL      int
}

type enumTypeData struct {
	Name   string
	Values []enumValueData
}

type enumValueData struct {
	ConstName string
	WireValue string
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

func (g *Generator) buildTemplateData(name string, agg *registry.AggregateEntry) (templateData, error) {
	td := templateData{
		PackageName:   strings.ToLower(name),
		AggregateRoot: name,
		SnakeName:     toSnake(name),
		Domain:        agg.Spec.Domain,
		Backend:       agg.Spec.StorageBackend,
		HasCache:      agg.Spec.CacheLayer != "" && agg.Spec.CacheLayer != "none",
		CacheTTL:      agg.Spec.CacheTTLSeconds,
	}

	entityNames := make([]string, 0, len(agg.Fields.Entities))
	for n := range agg.Fields.Entities {
		if g.cfg.skipViewEntities && strings.HasSuffix(n, "View") {
			continue
		}
		entityNames = append(entityNames, n)
	}
	sort.Strings(entityNames)

	entitySet := make(map[string]struct{}, len(entityNames))
	for _, n := range entityNames {
		entitySet[n] = struct{}{}
	}

	if g.cfg.typedEnums {
		enums, err := g.collectEnumTypes(agg, entityNames)
		if err != nil {
			return templateData{}, err
		}
		td.EnumTypes = enums
	}

	for _, entityName := range entityNames {
		entityDef := agg.Fields.Entities[entityName]
		isRoot := entityName == name
		var fields []fieldData
		for _, f := range entityDef.Fields {
			fields = append(fields, fieldData{
				Name:       f.Name,
				GoName:     g.fieldGoName(f.Name),
				GoType:     g.fieldGoType(f, entitySet),
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

	return td, nil
}

func (g *Generator) collectEnumTypes(agg *registry.AggregateEntry, entityNames []string) ([]enumTypeData, error) {
	seen := make(map[string]struct{})
	for _, en := range entityNames {
		ed := agg.Fields.Entities[en]
		for _, f := range ed.Fields {
			if strings.TrimSpace(f.Type) != "enum" || f.EnumRef == "" {
				continue
			}
			seen[f.EnumRef] = struct{}{}
		}
	}
	names := make([]string, 0, len(seen))
	for n := range seen {
		names = append(names, n)
	}
	sort.Strings(names)

	out := make([]enumTypeData, 0, len(names))
	for _, n := range names {
		vals, err := g.reg.GetEnum(n)
		if err != nil {
			return nil, fmt.Errorf("aggregate %q enum %q: %w", agg.Spec.Domain, n, err)
		}
		ev := make([]enumValueData, 0, len(vals))
		for _, w := range vals {
			ev = append(ev, enumValueData{
				ConstName: enumConstName(n, w),
				WireValue: w,
			})
		}
		out = append(out, enumTypeData{Name: n, Values: ev})
	}
	return out, nil
}

func enumConstName(typeName, wire string) string {
	parts := strings.Split(wire, "_")
	var b strings.Builder
	b.WriteString(typeName)
	for _, p := range parts {
		if p == "" {
			continue
		}
		r := []rune(p)
		b.WriteRune(unicode.ToUpper(r[0]))
		if len(r) > 1 {
			b.WriteString(string(r[1:]))
		}
	}
	return b.String()
}

func (g *Generator) fieldGoName(jsonName string) string {
	if g.cfg.goFieldIDSuffix && jsonName != "_id" && strings.HasSuffix(jsonName, "Id") {
		base := jsonName[:len(jsonName)-2]
		return camelBaseToPascal(base) + "ID"
	}
	return toPascal(jsonName)
}

// camelBaseToPascal turns "owner" -> "Owner", "defaultPublicGroup" -> "DefaultPublicGroup".
func camelBaseToPascal(s string) string {
	if s == "" {
		return ""
	}
	start := 0
	var b strings.Builder
	for i := 1; i < len(s); i++ {
		if s[i] >= 'A' && s[i] <= 'Z' && s[i-1] >= 'a' && s[i-1] <= 'z' {
			part := s[start:i]
			if len(part) > 0 {
				b.WriteString(strings.ToUpper(part[:1]))
				b.WriteString(part[1:])
			}
			start = i
		}
	}
	part := s[start:]
	if len(part) > 0 {
		b.WriteString(strings.ToUpper(part[:1]))
		b.WriteString(part[1:])
	}
	return b.String()
}

func (g *Generator) fieldGoType(f registry.FieldDef, entityNames map[string]struct{}) string {
	t := strings.TrimSpace(f.Type)
	if strings.HasPrefix(t, "[]") {
		inner := strings.TrimSpace(strings.TrimPrefix(t, "[]"))
		if inner == "string" {
			return "[]string"
		}
		if g.cfg.resolveSliceEntity {
			if _, ok := entityNames[inner]; ok {
				return "[]" + inner
			}
		}
		return yamlTypeToGo(t)
	}
	if t == "enum" {
		if g.cfg.typedEnums && f.EnumRef != "" {
			return f.EnumRef
		}
		return "string"
	}
	return yamlTypeToGo(t)
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
	case "int64":
		return "int64"
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
