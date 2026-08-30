// Package taxonomyrelease 是 TagTaxonomyRelease 的命令门面：
// Stage 以 releaseId 绑定完整 immutable intent 承载幂等；不同 releaseId 可以引用同一 canonicalDigest；
// Activate 做单 active 内部 CAS 切换并对纯竞态有限重放；目标已 active 时按 no-op 重放安全返回。
package taxonomyrelease

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/ports"
)

const maxAttempts = 3

type Facade struct {
	store     ports.Store
	snapshots ports.SnapshotReadinessReader
	now       func() time.Time
}

func NewFacade(store ports.Store, snapshots ports.SnapshotReadinessReader) (*Facade, error) {
	if store == nil {
		return nil, errors.New("taxonomy release store is required")
	}
	if snapshots == nil {
		return nil, errors.New("taxonomy snapshot readiness reader is required")
	}
	return &Facade{store: store, snapshots: snapshots, now: time.Now}, nil
}

type StageCommand struct {
	ReleaseID       string
	SourceOwner     string
	CanonicalDigest string
	ReleaseKind     model.ReleaseKind
	NodeCount       int
}

// Stage 落不可变 staged 记录。同 releaseId 只有完整相同的导入意图可重放；
// 不同 releaseId 可引用同一 canonicalDigest，同 releaseId 的任一 intent 字段漂移必须显式冲突。
func (f *Facade) Stage(ctx context.Context, command StageCommand) (model.Release, error) {
	release, err := model.NewStaged(
		command.ReleaseID, command.SourceOwner,
		command.CanonicalDigest, command.ReleaseKind, command.NodeCount, f.now())
	if err != nil {
		return model.Release{}, err
	}
	if existing, found, loadErr := f.store.Load(ctx, release.ReleaseID); loadErr != nil {
		return model.Release{}, loadErr
	} else if found {
		return resolveStageReplay(existing, release)
	}
	insertErr := f.store.InsertStaged(ctx, release)
	if insertErr == nil {
		return release, nil
	}
	if errors.Is(insertErr, model.ErrVersionConflict) {
		existing, found, loadErr := f.store.Load(ctx, release.ReleaseID)
		if loadErr != nil {
			return model.Release{}, loadErr
		}
		if found {
			return resolveStageReplay(existing, release)
		}
	}
	return model.Release{}, insertErr
}

func resolveStageReplay(existing, requested model.Release) (model.Release, error) {
	if existing.ReleaseID != requested.ReleaseID ||
		existing.SourceOwner != requested.SourceOwner ||
		existing.CanonicalDigest != requested.CanonicalDigest ||
		existing.ReleaseKind != requested.ReleaseKind ||
		existing.NodeCount != requested.NodeCount {
		return model.Release{}, model.ErrDigestConflict
	}
	return existing, nil
}

// Activate 激活 staged release：旧 active retire + 目标 active，同一事务提交。
func (f *Facade) Activate(ctx context.Context, releaseID string) (model.Release, error) {
	releaseID = strings.TrimSpace(releaseID)
	if releaseID == "" {
		return model.Release{}, model.ErrInvalidArgument
	}
	for attempt := 0; attempt < maxAttempts; attempt++ {
		target, found, err := f.store.Load(ctx, releaseID)
		if err != nil {
			return model.Release{}, err
		}
		if !found {
			return model.Release{}, model.ErrNotFound
		}
		current, activeFound, activeErr := f.store.FindActive(ctx)
		if activeErr != nil {
			return model.Release{}, activeErr
		}
		// 目标已 active：no-op 重放安全（不递增版本）。
		if target.Status == model.StatusActive {
			if !activeFound || current.ReleaseID != target.ReleaseID {
				return model.Release{}, model.ErrActiveReleaseDrift
			}
			return target, nil
		}
		complete, readinessErr := f.snapshots.HasCompleteSnapshot(ctx, target.ReleaseID, target.NodeCount)
		if readinessErr != nil {
			return model.Release{}, readinessErr
		}
		if !complete {
			return model.Release{}, model.ErrSnapshotIncomplete
		}
		if activateErr := target.Activate(f.now()); activateErr != nil {
			return model.Release{}, activateErr
		}
		var previous *model.Release
		if activeFound {
			if retireErr := current.Retire(); retireErr != nil {
				return model.Release{}, retireErr
			}
			previous = &current
		}
		commitErr := f.store.ActivateExclusive(ctx, target, previous)
		if commitErr == nil {
			return target, nil
		}
		if !errors.Is(commitErr, model.ErrVersionConflict) || attempt == maxAttempts-1 {
			return model.Release{}, commitErr
		}
	}
	panic("unreachable taxonomy release activate retry")
}
