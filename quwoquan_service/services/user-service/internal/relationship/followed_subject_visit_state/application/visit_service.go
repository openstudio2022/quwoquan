// Package followed_subject_visit_state 是访问水位对象的 command facade。
// mark-visited 是幂等命名命令：水位单调推进，重复 clientRequestId 重放原
// receipt。FollowedSubjectVisited 与水位在同一事务写入 outbox，投影与
// behavior-service 的消费由 OutboxRelay 承担，命令路径不做提交后投递。
package followed_subject_visit_state

import (
	"context"
	"errors"
	"time"

	generated "quwoquan_service/services/user-service/generated/account/user_account"
	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
	visitports "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/ports"
)

type VisitService struct {
	store visitports.VisitStateStore
}

func NewVisitService(store visitports.VisitStateStore) *VisitService {
	if store == nil {
		panic("followed subject visit store is required")
	}
	return &VisitService{store: store}
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
	return s.store.MarkVisited(ctx, command)
}
