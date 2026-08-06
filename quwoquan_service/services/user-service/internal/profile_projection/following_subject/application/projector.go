// Package following_subject 承载 FollowingSubject 投影：projector 是唯一
// writer，query facade 是 named reader。投影订阅 PersonaFollowStateChanged
// 与 SubjectFollowStateChanged（circle 域事件随 B4 批次接入）。
package following_subject

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type FollowChangedEvent struct {
	EventID         string
	ViewerPersonaID string
	SubjectType     string
	SubjectID       string
	Following       bool
	OccurredAt      time.Time
	SourceVersion   int64
}

// FollowingSubjectProjector 把已提交的关注事实投影为关注频道行。它被组合进两个 outbox
// relay 的 publisher 链：投影失败会使 relay 不推进 checkpoint 并重试，
// 幂等 upsert（sourceVersion 单调）保证至少一次投递下的收敛。
type FollowingSubjectProjector struct {
	store ProjectionStore
}

func NewFollowingSubjectProjector(store ProjectionStore) *FollowingSubjectProjector {
	if store == nil {
		panic("following subject projection store is required")
	}
	return &FollowingSubjectProjector{store: store}
}

// Apply consumes the object-owned typed projection event. Cross-object outbox
// payloads are translated only in the cmd composition root.
func (p *FollowingSubjectProjector) Apply(ctx context.Context, event FollowChangedEvent) error {
	event.ViewerPersonaID = strings.TrimSpace(event.ViewerPersonaID)
	event.SubjectType = strings.TrimSpace(event.SubjectType)
	event.SubjectID = strings.TrimSpace(event.SubjectID)
	if event.ViewerPersonaID == "" || event.SubjectType == "" ||
		event.SubjectID == "" || event.SourceVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("following subject projector: invalid event %s", event.EventID)
	}
	if event.Following {
		return p.store.UpsertFollow(
			ctx,
			event.ViewerPersonaID,
			event.SubjectType,
			event.SubjectID,
			event.OccurredAt,
			event.SourceVersion,
		)
	}
	return p.store.RemoveFollow(
		ctx,
		event.ViewerPersonaID,
		event.SubjectType,
		event.SubjectID,
		event.SourceVersion,
	)
}
