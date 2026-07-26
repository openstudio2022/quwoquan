package behavior

import (
	"context"
	"errors"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

// ActiveTaxonomyLeafValidationPort is the typed outbound boundary for the
// active tag taxonomy snapshot. The implementation must fail closed if the
// snapshot does not match ExpectedTaxonomyReleaseID.
type ActiveTaxonomyLeafValidationPort interface {
	ValidateActiveTaxonomyLeaves(
		ctx context.Context,
		expectedTaxonomyReleaseID string,
		tagRefs []string,
	) error
}

// CatalogBackedOnboardingInterestTaxonomy is the release-time catalog policy
// injected by composition. It checks local catalog invariants for the whole
// request, then makes exactly one typed outbound validation call for the
// deduplicated tag refs.
//
// The catalog version is an app-facing publishing version. Taxonomy release
// identity remains distinct and is verified by tag-service at the snapshot
// boundary.
type CatalogBackedOnboardingInterestTaxonomy struct {
	Version                  string
	TaxonomyReleaseID        string
	DimensionRoots           map[string]string
	MinSelections            int
	MaxSelections            int
	DimensionMinSelections   map[string]int
	DimensionMaxSelections   map[string]int
	ActiveLeafValidationPort ActiveTaxonomyLeafValidationPort
}

func (v CatalogBackedOnboardingInterestTaxonomy) ValidateOnboardingInterestBatch(
	ctx context.Context,
	inputs []OnboardingInterestTaxonomyValidationInput,
) error {
	if err := v.validatePolicy(); err != nil {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error())
	}
	if len(inputs) == 0 {
		return nil
	}
	tagRefs := make([]string, 0)
	seenTagRefs := make(map[string]struct{})
	for _, input := range inputs {
		if strings.TrimSpace(input.CatalogVersion) != strings.TrimSpace(v.Version) {
			return contentgenerated.AppErrorFromInvalidArgument(
				"onboarding catalogVersion is not active",
			)
		}
		if strings.TrimSpace(input.TaxonomyReleaseID) != strings.TrimSpace(v.TaxonomyReleaseID) {
			return contentgenerated.AppErrorFromInvalidArgument(
				"onboarding taxonomyReleaseId does not match the active catalog",
			)
		}
		if len(input.TagRefs) < v.MinSelections || len(input.TagRefs) > v.MaxSelections {
			return contentgenerated.AppErrorFromInvalidArgument(
				"onboarding tagRefs count is outside catalog bounds",
			)
		}
		perDimension := make(map[string]int, len(v.DimensionRoots))
		for _, rawTagRef := range input.TagRefs {
			tagRef := strings.TrimSpace(rawTagRef)
			dimension, root := v.dimensionForTagRef(tagRef)
			if dimension == "" {
				return contentgenerated.AppErrorFromInvalidArgument(
					"onboarding tagRef is outside declared dimensions",
				)
			}
			if tagRef == root {
				return contentgenerated.AppErrorFromInvalidArgument(
					"onboarding tagRef is a dimension root, not a leaf",
				)
			}
			perDimension[dimension]++
			if _, exists := seenTagRefs[tagRef]; !exists {
				seenTagRefs[tagRef] = struct{}{}
				tagRefs = append(tagRefs, tagRef)
			}
		}
		for dimension := range v.DimensionRoots {
			count := perDimension[dimension]
			if count < v.DimensionMinSelections[dimension] || count > v.DimensionMaxSelections[dimension] {
				return contentgenerated.AppErrorFromInvalidArgument(
					"onboarding dimension selection count is outside catalog bounds",
				)
			}
		}
	}
	if len(tagRefs) == 0 {
		return contentgenerated.AppErrorFromInvalidArgument(
			"onboarding_interest requires at least one canonical tagRef",
		)
	}
	if err := v.ActiveLeafValidationPort.ValidateActiveTaxonomyLeaves(
		ctx,
		v.TaxonomyReleaseID,
		tagRefs,
	); err != nil {
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return appError
		}
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"active taxonomy leaf validation failed",
		)
	}
	return nil
}

func (v CatalogBackedOnboardingInterestTaxonomy) validatePolicy() error {
	if strings.TrimSpace(v.Version) == "" {
		return errors.New("onboarding catalog policy has no version")
	}
	if strings.TrimSpace(v.TaxonomyReleaseID) == "" {
		return errors.New("onboarding catalog policy has no taxonomy release id")
	}
	if v.MinSelections <= 0 || v.MaxSelections < v.MinSelections {
		return errors.New("onboarding catalog policy has invalid global selection bounds")
	}
	if v.ActiveLeafValidationPort == nil {
		return errors.New("active taxonomy leaf validation port is not configured")
	}
	if len(v.DimensionRoots) == 0 ||
		len(v.DimensionRoots) != len(v.DimensionMinSelections) ||
		len(v.DimensionRoots) != len(v.DimensionMaxSelections) {
		return errors.New("onboarding catalog policy has incomplete dimension maps")
	}
	for id, rawRoot := range v.DimensionRoots {
		root := strings.TrimSpace(rawRoot)
		if strings.TrimSpace(id) == "" || root == "" || root != strings.Trim(root, "/") {
			return errors.New("onboarding catalog policy has an invalid dimension root")
		}
		minSelections, hasMin := v.DimensionMinSelections[id]
		maxSelections, hasMax := v.DimensionMaxSelections[id]
		if !hasMin || !hasMax || minSelections < 0 || maxSelections < minSelections {
			return errors.New("onboarding catalog policy has invalid dimension selection bounds")
		}
		for otherID, otherRawRoot := range v.DimensionRoots {
			if id == otherID {
				continue
			}
			otherRoot := strings.TrimSpace(otherRawRoot)
			if root == otherRoot ||
				strings.HasPrefix(root, otherRoot+"/") ||
				strings.HasPrefix(otherRoot, root+"/") {
				return errors.New("onboarding catalog policy has overlapping dimension roots")
			}
		}
	}
	return nil
}

func (v CatalogBackedOnboardingInterestTaxonomy) dimensionForTagRef(tagRef string) (string, string) {
	for id, rawRoot := range v.DimensionRoots {
		root := strings.TrimSpace(rawRoot)
		if tagRef == root || strings.HasPrefix(tagRef, root+"/") {
			return id, root
		}
	}
	return "", ""
}
