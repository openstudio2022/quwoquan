// Package followed_subject_visit_state 是访问水位对象的 command facade。
// mark-visited 是幂等命名命令：水位单调推进，重复 clientRequestId 重放原
// receipt；成功后同步清除 following_subjects 投影的未读计数。
package followed_subject_visit_state

import (
	"context"
	"errors"
	"log/slog"
	"time"

	generated "quwoquan_service/services/user-service/generated/account/user_account"
	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
)

// VisitStateStore 持久化水位；实现为 Mongo upsert（store_commit 并发语义）。
type VisitStateStore interface {
	MarkVisited(ctx context.Context, command visitmodel.MarkVisitedCommand) (visitmodel.VisitResult, error)
}

// VisitProjectionApplier 把已提交的访问事实应用到 following_subjects 投影。
type VisitProjectionApplier interface {
	ApplyVisit(ctx context.Context, personaID, subjectType, subjectID string, visitedAt time.Time) error
}

type VisitService struct {
	store      VisitStateStore
	projection VisitProjectionApplier
}

func NewVisitService(store VisitStateStore, projection VisitProjectionApplier) *VisitService {
	if store == nil {
		panic("followed subject visit store is required")
	}
	return &VisitService{store: store, projection: projection}
}

type MarkVisitedInput struct {
	PersonaID       string
	SubjectType     string
	SubjectID       string
	VisitedAt       time.Time
	ClientRequestID string
}

func (s *VisitService) MarkVisited(
	ctx context.Context,
	input MarkVisitedInput,
) (visitmodel.VisitResult, error) {
	command, err := visitmodel.NewMarkVisitedCommand(
		input.PersonaID,
		input.SubjectType,
		input.SubjectID,
		input.VisitedAt,
		input.ClientRequestID,
	)
	if err != nil {
		if errors.Is(err, visitmodel.ErrInvalidCommand) {
			return visitmodel.VisitResult{}, generated.AppErrorFromInvalidArgument(
				"personaId, subjectType, subjectId and clientRequestId are required",
			)
		}
		return visitmodel.VisitResult{}, err
	}
	result, err := s.store.MarkVisited(ctx, command)
	if err != nil {
		return visitmodel.VisitResult{}, err
	}
	if s.projection != nil && !result.Replayed {
		// 投影是可重建读模型：水位真相已提交，投影失败只结构化告警，
		// 下一次 mark-visited 或重建会收敛。
		if err := s.projection.ApplyVisit(
			ctx,
			command.PersonaID,
			command.SubjectType,
			command.SubjectID,
			result.LastVisitedAt,
		); err != nil {
			slog.ErrorContext(ctx, "followed subject visit projection apply failed",
				"subjectType", command.SubjectType, "err", err)
		}
	}
	return result, nil
}
