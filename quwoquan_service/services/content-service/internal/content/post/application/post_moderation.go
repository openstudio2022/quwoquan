package post

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postevent "quwoquan_service/services/content-service/generated/content/post/contract/event"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	moderationports "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/ports"
)

const (
	postModerationDecisionEventType = "content.post_moderation_case.decided"
	postModerationCASMaxAttempts    = 3
)

type ApplyPostModerationDecisionCommand struct {
	EventID       string
	CaseID        string
	CaseVersion   int64
	PostID        string
	PostVersion   int64
	ContentDigest string
	ReviewerID    string
	Status        string
	DecidedAt     time.Time
}

type ApplyPostModerationDecisionResult struct {
	PostID           string
	CommittedVersion int64
	ModerationStatus string
	Applied          bool
	Stale            bool
}

// PostModerationDecisionCommandFacet 是 Post 对象接收审核决定的内部命令面。
// 它不暴露 HTTP operation/If-Match；PostService 在内部装载版本并最多执行三次 CAS。
type PostModerationDecisionCommandFacet interface {
	ApplyPostModerationDecision(
		context.Context,
		ApplyPostModerationDecisionCommand,
	) (ApplyPostModerationDecisionResult, error)
}

func (s *PostService) ApplyPostModerationDecision(
	ctx context.Context,
	command ApplyPostModerationDecisionCommand,
) (ApplyPostModerationDecisionResult, error) {
	command.EventID = strings.TrimSpace(command.EventID)
	command.CaseID = strings.TrimSpace(command.CaseID)
	command.PostID = strings.TrimSpace(command.PostID)
	command.ContentDigest = strings.TrimSpace(command.ContentDigest)
	command.ReviewerID = strings.TrimSpace(command.ReviewerID)
	command.Status = strings.ToLower(strings.TrimSpace(command.Status))
	command.DecidedAt = command.DecidedAt.UTC()
	if command.EventID == "" || command.CaseID == "" || command.CaseVersion < 1 ||
		command.PostID == "" || command.PostVersion < 1 || command.ContentDigest == "" ||
		command.ReviewerID == "" || command.DecidedAt.IsZero() ||
		(command.Status != "approved" && command.Status != "rejected") {
		return ApplyPostModerationDecisionResult{}, contentgenerated.AppErrorFromInvalidArgument(
			"post moderation decision command is incomplete",
		)
	}
	if s == nil || s.store.ports.Aggregate == nil {
		return ApplyPostModerationDecisionResult{}, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"Post moderation decision aggregate store is not configured",
		)
	}

	ctx = commandmeta.WithIdempotencyKey(ctx, "post-moderation:"+command.EventID)
	for attempt := 0; attempt < postModerationCASMaxAttempts; attempt++ {
		post, found, err := s.store.ports.Aggregate.Load(ctx, command.PostID)
		if err != nil {
			return ApplyPostModerationDecisionResult{}, contentgenerated.AppErrorFromStorageReadFailed(
				"load Post for moderation decision: " + err.Error(),
			)
		}
		if !found || post == nil {
			// Post 已删除时没有可更新对象；确认决定事实，避免永久阻塞 outbox。
			return ApplyPostModerationDecisionResult{
				PostID: command.PostID,
				Stale:  true,
			}, nil
		}

		currentModeration := strings.ToLower(strings.TrimSpace(post.ModerationStatus))
		if currentModeration == command.Status {
			// 同一目标态是 no-op；既覆盖 outbox 至少一次重放，也覆盖并发相同决定。
			return ApplyPostModerationDecisionResult{
				PostID:           post.ID,
				CommittedVersion: post.Version,
				ModerationStatus: currentModeration,
			}, nil
		}
		if post.Version != command.PostVersion ||
			!strings.EqualFold(strings.TrimSpace(post.ContentDigest), command.ContentDigest) {
			// Case 只拥有其绑定 revision。旧决定不得覆盖任何较新 Post 状态。
			return ApplyPostModerationDecisionResult{
				PostID:           post.ID,
				CommittedVersion: post.Version,
				ModerationStatus: currentModeration,
				Stale:            true,
			}, nil
		}

		expectedVersion := post.Version
		post.ModerationStatus = command.Status
		eventType := postevent.PostModerationRejected
		if command.Status == "approved" {
			post.Status = "published"
			post.PublishedAt = command.DecidedAt
			post.LastActiveAt = command.DecidedAt
			eventType = postevent.PostPublished
		} else {
			post.Status = "rejected"
		}
		if command.DecidedAt.After(post.UpdatedAt) {
			post.UpdatedAt = command.DecidedAt
		}
		payload := projectionPayloadForPost(post)
		if eventType == postevent.PostPublished {
			if sourcePostID := strings.TrimSpace(post.SourcePostId); sourcePostID != "" {
				sourcePost, sourceFound := s.store.FindByID(ctx, sourcePostID)
				if sourceFound {
					payload["sourcePostId"] = sourcePostID
					payload["sourcePostAuthorId"] = strings.TrimSpace(sourcePost.AuthorId)
				}
			}
		}
		committed, commitErr := s.commitPostCommand(
			ctx,
			post,
			expectedVersion,
			"ApplyPostModerationDecision",
			command,
			eventType,
			payload,
			command.DecidedAt,
		)
		if commitErr == nil {
			return ApplyPostModerationDecisionResult{
				PostID:           committed.ID,
				CommittedVersion: committed.Version,
				ModerationStatus: committed.ModerationStatus,
				Applied:          true,
			}, nil
		}
		if !isPostVersionConflict(commitErr) {
			return ApplyPostModerationDecisionResult{}, commitErr
		}
	}
	return ApplyPostModerationDecisionResult{}, contentgenerated.AppErrorFromVersionConflict(
		"Post changed repeatedly while applying moderation decision",
	)
}

