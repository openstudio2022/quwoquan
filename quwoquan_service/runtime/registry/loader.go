package registry

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// LoadFromDirectory loads all metadata from a v3 modular directory structure.
// metadataDir should point to contracts/metadata/.
func LoadFromDirectory(metadataDir string) (*EntityRegistry, error) {
	reg := &EntityRegistry{
		aggregates: make(map[string]*AggregateEntry),
		entities:   make(map[string]*EntityEntry),
		enums:      make(map[string][]string),
	}

	if err := reg.loadSharedTypes(metadataDir); err != nil {
		return nil, fmt.Errorf("load shared types: %w", err)
	}

	entries, err := os.ReadDir(metadataDir)
	if err != nil {
		return nil, fmt.Errorf("read metadata dir: %w", err)
	}

	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}

		dir := filepath.Join(metadataDir, entry.Name())

		// Domain container: directory without aggregate.yaml/entity.yaml → recurse one level.
		isDomain := !fileExists(filepath.Join(dir, "aggregate.yaml")) && !fileExists(filepath.Join(dir, "entity.yaml"))
		if isDomain {
			subEntries, err := os.ReadDir(dir)
			if err != nil {
				return nil, fmt.Errorf("read domain dir %s: %w", entry.Name(), err)
			}
			for _, sub := range subEntries {
				if !sub.IsDir() || strings.HasPrefix(sub.Name(), "_") {
					continue
				}
				subDir := filepath.Join(dir, sub.Name())
				if err := reg.loadBusinessObject(subDir, sub.Name()); err != nil {
					return nil, fmt.Errorf("load %s/%s: %w", entry.Name(), sub.Name(), err)
				}
			}
			continue
		}

		if err := reg.loadBusinessObject(dir, entry.Name()); err != nil {
			return nil, fmt.Errorf("load %s: %w", entry.Name(), err)
		}
	}

	return reg, nil
}

func (r *EntityRegistry) loadSharedTypes(metadataDir string) error {
	typesPath := filepath.Join(metadataDir, "_shared", "types.yaml")
	data, err := os.ReadFile(typesPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}

	var shared SharedTypes
	if err := yaml.Unmarshal(data, &shared); err != nil {
		return fmt.Errorf("parse types.yaml: %w", err)
	}

	for name, values := range shared.Enums {
		r.enums[name] = values
	}
	return nil
}

func (r *EntityRegistry) loadBusinessObject(dir, dirName string) error {
	// JSON wire fixtures only; same convention as tools/verify_metadata (skip test_fixtures).
	if filepath.Base(dir) == "test_fixtures" || dirName == "test_fixtures" {
		return nil
	}

	aggPath := filepath.Join(dir, "aggregate.yaml")
	entPath := filepath.Join(dir, "entity.yaml")
	schemaPath := filepath.Join(dir, "schema.yaml")

	var aggSpec AggregateSpec
	var isAggregate bool

	if data, err := os.ReadFile(aggPath); err == nil {
		if err := yaml.Unmarshal(data, &aggSpec); err != nil {
			return fmt.Errorf("parse aggregate.yaml: %w", err)
		}
		isAggregate = true
	} else if data, err := os.ReadFile(entPath); err == nil {
		if err := yaml.Unmarshal(data, &aggSpec); err != nil {
			return fmt.Errorf("parse entity.yaml: %w", err)
		}
	} else if fileExists(schemaPath) {
		// Some domains keep schema-only runtime metadata that should not be
		// treated as a business object by aggregate/entity codegen.
		return nil
	} else {
		return fmt.Errorf("neither aggregate.yaml nor entity.yaml found in %s", dirName)
	}

	fieldsPath := filepath.Join(dir, "fields.yaml")
	var fieldsSpec FieldsSpec
	if data, err := os.ReadFile(fieldsPath); err == nil {
		if err := yaml.Unmarshal(data, &fieldsSpec); err != nil {
			return fmt.Errorf("parse fields.yaml: %w", err)
		}
		// Standalone entities use flat format: fields: [...] with entity: name at top
		// Aggregate entities use nested: entities: { Name: { fields: [...] } }
		if fieldsSpec.Entities == nil && fieldsSpec.Entity != "" {
			var flat struct {
				Fields []FieldDef `yaml:"fields"`
			}
			if err := yaml.Unmarshal(data, &flat); err == nil && len(flat.Fields) > 0 {
				fieldsSpec.Entities = map[string]EntityFieldDef{
					fieldsSpec.Entity: {Fields: flat.Fields},
				}
			}
		}
	}

	eventsPath := filepath.Join(dir, "events.yaml")
	var eventsSpec EventsSpec
	if data, err := os.ReadFile(eventsPath); err == nil {
		if err := yaml.Unmarshal(data, &eventsSpec); err != nil {
			return fmt.Errorf("parse events.yaml: %w", err)
		}
	}

	storagePath := filepath.Join(dir, "storage.yaml")
	var storageSpec StorageSpec
	if data, err := os.ReadFile(storagePath); err == nil {
		if err := yaml.Unmarshal(data, &storageSpec); err != nil {
			return fmt.Errorf("parse storage.yaml: %w", err)
		}
	}

	servicePath := filepath.Join(dir, "service.yaml")
	var serviceSpec ServiceSpec
	if data, err := os.ReadFile(servicePath); err == nil {
		if err := yaml.Unmarshal(data, &serviceSpec); err != nil {
			return fmt.Errorf("parse service.yaml: %w", err)
		}
	}

	rootName := aggSpec.RootName()

	if isAggregate {
		agg := &AggregateEntry{
			Spec:    aggSpec,
			Fields:  fieldsSpec,
			Events:  eventsSpec,
			Storage: storageSpec,
			Service: serviceSpec,
			DirName: dirName,
		}
		r.aggregates[rootName] = agg

		for entityName, entityFields := range fieldsSpec.Entities {
			r.entities[entityName] = &EntityEntry{
				Name:           entityName,
				AggregateName:  rootName,
				IsRoot:         entityName == rootName,
				Fields:         entityFields,
				StorageBackend: aggSpec.StorageBackend,
				CacheLayer:     aggSpec.CacheLayer,
				CacheTTL:       aggSpec.CacheTTLSeconds,
			}
		}
	} else {
		agg := &AggregateEntry{
			Spec:    aggSpec,
			Fields:  fieldsSpec,
			Events:  eventsSpec,
			Storage: storageSpec,
			Service: serviceSpec,
			DirName: dirName,
		}
		r.aggregates[rootName] = agg

		for entityName, entityFields := range fieldsSpec.Entities {
			r.entities[entityName] = &EntityEntry{
				Name:           entityName,
				AggregateName:  rootName,
				IsRoot:         true,
				Fields:         entityFields,
				StorageBackend: aggSpec.StorageBackend,
				CacheLayer:     aggSpec.CacheLayer,
				CacheTTL:       aggSpec.CacheTTLSeconds,
			}
		}
	}

	return nil
}

func readYAML(path string, out any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(data, out)
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
