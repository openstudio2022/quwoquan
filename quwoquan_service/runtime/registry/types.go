package registry

// AggregateSpec represents the parsed aggregate.yaml or entity.yaml.
type AggregateSpec struct {
	Version         int               `yaml:"version"`
	Domain          string            `yaml:"domain"`
	AggregateRoot   string            `yaml:"aggregate_root"`
	EntityName      string            `yaml:"entity_name"`
	Entity          string            `yaml:"entity"`
	Description     string            `yaml:"description"`
	StorageBackend  string            `yaml:"storage_backend"`
	CacheLayer      string            `yaml:"cache_layer"`
	CacheTTLSeconds int               `yaml:"cache_ttl_seconds"`
	Capabilities    []string          `yaml:"capabilities"`
	Taggable        bool              `yaml:"taggable"`
	VectorEnabled   bool              `yaml:"vector_enabled"`
	Members         []MemberSpec      `yaml:"members"`
	DDDLayerMapping map[string]string `yaml:"ddd_layer_mapping"`
}

// IsAggregate returns true if this spec defines an aggregate root (not a standalone entity).
func (a *AggregateSpec) IsAggregate() bool {
	return a.AggregateRoot != ""
}

// RootName returns the aggregate root name or standalone entity name.
func (a *AggregateSpec) RootName() string {
	if a.AggregateRoot != "" {
		return a.AggregateRoot
	}
	if a.EntityName != "" {
		return a.EntityName
	}
	return a.Entity
}

type MemberSpec struct {
	Entity        string `yaml:"entity"`
	Relation      string `yaml:"relation"`
	CascadeDelete bool   `yaml:"cascade_delete"`
	Description   string `yaml:"description"`
}

// FieldsSpec represents the parsed fields.yaml.
type FieldsSpec struct {
	Version   int                       `yaml:"version"`
	Aggregate string                    `yaml:"aggregate"`
	Entity    string                    `yaml:"entity"`
	Entities  map[string]EntityFieldDef `yaml:"entities"`
}

type EntityFieldDef struct {
	Description string     `yaml:"description"`
	Fields      []FieldDef `yaml:"fields"`
}

type FieldDef struct {
	Name             string   `yaml:"name"`
	Type             string   `yaml:"type"`
	EnumRef          string   `yaml:"enum_ref"`
	Constraints      []string `yaml:"constraints"`
	Classification   string   `yaml:"classification"`
	LogPolicy        string   `yaml:"log_policy"`
	APIExposure      string   `yaml:"api_exposure"`
	OpsExposure      string   `yaml:"ops_exposure"`
	ObserveMetric    any      `yaml:"observe_metric"`
	OpsMetric        any      `yaml:"ops_metric"`
	RecommendFeature any      `yaml:"recommend_feature"`
	SearchField      any      `yaml:"search_field"`
	Description      string   `yaml:"description"`
	Default          any      `yaml:"default"`
}

// HasObserveMetric returns true if observe_metric is set (bool true or non-empty string).
func (f *FieldDef) HasObserveMetric() bool {
	switch v := f.ObserveMetric.(type) {
	case bool:
		return v
	case string:
		return v != ""
	default:
		return false
	}
}

// HasRecommendFeature returns true if recommend_feature is set.
func (f *FieldDef) HasRecommendFeature() bool {
	switch v := f.RecommendFeature.(type) {
	case bool:
		return v
	case string:
		return v != ""
	default:
		return false
	}
}

// IsSearchField returns true if search_field is set.
func (f *FieldDef) IsSearchField() bool {
	switch v := f.SearchField.(type) {
	case bool:
		return v
	case string:
		return v != ""
	default:
		return false
	}
}

// EventsSpec represents the parsed events.yaml.
type EventsSpec struct {
	Version   int        `yaml:"version"`
	Aggregate string     `yaml:"aggregate"`
	Entity    string     `yaml:"entity"`
	Events    []EventDef `yaml:"events"`
}

type EventDef struct {
	Name            string   `yaml:"name"`
	Description     string   `yaml:"description"`
	Producer        string   `yaml:"producer"`
	Consumers       []string `yaml:"consumers"`
	Channel         string   `yaml:"channel"`
	PayloadEntity   string   `yaml:"payload_entity"`
	PayloadFields   []string `yaml:"payload_fields"`
	RecommendImpact string   `yaml:"recommend_impact"`
}

// StorageSpec represents the parsed storage.yaml.
type StorageSpec struct {
	Version    int                       `yaml:"version"`
	Aggregate  string                    `yaml:"aggregate"`
	Entity     string                    `yaml:"entity"`
	Backend    string                    `yaml:"backend"`
	Tables     map[string]PGTableDef     `yaml:"tables"`
	Collections map[string]MongoCollDef  `yaml:"collections"`
	RedisCache []RedisCacheDef           `yaml:"redis_cache"`
}

