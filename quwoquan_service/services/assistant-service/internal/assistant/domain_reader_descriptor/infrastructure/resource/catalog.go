package resource

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
)

// Catalog is an immutable service resource assembled from the descriptor set
// bound to the running binary. It stores no domain data and performs no file or
// database lookup on the request path.
type Catalog struct {
	byID       map[string]model.Descriptor
	byResolver map[string]model.Descriptor
	ordered    []model.Descriptor
}

var _ ports.Catalog = (*Catalog)(nil)

func NewCatalog(values []model.Descriptor) (*Catalog, error) {
	catalog := &Catalog{
		byID:       make(map[string]model.Descriptor, len(values)),
		byResolver: make(map[string]model.Descriptor, len(values)),
		ordered:    make([]model.Descriptor, 0, len(values)),
	}
	for _, value := range values {
		descriptor, err := model.NewDescriptor(value)
		if err != nil {
			return nil, fmt.Errorf("normalize domain reader descriptor: %w", err)
		}
		if _, exists := catalog.byID[descriptor.DescriptorID]; exists {
			return nil, fmt.Errorf("duplicate domain reader descriptor %q", descriptor.DescriptorID)
		}
		if _, exists := catalog.byResolver[descriptor.ResolverRef]; exists {
			return nil, fmt.Errorf("duplicate domain reader resolver %q", descriptor.ResolverRef)
		}
		catalog.byID[descriptor.DescriptorID] = descriptor
		catalog.byResolver[descriptor.ResolverRef] = descriptor
		catalog.ordered = append(catalog.ordered, descriptor)
	}
	sort.Slice(catalog.ordered, func(left, right int) bool {
		return catalog.ordered[left].DescriptorID < catalog.ordered[right].DescriptorID
	})
	return catalog, nil
}

func (catalog *Catalog) GetDescriptor(
	ctx context.Context,
	descriptorID string,
) (model.Descriptor, error) {
	if err := ctx.Err(); err != nil {
		return model.Descriptor{}, err
	}
	if catalog == nil {
		return model.Descriptor{}, model.ErrDescriptorNotFound
	}
	descriptor, found := catalog.byID[strings.TrimSpace(descriptorID)]
	if !found {
		return model.Descriptor{}, model.ErrDescriptorNotFound
	}
	return descriptor.Clone(), nil
}

func (catalog *Catalog) GetDescriptorByResolverRef(
	ctx context.Context,
	resolverRef string,
) (model.Descriptor, error) {
	if err := ctx.Err(); err != nil {
		return model.Descriptor{}, err
	}
	if catalog == nil {
		return model.Descriptor{}, model.ErrDescriptorNotFound
	}
	descriptor, found := catalog.byResolver[strings.TrimSpace(resolverRef)]
	if !found {
		return model.Descriptor{}, model.ErrDescriptorNotFound
	}
	return descriptor.Clone(), nil
}

func (catalog *Catalog) ListDescriptors(
	ctx context.Context,
	limit int,
) ([]model.Descriptor, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if catalog == nil {
		return nil, fmt.Errorf("domain reader catalog is unavailable")
	}
	if limit <= 0 || limit > 100 {
		return nil, model.ErrInvalidDescriptor
	}
	if limit > len(catalog.ordered) {
		limit = len(catalog.ordered)
	}
	result := make([]model.Descriptor, 0, limit)
	for _, descriptor := range catalog.ordered[:limit] {
		result = append(result, descriptor.Clone())
	}
	return result, nil
}
