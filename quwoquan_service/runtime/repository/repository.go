package repository

import (
	"context"
)

// Repository defines the generic interface for entity persistence.
// Business services code against this interface; adapters handle storage-specific logic.
type Repository[T any] interface {
	FindByID(ctx context.Context, id string) (*T, error)
	FindAll(ctx context.Context, query Query) (*Page[T], error)
	Create(ctx context.Context, entity *T) error
	Update(ctx context.Context, id string, entity *T) error
	Delete(ctx context.Context, id string) error
	Count(ctx context.Context, filter Filter) (int64, error)
}

// Query encapsulates list/search parameters.
type Query struct {
	Filter  Filter
	Sort    []SortField
	Cursor  string
	Limit   int
}

type Filter struct {
	Conditions []Condition
	Logic      LogicOp
}

type Condition struct {
	Field    string
	Operator Operator
	Value    any
}

type SortField struct {
	Field     string
	Direction SortDirection
}

type SortDirection int

const (
	Asc  SortDirection = 1
	Desc SortDirection = -1
)

type LogicOp string

const (
	And LogicOp = "AND"
	Or  LogicOp = "OR"
)

type Operator string

const (
	Eq    Operator = "eq"
	Ne    Operator = "ne"
	Gt    Operator = "gt"
	Gte   Operator = "gte"
	Lt    Operator = "lt"
	Lte   Operator = "lte"
	In    Operator = "in"
	Regex Operator = "regex"
)

// Page holds a cursor-paginated result set.
type Page[T any] struct {
	Items      []T    `json:"items"`
	NextCursor string `json:"nextCursor,omitempty"`
	Total      int64  `json:"total,omitempty"`
}

// CacheableRepository extends Repository with cache-aware operations.
type CacheableRepository[T any] interface {
	Repository[T]
	FindByIDCached(ctx context.Context, id string) (*T, error)
	InvalidateCache(ctx context.Context, id string) error
}

// UnitOfWork provides transaction support across repositories.
type UnitOfWork interface {
	Begin(ctx context.Context) (context.Context, error)
	Commit(ctx context.Context) error
	Rollback(ctx context.Context) error
}

// EventPublisher supports domain event emission after repository writes.
type EventPublisher interface {
	Publish(ctx context.Context, event DomainEvent) error
}

// DomainEvent represents a business event produced by repository operations.
type DomainEvent struct {
	Type          string         `json:"type"`
	AggregateType string         `json:"aggregateType"`
	AggregateID   string         `json:"aggregateId"`
	Payload       map[string]any `json:"payload"`
	OccurredAt    string         `json:"occurredAt"`
}
