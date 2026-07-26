// Package ports 定义 FilterCatalogRelease 对象专属 Store/Reader 边界。
package ports

import (
	"context"
	"time"

	"quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
)

const (
	CommandStageFilterCatalogRelease    = "StageFilterCatalogRelease"
	CommandActivateFilterCatalogRelease = "ActivateFilterCatalogRelease"
	CommandRollbackFilterCatalogRelease = "RollbackFilterCatalogRelease"
)

type CommandResult struct {
	Release  *model.FilterCatalogRelease
	Changed  bool
	Replayed bool
}

type StageCommit struct {
	Release          *model.FilterCatalogRelease
	IdempotencyKey   string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type TransitionCommit struct {
	ReleaseID        string
	IdempotencyKey   string
	CommandDigest    string
	TransitionedAt   time.Time
	ReceiptExpiresAt time.Time
}

// AggregateStore 在真实存储事务内提交聚合状态与 command receipt。
// Activate/Rollback 必须同时切换旧、新 release，调用方不得拆成两个写入。
type AggregateStore interface {
	Load(
		ctx context.Context,
		releaseID string,
	) (*model.FilterCatalogRelease, bool, error)
	Stage(ctx context.Context, commit StageCommit) (CommandResult, error)
	Activate(ctx context.Context, commit TransitionCommit) (CommandResult, error)
	Rollback(ctx context.Context, commit TransitionCommit) (CommandResult, error)
}

// ActiveFilterCatalogReader 只返回完整 active release；staged/retired 不可见。
type ActiveFilterCatalogReader interface {
	GetActive(
		ctx context.Context,
	) (*model.FilterCatalogRelease, bool, error)
}

// ActiveFilterCatalogInvalidator 是事务提交后的缓存失效端口。缓存失败不能改变
// Mongo 已提交事实，但上层会返回结构化依赖失败并允许同 receipt 重试修复。
type ActiveFilterCatalogInvalidator interface {
	InvalidateActive(ctx context.Context) error
}
