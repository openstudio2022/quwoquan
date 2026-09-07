package homepage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

const HomepageReleaseCandidateReceiptSchema = "quwoquan.homepage_release_candidate_receipt"

var releaseSHA256Pattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type ReleaseIdentity = homepageports.ReleaseIdentity
type ReleaseProjection = homepageports.ReleaseProjection
type ReleaseCandidateState = homepageports.ReleaseCandidateState

type ReleaseStageRequest struct {
	Identity homepageports.ReleaseIdentity
	Inputs   []ImportedInput
}

type ReleaseStageReport struct {
	Identity               homepageports.ReleaseIdentity `json:"identity"`
	ProjectionVersion      int64                         `json:"projectionVersion"`
	ClosureDigest          string                        `json:"closureDigest"`
	ExpectedCount          int                           `json:"expectedCount"`
	ProjectedCount         int                           `json:"projectedCount"`
	EntityRefToHomepageID  map[string]string             `json:"entityRefToHomepageId"`
	EntityRefMappingDigest string                        `json:"entityRefMappingDigest"`
	Replayed               bool                          `json:"replayed"`
	VerifiedAt             time.Time                     `json:"verifiedAt"`
}

type HomepageReleaseCandidateReceiptIdentity struct {
	Environment    string `json:"environment"`
	SourceOwner    string `json:"sourceOwner"`
	ReleaseID      string `json:"releaseId"`
	ManifestDigest string `json:"manifestDigest"`
}

type HomepageReleaseCandidateReceiptCounts struct {
	Expected  int `json:"expected"`
	Projected int `json:"projected"`
}

type HomepageReleaseCandidateReceipt struct {
	Schema                 string                                  `json:"schema"`
	Status                 string                                  `json:"status"`
	Identity               HomepageReleaseCandidateReceiptIdentity `json:"identity"`
	ProjectionVersion      int64                                   `json:"projectionVersion,omitempty"`
	VerifiedAt             *time.Time                              `json:"verifiedAt,omitempty"`
	ClosureDigest          string                                  `json:"closureDigest,omitempty"`
	Counts                 *HomepageReleaseCandidateReceiptCounts  `json:"counts,omitempty"`
	EntityRefMappingDigest string                                  `json:"entityRefMappingDigest,omitempty"`
}

func NormalizeReleaseIdentity(identity homepageports.ReleaseIdentity) (homepageports.ReleaseIdentity, error) {
	identity.Environment = strings.TrimSpace(identity.Environment)
	identity.SourceOwner = strings.TrimSpace(identity.SourceOwner)
	identity.ReleaseID = strings.TrimSpace(identity.ReleaseID)
	identity.ManifestDigest = strings.TrimSpace(identity.ManifestDigest)
	if identity.Environment == "" || identity.SourceOwner == "" || identity.ReleaseID == "" ||
		!releaseSHA256Pattern.MatchString(identity.ManifestDigest) {
		return homepageports.ReleaseIdentity{}, fmt.Errorf("homepage release identity is incomplete or non-canonical")
	}
	return identity, nil
}

