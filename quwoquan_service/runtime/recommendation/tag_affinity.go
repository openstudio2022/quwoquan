package recommendation

import "strings"

// TagDimension identifies which dimension a tag belongs to.
type TagDimension string

const (
	DimensionTopic    TagDimension = "Topic"
	DimensionAudience TagDimension = "Audience"
	DimensionFormat   TagDimension = "Format"
	DimensionEntity   TagDimension = "Entity"
	DimensionUnknown  TagDimension = ""
)

// ClassifyTagDimension extracts the top-level dimension from a tagRef path.
// Tag paths follow the format "Dimension/Level1/Level2/..." (e.g. "Topic/旅行/自驾").
func ClassifyTagDimension(tagRef string) TagDimension {
	parts := strings.SplitN(tagRef, "/", 2)
	if len(parts) == 0 {
		return DimensionUnknown
	}
	switch parts[0] {
	case "Topic":
		return DimensionTopic
	case "Audience":
		return DimensionAudience
	case "Format":
		return DimensionFormat
	case "Entity":
		return DimensionEntity
	default:
		return DimensionUnknown
	}
}

// TagAncestors returns the ancestor paths of a tag for hierarchical generalization.
// For "Topic/旅行/自驾/川西自驾" it returns ["Topic/旅行/自驾", "Topic/旅行"].
// The root dimension (e.g. "Topic") alone is NOT included as it's too generic.
func TagAncestors(tagRef string) []string {
	parts := strings.Split(tagRef, "/")
	if len(parts) <= 2 {
		return nil
	}
	ancestors := make([]string, 0, len(parts)-2)
	for i := len(parts) - 1; i >= 2; i-- {
		ancestors = append(ancestors, strings.Join(parts[:i], "/"))
	}
	return ancestors
}

// HierarchicalDecayFactors defines the decay applied at each ancestor level.
// Index 0 = immediate parent (0.5), index 1 = grandparent (0.25), etc.
var HierarchicalDecayFactors = []float64{0.5, 0.25, 0.125, 0.0625}

// PropagateTagHierarchy distributes a weighted tag interaction up the hierarchy.
// Returns a map of tag paths to their propagated weight increments.
func PropagateTagHierarchy(tagRef string, weight float64) map[string]float64 {
	result := make(map[string]float64)
	result[tagRef] = weight

	ancestors := TagAncestors(tagRef)
	for i, ancestor := range ancestors {
		decay := 0.0
		if i < len(HierarchicalDecayFactors) {
			decay = HierarchicalDecayFactors[i]
		}
		if decay > 0 {
			result[ancestor] = weight * decay
		}
	}
	return result
}

// SameAsResolver resolves a tagRef to the tagRefs on other axes that denote the
// same real-world concept, as declared by sameAsRefs in the tag taxonomy.
//
// It exists because the four tag groups are stored in four independent affinity
// maps and matched by exact string. Without a bridge, an onboarding pick of
// "Audience/用户/兴趣偏好/旅行摄影/摄影" contributes exactly zero weight to
// "Topic/摄影" content, and hierarchical propagation cannot help because it only
// walks path prefixes and never crosses a group boundary.
type SameAsResolver interface {
	SameAsRefs(tagRef string) []string
}

// SameAsBridgeWeight is the fraction of a tag's weight propagated to the same
// concept on another axis.
//
// It sits above the immediate-parent decay (0.5) because a cross-axis synonym is
// the same concept rather than a generalization of it, but stays below 1.0 so a
// directly observed tag always outranks a bridged one.
const SameAsBridgeWeight = 0.6

// StaticSameAsResolver resolves bridges from an in-memory table.
type StaticSameAsResolver map[string][]string

// SameAsRefs implements SameAsResolver.
func (r StaticSameAsResolver) SameAsRefs(tagRef string) []string {
	return r[tagRef]
}

// ClassifyAndWeightTagsWithBridge classifies tags into four dimensions, applies
// depth-weighted hierarchical propagation, and propagates each tag's weight to
// the same concept on other axes when a resolver is present.
//
// Bridged tags are propagated up their own hierarchy too, so bridging
// "Audience/用户/兴趣偏好/旅行摄影/自驾" to "Topic/旅行/出行方式/自驾" also lifts
// "Topic/旅行/出行方式" and "Topic/旅行". Bridges are not followed transitively:
// a bridge of a bridge is a different concept, and chaining would let weight
// leak across the whole graph.
func ClassifyAndWeightTagsWithBridge(
	tags []string,
	depthLevel int,
	referralSource string,
	resolver SameAsResolver,
) FourDimAffinityDelta {
	baseWeight := 1.0
	depthCoeff := 1.0
	if depthLevel >= 0 && depthLevel < len(DepthLevelCoefficient) {
		depthCoeff = DepthLevelCoefficient[depthLevel]
	}
	sourceMultiplier := 1.0
	if referralSource != "" {
		if m, ok := ReferralSourceMultiplier[referralSource]; ok {
			sourceMultiplier = m
		}
	}
	effectiveWeight := baseWeight * depthCoeff * sourceMultiplier

	delta := FourDimAffinityDelta{
		Topic:    make(map[string]float64),
		Audience: make(map[string]float64),
		Format:   make(map[string]float64),
		Entity:   make(map[string]float64),
	}

	accumulate := func(tagRef string, weight float64) {
		target := delta.Topic
		switch ClassifyTagDimension(tagRef) {
		case DimensionAudience:
			target = delta.Audience
		case DimensionFormat:
			target = delta.Format
		case DimensionEntity:
			target = delta.Entity
		}
		for path, w := range PropagateTagHierarchy(tagRef, weight) {
			target[path] += w
		}
	}

	for _, tag := range tags {
		accumulate(tag, effectiveWeight)
		if resolver == nil {
			continue
		}
		for _, bridged := range resolver.SameAsRefs(tag) {
			if bridged == "" || bridged == tag {
				continue
			}
			accumulate(bridged, effectiveWeight*SameAsBridgeWeight)
		}
	}

	return delta
}

// FourDimAffinityDelta holds per-dimension tag affinity increments.
type FourDimAffinityDelta struct {
	Topic    map[string]float64
	Audience map[string]float64
	Format   map[string]float64
	Entity   map[string]float64
}