func isPostVersionConflict(err error) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) &&
		appError.Code.String() == contentgenerated.ErrVersionConflict.Error()
}

// PostModerationDecisionConsumer 把已提交的 PostModerationCase decided 事实
// 翻译为 Post 对象命令；其它 case 事实是该 consumer 的确定性 no-op。
type PostModerationDecisionConsumer struct {
	commands PostModerationDecisionCommandFacet
}

func NewPostModerationDecisionConsumer(
	commands PostModerationDecisionCommandFacet,
) *PostModerationDecisionConsumer {
	if commands == nil {
		panic("Post moderation decision consumer requires command facet")
	}
	return &PostModerationDecisionConsumer{commands: commands}
}

type postModerationDecidedFact struct {
	ID            string    `json:"id"`
	Version       int64     `json:"version"`
	PostID        string    `json:"postId"`
	PostVersion   int64     `json:"postVersion"`
	ContentDigest string    `json:"contentDigest"`
	ReviewerID    string    `json:"reviewerId"`
	Status        string    `json:"status"`
	DecidedAt     time.Time `json:"decidedAt"`
}

func (c *PostModerationDecisionConsumer) Publish(
	ctx context.Context,
	event moderationports.OutboxEvent,
) error {
	if c == nil || c.commands == nil {
		return fmt.Errorf("Post moderation decision consumer is not configured")
	}
	if event.EventType != postModerationDecisionEventType {
		return nil
	}
	var fact postModerationDecidedFact
	if err := json.Unmarshal(event.Payload, &fact); err != nil {
		return fmt.Errorf("decode Post moderation decision %q: %w", event.EventID, err)
	}
	if strings.TrimSpace(fact.ID) != strings.TrimSpace(event.AggregateID) ||
		fact.Version != event.AggregateVersion {
		return fmt.Errorf("Post moderation decision %q aggregate identity mismatch", event.EventID)
	}
	_, err := c.commands.ApplyPostModerationDecision(ctx, ApplyPostModerationDecisionCommand{
		EventID:       event.EventID,
		CaseID:        fact.ID,
		CaseVersion:   fact.Version,
		PostID:        fact.PostID,
		PostVersion:   fact.PostVersion,
		ContentDigest: fact.ContentDigest,
		ReviewerID:    fact.ReviewerID,
		Status:        fact.Status,
		DecidedAt:     fact.DecidedAt,
	})
	if err != nil {
		return fmt.Errorf("apply Post moderation decision %q: %w", event.EventID, err)
	}
	return nil
}

var _ moderationports.OutboxPublisher = (*PostModerationDecisionConsumer)(nil)