func StageReleaseCandidate(
	ctx context.Context,
	store homepageports.ReleaseProjectionStore,
	request ReleaseStageRequest,
	now time.Time,
) (ReleaseStageReport, error) {
	if store == nil {
		return ReleaseStageReport{}, fmt.Errorf("homepage release projection store is required")
	}
	identity, err := NormalizeReleaseIdentity(request.Identity)
	if err != nil {
		return ReleaseStageReport{}, err
	}
	if identity.SourceOwner != "qwq_data" {
		return ReleaseStageReport{}, fmt.Errorf("homepage release source owner must be qwq_data")
	}
	if err := validateImportedInputs(request.Inputs); err != nil {
		return ReleaseStageReport{}, err
	}
	if now.IsZero() {
		return ReleaseStageReport{}, fmt.Errorf("homepage release verifiedAt is required")
	}
	now = now.UTC()
	inputs := append([]ImportedInput(nil), request.Inputs...)
	sort.Slice(inputs, func(i, j int) bool {
		return strings.TrimSpace(inputs[i].EntityRef) < strings.TrimSpace(inputs[j].EntityRef)
	})
	mapping := make(map[string]string, len(inputs))
	projections := make([]homepageports.ReleaseProjection, 0, len(inputs))
	for _, input := range inputs {
		entityRef := strings.TrimSpace(input.EntityRef)
		homepageID := homepagemodel.StableID(
			homepagemodel.CanonicalEntityID(input.HomepageType, input.Title),
			identity.SourceOwner, entityRef, input.HomepageType, input.Title,
		)
		projection := homepageports.ReleaseProjection{
			Identity: identity, HomepageID: homepageID, EntityRef: entityRef,
			Title: strings.TrimSpace(input.Title), HomepageType: strings.TrimSpace(input.HomepageType),
			City: strings.TrimSpace(input.City), Location: cloneGeo(input.Location),
			CategoryTags:         cloneStrings(input.CategoryTags),
			IntroductionMarkdown: strings.TrimSpace(input.IntroductionMarkdown),
			IntroductionAssets:   append([]homepagemodel.IntroductionAsset(nil), input.IntroductionAssets...),
			StructuredFacts:      input.StructuredFacts.Clone(), PrimarySource: cloneSource(input.PrimarySource),
			SourceURLs: cloneStrings(input.SourceURLs), VerifiedAt: now,
		}
		projection.CoverURL, _, _ = releaseCoverBinding(projection.IntroductionAssets)
		projection.DocumentDigest, err = releaseDocumentDigest(projection)
		if err != nil {
			return ReleaseStageReport{}, err
		}
		mapping[entityRef] = homepageID
		projections = append(projections, projection)
	}
	closureDigest, err := releaseClosureDigest(projections)
	if err != nil {
		return ReleaseStageReport{}, err
	}
	mappingDigest, err := releaseMappingDigest(mapping)
	if err != nil {
		return ReleaseStageReport{}, err
	}
	projectionVersion := releaseProjectionVersion(identity, closureDigest)
	for index := range projections {
		projections[index].ProjectionVersion = projectionVersion
		projections[index].ClosureDigest = closureDigest
		projections[index].VerifiedAt = now
	}
	state := homepageports.ReleaseCandidateState{
		Identity: identity, ProjectionVersion: projectionVersion, VerifiedAt: now,
		ClosureDigest: closureDigest, ExpectedCount: len(inputs), ProjectedCount: len(projections),
		EntityRefMappingDigest: mappingDigest,
	}
	replayed, err := store.StageReleaseCandidate(ctx, state, projections)
	if err != nil {
		return ReleaseStageReport{}, err
	}
	if shells, ok := store.(homepageports.ReleaseShellStore); ok {
		if err := shells.EnsureReleaseShells(ctx, projections); err != nil {
			return ReleaseStageReport{}, err
		}
	}
	reportVerifiedAt := now
	if replayed {
		stored, found, readErr := store.ReadVerifiedReleaseCandidate(ctx, identity)
		if readErr != nil || !found {
			return ReleaseStageReport{}, fmt.Errorf("read back replayed homepage release candidate: %w", readErr)
		}
		reportVerifiedAt = stored.VerifiedAt.UTC()
	}
	return ReleaseStageReport{
		Identity: identity, ProjectionVersion: projectionVersion, ClosureDigest: closureDigest,
		ExpectedCount: len(inputs), ProjectedCount: len(projections),
		EntityRefToHomepageID: mapping, EntityRefMappingDigest: mappingDigest,
		Replayed: replayed, VerifiedAt: reportVerifiedAt,
	}, nil
}

func QueryReleaseCandidate(
	ctx context.Context,
	store homepageports.ReleaseProjectionStore,
	identity homepageports.ReleaseIdentity,
) (HomepageReleaseCandidateReceipt, error) {
	if store == nil {
		return HomepageReleaseCandidateReceipt{}, fmt.Errorf("homepage release projection store is required")
	}
	identity, err := NormalizeReleaseIdentity(identity)
	if err != nil {
		return HomepageReleaseCandidateReceipt{}, err
	}
	receipt := HomepageReleaseCandidateReceipt{
		Schema: HomepageReleaseCandidateReceiptSchema, Status: "not_found",
		Identity: receiptIdentity(identity),
	}
	state, found, err := store.ReadVerifiedReleaseCandidate(ctx, identity)
	if err != nil {
		return HomepageReleaseCandidateReceipt{}, err
	}
	if !found {
		return receipt, nil
	}
	verifiedAt := state.VerifiedAt.UTC()
	receipt.Status = "found"
	receipt.ProjectionVersion = state.ProjectionVersion
	receipt.VerifiedAt = &verifiedAt
	receipt.ClosureDigest = state.ClosureDigest
	receipt.Counts = &HomepageReleaseCandidateReceiptCounts{
		Expected: state.ExpectedCount, Projected: state.ProjectedCount,
	}
	receipt.EntityRefMappingDigest = state.EntityRefMappingDigest
	return receipt, nil
}

