package ast

// StorageDocument is the compiler's only typed view of storage.yaml.
//
// Keep every authored key in this document and its nested structs in exact
// lockstep with contracts/metadata/_schemas/storage.schema.json. Loaders must
// decode into this type with unknown-field rejection instead of maintaining a
// consumer-specific anonymous subset.
type StorageDocument struct {
	Backend             string                               `json:"backend" yaml:"backend"`
	Description         string                               `json:"description,omitempty" yaml:"description,omitempty"`
	Role                string                               `json:"role" yaml:"role"`
	Tables              map[string]StorageTable              `json:"tables,omitempty" yaml:"tables,omitempty"`
	Collections         map[string]StorageCollection         `json:"collections,omitempty" yaml:"collections,omitempty"`
	Streams             map[string]StorageStream             `json:"streams,omitempty" yaml:"streams,omitempty"`
	Transaction         *StorageTransaction                  `json:"transaction,omitempty" yaml:"transaction,omitempty"`
	RedisCache          []StorageRedisCache                  `json:"redis_cache,omitempty" yaml:"redis_cache,omitempty"`
	EnvironmentBackends map[string]StorageEnvironmentBackend `json:"environment_backends,omitempty" yaml:"environment_backends,omitempty"`
	Fallback            string                               `json:"fallback,omitempty" yaml:"fallback,omitempty"`
	Logstores           map[string]StorageLogstore           `json:"logstores,omitempty" yaml:"logstores,omitempty"`
	Codegen             *StorageCodegen                      `json:"codegen,omitempty" yaml:"codegen,omitempty"`
}

type StorageTable struct {
	Entity             string                    `json:"entity,omitempty" yaml:"entity,omitempty"`
	Role               string                    `json:"role,omitempty" yaml:"role,omitempty"`
	PublicationRole    string                    `json:"publication_role,omitempty" yaml:"publication_role,omitempty"`
	Description        string                    `json:"description,omitempty" yaml:"description,omitempty"`
	PK                 []string                  `json:"pk,omitempty" yaml:"pk,omitempty"`
	Columns            []StorageColumn           `json:"columns,omitempty" yaml:"columns,omitempty"`
	ForeignKeys        []StorageForeignKey       `json:"foreign_keys,omitempty" yaml:"foreign_keys,omitempty"`
	Indexes            []StorageTableIndex       `json:"indexes,omitempty" yaml:"indexes,omitempty"`
	UniqueConstraints  []StorageUniqueConstraint `json:"unique_constraints,omitempty" yaml:"unique_constraints,omitempty"`
	SearchIndexes      []StorageTableSearchIndex `json:"search_indexes,omitempty" yaml:"search_indexes,omitempty"`
	CacheExcluded      bool                      `json:"cache_excluded,omitempty" yaml:"cache_excluded,omitempty"`
	InfrastructureOnly bool                      `json:"infrastructure_only,omitempty" yaml:"infrastructure_only,omitempty"`
}

type StorageColumn struct {
	Name        string   `json:"name" yaml:"name"`
	Type        string   `json:"type" yaml:"type"`
	Constraints []string `json:"constraints,omitempty" yaml:"constraints,omitempty"`
	Default     any      `json:"default,omitempty" yaml:"default,omitempty"`
}

type StorageTableIndex struct {
	Name        string   `json:"name" yaml:"name"`
	Columns     []string `json:"columns" yaml:"columns"`
	Unique      bool     `json:"unique,omitempty" yaml:"unique,omitempty"`
	Condition   string   `json:"condition,omitempty" yaml:"condition,omitempty"`
	Description string   `json:"description,omitempty" yaml:"description,omitempty"`
}

type StorageUniqueConstraint struct {
	Name      string   `json:"name" yaml:"name"`
	Columns   []string `json:"columns" yaml:"columns"`
	Condition string   `json:"condition,omitempty" yaml:"condition,omitempty"`
}

type StorageForeignKey struct {
	Columns    []string `json:"columns" yaml:"columns"`
	References string   `json:"references" yaml:"references"`
	OnDelete   string   `json:"on_delete,omitempty" yaml:"on_delete,omitempty"`
}

type StorageTableSearchIndex struct {
	Name    string   `json:"name" yaml:"name"`
	Columns []string `json:"columns" yaml:"columns"`
	Type    string   `json:"type" yaml:"type"`
}

