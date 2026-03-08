package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/runtime/codegen"

	"gopkg.in/yaml.v3"
)

func main() {
	var metadataDir string
	var manifestPath string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&manifestPath, "manifest", "", "service codegen manifest YAML path")
	flag.Parse()

	if manifestPath == "" {
		exitErr(fmt.Errorf("--manifest is required"))
	}

	manifest, err := loadManifest(manifestPath)
	if err != nil {
		exitErr(fmt.Errorf("load manifest: %w", err))
	}

	migrationSeq := 1

	for _, src := range manifest.Sources {
		storagePath := filepath.Join(metadataDir, src.Metadata, "storage.yaml")
		fieldsPath := filepath.Join(metadataDir, src.Metadata, "fields.yaml")

		storage, err := loadStorageYAML(storagePath)
		if err != nil {
			exitErr(fmt.Errorf("load storage %s: %w", storagePath, err))
		}

		fields, err := loadFieldsYAML(fieldsPath)
		if err != nil {
			exitErr(fmt.Errorf("load fields %s: %w", fieldsPath, err))
		}

		ctx := &genContext{
			manifest:     manifest,
			source:       src,
			storage:      storage,
			fields:       fields,
			migrationSeq: migrationSeq,
		}

		// Phase 1: Generate domain models
		fmt.Printf("--- models: %s ---\n", src.Metadata)
		if err := generateModels(ctx); err != nil {
			exitErr(fmt.Errorf("gen models %s: %w", src.Metadata, err))
		}

		// Phase 2: Generate PG stores + migrations
		if storage.Backend == "postgres" || len(storage.Tables) > 0 {
			orderedTables := orderedTableNames(storage.Tables, src.Tables)
			for _, tableName := range orderedTables {
				tableDef := storage.Tables[tableName]
				ctx.migrationSeq = migrationSeq
				if err := generateMigrationSQL(ctx, tableName, tableDef); err != nil {
					exitErr(fmt.Errorf("gen migration %s: %w", tableName, err))
				}
				migrationSeq++

				if err := generatePGStore(ctx, tableName, tableDef); err != nil {
					exitErr(fmt.Errorf("gen pg store %s: %w", tableName, err))
				}
			}
		}

		// Phase 3: Generate Mongo stores
		if storage.Backend == "mongodb" || len(storage.Collections) > 0 {
			for collName, collDef := range storage.Collections {
				if err := generateMongoStore(ctx, collName, collDef); err != nil {
					exitErr(fmt.Errorf("gen mongo store %s: %w", collName, err))
				}
			}
		}

		// Phase 4: Generate caches
		for _, cacheDef := range storage.RedisCache {
			if err := generateCache(ctx, cacheDef); err != nil {
				exitErr(fmt.Errorf("gen cache %s: %w", cacheDef.Key, err))
			}
		}
	}

	if err := generateMigrator(manifest); err != nil {
		exitErr(fmt.Errorf("gen migrator: %w", err))
	}

	fmt.Printf("codegen_storage: generated storage layer for %s\n", manifest.Service)
}

// --- Manifest ---

type Manifest struct {
	Service    string   `yaml:"service"`
	OutputDir  string   `yaml:"output_dir"`
	ModulePath string   `yaml:"module_path"`
	Sources    []Source `yaml:"sources"`
}

type Source struct {
	Metadata       string                       `yaml:"metadata"`
	DomainPkg      string                       `yaml:"domain_pkg"`
	Tables         []string                     `yaml:"tables"`
	NameOverrides  map[string]string            `yaml:"name_overrides"`
	TypeOverrides  map[string]map[string]string `yaml:"type_overrides"`
	CacheOverrides map[string]CacheOverride     `yaml:"cache_overrides"`
}

type CacheOverride struct {
	Entity string `yaml:"entity"`
	Name   string `yaml:"name"`
	Skip   bool   `yaml:"skip"`
}

func (s Source) resolveStoreName(entity string) string {
	if short, ok := s.NameOverrides[entity]; ok {
		return short
	}
	return entity
}

func loadManifest(path string) (*Manifest, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var m Manifest
	if err := yaml.Unmarshal(data, &m); err != nil {
		return nil, err
	}
	return &m, nil
}

// --- Storage YAML ---

type StorageYAML struct {
	Version     int                      `yaml:"version"`
	Aggregate   string                   `yaml:"aggregate"`
	Entity      string                   `yaml:"entity"`
	Backend     string                   `yaml:"backend"`
	Tables      map[string]TableDef      `yaml:"tables"`
	Collections map[string]CollectionDef `yaml:"collections"`
	RedisCache  []RedisCacheDef          `yaml:"redis_cache"`
}

type TableDef struct {
	Entity            string             `yaml:"entity"`
	PK                string             `yaml:"pk"`
	FK                *ForeignKeyDef     `yaml:"fk"`
	Columns           []ColumnDef        `yaml:"columns"`
	Indexes           []IndexDef         `yaml:"indexes"`
	UniqueConstraints []UniqueConstraint `yaml:"unique_constraints"`
	SearchIndexes     []SearchIndexDef   `yaml:"search_indexes"`
	CacheExcluded     bool               `yaml:"cache_excluded"`
}

