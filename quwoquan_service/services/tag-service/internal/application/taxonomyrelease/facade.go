// Package taxonomyrelease 是 TagTaxonomyRelease 的命令门面：
// Stage 以 canonicalDigest 唯一约束承载幂等；Activate 做单 active 内部 CAS
// 切换并对纯竞态有限重放；目标已 active 时按 no-op 重放安全返回。
package taxonomyrelease

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/tag-service/internal/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/domain/taxonomyrelease/ports"
)

const maxAttempts = 3

type Facade struct {
	store ports.Store
	now   func() time.Time
}

func NewFacade(store ports.Store) (*Facade, error) {
	if store == nil {
		return nil, errors.New("taxonomy release store is required")
	}
	return &Facade{store: store, now: time.Now}, nil
}

type StageCommand struct {
	ReleaseID       string
	SourceOwner     string
	CanonicalDigest string
	NodeCount       int
}

// Stage 落不可变 staged 记录。同 canonicalDigest 重复 Stage 幂等返回首次记录。
func (f *Facade) Stage(ctx context.Context, command StageCommand) (model.Release, error) {
	release, err := model.NewStaged(
		command.ReleaseID, command.SourceOwner,
		command.CanonicalDigest, command.NodeCount, f.now())
	if err != nil {
		return model.Release{}, err
	}
	if existing, found, findErr := f.store.FindByDigest(ctx, release.CanonicalDigest); findErr != nil {
		return model.Release{}, findErr
	} else if found {
		return existing, nil
	}
	insertErr := f.store.InsertStaged(ctx, release)
	if insertErr == nil {
		return release, nil
	}
	if errors.Is(insertErr, model.ErrDigestConflict) {
		existing, found, findErr := f.store.FindByDigest(ctx, release.CanonicalDigest)
		if findErr != nil {
			return model.Release{}, findErr
		}
		if found {
			return existing, nil
		}
	}
	return model.Release{}, insertErr
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
		// 目标已 active：no-op 重放安全（不递增版本）。
		if target.Status == model.StatusActive {
			return target, nil
		}
		if activateErr := target.Activate(f.now()); activateErr != nil {
			return model.Release{}, activateErr
		}
		var previous *model.Release
		if current, activeFound, activeErr := f.store.FindActive(ctx); activeErr != nil {
			return model.Release{}, activeErr
		} else if activeFound {
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
