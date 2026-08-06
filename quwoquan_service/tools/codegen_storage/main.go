package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	var metadataDir string
	var serviceDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&serviceDir, "service-dir", "", "service root containing contracts and generated directories")
	flag.Parse()

	if serviceDir == "" {
		exitErr(fmt.Errorf("--service-dir is required"))
	}

	manifest, err := deriveGenerationPlan(serviceDir)
	if err != nil {
		exitErr(fmt.Errorf("derive generation plan: %w", err))
	}
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	contractGraph := source.Graph()

	sharedTypes, err := loadSharedTypes(contractGraph)
	if err != nil {
		exitErr(fmt.Errorf("load shared types: %w", err))
	}

	// Pre-pass: merge events from all sources with same domain_pkg → one events.g.go per pkg.
	if err := generateMergedEventConstants(manifest, contractGraph); err != nil {
		exitErr(fmt.Errorf("gen events: %w", err))
	}

	migrationSeq := 1

	for _, src := range manifest.Sources {
		if src.EventsOnly {
			continue
		}
		storagePath := filepath.ToSlash(filepath.Join(src.Metadata, "storage.yaml"))
		fieldsPath := filepath.ToSlash(filepath.Join(src.Metadata, "fields.yaml"))

		storage, err := loadStorageYAML(contractGraph, storagePath)
		if err != nil {
			exitErr(fmt.Errorf("load storage %s: %w", storagePath, err))
		}

		fields, err := loadFieldsYAML(contractGraph, fieldsPath)
		if err != nil {
			exitErr(fmt.Errorf("load fields %s: %w", fieldsPath, err))
		}

		ctx := &genContext{
			manifest:     manifest,
			source:       src,
			storage:      storage,
			fields:       fields,
			sharedTypes:  sharedTypes,
			migrationSeq: migrationSeq,
		}
		ctx.normalizeRootFields()

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
				if src.skipsMigration(tableName) {
					fmt.Printf("  migration: %s (manual)\n", tableName)
				} else {
					ctx.migrationSeq = migrationSeq
					if err := generateMigrationSQL(ctx, tableName, tableDef); err != nil {
						exitErr(fmt.Errorf("gen migration %s: %w", tableName, err))
					}
					migrationSeq++
				}

				if tableDef.InfrastructureOnly {
					fmt.Printf("  pg_store: %s (infrastructure-only table)\n", tableName)
					continue
				}
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

	fmt.Printf("codegen_storage: generated storage layer for %s\n", manifest.Service)
}

// --- Manifest ---

type Manifest struct {
	Service    string
	OutputDir  string
	ModulePath string
	Sources    []Source
}

type Source struct {
	Metadata            string
	ObjectPath          string
	RootEntity          string
	DomainPkg           string
	DomainPath          string
	EventsOnly          bool
	Tables              []string
	MigrationSkipTables []string
	NameOverrides       map[string]string
	TypeOverrides       map[string]map[string]string
	CacheOverrides      map[string]CacheOverride
}

func (s Source) domainPath() string {
	if s.DomainPath != "" {
		return s.DomainPath
	}
	return s.DomainPkg
}

func (s Source) modelImport(modulePath string) string {
	return modulePath + "/contract/" + filepath.ToSlash(s.domainPath())
}

func (s Source) infrastructurePath(kind string) string {
	return filepath.Join("persistence", s.domainPath(), kind)
}

type CacheOverride struct {
	Entity string
	Name   string
	Skip   bool
}

func (s Source) resolveStoreName(entity string) string {
	if short, ok := s.NameOverrides[entity]; ok {
		return short
	}
	return entity
}

func (s Source) skipsMigration(tableName string) bool {
	for _, candidate := range s.MigrationSkipTables {
		if candidate == tableName {
			return true
		}
	}
	return false
}

// --- Storage YAML ---

// StorageYAML 的字段集必须是 contracts/metadata/_schemas/storage.schema.json
// 顶层键集的子集；schema 是键集唯一真相源，由
// storage_reader_keyset__contract__local_contract_test.go 断言。
type StorageYAML struct {
	Backend     string                   `yaml:"backend"`
	Tables      map[string]TableDef      `yaml:"tables"`
	Collections map[string]CollectionDef `yaml:"collections"`
	RedisCache  []RedisCacheDef          `yaml:"redis_cache"`
}

