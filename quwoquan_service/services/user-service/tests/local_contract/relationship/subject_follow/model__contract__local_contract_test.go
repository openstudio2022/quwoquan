// readiness_case: follow-subject-local
// readiness_case: unfollow-subject-local
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
package local_contract

import (
	"errors"
	"testing"
	"time"

	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
)

// TestSubjectFollowCommandRejectsPersonaSubject 固定 metadata 业务规则：
// subjectType 不得为 persona，persona 间关系只能写 PersonaRelationship。
func TestSubjectFollowCommandRejectsPersonaSubject(t *testing.T) {
	t.Parallel()
	for _, subjectType := range []string{"persona", "user", "post", ""} {
		if _, err := sfmodel.NewCommand(
			sfmodel.CommandFollow, "ps_1", subjectType, "subject_1", "", "key",
		); !errors.Is(err, sfmodel.ErrInvalidSubjectType) &&
			!errors.Is(err, sfmodel.ErrInvalidCommand) {
			t.Fatalf("subjectType %q must be rejected, got %v", subjectType, err)
		}
	}
	for _, subjectType := range []string{"homepage", "circle", "location", "HOMEPAGE"} {
		if _, err := sfmodel.NewCommand(
			sfmodel.CommandFollow, "ps_1", subjectType, "subject_1", "", "key",
		); err != nil {
			t.Fatalf("subjectType %q must be accepted, got %v", subjectType, err)
		}
	}
}

// TestSubjectFollowApplyIsSetUnsetStateMachine 固定 set/unset 命名迁移语义：
// 目标状态已满足时不变更、版本不推进；unfollow 不存在的关注是幂等 no-op。
func TestSubjectFollowApplyIsSetUnsetStateMachine(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	follow, _ := sfmodel.NewCommand(sfmodel.CommandFollow, "ps_1", "homepage", "h_1", "", "k1")
	unfollow, _ := sfmodel.NewCommand(sfmodel.CommandUnfollow, "ps_1", "homepage", "h_1", "", "k2")

	created, changed := sfmodel.Apply(sfmodel.SubjectFollow{}, false, follow, now)
	if !changed || created.State != sfmodel.StateFollowing || created.Version != 1 ||
		created.FollowedAt == nil {
		t.Fatalf("first follow must create version 1 following: %+v changed=%v", created, changed)
	}
	replayed, changed := sfmodel.Apply(created, true, follow, now.Add(time.Second))
	if changed || replayed.Version != 1 {
		t.Fatalf("repeated follow must be a no-op: %+v changed=%v", replayed, changed)
	}
	unfollowed, changed := sfmodel.Apply(created, true, unfollow, now.Add(2*time.Second))
	if !changed || unfollowed.State != sfmodel.StateUnfollowed || unfollowed.Version != 2 {
		t.Fatalf("unfollow must advance version: %+v changed=%v", unfollowed, changed)
	}
	missing, changed := sfmodel.Apply(sfmodel.SubjectFollow{}, false, unfollow, now)
	if changed || missing.State != sfmodel.StateUnfollowed {
		t.Fatalf("unfollow of missing aggregate must be a no-op: %+v changed=%v", missing, changed)
	}
	refollow, changed := sfmodel.Apply(unfollowed, true, follow, now.Add(3*time.Second))
	if !changed || refollow.State != sfmodel.StateFollowing || refollow.Version != 3 {
		t.Fatalf("refollow must advance version monotonically: %+v changed=%v", refollow, changed)
	}
}
