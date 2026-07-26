// Package ports 定义 TagTaxonomyRelease 对象专属持久化端口。
package ports

import (
	"context"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
)

// ActiveReleaseReader is the narrow cross-object port for consumers that must
// bind reads to the one active taxonomy snapshot.
type ActiveReleaseReader interface {
	ActiveReleaseID(ctx context.Context) (string, bool, error)
}

// SnapshotReadinessReader verifies that a staged node snapshot is complete
// before its release can become active.
type SnapshotReadinessReader interface {
	HasCompleteSnapshot(ctx context.Context, releaseID string, expectedNodeCount int) (bool, error)
}

// Store 是聚合专属 AggregateStore：digest 幂等 Stage 与单 active CAS 切换。
type Store interface {
	ActiveReleaseReader
	FindActive(ctx context.Context) (model.Release, bool, error)
	Load(ctx context.Context, releaseID string) (model.Release, bool, error)
	FindByDigest(ctx context.Context, canonicalDigest string) (model.Release, bool, error)
	// InsertStaged 落不可变 staged 记录；digest 已存在返回 model.ErrDigestConflict，
	// releaseId 已存在返回 model.ErrVersionConflict。
	InsertStaged(ctx context.Context, release model.Release) error
	// ActivateExclusive 在同一事务内：旧 active（如有）retire + 目标 staged→active。
	// 目标或旧 active 的 version CAS 失败返回 model.ErrVersionConflict。
	ActivateExclusive(ctx context.Context, target model.Release, previous *model.Release) error
}
