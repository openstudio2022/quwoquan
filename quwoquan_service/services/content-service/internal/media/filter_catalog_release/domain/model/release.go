package model

import (
	"encoding/hex"
	"fmt"
	"time"
)

type Status string

const (
	StatusStaged  Status = "staged"
	StatusActive  Status = "active"
	StatusRetired Status = "retired"
)

type NewStagedParams struct {
	ReleaseID                    string
	SourceOwner                  string
	CanonicalDigest              string
	Categories                   []FilterCategoryDefinition
	Presets                      []FilterPresetDefinition
	RecommendedFallbackPresetIDs []string
	ImportedAt                   time.Time
}

// Snapshot 是聚合在 port 边界上的完整强类型快照。内部字段显式禁止 JSON 暴露，
// transport 必须投影为 application.FilterCatalogSlice。
type Snapshot struct {
	ReleaseID                    string                     `json:"releaseId"`
	Version                      int64                      `json:"-"`
	SourceOwner                  string                     `json:"-"`
	CanonicalDigest              string                     `json:"canonicalDigest"`
	Status                       Status                     `json:"status"`
	CategoryCount                int                        `json:"categoryCount"`
	PresetCount                  int                        `json:"presetCount"`
	Categories                   []FilterCategoryDefinition `json:"categories"`
	Presets                      []FilterPresetDefinition   `json:"presets"`
	RecommendedFallbackPresetIDs []string                   `json:"recommendedFallbackPresetIds"`
	ImportedAt                   time.Time                  `json:"importedAt"`
	ActivatedAt                  *time.Time                 `json:"activatedAt"`
}

// FilterCatalogRelease 是一次不可变目录发布。只有状态、version 与 activatedAt
// 可经聚合行为演进；目录内容没有修改行为。
type FilterCatalogRelease struct {
	releaseID                    string
	version                      int64
	sourceOwner                  string
	canonicalDigest              string
	status                       Status
	categories                   []FilterCategoryDefinition
	presets                      []FilterPresetDefinition
	recommendedFallbackPresetIDs []string
	importedAt                   time.Time
	activatedAt                  *time.Time
}

func NewStaged(params NewStagedParams) (*FilterCatalogRelease, error) {
	releaseID := params.ReleaseID
	sourceOwner := params.SourceOwner
	if !validCanonicalText(releaseID) ||
		!validCanonicalText(sourceOwner) ||
		params.ImportedAt.IsZero() {
		return nil, fmt.Errorf(
			"%w: releaseId, sourceOwner and importedAt must be canonical",
			ErrInvalidArgument,
		)
	}
	payload, err := normalizeAndValidateCatalog(
		params.Categories,
		params.Presets,
		params.RecommendedFallbackPresetIDs,
	)
	if err != nil {
		return nil, err
	}
	computedDigest, err := ComputeCanonicalDigest(
		payload.Categories,
		payload.Presets,
		payload.RecommendedFallbackPresetIDs,
	)
	if err != nil {
		return nil, err
	}
	suppliedDigest := params.CanonicalDigest
	if !validSHA256(suppliedDigest) || suppliedDigest != computedDigest {
		return nil, fmt.Errorf(
			"%w: supplied=%q computed=%q",
			ErrDigestMismatch,
			suppliedDigest,
			computedDigest,
		)
	}
	return &FilterCatalogRelease{
		releaseID:                    releaseID,
		version:                      1,
		sourceOwner:                  sourceOwner,
		canonicalDigest:              computedDigest,
		status:                       StatusStaged,
		categories:                   cloneCategories(payload.Categories),
		presets:                      clonePresets(payload.Presets),
		recommendedFallbackPresetIDs: cloneStrings(payload.RecommendedFallbackPresetIDs),
		importedAt:                   normalizeTime(params.ImportedAt),
	}, nil
}

