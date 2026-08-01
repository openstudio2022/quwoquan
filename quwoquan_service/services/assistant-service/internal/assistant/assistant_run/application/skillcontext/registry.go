package skillcontext

import (
	"fmt"
	"strings"
)

type RegisteredResolver struct {
	ResolverRef string
	Resolver    Resolver
}

type ResolverRegistry struct {
	resolvers map[string]Resolver
}

func NewResolverRegistry(values ...RegisteredResolver) (*ResolverRegistry, error) {
	registry := &ResolverRegistry{resolvers: make(map[string]Resolver, len(values))}
	for _, value := range values {
		ref := strings.TrimSpace(value.ResolverRef)
		if ref == "" || value.Resolver == nil {
			return nil, ErrResolverUnavailable
		}
		if _, exists := registry.resolvers[ref]; exists {
			return nil, fmt.Errorf("duplicate context resolver %q", ref)
		}
		registry.resolvers[ref] = value.Resolver
	}
	return registry, nil
}

func (r *ResolverRegistry) resolve(ref string) (Resolver, bool) {
	if r == nil {
		return nil, false
	}
	resolver, ok := r.resolvers[strings.TrimSpace(ref)]
	return resolver, ok
}
