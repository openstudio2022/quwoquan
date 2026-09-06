package persistence

import (
	"context"
	"fmt"
	"strings"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

func releaseIdentityKey(identity homepageports.ReleaseIdentity) string {
	return strings.Join([]string{
		strings.TrimSpace(identity.Environment), strings.TrimSpace(identity.SourceOwner),
		strings.TrimSpace(identity.ReleaseID), strings.TrimSpace(identity.ManifestDigest),
	}, "\x00")
}

func (s *MemoryHomepageStore) StageReleaseCandidate(
	_ context.Context,
	state homepageports.ReleaseCandidateState,
	projections []homepageports.ReleaseProjection,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := releaseIdentityKey(state.Identity)
	if current, found := s.releaseCandidates[key]; found {
		if !sameReleaseCandidateState(current, state) {
			return false, fmt.Errorf("homepage release candidate drift for exact tuple")
		}
		stored := s.releaseProjections[key]
		if len(stored) != len(projections) {
			return false, fmt.Errorf("homepage release candidate closure drift for exact tuple")
		}
		for _, projection := range projections {
			currentProjection, ok := stored[projection.HomepageID]
			if !ok || currentProjection.DocumentDigest != projection.DocumentDigest ||
				currentProjection.EntityRef != projection.EntityRef {
				return false, fmt.Errorf("homepage release candidate projection drift for exact tuple")
			}
		}
		return true, nil
	}
	byHomepage := make(map[string]homepageports.ReleaseProjection, len(projections))
	byEntityRef := make(map[string]bool, len(projections))
	for _, projection := range projections {
		if projection.HomepageID == "" || projection.EntityRef == "" ||
			releaseIdentityKey(projection.Identity) != key ||
			projection.ProjectionVersion != state.ProjectionVersion ||
			projection.ClosureDigest != state.ClosureDigest ||
			projection.DocumentDigest == "" {
			return false, fmt.Errorf("homepage release projection is incomplete")
		}
		if _, exists := byHomepage[projection.HomepageID]; exists || byEntityRef[projection.EntityRef] {
			return false, fmt.Errorf("homepage release projection identity is duplicated")
		}
		byEntityRef[projection.EntityRef] = true
		byHomepage[projection.HomepageID] = cloneReleaseProjection(projection)
	}
	if len(byHomepage) != state.ExpectedCount || state.ExpectedCount != state.ProjectedCount {
		return false, fmt.Errorf("homepage release candidate counts are invalid")
	}
	s.releaseCandidates[key] = state
	s.releaseProjections[key] = byHomepage
	return false, nil
}

func (s *MemoryHomepageStore) ReadVerifiedReleaseCandidate(
	_ context.Context,
	identity homepageports.ReleaseIdentity,
) (homepageports.ReleaseCandidateState, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	state, found := s.releaseCandidates[releaseIdentityKey(identity)]
	if !found {
		return homepageports.ReleaseCandidateState{}, false, nil
	}
	projections := s.releaseProjections[releaseIdentityKey(identity)]
	if len(projections) != state.ProjectedCount || state.ExpectedCount != state.ProjectedCount ||
		state.ProjectionVersion <= 0 || state.VerifiedAt.IsZero() || state.ClosureDigest == "" ||
		state.EntityRefMappingDigest == "" {
		return homepageports.ReleaseCandidateState{}, false, fmt.Errorf("homepage release candidate closure is invalid")
	}
	for _, projection := range projections {
		if releaseIdentityKey(projection.Identity) != releaseIdentityKey(identity) ||
			projection.ProjectionVersion != state.ProjectionVersion || projection.ClosureDigest != state.ClosureDigest ||
			projection.DocumentDigest == "" {
			return homepageports.ReleaseCandidateState{}, false, fmt.Errorf("homepage release candidate projection is invalid")
		}
	}
	return state, true, nil
}

func (s *MemoryHomepageStore) LoadExactReleaseProjection(
	_ context.Context,
	identity homepageports.ReleaseIdentity,
	homepageID string,
) (homepageports.ReleaseProjection, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	key := releaseIdentityKey(identity)
	state, found := s.releaseCandidates[key]
	if !found {
		return homepageports.ReleaseProjection{}, false, nil
	}
	projection, found := s.releaseProjections[key][strings.TrimSpace(homepageID)]
	if !found {
		return homepageports.ReleaseProjection{}, false, nil
	}
	if projection.ProjectionVersion != state.ProjectionVersion || projection.ClosureDigest != state.ClosureDigest ||
		releaseIdentityKey(projection.Identity) != key {
		return homepageports.ReleaseProjection{}, false, fmt.Errorf("homepage exact release projection differs from candidate closure")
	}
	return cloneReleaseProjection(projection), true, nil
}

func sameReleaseCandidateState(left, right homepageports.ReleaseCandidateState) bool {
	return releaseIdentityKey(left.Identity) == releaseIdentityKey(right.Identity) &&
		left.ProjectionVersion == right.ProjectionVersion && left.ClosureDigest == right.ClosureDigest &&
		left.ExpectedCount == right.ExpectedCount && left.ProjectedCount == right.ProjectedCount &&
		left.EntityRefMappingDigest == right.EntityRefMappingDigest
}

func cloneReleaseProjection(value homepageports.ReleaseProjection) homepageports.ReleaseProjection {
	result := value
	result.Location = cloneReleaseGeo(value.Location)
	result.CategoryTags = append([]string(nil), value.CategoryTags...)
	result.IntroductionAssets = append([]homepagemodel.IntroductionAsset(nil), value.IntroductionAssets...)
	result.StructuredFacts = value.StructuredFacts.Clone()
	if value.PrimarySource != nil {
		copy := *value.PrimarySource
		result.PrimarySource = &copy
	}
	result.SourceURLs = append([]string(nil), value.SourceURLs...)
	return result
}

func cloneReleaseGeo(value *homepagemodel.GeoPoint) *homepagemodel.GeoPoint {
	if value == nil {
		return nil
	}
	copy := *value
	return &copy
}

func (s *MemoryHomepageStore) EnsureReleaseShells(
	_ context.Context,
	projections []homepageports.ReleaseProjection,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, projection := range projections {
		if existing, found := s.homepages[projection.HomepageID]; found {
			if existing.SourceOwner != projection.Identity.SourceOwner || existing.SourceEntityRef != projection.EntityRef {
				return fmt.Errorf("homepage release shell identity conflict")
			}
			continue
		}
		aggregate, err := homepagemodel.NewReleaseShell(
			projection.HomepageID, projection.EntityRef, projection.HomepageType,
			projection.Title, projection.Identity.SourceOwner, projection.VerifiedAt,
		)
		if err != nil {
			return err
		}
		snapshot := aggregate.Snapshot()
		if err := s.ensureUniqueLocked(snapshot, ""); err != nil {
			return err
		}
		s.homepages[snapshot.ID] = snapshot
	}
	return nil
}
