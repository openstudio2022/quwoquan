// Package model 定义 TagTaxonomyRelease 聚合：一次不可变标签分类发布。
// releaseId/canonicalDigest/nodeCount 创建后不可变；同一 taxonomy 只能有一个
// active release；幂等由 canonicalDigest 唯一约束承载（aggregate.yaml
// idempotency: import_receipt 的落地形态——digest 即导入回执身份）。
package model

import (
	"errors"
	"strings"
	"time"
)

type Status string

const (
	StatusStaged   Status = "staged"
	StatusActive   Status = "active"
	StatusRetired  Status = "retired"
	StatusRejected Status = "rejected"
)

var (
	ErrInvalidArgument   = errors.New("tag taxonomy release invalid argument")
	ErrNotFound          = errors.New("tag taxonomy release not found")
	ErrInvalidTransition = errors.New("tag taxonomy release invalid transition")
	ErrVersionConflict   = errors.New("tag taxonomy release version conflict")
	ErrDigestConflict    = errors.New("tag taxonomy release digest conflict")
)

// Release 是聚合文档。
type Release struct {
	ReleaseID       string     `bson:"_id" json:"releaseId"`
	SourceOwner     string     `bson:"sourceOwner" json:"-"`
	CanonicalDigest string     `bson:"canonicalDigest" json:"-"`
	NodeCount       int        `bson:"nodeCount" json:"nodeCount"`
	Status          Status     `bson:"status" json:"status"`
	Version         int64      `bson:"version" json:"-"`
	ImportedAt      time.Time  `bson:"importedAt" json:"importedAt"`
	ActivatedAt     *time.Time `bson:"activatedAt,omitempty" json:"activatedAt,omitempty"`
}

// NewStaged 构造 staged release（首次 Stage）。
func NewStaged(releaseID, sourceOwner, canonicalDigest string, nodeCount int, now time.Time) (Release, error) {
	releaseID = strings.TrimSpace(releaseID)
	sourceOwner = strings.TrimSpace(sourceOwner)
	canonicalDigest = strings.TrimSpace(canonicalDigest)
	if releaseID == "" || len(releaseID) > 96 ||
		sourceOwner == "" || canonicalDigest == "" || nodeCount <= 0 {
		return Release{}, ErrInvalidArgument
	}
	return Release{
		ReleaseID:       releaseID,
		SourceOwner:     sourceOwner,
		CanonicalDigest: canonicalDigest,
		NodeCount:       nodeCount,
		Status:          StatusStaged,
		Version:         1,
		ImportedAt:      now.UTC(),
	}, nil
}

// Activate 从 staged 迁移到 active；其它状态返回 ErrInvalidTransition
// （already active 由调用方按 no-op 重放处理，不进入本行为）。
func (r *Release) Activate(now time.Time) error {
	if r.Status != StatusStaged {
		return ErrInvalidTransition
	}
	r.Status = StatusActive
	r.Version++
	activatedAt := now.UTC()
	r.ActivatedAt = &activatedAt
	return nil
}

// Retire 把当前 active release 让位给新激活的版本。
func (r *Release) Retire() error {
	if r.Status != StatusActive {
		return ErrInvalidTransition
	}
	r.Status = StatusRetired
	r.Version++
	return nil
}