type StorageCollection struct {
	Entity          string                   `json:"entity,omitempty" yaml:"entity,omitempty"`
	Role            string                   `json:"role,omitempty" yaml:"role,omitempty"`
	PublicationRole string                   `json:"publication_role,omitempty" yaml:"publication_role,omitempty"`
	Description     string                   `json:"description,omitempty" yaml:"description,omitempty"`
	Indexes         []StorageCollectionIndex `json:"indexes,omitempty" yaml:"indexes,omitempty"`
}

// StorageCollectionIndex is a closed union of a Mongo index, a text-search
// index, and a vector index. The schema oneOf selects the concrete form; one
// typed field set prevents separate readers from inventing aliases.
type StorageCollectionIndex struct {
	Name               string         `json:"name" yaml:"name"`
	Keys               map[string]any `json:"keys,omitempty" yaml:"keys,omitempty"`
	KeyOrder           []string       `json:"key_order,omitempty" yaml:"key_order,omitempty"`
	Unique             bool           `json:"unique,omitempty" yaml:"unique,omitempty"`
	Sparse             bool           `json:"sparse,omitempty" yaml:"sparse,omitempty"`
	PartialFilter      map[string]any `json:"partial_filter,omitempty" yaml:"partial_filter,omitempty"`
	ExpireAfterSeconds *int64         `json:"expire_after_seconds,omitempty" yaml:"expire_after_seconds,omitempty"`
	Description        string         `json:"description,omitempty" yaml:"description,omitempty"`
	Type               string         `json:"type,omitempty" yaml:"type,omitempty"`
	Source             string         `json:"source,omitempty" yaml:"source,omitempty"`
	Fields             []string       `json:"fields,omitempty" yaml:"fields,omitempty"`
	Weights            map[string]int `json:"weights,omitempty" yaml:"weights,omitempty"`
	Field              string         `json:"field,omitempty" yaml:"field,omitempty"`
	Dimensions         int            `json:"dimensions,omitempty" yaml:"dimensions,omitempty"`
	Similarity         string         `json:"similarity,omitempty" yaml:"similarity,omitempty"`
}

type StorageStream struct {
	Entity           string   `json:"entity" yaml:"entity"`
	Role             string   `json:"role" yaml:"role"`
	IdempotencyKey   string   `json:"idempotency_key" yaml:"idempotency_key"`
	RetentionSeconds int      `json:"retention_seconds" yaml:"retention_seconds"`
	Description      string   `json:"description,omitempty" yaml:"description,omitempty"`
	Writers          []string `json:"writers,omitempty" yaml:"writers,omitempty"`
	PublicationRole  string   `json:"publication_role,omitempty" yaml:"publication_role,omitempty"`
}

type StorageTransaction struct {
	Scope      []string `json:"scope" yaml:"scope"`
	Isolation  string   `json:"isolation" yaml:"isolation"`
	Guarantees []string `json:"guarantees" yaml:"guarantees"`
}