type PGTableDef struct {
	Entity            string                `yaml:"entity"`
	PK                string                `yaml:"pk"`
	FK                *PGFKDef              `yaml:"fk"`
	Columns           []PGColumnDef         `yaml:"columns"`
	Indexes           []PGIndexDef          `yaml:"indexes"`
	ForeignKeys       []PGFKDef             `yaml:"foreign_keys"`
	UniqueConstraints []PGUniqueConstraint  `yaml:"unique_constraints"`
	SearchIndexes     []PGSearchIndexDef    `yaml:"search_indexes"`
	CacheExcluded     bool                  `yaml:"cache_excluded"`
}

type PGColumnDef struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	Constraints []string `yaml:"constraints"`
	Default     any      `yaml:"default"`
}

// IsPK returns true if column has PK constraint.
func (c PGColumnDef) IsPK() bool      { return containsConstraint(c.Constraints, "PK") }

// IsNotNull returns true if column has NOT_NULL constraint.
func (c PGColumnDef) IsNotNull() bool  { return containsConstraint(c.Constraints, "NOT_NULL") }

// IsUnique returns true if column has UNIQUE constraint.
func (c PGColumnDef) IsUnique() bool   { return containsConstraint(c.Constraints, "UNIQUE") }

func containsConstraint(ss []string, target string) bool {
	for _, s := range ss {
		if s == target {
			return true
		}
	}
	return false
}

type PGIndexDef struct {
	Name      string   `yaml:"name"`
	Columns   []string `yaml:"columns"`
	Unique    bool     `yaml:"unique"`
	Condition string   `yaml:"condition"`
}

type PGUniqueConstraint struct {
	Name      string   `yaml:"name"`
	Columns   []string `yaml:"columns"`
	Condition string   `yaml:"condition"`
}

type PGSearchIndexDef struct {
	Name    string   `yaml:"name"`
	Columns []string `yaml:"columns"`
	Type    string   `yaml:"type"`
}

type PGFKDef struct {
	Column     string `yaml:"column"`
	References string `yaml:"references"`
	OnDelete   string `yaml:"on_delete"`
}

type MongoCollDef struct {
	Entity        string           `yaml:"entity"`
	Indexes       []MongoIndexDef  `yaml:"indexes"`
	SearchIndexes []any            `yaml:"search_indexes"`
	VectorIndexes []any            `yaml:"vector_indexes"`
	ChangeStreams []any            `yaml:"change_streams"`
	Sharding      map[string]any   `yaml:"sharding"`
	WritePattern  string           `yaml:"write_pattern"`
}

type MongoIndexDef struct {
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

// ServiceSpec represents the parsed service.yaml.
// service.yaml has two possible route formats:
//   - routes: [{path: "/foo", operations: [{method, name, ...}]}]
//   - api_routes: [{method, path, operation, ...}]
type ServiceSpec struct {
	Version      int               `yaml:"version"`
	Aggregate    string            `yaml:"aggregate"`
	Entity       string            `yaml:"entity"`
	Service      *ServiceDef       `yaml:"service"`
	OwnerTeam    string            `yaml:"owner_team"`
	Routes       []RouteSpec       `yaml:"routes"`
	APIRoutes    []APIRouteSpec    `yaml:"api_routes"`
	ContractTest *ContractTestDef  `yaml:"contract_test"`
}

// ServiceName returns the service name regardless of YAML format.
func (s *ServiceSpec) ServiceName() string {
	if s.Service != nil {
		return s.Service.Name
	}
	return ""
}

type ServiceDef struct {
	Name        string `yaml:"name"`
	Domain      string `yaml:"domain"`
	Owner       string `yaml:"owner"`
	Description string `yaml:"description"`
}

type RouteSpec struct {
	Path       string          `yaml:"path"`
	Operations []OperationSpec `yaml:"operations"`
}

type OperationSpec struct {
	Method         string `yaml:"method"`
	Name           string `yaml:"name"`
	Description    string `yaml:"description"`
	RequestEntity  string `yaml:"request_entity"`
	ResponseEntity string `yaml:"response_entity"`
}

type APIRouteSpec struct {
	Method         string   `yaml:"method"`
	Path           string   `yaml:"path"`
	Operation      string   `yaml:"operation"`
	Description    string   `yaml:"description"`
	RequestFields  []string `yaml:"request_fields"`
	ResponseEntity string   `yaml:"response_entity"`
}

type ContractTestDef struct {
	AppSide     any `yaml:"app_side"`
	ServiceSide any `yaml:"service_side"`
}

// SharedTypes represents the parsed _shared/types.yaml.
type SharedTypes struct {
	Version int                       `yaml:"version"`
	Types   map[string]any            `yaml:"types"`
	Enums   map[string][]string       `yaml:"enums"`
}
