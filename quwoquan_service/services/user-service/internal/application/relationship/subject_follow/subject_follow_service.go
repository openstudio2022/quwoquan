// Package subject_follow 是 SubjectFollow 聚合的对象专属 command facade。
// 关注/取关为 set/unset 命名迁移：服务端内部 CAS + 幂等 receipt，公开请求
// 不携带版本字段。
package subject_follow

import (
	"context"
	"errors"

	sfmodel "quwoquan_service/services/user-service/internal/domain/relationship/subject_follow/model"
	sfports "quwoquan_service/services/user-service/internal/domain/relationship/subject_follow/ports"
	generated "quwoquan_service/services/user-service/internal/generated"
)

type SubjectFollowService struct {
	store sfports.SubjectFollowStore
}

func NewSubjectFollowService(store sfports.SubjectFollowStore) *SubjectFollowService {
	if store == nil {
		panic("subject follow store is required")
	}
	return &SubjectFollowService{store: store}
}

type FollowSubjectCommand struct {
	PersonaID      string
	SubjectType    string
	SubjectID      string
	Source         string
	IdempotencyKey string
}

func (s *SubjectFollowService) Follow(
	ctx context.Context,
	command FollowSubjectCommand,
) (sfmodel.MutationResult, error) {
	return s.execute(ctx, sfmodel.CommandFollow, command)
}

func (s *SubjectFollowService) Unfollow(
	ctx context.Context,
	command FollowSubjectCommand,
) (sfmodel.MutationResult, error) {
	return s.execute(ctx, sfmodel.CommandUnfollow, command)
}

func (s *SubjectFollowService) execute(
	ctx context.Context,
	kind string,
	input FollowSubjectCommand,
) (sfmodel.MutationResult, error) {
	command, err := sfmodel.NewCommand(
		kind,
		input.PersonaID,
		input.SubjectType,
		input.SubjectID,
		input.Source,
		input.IdempotencyKey,
	)
	if err != nil {
		if errors.Is(err, sfmodel.ErrInvalidSubjectType) {
			return sfmodel.MutationResult{}, generated.AppErrorFromSubjectFollowInvalidSubjectType(
				"subjectType must be one of homepage/circle/location",
			)
		}
		return sfmodel.MutationResult{}, generated.AppErrorFromInvalidArgument(err.Error())
	}
	result, err := s.store.Apply(ctx, command)
	if err != nil {
		return sfmodel.MutationResult{}, err
	}
	if !result.Changed {
		// 目标状态已满足：no-op receipt 已由 Store 持久化，结果按幂等重放
		// 语义返回，不推进版本、不追加事件。
		result.IdempotentReplay = true
	}
	return result, nil
}

func (s *SubjectFollowService) Get(
	ctx context.Context,
	personaID, subjectType, subjectID string,
) (sfmodel.SubjectFollow, bool, error) {
	return s.store.Get(ctx, personaID, subjectType, subjectID)
}