type StorageRedisCache struct {
	Key                         string   `json:"key" yaml:"key"`
	TTLSeconds                  *int64   `json:"ttl_seconds,omitempty" yaml:"ttl_seconds,omitempty"`
	Type                        string   `json:"type,omitempty" yaml:"type,omitempty"`
	Scene                       string   `json:"scene,omitempty" yaml:"scene,omitempty"`
	Entity                      string   `json:"entity,omitempty" yaml:"entity,omitempty"`
	Description                 string   `json:"description,omitempty" yaml:"description,omitempty"`
	Isolation                   string   `json:"isolation,omitempty" yaml:"isolation,omitempty"`
	InvalidateOn                []string `json:"invalidate_on,omitempty" yaml:"invalidate_on,omitempty"`
	CreateOperation             string   `json:"create_operation,omitempty" yaml:"create_operation,omitempty"`
	Member                      string   `json:"member,omitempty" yaml:"member,omitempty"`
	Score                       string   `json:"score,omitempty" yaml:"score,omitempty"`
	Field                       string   `json:"field,omitempty" yaml:"field,omitempty"`
	Value                       string   `json:"value,omitempty" yaml:"value,omitempty"`
	QuotaIndex                  string   `json:"quota_index,omitempty" yaml:"quota_index,omitempty"`
	QuotaMetadata               string   `json:"quota_metadata,omitempty" yaml:"quota_metadata,omitempty"`
	QuotaShards                 int      `json:"quota_shards,omitempty" yaml:"quota_shards,omitempty"`
	MaxItems                    int      `json:"max_items,omitempty" yaml:"max_items,omitempty"`
	MaxFields                   int      `json:"max_fields,omitempty" yaml:"max_fields,omitempty"`
	MaxMembers                  int      `json:"max_members,omitempty" yaml:"max_members,omitempty"`
	MaxValueBytes               int      `json:"max_value_bytes,omitempty" yaml:"max_value_bytes,omitempty"`
	MaxObjectCards              int      `json:"max_object_cards,omitempty" yaml:"max_object_cards,omitempty"`
	MaxActivePerScope           int      `json:"max_active_per_scope,omitempty" yaml:"max_active_per_scope,omitempty"`
	MaxLiveRecordsPerQuotaShard int      `json:"max_live_records_per_quota_shard,omitempty" yaml:"max_live_records_per_quota_shard,omitempty"`
	MaxLiveBytesPerQuotaShard   int      `json:"max_live_bytes_per_quota_shard,omitempty" yaml:"max_live_bytes_per_quota_shard,omitempty"`
	GlobalMaxLiveRecords        int      `json:"global_max_live_records,omitempty" yaml:"global_max_live_records,omitempty"`
	GlobalMaxLiveBytes          int      `json:"global_max_live_bytes,omitempty" yaml:"global_max_live_bytes,omitempty"`
}

type StorageEnvironmentBackend struct {
	Adapter string `json:"adapter" yaml:"adapter"`
	Backend string `json:"backend" yaml:"backend"`
}

type StorageLogstore struct {
	ProviderConfigKeys map[string]string `json:"provider_config_keys" yaml:"provider_config_keys"`
	DefaultName        string            `json:"default_name" yaml:"default_name"`
	TTLDays            int               `json:"ttl_days" yaml:"ttl_days"`
	TimeField          string            `json:"time_field,omitempty" yaml:"time_field,omitempty"`
	BusinessTimeField  string            `json:"business_time_field,omitempty" yaml:"business_time_field,omitempty"`
	IndexedFields      []string          `json:"indexed_fields,omitempty" yaml:"indexed_fields,omitempty"`
	NonIndexedFields   []string          `json:"non_indexed_fields,omitempty" yaml:"non_indexed_fields,omitempty"`
	InternalFields     []string          `json:"internal_fields,omitempty" yaml:"internal_fields,omitempty"`
	ForbiddenFields    []string          `json:"forbidden_fields,omitempty" yaml:"forbidden_fields,omitempty"`
}

type StorageCodegen struct {
	Enabled             bool                                   `json:"enabled" yaml:"enabled"`
	RootEntity          string                                 `json:"root_entity,omitempty" yaml:"root_entity,omitempty"`
	Package             string                                 `json:"package,omitempty" yaml:"package,omitempty"`
	DomainPath          string                                 `json:"domain_path,omitempty" yaml:"domain_path,omitempty"`
	EventsOnly          bool                                   `json:"events_only,omitempty" yaml:"events_only,omitempty"`
	Tables              []string                               `json:"tables,omitempty" yaml:"tables,omitempty"`
	MigrationSkipTables []string                               `json:"migration_skip_tables,omitempty" yaml:"migration_skip_tables,omitempty"`
	NameOverrides       map[string]string                      `json:"name_overrides,omitempty" yaml:"name_overrides,omitempty"`
	TypeOverrides       map[string]map[string]string           `json:"type_overrides,omitempty" yaml:"type_overrides,omitempty"`
	CacheOverrides      map[string]StorageCodegenCacheOverride `json:"cache_overrides,omitempty" yaml:"cache_overrides,omitempty"`
}

type StorageCodegenCacheOverride struct {
	Entity string `json:"entity,omitempty" yaml:"entity,omitempty"`
	Name   string `json:"name,omitempty" yaml:"name,omitempty"`
	Skip   bool   `json:"skip,omitempty" yaml:"skip,omitempty"`
}
