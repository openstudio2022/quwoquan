package interceptor

import (
	"context"

	"quwoquan_service/runtime/registry"
	"quwoquan_service/runtime/repository"
)

// Operation describes the type of repository operation being intercepted.
type Operation string

const (
	OpRead   Operation = "read"
	OpCreate Operation = "create"
	OpUpdate Operation = "update"
	OpDelete Operation = "delete"
)

// Context carries metadata about the intercepted operation.
type Context struct {
	EntityName string
	Operation  Operation
	EntityID   string
	Input      *map[string]any
	FieldMeta  []registry.FieldDef
}

// Handler is the function signature for the next handler in the chain.
type Handler func(ctx context.Context, ic *Context) error

// Interceptor processes repository operations in a pipeline.
type Interceptor interface {
	Name() string
	Intercept(ctx context.Context, ic *Context, next Handler) error
}

// Chain composes multiple interceptors into a pipeline.
type Chain struct {
	interceptors []Interceptor
}

// NewChain creates an interceptor chain.
func NewChain(interceptors ...Interceptor) *Chain {
	return &Chain{interceptors: interceptors}
}

// Execute runs the chain with the given final handler.
func (c *Chain) Execute(ctx context.Context, ic *Context, final Handler) error {
	return c.buildChain(0, final)(ctx, ic)
}

func (c *Chain) buildChain(idx int, final Handler) Handler {
	if idx >= len(c.interceptors) {
		return final
	}
	return func(ctx context.Context, ic *Context) error {
		return c.interceptors[idx].Intercept(ctx, ic, c.buildChain(idx+1, final))
	}
}

// InterceptedRepository wraps a repository with an interceptor chain.
type InterceptedRepository struct {
	inner repository.Repository[map[string]any]
	chain *Chain
	reg   *registry.EntityRegistry
	name  string
}

// NewInterceptedRepository decorates a repository with interceptors.
func NewInterceptedRepository(
	inner repository.Repository[map[string]any],
	chain *Chain,
	reg *registry.EntityRegistry,
	entityName string,
) *InterceptedRepository {
	return &InterceptedRepository{
		inner: inner,
		chain: chain,
		reg:   reg,
		name:  entityName,
	}
}

func (r *InterceptedRepository) buildContext(op Operation, id string, entity *map[string]any) *Context {
	fieldMeta, _ := r.reg.GetFieldPolicy(r.name)
	return &Context{
		EntityName: r.name,
		Operation:  op,
		EntityID:   id,
		Input:      entity,
		FieldMeta:  fieldMeta,
	}
}

func (r *InterceptedRepository) FindByID(ctx context.Context, id string) (*map[string]any, error) {
	var result *map[string]any
	ic := r.buildContext(OpRead, id, nil)

	err := r.chain.Execute(ctx, ic, func(ctx context.Context, _ *Context) error {
		var err error
		result, err = r.inner.FindByID(ctx, id)
		return err
	})
	return result, err
}

func (r *InterceptedRepository) FindAll(ctx context.Context, q repository.Query) (*repository.Page[map[string]any], error) {
	var result *repository.Page[map[string]any]
	ic := r.buildContext(OpRead, "", nil)

	err := r.chain.Execute(ctx, ic, func(ctx context.Context, _ *Context) error {
		var err error
		result, err = r.inner.FindAll(ctx, q)
		return err
	})
	return result, err
}

func (r *InterceptedRepository) Create(ctx context.Context, entity *map[string]any) error {
	ic := r.buildContext(OpCreate, "", entity)
	return r.chain.Execute(ctx, ic, func(ctx context.Context, ic *Context) error {
		return r.inner.Create(ctx, ic.Input)
	})
}

func (r *InterceptedRepository) Update(ctx context.Context, id string, entity *map[string]any) error {
	ic := r.buildContext(OpUpdate, id, entity)
	return r.chain.Execute(ctx, ic, func(ctx context.Context, ic *Context) error {
		return r.inner.Update(ctx, id, ic.Input)
	})
}

func (r *InterceptedRepository) Delete(ctx context.Context, id string) error {
	ic := r.buildContext(OpDelete, id, nil)
	return r.chain.Execute(ctx, ic, func(ctx context.Context, _ *Context) error {
		return r.inner.Delete(ctx, id)
	})
}

func (r *InterceptedRepository) Count(ctx context.Context, filter repository.Filter) (int64, error) {
	return r.inner.Count(ctx, filter)
}
