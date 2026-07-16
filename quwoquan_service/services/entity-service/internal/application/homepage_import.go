package application

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"
)

// ImportedHomepageInput is one approved data entity projected to a homepage.
// The release-level source identity lives in HomepageImportRequest so every
// object in one invocation is reconciled against the same immutable release.
type ImportedHomepageInput struct {
	EntityRef            string
	Title                string
	HomepageType         string
	City                 string
	IntroductionMarkdown string
	IntroductionAssets   []HomepageIntroductionAsset
	PrimarySource        *HomepageSource
	SourceURLs           []string
	CategoryTags         []string
	SourceTaskID         string
}

type HomepageImportMode string

const (
	HomepageImportModeUpsert HomepageImportMode = "upsert"
	HomepageImportModeSync   HomepageImportMode = "sync"
)

// HomepageImportRequest is the only importer application boundary. Sync is
// source-owner scoped: it never deletes or offlines an independently managed
// homepage, even where title or type overlaps with a data-owned homepage.
type HomepageImportRequest struct {
	Mode            HomepageImportMode
	SourceOwner     string
	SourceReleaseID string
	Inputs          []ImportedHomepageInput
}

type HomepageImportReport struct {
	Mode                  HomepageImportMode `json:"mode"`
	SourceOwner           string             `json:"sourceOwner"`
	Created               []string           `json:"created"`
	Updated               []string           `json:"updated"`
	Offlined              []string           `json:"offlined"`
	Skipped               []string           `json:"skipped"`
	EntityRefToHomepageID map[string]string  `json:"entityRefToHomepageId"`
}

// ReconcileImportedHomepages atomically applies one immutable desired state.
// Upsert only changes declared entities. Sync additionally offlines stale
// homepages owned by the same source owner. It never uses title matching: a
// release source reference is the only safe identity across independent owners.
func (s *HomepageService) ReconcileImportedHomepages(
	ctx context.Context,
	request HomepageImportRequest,
) (HomepageImportReport, error) {
	request.Mode = HomepageImportMode(strings.TrimSpace(string(request.Mode)))
	request.SourceOwner = strings.TrimSpace(request.SourceOwner)
	request.SourceReleaseID = strings.TrimSpace(request.SourceReleaseID)
	if request.Mode != HomepageImportModeUpsert && request.Mode != HomepageImportModeSync {
		return HomepageImportReport{}, fmt.Errorf("unsupported homepage import mode %q", request.Mode)
	}
	if request.SourceOwner == "" || request.SourceReleaseID == "" {
		return HomepageImportReport{}, fmt.Errorf("homepage import source owner and release id are required")
	}
	if err := validateImportedHomepageInputs(request.Inputs); err != nil {
		return HomepageImportReport{}, err
	}

	report := HomepageImportReport{
		Mode:                  request.Mode,
		SourceOwner:           request.SourceOwner,
		Created:               []string{},
		Updated:               []string{},
		Offlined:              []string{},
		Skipped:               []string{},
		EntityRefToHomepageID: map[string]string{},
	}
	emits := make([]ProjectorEvent, 0, len(request.Inputs))
	desiredRefs := make(map[string]struct{}, len(request.Inputs))

	s.mu.Lock()
	now := time.Now().UTC()
	for _, input := range request.Inputs {
		entityRef := strings.TrimSpace(input.EntityRef)
		desiredRefs[entityRef] = struct{}{}
		homepage, found := s.importedHomepageBySourceLocked(request.SourceOwner, entityRef)
		if found {
			applyImportedProjection(homepage, input, request.SourceOwner, request.SourceReleaseID, now)
			report.Updated = append(report.Updated, homepage.ID)
		} else {
			id := s.nextID("homepage")
			homepage = &Homepage{
				ID:                 id,
				Title:              strings.TrimSpace(input.Title),
				HomepageType:       strings.TrimSpace(input.HomepageType),
				CanonicalEntityID:  canonicalEntityIDFromTypeAndTitle(input.HomepageType, input.Title),
				ObjectPageTemplate: objectPageTemplate(input.HomepageType, ""),
				Status:             "published",
				SourceType:         "official_seed",
				ClaimStatus:        "unclaimed",
				City:               strings.TrimSpace(input.City),
				CreatedAt:          now,
				PublishedAt:        &now,
			}
			applyImportedProjection(homepage, input, request.SourceOwner, request.SourceReleaseID, now)
			applyDefaultShellData(homepage)
			s.homepages[id] = homepage
			report.Created = append(report.Created, id)
		}
		report.EntityRefToHomepageID[entityRef] = homepage.ID
		out := cloneHomepage(homepage)
		emits = append(emits, ProjectorEvent{Type: ProjectorEventHomepageUpserted, HomepageID: out.ID, Homepage: &out})
	}
	if request.Mode == HomepageImportModeSync {
		for _, homepage := range s.homepages {
			if homepage.SourceOwner != request.SourceOwner {
				continue
			}
			if _, retained := desiredRefs[strings.TrimSpace(homepage.SourceEntityRef)]; retained {
				continue
			}
			if homepage.Status == "offline" && homepage.SourceReleaseID == request.SourceReleaseID {
				continue
			}
			homepage.Status = "offline"
			homepage.OfflineAt = &now
			homepage.SourceReleaseID = request.SourceReleaseID
			homepage.UpdatedAt = now
			report.Offlined = append(report.Offlined, homepage.ID)
			out := cloneHomepage(homepage)
			emits = append(emits, ProjectorEvent{Type: ProjectorEventHomepageRemoved, HomepageID: out.ID, Homepage: &out})
		}
	}
	err := s.persistLocked(ctx)
	s.mu.Unlock()
	if err != nil {
		return report, err
	}
	for _, event := range emits {
		s.emitSearchIndex(ctx, event)
	}
	sort.Strings(report.Created)
	sort.Strings(report.Updated)
	sort.Strings(report.Offlined)
	return report, nil
}

