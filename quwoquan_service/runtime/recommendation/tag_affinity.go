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

// ClassifyAndWeightTags classifies tags into four dimensions and applies
// depth-weighted hierarchical propagation.
// Returns per-dimension affinity increments.
func ClassifyAndWeightTags(tags []string, depthLevel int, referralSource string) FourDimAffinityDelta {
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

	for _, tag := range tags {
		dim := ClassifyTagDimension(tag)
		propagated := PropagateTagHierarchy(tag, effectiveWeight)

		var target map[string]float64
		switch dim {
		case DimensionTopic:
			target = delta.Topic
		case DimensionAudience:
			target = delta.Audience
		case DimensionFormat:
			target = delta.Format
		case DimensionEntity:
			target = delta.Entity
		default:
			target = delta.Topic
		}

		for path, w := range propagated {
			target[path] += w
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
