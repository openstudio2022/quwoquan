package main

import (
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"sort"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

type eventCatalogFile struct {
	LogTypes          []string                     `yaml:"log_types"`
	NetworkClasses    []string                     `yaml:"network_classes"`
	CommonFields      []string                     `yaml:"common_fields"`
	ContextExtensions []string                     `yaml:"context_extensions"`
	ExtensionFields   map[string]eventExtensionDef `yaml:"extension_fields"`
	Events            []eventCatalogEntry          `yaml:"events"`
}

type eventExtensionDef struct {
	Type          string   `yaml:"type"`
	Minimum       *int     `yaml:"minimum"`
	Maximum       *int     `yaml:"maximum"`
	MaxLength     int      `yaml:"max_length"`
	MaxItems      int      `yaml:"max_items"`
	ItemMaxLength int      `yaml:"item_max_length"`
	Sensitive     bool     `yaml:"sensitive"`
	Enum          []string `yaml:"enum"`
}

type eventCatalogEntry struct {
	EventType          string   `yaml:"event_type"`
	LogType            string   `yaml:"log_type"`
	RequiredExtensions []string `yaml:"required_extensions"`
	OptionalExtensions []string `yaml:"optional_extensions"`
	NormalSampleRate   float64  `yaml:"normal_sample_rate"`
	SlowThresholdMS    int      `yaml:"slow_threshold_ms"`
	InternalPriority   string   `yaml:"internal_priority"`
}

type eventRecordFieldsFile struct {
	Fields          []eventRecordField    `yaml:"fields"`
	TypedExtensions typedExtensionBinding `yaml:"typed_extensions"`
}

type eventRecordField struct {
	Name string `yaml:"name"`
}

type typedExtensionBinding struct {
	Catalog            string `yaml:"catalog"`
	Discriminator      string `yaml:"discriminator"`
	DefinitionsKey     string `yaml:"definitions_key"`
	RequiredByEventKey string `yaml:"required_by_event_key"`
	OptionalByEventKey string `yaml:"optional_by_event_key"`
	WireEncoding       string `yaml:"wire_encoding"`
	UnknownFieldPolicy string `yaml:"unknown_field_policy"`
}

type appPagesFile struct {
	Pages            []appPageEntry `yaml:"pages"`
	InternalPages    []appPageEntry `yaml:"internal_pages"`
	FallbackContexts []string       `yaml:"fallback_contexts"`
}

type appPageEntry struct {
	PageName string `yaml:"page_name"`
}

func main() {
	var metadataDir string
	var outputDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/product-ops-service/generated", "product-ops generated root directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	errorPaths, err := productOpsObjectErrorPaths(
		source.Paths("ops/product_ops/", "/errors.yaml"),
	)
	if err != nil {
		exitErr(err)
	}
	totalErrors := 0
	for _, sourcePath := range errorPaths {
		parts := strings.Split(sourcePath, "/")
		var errorsFile contractcodegen.ErrorsFile
		if err := source.Decode(sourcePath, &errorsFile); err != nil {
			exitErr(fmt.Errorf("load %s: %w", sourcePath, err))
		}
		rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
			Generator:    "tools/codegen_product_ops_service",
			SourcePath:   sourcePath,
			CommentLines: []string{"Object-owned ProductOps errors. Transport semantics come from errors.yaml."},
		})
		formatted, err := format.Source([]byte(rendered))
		if err != nil {
			exitErr(fmt.Errorf("gofmt generated errors from %s: %w", sourcePath, err))
		}
		outPath := filepath.Join(outputDir, parts[1], parts[2], "errors.go")
		if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
			exitErr(err)
		}
		if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
			exitErr(err)
		}
		totalErrors += len(errorsFile.Errors)
	}

	var catalog eventCatalogFile
	const eventCatalogPath = "ops/product_ops/event_record/event_catalog.yaml"
	if err := source.Decode(eventCatalogPath, &catalog); err != nil {
		exitErr(fmt.Errorf("load %s: %w", eventCatalogPath, err))
	}
	if err := validateEventCatalog(catalog); err != nil {
		exitErr(err)
	}
	var eventFields eventRecordFieldsFile
	const eventFieldsPath = "ops/product_ops/event_record/fields.yaml"
	if err := source.Decode(eventFieldsPath, &eventFields); err != nil {
		exitErr(fmt.Errorf("load %s: %w", eventFieldsPath, err))
	}
	if err := validateEventRecordFields(eventFields, catalog); err != nil {
		exitErr(err)
	}
	var pages appPagesFile
	const appPagesPath = "_shared/app_pages.yaml"
	if err := source.Decode(appPagesPath, &pages); err != nil {
		exitErr(fmt.Errorf("load %s: %w", appPagesPath, err))
	}
	catalogRendered := renderEventCatalogGo(catalog, pages)
	catalogFormatted, err := format.Source([]byte(catalogRendered))
	if err != nil {
		exitErr(fmt.Errorf("gofmt generated event catalog: %w", err))
	}
	catalogOutPath := filepath.Join(outputDir, "product_ops", "event_record", "event_catalog.go")
	if err := os.MkdirAll(filepath.Dir(catalogOutPath), 0o755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(catalogOutPath, catalogFormatted, 0o644); err != nil {
		exitErr(err)
	}
	fmt.Printf("codegen_product_ops_service: wrote %d errors and %d telemetry events\n", totalErrors, len(catalog.Events))
}

