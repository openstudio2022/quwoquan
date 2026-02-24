package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

func main() {
	metadataDir := "contracts/metadata"
	if len(os.Args) > 1 {
		metadataDir = os.Args[1]
	}

	v := &validator{
		metadataDir: metadataDir,
		errors:      nil,
		warnings:    nil,
	}

	v.run()

	if len(v.warnings) > 0 {
		fmt.Printf("\n⚠ Warnings (%d):\n", len(v.warnings))
		for _, w := range v.warnings {
			fmt.Printf("  - %s\n", w)
		}
	}

	if len(v.errors) > 0 {
		fmt.Printf("\n✗ Errors (%d):\n", len(v.errors))
		for _, e := range v.errors {
			fmt.Printf("  - %s\n", e)
		}
		os.Exit(1)
	}

	fmt.Printf("\n✓ Metadata validation passed. %d aggregates/entities, %d enums.\n",
		v.objectCount, v.enumCount)
}

type validator struct {
	metadataDir string
	errors      []string
	warnings    []string
	enums       map[string]bool
	objectCount int
	enumCount   int
}

func (v *validator) errorf(format string, args ...any) {
	v.errors = append(v.errors, fmt.Sprintf(format, args...))
}

func (v *validator) warnf(format string, args ...any) {
	v.warnings = append(v.warnings, fmt.Sprintf(format, args...))
}

func (v *validator) run() {
	v.loadSharedEnums()
	v.validateBusinessObjects()
}

func (v *validator) loadSharedEnums() {
	v.enums = make(map[string]bool)

	typesPath := filepath.Join(v.metadataDir, "_shared", "types.yaml")
	data, err := os.ReadFile(typesPath)
	if err != nil {
		v.errorf("_shared/types.yaml: %v", err)
		return
	}

	var parsed struct {
		Enums map[string][]string `yaml:"enums"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("_shared/types.yaml parse error: %v", err)
		return
	}

	for name := range parsed.Enums {
		v.enums[name] = true
	}
	v.enumCount = len(v.enums)
	fmt.Printf("  ✓ _shared/types.yaml: %d enums loaded\n", v.enumCount)
}

func (v *validator) validateBusinessObjects() {
	entries, err := os.ReadDir(v.metadataDir)
	if err != nil {
		v.errorf("cannot read metadata dir: %v", err)
		return
	}

	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}
		v.validateObject(entry.Name())
		v.objectCount++
	}
}

func (v *validator) validateObject(dirName string) {
	dir := filepath.Join(v.metadataDir, dirName)
	fmt.Printf("  checking %s/ ...\n", dirName)

	aggFile := filepath.Join(dir, "aggregate.yaml")
	entFile := filepath.Join(dir, "entity.yaml")
	hasAgg := fileExists(aggFile)
	hasEnt := fileExists(entFile)

	if !hasAgg && !hasEnt {
		v.errorf("%s: neither aggregate.yaml nor entity.yaml found", dirName)
		return
	}
	if hasAgg && hasEnt {
		v.warnf("%s: both aggregate.yaml and entity.yaml found, using aggregate.yaml", dirName)
	}

	requiredFiles := []string{"fields.yaml", "events.yaml", "storage.yaml", "service.yaml"}
	for _, f := range requiredFiles {
		if !fileExists(filepath.Join(dir, f)) {
			v.errorf("%s: missing required file %s", dirName, f)
		}
	}

	var rootName string
	if hasAgg {
		rootName = v.parseAggRoot(dir, dirName)
	} else {
		rootName = v.parseEntityRoot(dir, dirName)
	}

	fieldsEntities := v.parseFieldsEntities(dir, dirName)
	v.validateEnumRefs(dir, dirName, fieldsEntities)
	v.validateEventsPayload(dir, dirName, fieldsEntities)
	v.validateStorageEntities(dir, dirName, fieldsEntities)
	v.validateServiceEntities(dir, dirName, fieldsEntities)

	_ = rootName
}

func (v *validator) parseAggRoot(dir, dirName string) string {
	data, err := os.ReadFile(filepath.Join(dir, "aggregate.yaml"))
	if err != nil {
		return ""
	}
	var parsed struct {
		AggregateRoot string `yaml:"aggregate_root"`
		Members       []struct {
			Entity string `yaml:"entity"`
		} `yaml:"members"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s/aggregate.yaml: parse error: %v", dirName, err)
		return ""
	}
	if parsed.AggregateRoot == "" {
		v.errorf("%s/aggregate.yaml: aggregate_root is empty", dirName)
	}
	return parsed.AggregateRoot
}