// Restore 从持久化快照恢复聚合并重新执行全部目录不变量与 digest 校验。
func Restore(snapshot Snapshot) (*FilterCatalogRelease, error) {
	if snapshot.Version < 1 {
		return nil, fmt.Errorf("%w: version must be positive", ErrInvalidArgument)
	}
	switch snapshot.Status {
	case StatusStaged:
		if snapshot.ActivatedAt != nil {
			return nil, fmt.Errorf(
				"%w: staged release cannot have activatedAt",
				ErrInvalidArgument,
			)
		}
	case StatusActive, StatusRetired:
		if snapshot.ActivatedAt == nil || snapshot.ActivatedAt.IsZero() {
			return nil, fmt.Errorf(
				"%w: active or retired release requires activatedAt",
				ErrInvalidArgument,
			)
		}
	default:
		return nil, fmt.Errorf("%w: unsupported status %q", ErrInvalidArgument, snapshot.Status)
	}
	release, err := NewStaged(NewStagedParams{
		ReleaseID:                    snapshot.ReleaseID,
		SourceOwner:                  snapshot.SourceOwner,
		CanonicalDigest:              snapshot.CanonicalDigest,
		Categories:                   snapshot.Categories,
		Presets:                      snapshot.Presets,
		RecommendedFallbackPresetIDs: snapshot.RecommendedFallbackPresetIDs,
		ImportedAt:                   snapshot.ImportedAt,
	})
	if err != nil {
		return nil, err
	}
	if snapshot.CategoryCount != len(release.categories) ||
		snapshot.PresetCount != len(release.presets) {
		return nil, fmt.Errorf(
			"%w: persisted category or preset count drift",
			ErrInvalidArgument,
		)
	}
	release.version = snapshot.Version
	release.status = snapshot.Status
	release.activatedAt = cloneTime(snapshot.ActivatedAt)
	return release, nil
}

func (release *FilterCatalogRelease) Activate(now time.Time) error {
	if release == nil || release.status != StatusStaged || now.IsZero() {
		return ErrInvalidTransition
	}
	release.status = StatusActive
	release.version++
	activatedAt := normalizeTime(now)
	release.activatedAt = &activatedAt
	return nil
}

func (release *FilterCatalogRelease) Retire() error {
	if release == nil || release.status != StatusActive {
		return ErrInvalidTransition
	}
	release.status = StatusRetired
	release.version++
	return nil
}

func (release *FilterCatalogRelease) Rollback(now time.Time) error {
	if release == nil || release.status != StatusRetired || now.IsZero() {
		return ErrInvalidTransition
	}
	release.status = StatusActive
	release.version++
	activatedAt := normalizeTime(now)
	release.activatedAt = &activatedAt
	return nil
}

func (release *FilterCatalogRelease) ID() string {
	if release == nil {
		return ""
	}
	return release.releaseID
}

func (release *FilterCatalogRelease) Version() int64 {
	if release == nil {
		return 0
	}
	return release.version
}

func (release *FilterCatalogRelease) Status() Status {
	if release == nil {
		return ""
	}
	return release.status
}

func (release *FilterCatalogRelease) CanonicalDigest() string {
	if release == nil {
		return ""
	}
	return release.canonicalDigest
}

func (release *FilterCatalogRelease) Snapshot() Snapshot {
	if release == nil {
		return Snapshot{}
	}
	return Snapshot{
		ReleaseID:                    release.releaseID,
		Version:                      release.version,
		SourceOwner:                  release.sourceOwner,
		CanonicalDigest:              release.canonicalDigest,
		Status:                       release.status,
		CategoryCount:                len(release.categories),
		PresetCount:                  len(release.presets),
		Categories:                   cloneCategories(release.categories),
		Presets:                      clonePresets(release.presets),
		RecommendedFallbackPresetIDs: cloneStrings(release.recommendedFallbackPresetIDs),
		ImportedAt:                   release.importedAt,
		ActivatedAt:                  cloneTime(release.activatedAt),
	}
}

func validSHA256(value string) bool {
	if len(value) != sha256HexLength {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == sha256ByteLength
}

const (
	sha256ByteLength = 32
	sha256HexLength  = sha256ByteLength * 2
)

func cloneCategories(source []FilterCategoryDefinition) []FilterCategoryDefinition {
	cloned := make([]FilterCategoryDefinition, len(source))
	for index, category := range source {
		category.DisplayNameEn = cloneString(category.DisplayNameEn)
		cloned[index] = category
	}
	return cloned
}

func clonePresets(source []FilterPresetDefinition) []FilterPresetDefinition {
	cloned := make([]FilterPresetDefinition, len(source))
	for index, preset := range source {
		preset.DisplayNameEn = cloneString(preset.DisplayNameEn)
		cloned[index] = preset
	}
	return cloned
}

func cloneString(value *string) *string {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}

func cloneStrings(source []string) []string {
	if source == nil {
		return nil
	}
	cloned := make([]string, len(source))
	copy(cloned, source)
	return cloned
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := normalizeTime(*value)
	return &cloned
}

func normalizeTime(value time.Time) time.Time {
	return value.UTC().Truncate(time.Millisecond)
}