func productOpsObjectErrorPaths(paths []string) ([]string, error) {
	if len(paths) == 0 {
		return nil, fmt.Errorf("ProductOps metadata has no object-owned errors.yaml")
	}
	result := append([]string(nil), paths...)
	sort.Strings(result)
	for _, sourcePath := range result {
		parts := strings.Split(sourcePath, "/")
		if len(parts) != 4 ||
			parts[0] != "ops" ||
			parts[1] != "product_ops" ||
			strings.TrimSpace(parts[2]) == "" ||
			parts[3] != "errors.yaml" {
			return nil, fmt.Errorf(
				"ProductOps errors must be owned by exactly one object: %q",
				sourcePath,
			)
		}
	}
	return result, nil
}

func validateEventCatalog(catalog eventCatalogFile) error {
	if strings.Join(catalog.CommonFields, ",") != "logType,eventType,sessionId,pageName,occurredAt,deviceManufacturer,deviceModel,appVersion,networkClass" {
		return fmt.Errorf("event catalog common_fields must be the frozen nine-field envelope")
	}
	if strings.Join(catalog.ContextExtensions, ",") != "devicePlatform" {
		return fmt.Errorf("event catalog context_extensions must be [devicePlatform]")
	}
	for _, field := range catalog.ContextExtensions {
		if _, ok := catalog.ExtensionFields[field]; !ok {
			return fmt.Errorf("context extension references unknown extension %s", field)
		}
	}
	seen := map[string]bool{}
	for _, event := range catalog.Events {
		if event.EventType == "" || seen[event.EventType] {
			return fmt.Errorf("event_type must be non-empty and unique: %q", event.EventType)
		}
		seen[event.EventType] = true
		for _, field := range append(append([]string{}, event.RequiredExtensions...), event.OptionalExtensions...) {
			if _, ok := catalog.ExtensionFields[field]; !ok {
				return fmt.Errorf("event %s references unknown extension %s", event.EventType, field)
			}
		}
	}
	for name, definition := range catalog.ExtensionFields {
		if len(definition.Enum) == 0 {
			continue
		}
		if definition.Type != "string" {
			return fmt.Errorf("extension %s enum requires string type", name)
		}
		seenValues := map[string]struct{}{}
		for _, value := range definition.Enum {
			if strings.TrimSpace(value) == "" {
				return fmt.Errorf("extension %s enum contains empty value", name)
			}
			if _, exists := seenValues[value]; exists {
				return fmt.Errorf("extension %s enum contains duplicate value %q", name, value)
			}
			seenValues[value] = struct{}{}
		}
	}
	return nil
}

