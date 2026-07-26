package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

var goPackagePattern = regexp.MustCompile(`^[a-z][a-z0-9_]*$`)

type storageCodegenYAML struct {
	Enabled             bool                         `yaml:"enabled"`
	RootEntity          string                       `yaml:"root_entity"`
	Package             string                       `yaml:"package"`
	DomainPath          string                       `yaml:"domain_path"`
	EventsOnly          bool                         `yaml:"events_only"`
	Tables              []string                     `yaml:"tables"`
	MigrationSkipTables []string                     `yaml:"migration_skip_tables"`
	NameOverrides       map[string]string            `yaml:"name_overrides"`
	TypeOverrides       map[string]map[string]string `yaml:"type_overrides"`
	CacheOverrides      map[string]cacheOverrideYAML `yaml:"cache_overrides"`
}

type cacheOverrideYAML struct {
	Entity string `yaml:"entity"`
	Name   string `yaml:"name"`
	Skip   bool   `yaml:"skip"`
}

type domainContractYAML struct {
	Domain string `yaml:"domain"`
}

func deriveGenerationPlan(serviceDir string) (*Manifest, error) {
	serviceDir = filepath.Clean(serviceDir)
	service := filepath.Base(serviceDir)
	if service == "." || service == string(filepath.Separator) || !strings.HasSuffix(service, "-service") {
		return nil, fmt.Errorf("service directory must end in -service: %q", serviceDir)
	}
	contractsDir := filepath.Join(serviceDir, "contracts")
	domainRaw, err := os.ReadFile(filepath.Join(contractsDir, "domain.yaml"))
	if err != nil {
		return nil, fmt.Errorf("read domain.yaml: %w", err)
	}
	var domainContract domainContractYAML
	if err := yaml.Unmarshal(domainRaw, &domainContract); err != nil {
		return nil, fmt.Errorf("decode domain.yaml: %w", err)
	}
	domain := strings.TrimSpace(domainContract.Domain)
	if domain == "" {
		return nil, fmt.Errorf("domain.yaml missing domain")
	}

	plan := &Manifest{
		Service:    service,
		OutputDir:  filepath.Join(serviceDir, "generated"),
		ModulePath: filepath.ToSlash(filepath.Join("quwoquan_service", "services", service, "generated")),
	}
	err = filepath.WalkDir(contractsDir, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "storage.yaml" {
			return nil
		}
		rel, err := filepath.Rel(contractsDir, path)
		if err != nil {
			return err
		}
		parts := strings.Split(filepath.ToSlash(rel), "/")
		if len(parts) != 3 {
			return nil
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var hints struct {
			Codegen storageCodegenYAML `yaml:"codegen"`
		}
		if err := yaml.Unmarshal(raw, &hints); err != nil {
			return fmt.Errorf("decode %s: %w", filepath.ToSlash(rel), err)
		}
		if !hints.Codegen.Enabled {
			return nil
		}
		var storage StorageYAML
		if err := yaml.Unmarshal(raw, &storage); err != nil {
			return fmt.Errorf("decode %s: %w", filepath.ToSlash(rel), err)
		}
		contextName, objectName := parts[0], parts[1]
		pkg := strings.TrimSpace(hints.Codegen.Package)
		if pkg == "" {
			pkg = strings.ReplaceAll(contextName, "-", "_")
		}
		rootEntity := strings.TrimSpace(hints.Codegen.RootEntity)
		if rootEntity == "" && !hints.Codegen.EventsOnly {
			rootEntity = deriveRootEntity(storage)
		}
		cacheOverrides := make(map[string]CacheOverride, len(hints.Codegen.CacheOverrides))
		for key, override := range hints.Codegen.CacheOverrides {
			cacheOverrides[key] = CacheOverride{
				Entity: override.Entity,
				Name:   override.Name,
				Skip:   override.Skip,
			}
		}
		source := Source{
			Metadata:            filepath.ToSlash(filepath.Join(domain, contextName, objectName)),
			ObjectPath:          filepath.ToSlash(filepath.Join(contextName, objectName)),
			RootEntity:          rootEntity,
			DomainPkg:           pkg,
			DomainPath:          filepath.ToSlash(strings.TrimSpace(hints.Codegen.DomainPath)),
			EventsOnly:          hints.Codegen.EventsOnly,
			Tables:              hints.Codegen.Tables,
			MigrationSkipTables: hints.Codegen.MigrationSkipTables,
			NameOverrides:       hints.Codegen.NameOverrides,
			TypeOverrides:       hints.Codegen.TypeOverrides,
			CacheOverrides:      cacheOverrides,
		}
		if err := validateDerivedSource(source, storage); err != nil {
			return fmt.Errorf("%s: %w", filepath.ToSlash(rel), err)
		}
		plan.Sources = append(plan.Sources, source)
		return nil
	})
	if err != nil {
		return nil, err
	}
	if len(plan.Sources) == 0 {
		return nil, fmt.Errorf("no object storage.yaml declares codegen.enabled")
	}
	sort.Slice(plan.Sources, func(i, j int) bool {
		return plan.Sources[i].ObjectPath < plan.Sources[j].ObjectPath
	})
	return plan, nil
}

func deriveRootEntity(storage StorageYAML) string {
	if storage.Aggregate != "" {
		return storage.Aggregate
	}
	if storage.Entity != "" {
		return storage.Entity
	}
	entities := map[string]struct{}{}
	for _, table := range storage.Tables {
		if table.Entity != "" {
			entities[table.Entity] = struct{}{}
		}
	}
	for _, collection := range storage.Collections {
		if collection.Entity != "" {
			entities[collection.Entity] = struct{}{}
		}
	}
	if len(entities) != 1 {
		return ""
	}
	for entity := range entities {
		return entity
	}
	return ""
}

func validateDerivedSource(source Source, storage StorageYAML) error {
	objectPath := filepath.Clean(source.ObjectPath)
	domainPath := filepath.Clean(source.domainPath())
	if objectPath == "." || filepath.IsAbs(objectPath) ||
		objectPath == ".." || strings.HasPrefix(objectPath, ".."+string(filepath.Separator)) {
		return fmt.Errorf("invalid generated object ownership %q", source.ObjectPath)
	}
	if !goPackagePattern.MatchString(source.DomainPkg) || domainPath == "." || filepath.IsAbs(domainPath) ||
		domainPath == ".." || strings.HasPrefix(domainPath, ".."+string(filepath.Separator)) {
		return fmt.Errorf("invalid generated package=%q domain_path=%q", source.DomainPkg, source.DomainPath)
	}
	if !source.EventsOnly && source.RootEntity == "" {
		return fmt.Errorf("root entity is ambiguous; declare codegen.root_entity in this object storage contract")
	}
	for _, table := range source.Tables {
		if _, ok := storage.Tables[table]; !ok {
			return fmt.Errorf("codegen.tables references unknown table %q", table)
		}
	}
	for _, table := range source.MigrationSkipTables {
		if _, ok := storage.Tables[table]; !ok {
			return fmt.Errorf("codegen.migration_skip_tables references unknown table %q", table)
		}
	}
	return nil
}