func (v *validator) parseEntityRoot(dir, dirName string) string {
	data, err := os.ReadFile(filepath.Join(dir, "entity.yaml"))
	if err != nil {
		return ""
	}
	var parsed struct {
		EntityName string `yaml:"entity_name"`
		Entity     string `yaml:"entity"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		v.errorf("%s/entity.yaml: parse error: %v", dirName, err)
		return ""
	}
	name := parsed.EntityName
	if name == "" {
		name = parsed.Entity
	}
	if name == "" {
		v.errorf("%s/entity.yaml: entity/entity_name is empty", dirName)
	}
	return name
}

func (v *validator) parseFieldsEntities(dir, dirName string) map[string]bool {
	entities := make(map[string]bool)
	data, err := os.ReadFile(filepath.Join(dir, "fields.yaml"))
	if err != nil {
		return entities
	}

	// Try nested format (aggregates): entities: { Name: { fields: [...] } }
	var nested struct {
		Entities map[string]any `yaml:"entities"`
	}
	if err := yaml.Unmarshal(data, &nested); err != nil {
		v.errorf("%s/fields.yaml: parse error: %v", dirName, err)
		return entities
	}

	if len(nested.Entities) > 0 {
		for name := range nested.Entities {
			entities[name] = true
		}
		return entities
	}

	// Flat format (standalone entities): entity: Name, fields: [...]
	var flat struct {
		Entity string `yaml:"entity"`
	}
	if err := yaml.Unmarshal(data, &flat); err == nil && flat.Entity != "" {
		entities[flat.Entity] = true
	}

	return entities
}

func (v *validator) validateEnumRefs(dir, dirName string, _ map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "fields.yaml"))
	if err != nil {
		return
	}

	var parsed struct {
		Entities map[string]struct {
			Fields []struct {
				Name    string `yaml:"name"`
				Type    string `yaml:"type"`
				EnumRef string `yaml:"enum_ref"`
			} `yaml:"fields"`
		} `yaml:"entities"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for entityName, entity := range parsed.Entities {
		for _, field := range entity.Fields {
			if field.EnumRef != "" && !v.enums[field.EnumRef] {
				v.errorf("%s/fields.yaml: %s.%s references enum %q not defined in _shared/types.yaml",
					dirName, entityName, field.Name, field.EnumRef)
			}
		}
	}
}

func (v *validator) validateEventsPayload(dir, dirName string, fieldsEntities map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "events.yaml"))
	if err != nil {
		return
	}
	var parsed struct {
		Events []struct {
			Name          string `yaml:"name"`
			PayloadEntity string `yaml:"payload_entity"`
		} `yaml:"events"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for _, event := range parsed.Events {
		if event.PayloadEntity != "" && !fieldsEntities[event.PayloadEntity] {
			v.errorf("%s/events.yaml: event %q references payload_entity %q not in fields.yaml",
				dirName, event.Name, event.PayloadEntity)
		}
	}
}

func (v *validator) validateStorageEntities(dir, dirName string, fieldsEntities map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "storage.yaml"))
	if err != nil {
		return
	}
	var parsed struct {
		Tables      map[string]struct{ Entity string `yaml:"entity"` } `yaml:"tables"`
		Collections map[string]struct{ Entity string `yaml:"entity"` } `yaml:"collections"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for tableName, table := range parsed.Tables {
		if table.Entity != "" && !fieldsEntities[table.Entity] {
			v.errorf("%s/storage.yaml: table %q references entity %q not in fields.yaml",
				dirName, tableName, table.Entity)
		}
	}
	for collName, coll := range parsed.Collections {
		if coll.Entity != "" && !fieldsEntities[coll.Entity] {
			v.errorf("%s/storage.yaml: collection %q references entity %q not in fields.yaml",
				dirName, collName, coll.Entity)
		}
	}
}

func (v *validator) validateServiceEntities(dir, dirName string, fieldsEntities map[string]bool) {
	data, err := os.ReadFile(filepath.Join(dir, "service.yaml"))
	if err != nil {
		return
	}
	var parsed struct {
		Routes []struct {
			Operations []struct {
				ResponseEntity string `yaml:"response_entity"`
				RequestEntity  string `yaml:"request_entity"`
			} `yaml:"operations"`
		} `yaml:"routes"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}

	for _, route := range parsed.Routes {
		for _, op := range route.Operations {
			if op.ResponseEntity != "" && !fieldsEntities[op.ResponseEntity] {
				v.warnf("%s/service.yaml: operation references response_entity %q not in fields.yaml (may be a list/special type)",
					dirName, op.ResponseEntity)
			}
		}
	}
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