func ViewFromReleaseProjection(projection homepageports.ReleaseProjection) View {
	publishedAt := projection.VerifiedAt.UTC()
	view := View{
		ID: projection.HomepageID, Title: projection.Title, HomepageType: projection.HomepageType,
		CanonicalEntityID:  homepagemodel.CanonicalEntityID(projection.HomepageType, projection.Title),
		LookupAliases:      []string{projection.HomepageID, projection.EntityRef},
		ObjectPageTemplate: homepagemodel.ObjectPageTemplate(projection.HomepageType, ""),
		Status:             string(homepagemodel.StatusPublished), SourceType: "official_seed",
		SourceOwner: projection.Identity.SourceOwner, SourceEntityRef: projection.EntityRef,
		SourceReleaseID: projection.Identity.ReleaseID, ClaimStatus: "unclaimed",
		CreatedAt: projection.VerifiedAt.UTC(), UpdatedAt: projection.VerifiedAt.UTC(),
		PublishedAt: &publishedAt, ContentPreview: []ContentPreview{},
		QuestionPreview: []QuestionPreview{}, RelatedGroups: []RelatedGroup{},
		RelationEdges: []json.RawMessage{}, SourceURLs: []string{},
	}
	return ApplyExactReleaseProjection(view, projection)
}

func ApplyExactReleaseProjection(view View, projection homepageports.ReleaseProjection) View {
	// Release-owned fields follow the Content fence. Claim/owner and other
	// governance overlays remain sourced from the stable Homepage aggregate.
	view.ID = projection.HomepageID
	view.HomepageType = projection.HomepageType
	view.SourceOwner = projection.Identity.SourceOwner
	view.SourceEntityRef = projection.EntityRef
	view.SourceReleaseID = projection.Identity.ReleaseID
	if view.ClaimStatus != "claimed" {
		view.Title = projection.Title
		view.CategoryTags = cloneStrings(projection.CategoryTags)
		view.CoverURL = projection.CoverURL
		view.CoverAssetID, view.CoverAccessMode = detailCoverBinding(projection.CoverURL, projection.IntroductionAssets)
		view.City = projection.City
		view.Location = cloneGeo(projection.Location)
	}
	view.IntroductionMarkdown = projection.IntroductionMarkdown
	view.IntroductionAssets = append([]IntroductionAsset(nil), projection.IntroductionAssets...)
	view.StructuredFacts = projection.StructuredFacts.Clone()
	view.PrimarySource = cloneSource(projection.PrimarySource)
	view.SourceURLs = emptyStringsIfNil(projection.SourceURLs)
	view.UpdatedAt = projection.VerifiedAt.UTC()
	return view
}

func receiptIdentity(identity homepageports.ReleaseIdentity) HomepageReleaseCandidateReceiptIdentity {
	return HomepageReleaseCandidateReceiptIdentity{
		Environment: identity.Environment, SourceOwner: identity.SourceOwner,
		ReleaseID: identity.ReleaseID, ManifestDigest: identity.ManifestDigest,
	}
}

func releaseProjectionVersion(identity homepageports.ReleaseIdentity, closureDigest string) int64 {
	sum := sha256.Sum256([]byte(identity.Environment + "\x00" + identity.SourceOwner + "\x00" + identity.ReleaseID + "\x00" + identity.ManifestDigest + "\x00" + closureDigest))
	value := int64(0)
	for _, item := range sum[:8] {
		value = (value << 8) | int64(item)
	}
	value &= int64(^uint64(0) >> 1)
	if value == 0 {
		return 1
	}
	return value
}

func releaseDocumentDigest(projection homepageports.ReleaseProjection) (string, error) {
	copy := projection
	copy.ProjectionVersion = 0
	copy.ClosureDigest = ""
	copy.DocumentDigest = ""
	copy.VerifiedAt = time.Time{}
	return canonicalDigest(copy)
}

func releaseClosureDigest(projections []homepageports.ReleaseProjection) (string, error) {
	type closureEntry struct {
		EntityRef      string `json:"entityRef"`
		HomepageID     string `json:"homepageId"`
		DocumentDigest string `json:"documentDigest"`
	}
	entries := make([]closureEntry, 0, len(projections))
	for _, projection := range projections {
		entries = append(entries, closureEntry{
			EntityRef: projection.EntityRef, HomepageID: projection.HomepageID,
			DocumentDigest: projection.DocumentDigest,
		})
	}
	return canonicalDigest(entries)
}

func releaseMappingDigest(mapping map[string]string) (string, error) {
	type entry struct {
		EntityRef  string `json:"entityRef"`
		HomepageID string `json:"homepageId"`
	}
	keys := make([]string, 0, len(mapping))
	for key := range mapping {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	entries := make([]entry, 0, len(keys))
	for _, key := range keys {
		entries = append(entries, entry{EntityRef: key, HomepageID: mapping[key]})
	}
	return canonicalDigest(entries)
}

func canonicalDigest(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", fmt.Errorf("encode homepage release closure: %w", err)
	}
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func releaseCoverBinding(assets []homepagemodel.IntroductionAsset) (string, string, string) {
	for _, asset := range assets {
		if strings.TrimSpace(asset.Role) == "cover" && strings.TrimSpace(asset.URL) != "" {
			return strings.TrimSpace(asset.URL), strings.TrimSpace(asset.AssetID), strings.TrimSpace(asset.AccessMode)
		}
	}
	return "", "", ""
}