func validateEventRecordFields(fields eventRecordFieldsFile, catalog eventCatalogFile) error {
	rootNames := make([]string, 0, len(fields.Fields))
	for _, field := range fields.Fields {
		rootNames = append(rootNames, strings.TrimSpace(field.Name))
	}
	if strings.Join(rootNames, ",") != strings.Join(catalog.CommonFields, ",") {
		return fmt.Errorf("event record fields must contain only the frozen nine-field envelope in canonical order")
	}
	binding := fields.TypedExtensions
	if binding.Catalog != "event_catalog.yaml" ||
		binding.Discriminator != "eventType" ||
		binding.DefinitionsKey != "extension_fields" ||
		binding.RequiredByEventKey != "required_extensions" ||
		binding.OptionalByEventKey != "optional_extensions" ||
		binding.WireEncoding != "flattened" ||
		binding.UnknownFieldPolicy != "reject" {
		return fmt.Errorf("event record typed_extensions must bind the canonical event catalog without fallback")
	}
	return nil
}

func renderEventCatalogGo(catalog eventCatalogFile, pages appPagesFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_product_ops_service from ops/product_ops/event_record/event_catalog.yaml. DO NOT EDIT.\n")
	b.WriteString("package generated\n\n")
	b.WriteString("type EventExtensionDefinition struct { Type string; Minimum *int; Maximum *int; MaxLength int; MaxItems int; ItemMaxLength int; Sensitive bool; AllowedValues map[string]struct{} }\n")
	b.WriteString("type EventCatalogDefinition struct { EventType string; LogType string; RequiredExtensions map[string]struct{}; OptionalExtensions map[string]struct{}; NormalSampleRate float64; SlowThresholdMS int; InternalPriority string }\n\n")
	extensionNames := make([]string, 0, len(catalog.ExtensionFields))
	for name := range catalog.ExtensionFields {
		extensionNames = append(extensionNames, name)
	}
	sort.Strings(extensionNames)
	b.WriteString("type EventRecordInput struct {\n")
	b.WriteString("LogType string `json:\"logType\"`\n")
	b.WriteString("EventType string `json:\"eventType\"`\n")
	b.WriteString("SessionID string `json:\"sessionId\"`\n")
	b.WriteString("PageName string `json:\"pageName\"`\n")
	b.WriteString("OccurredAt string `json:\"occurredAt\"`\n")
	b.WriteString("DeviceManufacturer string `json:\"deviceManufacturer\"`\n")
	b.WriteString("DeviceModel string `json:\"deviceModel\"`\n")
	b.WriteString("AppVersion string `json:\"appVersion\"`\n")
	b.WriteString("NetworkClass string `json:\"networkClass\"`\n")
	for _, name := range extensionNames {
		definition := catalog.ExtensionFields[name]
		if isEventContextExtension(name, catalog.ContextExtensions) {
			b.WriteString(
				fmt.Sprintf(
					"%s string `json:\"%s\"`\n",
					goEventExtensionFieldName(name),
					name,
				),
			)
			continue
		}
		b.WriteString(
			fmt.Sprintf(
				"%s %s `json:\"%s,omitempty\"`\n",
				goEventExtensionFieldName(name),
				goEventExtensionFieldType(definition.Type),
				name,
			),
		)
	}
	b.WriteString("}\n\n")
	b.WriteString("func (input EventRecordInput) ExtensionValues() map[string]any {\n")
	b.WriteString("out := map[string]any{}\n")
	for _, name := range extensionNames {
		field := goEventExtensionFieldName(name)
		if isEventContextExtension(name, catalog.ContextExtensions) {
			b.WriteString(fmt.Sprintf("if input.%s != \"\" { out[%q] = input.%s }\n", field, name, field))
			continue
		}
		if catalog.ExtensionFields[name].Type == "string_list" {
			b.WriteString(fmt.Sprintf("if input.%s != nil { out[%q] = input.%s }\n", field, name, field))
			continue
		}
		b.WriteString(fmt.Sprintf("if input.%s != nil { out[%q] = *input.%s }\n", field, name, field))
	}
	b.WriteString("return out\n}\n\n")
	b.WriteString("var EventCommonFields = []string{")
	for _, field := range catalog.CommonFields {
		b.WriteString(fmt.Sprintf("%q,", field))
	}
	b.WriteString("}\n")
	b.WriteString("var EventContextExtensions = map[string]struct{}{")
	for _, field := range catalog.ContextExtensions {
		b.WriteString(fmt.Sprintf("%q:{},", field))
	}
	b.WriteString("}\n")
	b.WriteString("var EventNetworkClasses = map[string]struct{}{")
	for _, value := range catalog.NetworkClasses {
		b.WriteString(fmt.Sprintf("%q:{},", value))
	}
	b.WriteString("}\n")
	b.WriteString("var EventExtensionFields = map[string]EventExtensionDefinition{\n")
	for _, name := range extensionNames {
		definition := catalog.ExtensionFields[name]
		b.WriteString(fmt.Sprintf("%q:{Type:%q,Minimum:%s,Maximum:%s,MaxLength:%d,MaxItems:%d,ItemMaxLength:%d,Sensitive:%t,AllowedValues:map[string]struct{}{", name, definition.Type, goIntPointer(definition.Minimum), goIntPointer(definition.Maximum), definition.MaxLength, definition.MaxItems, definition.ItemMaxLength, definition.Sensitive))
		for _, value := range definition.Enum {
			b.WriteString(fmt.Sprintf("%q:{},", value))
		}
		b.WriteString("}},\n")
	}
	b.WriteString("}\n")
	b.WriteString("var EventCatalog = map[string]EventCatalogDefinition{\n")
	for _, event := range catalog.Events {
		b.WriteString(fmt.Sprintf("%q:{EventType:%q,LogType:%q,RequiredExtensions:map[string]struct{}{", event.EventType, event.EventType, event.LogType))
		for _, field := range event.RequiredExtensions {
			b.WriteString(fmt.Sprintf("%q:{},", field))
		}
		b.WriteString("},OptionalExtensions:map[string]struct{}{")
		for _, field := range event.OptionalExtensions {
			b.WriteString(fmt.Sprintf("%q:{},", field))
		}
		b.WriteString(fmt.Sprintf("},NormalSampleRate:%g,SlowThresholdMS:%d,InternalPriority:%q},\n", event.NormalSampleRate, event.SlowThresholdMS, event.InternalPriority))
	}
	b.WriteString("}\n")
	pageNames := map[string]struct{}{}
	for _, page := range append(pages.Pages, pages.InternalPages...) {
		pageNames[page.PageName] = struct{}{}
	}
	for _, pageName := range pages.FallbackContexts {
		pageNames[pageName] = struct{}{}
	}
	sortedPageNames := make([]string, 0, len(pageNames))
	for pageName := range pageNames {
		sortedPageNames = append(sortedPageNames, pageName)
	}
	sort.Strings(sortedPageNames)
	b.WriteString("var AppPageNames = map[string]struct{}{\n")
	for _, pageName := range sortedPageNames {
		b.WriteString(fmt.Sprintf("%q:{},\n", pageName))
	}
	b.WriteString("}\n")
	return b.String()
}

func isEventContextExtension(name string, contextExtensions []string) bool {
	for _, contextExtension := range contextExtensions {
		if contextExtension == name {
			return true
		}
	}
	return false
}

func goEventExtensionFieldName(name string) string {
	if name == "" {
		return ""
	}
	field := strings.ToUpper(name[:1]) + name[1:]
	field = strings.ReplaceAll(field, "Id", "ID")
	field = strings.ReplaceAll(field, "Ms", "MS")
	field = strings.ReplaceAll(field, "Http", "HTTP")
	field = strings.ReplaceAll(field, "Ttff", "TTFF")
	return field
}

func goEventExtensionFieldType(kind string) string {
	switch kind {
	case "string":
		return "*string"
	case "int":
		return "*int"
	case "double":
		return "*float64"
	case "bool":
		return "*bool"
	case "string_list":
		return "[]string"
	default:
		panic(fmt.Sprintf("unsupported telemetry extension type %q", kind))
	}
}

func goIntPointer(value *int) string {
	if value == nil {
		return "nil"
	}
	return fmt.Sprintf("func(v int) *int { return &v }(%d)", *value)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_product_ops_service error: %v\n", err)
	os.Exit(1)
}
