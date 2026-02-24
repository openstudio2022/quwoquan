package registry

import (
	"fmt"
	"sync"
)

// AggregateEntry holds all metadata for one aggregate or standalone entity.
type AggregateEntry struct {
	Spec    AggregateSpec
	Fields  FieldsSpec
	Events  EventsSpec
	Storage StorageSpec
	Service ServiceSpec
	DirName string
}

// EntityEntry holds field-level metadata for a single entity.
type EntityEntry struct {
	Name           string
	AggregateName  string
	IsRoot         bool
	Fields         EntityFieldDef
	StorageBackend string
	CacheLayer     string
	CacheTTL       int
}

// EntityRegistry provides runtime access to all metadata definitions.
// It is safe for concurrent use after initialization.
type EntityRegistry struct {
	mu         sync.RWMutex
	aggregates map[string]*AggregateEntry
	entities   map[string]*EntityEntry
	enums      map[string][]string
}

// GetAggregate returns the full aggregate entry by root name.
func (r *EntityRegistry) GetAggregate(name string) (*AggregateEntry, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	agg, ok := r.aggregates[name]
	if !ok {
		return nil, fmt.Errorf("aggregate %q not registered in metadata", name)
	}
	return agg, nil
}

// GetEntity returns entity metadata by name.
func (r *EntityRegistry) GetEntity(name string) (*EntityEntry, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	ent, ok := r.entities[name]
	if !ok {
		return nil, fmt.Errorf("entity %q not registered in metadata", name)
	}
	return ent, nil
}

// GetFieldPolicy returns field definitions for an entity.
func (r *EntityRegistry) GetFieldPolicy(entityName string) ([]FieldDef, error) {
	ent, err := r.GetEntity(entityName)
	if err != nil {
		return nil, err
	}
	return ent.Fields.Fields, nil
}

// GetField returns a single field definition.
func (r *EntityRegistry) GetField(entityName, fieldName string) (*FieldDef, error) {
	fields, err := r.GetFieldPolicy(entityName)
	if err != nil {
		return nil, err
	}
	for i := range fields {
		if fields[i].Name == fieldName {
			return &fields[i], nil
		}
	}
	return nil, fmt.Errorf("field %q not found in entity %q", fieldName, entityName)
}

// GetCapabilities returns the list of capabilities for an aggregate.
func (r *EntityRegistry) GetCapabilities(aggregateName string) ([]string, error) {
	agg, err := r.GetAggregate(aggregateName)
	if err != nil {
		return nil, err
	}
	return agg.Spec.Capabilities, nil
}

// GetStorageBackend returns the storage backend for an entity.
func (r *EntityRegistry) GetStorageBackend(entityName string) (string, error) {
	ent, err := r.GetEntity(entityName)
	if err != nil {
		return "", err
	}
	return ent.StorageBackend, nil
}

// GetCacheTTL returns the cache TTL in seconds, 0 if no cache.
func (r *EntityRegistry) GetCacheTTL(entityName string) (int, error) {
	ent, err := r.GetEntity(entityName)
	if err != nil {
		return 0, err
	}
	return ent.CacheTTL, nil
}

// GetEnum returns the enum values for a named enum type.
func (r *EntityRegistry) GetEnum(name string) ([]string, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	vals, ok := r.enums[name]
	if !ok {
		return nil, fmt.Errorf("enum %q not defined in shared types", name)
	}
	return vals, nil
}

// GetEvents returns all event definitions for an aggregate.
func (r *EntityRegistry) GetEvents(aggregateName string) ([]EventDef, error) {
	agg, err := r.GetAggregate(aggregateName)
	if err != nil {
		return nil, err
	}
	return agg.Events.Events, nil
}

// GetService returns the service spec for an aggregate.
func (r *EntityRegistry) GetService(aggregateName string) (*ServiceSpec, error) {
	agg, err := r.GetAggregate(aggregateName)
	if err != nil {
		return nil, err
	}
	return &agg.Service, nil
}

// ListAggregates returns all registered aggregate names.
func (r *EntityRegistry) ListAggregates() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()

	names := make([]string, 0, len(r.aggregates))
	for name := range r.aggregates {
		names = append(names, name)
	}
	return names
}

// ListEntities returns all registered entity names.
func (r *EntityRegistry) ListEntities() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()

	names := make([]string, 0, len(r.entities))
	for name := range r.entities {
		names = append(names, name)
	}
	return names
}

// Stats returns loading statistics.
func (r *EntityRegistry) Stats() RegistryStats {
	r.mu.RLock()
	defer r.mu.RUnlock()

	totalFields := 0
	for _, ent := range r.entities {
		totalFields += len(ent.Fields.Fields)
	}

	totalEvents := 0
	for _, agg := range r.aggregates {
		totalEvents += len(agg.Events.Events)
	}

	return RegistryStats{
		AggregateCount: len(r.aggregates),
		EntityCount:    len(r.entities),
		FieldCount:     totalFields,
		EventCount:     totalEvents,
		EnumCount:      len(r.enums),
	}
}

type RegistryStats struct {
	AggregateCount int
	EntityCount    int
	FieldCount     int
	EventCount     int
	EnumCount      int
}