type ColumnDef struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	Constraints []string `yaml:"constraints"`
	Default     any      `yaml:"default"`
}

func (c ColumnDef) IsPK() bool      { return hasConstraint(c.Constraints, "PK") }
func (c ColumnDef) IsNotNull() bool { return hasConstraint(c.Constraints, "NOT_NULL") }
func (c ColumnDef) IsUnique() bool  { return hasConstraint(c.Constraints, "UNIQUE") }

type IndexDef struct {
	Name      string   `yaml:"name"`
	Columns   []string `yaml:"columns"`
	Unique    bool     `yaml:"unique"`
	Condition string   `yaml:"condition"`
}

type UniqueConstraint struct {
	Name      string   `yaml:"name"`
	Columns   []string `yaml:"columns"`
	Condition string   `yaml:"condition"`
}

type SearchIndexDef struct {
	Name    string   `yaml:"name"`
	Columns []string `yaml:"columns"`
	Type    string   `yaml:"type"`
}

type ForeignKeyDef struct {
	Column     string `yaml:"column"`
	References string `yaml:"references"`
	OnDelete   string `yaml:"on_delete"`
}

type CollectionDef struct {
	Entity  string     `yaml:"entity"`
	Indexes []MongoIdx `yaml:"indexes"`
}

type MongoIdx struct {
	Name   string         `yaml:"name"`
	Keys   map[string]int `yaml:"keys"`
	Unique bool           `yaml:"unique"`
	Sparse bool           `yaml:"sparse"`
}

type RedisCacheDef struct {
	Key          string   `yaml:"key"`
	TTLSeconds   int      `yaml:"ttl_seconds"`
	Entity       string   `yaml:"entity"`
	Type         string   `yaml:"type"`
	Description  string   `yaml:"description"`
	InvalidateOn []string `yaml:"invalidate_on"`
}

// --- Fields YAML ---

type FieldsYAML struct {
	Version   int                        `yaml:"version"`
	Aggregate string                     `yaml:"aggregate"`
	Entity    string                     `yaml:"entity"`
	Entities  map[string]EntityFieldsDef `yaml:"entities"`
}

type EntityFieldsDef struct {
	Description string     `yaml:"description"`
	Fields      []FieldDef `yaml:"fields"`
}

type FieldDef struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	Constraints []string `yaml:"constraints"`
	APIExposure string   `yaml:"api_exposure"`
}

func loadStorageYAML(path string) (*StorageYAML, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var s StorageYAML
	if err := yaml.Unmarshal(data, &s); err != nil {
		return nil, err
	}
	return &s, nil
}

func loadFieldsYAML(path string) (*FieldsYAML, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var f FieldsYAML
	if err := yaml.Unmarshal(data, &f); err != nil {
		return nil, err
	}
	if f.Entities == nil && f.Entity != "" {
		var flat struct {
			Fields []FieldDef `yaml:"fields"`
		}
		if err := yaml.Unmarshal(data, &flat); err == nil && len(flat.Fields) > 0 {
			f.Entities = map[string]EntityFieldsDef{
				f.Entity: {Fields: flat.Fields},
			}
		}
	}
	return &f, nil
}

func orderedTableNames(all map[string]TableDef, filter []string) []string {
	if len(filter) > 0 {
		var result []string
		for _, t := range filter {
			if _, ok := all[t]; ok {
				result = append(result, t)
			}
		}
		return result
	}
	names := make([]string, 0, len(all))
	for name := range all {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

// --- Generation context ---

type genContext struct {
	manifest     *Manifest
	source       Source
	storage      *StorageYAML
	fields       *FieldsYAML
	migrationSeq int
}

func (c *genContext) outputDir() string  { return c.manifest.OutputDir }
func (c *genContext) modulePath() string { return c.manifest.ModulePath }
func (c *genContext) domainPkg() string  { return c.source.DomainPkg }

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_storage: %v\n", err)
	os.Exit(1)
}

func hasConstraint(ss []string, target string) bool {
	for _, s := range ss {
		if s == target {
			return true
		}
	}
	return false
}

// --- Naming (delegated to runtime/codegen) ---

func toGoName(snakeName string) string  { return codegen.SnakeToGoName(snakeName) }
func toSnake(s string) string           { return codegen.CamelToSnake(s) }
func entityToSnake(entity string) string { return codegen.CamelToSnake(entity) }

func sqlTypeToGo(sqlType string, notNull bool) string {
	upper := strings.ToUpper(sqlType)
	switch {
	case strings.HasPrefix(upper, "VARCHAR"), upper == "TEXT":
		return "string"
	case upper == "INTEGER", upper == "INT", upper == "BIGINT":
		return "int"
	case upper == "BOOLEAN", upper == "BOOL":
		return "bool"
	case strings.HasPrefix(upper, "TIMESTAMP"):
		return "time.Time"
	case upper == "DATE", upper == "TIME":
		if !notNull {
			return "*string"
		}
		return "string"
	case upper == "JSONB", upper == "JSON":
		return "json.RawMessage"
	default:
		return "string"
	}
}
