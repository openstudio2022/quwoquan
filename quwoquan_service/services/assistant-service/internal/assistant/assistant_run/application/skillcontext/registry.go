package skillcontext

import (
	"context"
	"fmt"
	"strings"

	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	readerports "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
)

type RegisteredResolver struct {
	ResolverRef string
	Resolver    Resolver
}

type ResolverRegistry struct {
	catalog   readerports.Catalog
	resolvers map[string]RegisteredResolver
}

func NewResolverRegistry(
	catalog readerports.Catalog,
	values ...RegisteredResolver,
) (*ResolverRegistry, error) {
	if catalog == nil {
		return nil, ErrResolverUnavailable
	}
	registry := &ResolverRegistry{
		catalog:   catalog,
		resolvers: make(map[string]RegisteredResolver, len(values)),
	}
	for _, value := range values {
		resolverRef := strings.TrimSpace(value.ResolverRef)
		if resolverRef == "" || value.Resolver == nil {
			return nil, ErrResolverUnavailable
		}
		if _, err := catalog.GetDescriptorByResolverRef(context.Background(), resolverRef); err != nil {
			return nil, ErrResolverUnavailable
		}
		if _, exists := registry.resolvers[resolverRef]; exists {
			return nil, fmt.Errorf("duplicate context resolver %q", resolverRef)
		}
		registry.resolvers[resolverRef] = RegisteredResolver{
			ResolverRef: resolverRef,
			Resolver:    value.Resolver,
		}
	}
	return registry, nil
}

func (r *ResolverRegistry) resolve(
	ctx context.Context,
	ref string,
) (RegisteredResolver, readermodel.Descriptor, bool) {
	if r == nil {
		return RegisteredResolver{}, readermodel.Descriptor{}, false
	}
	ref = strings.TrimSpace(ref)
	resolver, ok := r.resolvers[ref]
	if !ok {
		return RegisteredResolver{}, readermodel.Descriptor{}, false
	}
	descriptor, err := r.catalog.GetDescriptorByResolverRef(ctx, ref)
	if err != nil {
		return RegisteredResolver{}, readermodel.Descriptor{}, false
	}
	return resolver, descriptor, true
}

func (r *ResolverRegistry) Describe(
	ctx context.Context,
	ref string,
) (readermodel.Descriptor, bool) {
	_, descriptor, ok := r.resolve(ctx, ref)
	if !ok {
		return readermodel.Descriptor{}, false
	}
	return descriptor, true
}