func validateImportedHomepageInputs(inputs []ImportedHomepageInput) error {
	seen := make(map[string]struct{}, len(inputs))
	for index, input := range inputs {
		ref := strings.TrimSpace(input.EntityRef)
		if ref == "" {
			return fmt.Errorf("homepage import input[%d] has empty entity ref", index)
		}
		if _, duplicate := seen[ref]; duplicate {
			return fmt.Errorf("homepage import has duplicate entity ref %q", ref)
		}
		seen[ref] = struct{}{}
		if err := validateHomepageInput(HomepageInput{
			Title:        strings.TrimSpace(input.Title),
			HomepageType: strings.TrimSpace(input.HomepageType),
		}); err != nil {
			return fmt.Errorf("homepage import input %q is invalid: %w", ref, err)
		}
	}
	return nil
}

func (s *HomepageService) importedHomepageBySourceLocked(sourceOwner string, entityRef string) (*Homepage, bool) {
	for _, homepage := range s.homepages {
		if homepage.SourceOwner == sourceOwner && homepage.SourceEntityRef == entityRef {
			return homepage, true
		}
	}
	return nil, false
}

func applyImportedProjection(
	homepage *Homepage,
	input ImportedHomepageInput,
	sourceOwner string,
	sourceReleaseID string,
	now time.Time,
) {
	homepage.IntroductionMarkdown = strings.TrimSpace(input.IntroductionMarkdown)
	homepage.IntroductionAssets = cloneIntroductionAssets(input.IntroductionAssets)
	if input.PrimarySource != nil {
		source := *input.PrimarySource
		homepage.PrimarySource = &source
	} else {
		homepage.PrimarySource = nil
	}
	homepage.SourceURLs = cloneStrings(input.SourceURLs)
	if len(input.CategoryTags) > 0 {
		homepage.CategoryTags = cloneStrings(input.CategoryTags)
	}
	if strings.TrimSpace(homepage.CoverURL) == "" {
		homepage.CoverURL = coverURLFromIntroductionAssets(homepage.IntroductionAssets)
	}
	if strings.TrimSpace(homepage.City) == "" {
		homepage.City = strings.TrimSpace(input.City)
	}
	homepage.SourceOwner = sourceOwner
	homepage.SourceEntityRef = strings.TrimSpace(input.EntityRef)
	homepage.SourceReleaseID = sourceReleaseID
	homepage.Status = "published"
	homepage.OfflineAt = nil
	if homepage.PublishedAt == nil {
		publishedAt := now
		homepage.PublishedAt = &publishedAt
	}
	homepage.UpdatedAt = now
}
