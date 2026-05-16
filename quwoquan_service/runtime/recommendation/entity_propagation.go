package recommendation

import "context"

// EntityTagIndex provides the tag associations for entities.
// Implemented by infrastructure layer backed by MongoDB rm_entity_tags collection.
type EntityTagIndex interface {
	GetEntityTags(ctx context.Context, entityID string) ([]string, error)
}

// NullEntityTagIndex returns empty tags (used when no entity index is configured).
type NullEntityTagIndex struct{}

func (*NullEntityTagIndex) GetEntityTags(_ context.Context, _ string) ([]string, error) {
	return nil, nil
}

// EntityInterestPropagation computes entity-level and tag-level interest increments
// from a user interacting with content that references entities.
type EntityInterestPropagation struct {
	entityTagIndex EntityTagIndex
	decayFactor    float64 // propagation decay (default 0.5 = 50% attenuation)
}

func NewEntityInterestPropagation(index EntityTagIndex) *EntityInterestPropagation {
	if index == nil {
		index = &NullEntityTagIndex{}
	}
	return &EntityInterestPropagation{
		entityTagIndex: index,
		decayFactor:    0.5,
	}
}

// EntityPropagationResult holds the computed interest increments from entity interaction.
type EntityPropagationResult struct {
	// Direct entity instance affinities (entityID → increment)
	EntityInstanceDeltas map[string]float64
	// Propagated tag affinities from entity tags (tagRef → increment)
	PropagatedTagDeltas map[string]float64
}

// Propagate computes interest propagation for a set of entityRefs given engagement depth.
// Flow: entityRefs → lookup entity tags → propagate with decay
func (p *EntityInterestPropagation) Propagate(ctx context.Context, entityRefs []string, depthLevel int) (*EntityPropagationResult, error) {
	if len(entityRefs) == 0 {
		return &EntityPropagationResult{
			EntityInstanceDeltas: make(map[string]float64),
			PropagatedTagDeltas:  make(map[string]float64),
		}, nil
	}

	depthCoeff := 1.0
	if depthLevel >= 0 && depthLevel < len(DepthLevelCoefficient) {
		depthCoeff = DepthLevelCoefficient[depthLevel]
	}

	result := &EntityPropagationResult{
		EntityInstanceDeltas: make(map[string]float64, len(entityRefs)),
		PropagatedTagDeltas:  make(map[string]float64),
	}

	for _, entityID := range entityRefs {
		// Direct entity affinity increment
		result.EntityInstanceDeltas[entityID] += depthCoeff

		// Lookup entity's associated tags and propagate with decay
		entityTags, err := p.entityTagIndex.GetEntityTags(ctx, entityID)
		if err != nil {
			continue
		}
		for _, tag := range entityTags {
			propagated := PropagateTagHierarchy(tag, depthCoeff*p.decayFactor)
			for path, w := range propagated {
				result.PropagatedTagDeltas[path] += w
			}
		}
	}

	return result, nil
}