type TableDef struct {
	Entity             string             `yaml:"entity"`
	PK                 []string           `yaml:"pk"`
	FK                 *ForeignKeyDef     `yaml:"fk"`
	Columns            []ColumnDef        `yaml:"columns"`
	Indexes            []IndexDef         `yaml:"indexes"`
	UniqueConstraints  []UniqueConstraint `yaml:"unique_constraints"`
	SearchIndexes      []SearchIndexDef   `yaml:"search_indexes"`
	CacheExcluded      bool               `yaml:"cache_excluded"`
	InfrastructureOnly bool               `yaml:"infrastructure_only"`
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
	Name     string         `yaml:"name"`
	Keys     map[string]any `yaml:"keys"`
	KeyOrder []string       `yaml:"key_order"`
	Unique   bool           `yaml:"unique"`
	Sparse   bool           `yaml:"sparse"`
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
	Fields    []FieldDef                 `yaml:"fields"`
	Entities  map[string]EntityFieldsDef `yaml:"entities"`
	Types     map[string]EntityFieldsDef `yaml:"types"`
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
	// Nullable is how composite types in `types:` blocks express optionality;
	// entity fields use the NULLABLE constraint instead.
	Nullable bool `yaml:"nullable"`
}

func loadStorageYAML(contractGraph *graph.ContractGraph, path string) (*StorageYAML, error) {
	var s StorageYAML
	if err := contractGraph.DecodeDocumentYAML(path, &s); err != nil {
		return nil, err
	}
	return &s, nil
}

// loadSharedTypes reads the cross-service composite types so that a field
// declaring `type: TagHeatWindow` becomes a nested struct instead of silently
// degrading to string, which is what the scalar fallback used to do.
func loadSharedTypes(contractGraph *graph.ContractGraph) (map[string]EntityFieldsDef, error) {
	var shared struct {
		Types map[string]EntityFieldsDef `yaml:"types"`
	}
	if err := contractGraph.DecodeDocumentYAML("_shared/types.yaml", &shared); err != nil {
		return nil, err
	}
	if shared.Types == nil {
		shared.Types = make(map[string]EntityFieldsDef)
	}
	return shared.Types, nil
}

func loadFieldsYAML(contractGraph *graph.ContractGraph, path string) (*FieldsYAML, error) {
	var f FieldsYAML
	if err := contractGraph.DecodeDocumentYAML(path, &f); err != nil {
		return nil, err
	}
	if f.Entities == nil {
		f.Entities = make(map[string]EntityFieldsDef)
	}
	for name, definition := range f.Types {
		f.Entities[name] = definition
	}
	if f.Entity != "" && len(f.Fields) > 0 {
		f.Entities[f.Entity] = EntityFieldsDef{Fields: f.Fields}
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
	sharedTypes  map[string]EntityFieldsDef
	migrationSeq int
}

// compositeType resolves a field type name to its composite definition. Local
// `types:` blocks win over `_shared/types.yaml` so a service can keep a private
// shape without reserving the shared name.
func (c *genContext) compositeType(typeName string) (EntityFieldsDef, bool) {
	if typeName == "" {
		return EntityFieldsDef{}, false
	}
	if definition, ok := c.fields.Types[typeName]; ok && len(definition.Fields) > 0 {
		return definition, true
	}
	definition, ok := c.sharedTypes[typeName]
	return definition, ok && len(definition.Fields) > 0
}

func (c *genContext) normalizeRootFields() {
	if c.source.RootEntity == "" || len(c.fields.Fields) == 0 {
		return
	}
	c.fields.Entities[c.source.RootEntity] = EntityFieldsDef{Fields: c.fields.Fields}
}

func (c *genContext) outputDir() string {
	return filepath.Join(c.manifest.OutputDir, c.source.ObjectPath)
}
func (c *genContext) migrationDir() string {
	return filepath.Join(filepath.Dir(c.manifest.OutputDir), "resources", "migrations", c.source.ObjectPath)
}
func (c *genContext) modulePath() string {
	return strings.TrimSuffix(c.manifest.ModulePath, "/") + "/" + filepath.ToSlash(c.source.ObjectPath)
}
func (c *genContext) domainPkg() string { return c.source.DomainPkg }

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

// --- Naming ---

func toGoName(snakeName string) string {
	return contractcodegen.SnakeToGoName(snakeName)
}
func toSnake(s string) string {
	return contractcodegen.CamelToSnake(s)
}
func entityToSnake(entity string) string {
	return contractcodegen.CamelToSnake(entity)
}

func sqlTypeToGo(sqlType string, notNull bool) string {
	upper := strings.ToUpper(sqlType)
	switch {
	case upper == "TEXT[]", upper == "VARCHAR[]":
		return "[]string"
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
