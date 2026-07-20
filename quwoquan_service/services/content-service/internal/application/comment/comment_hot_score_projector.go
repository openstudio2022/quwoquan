package comment

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/domain/reaction/ports"
)

// CommentHotScoreWriter 把重算后的 hotScore 投影分写入 comments 集合；
// 目标缺失（已删除/tombstoned 后被物理清理）返回 false 而非报错。
type CommentHotScoreWriter interface {
	SetCommentHotScore(ctx context.Context, commentID string, score int64) (bool, error)
}

// CommentHotScoreProjector 消费 Comment 与 ContentReaction 事实，
// 以「事件触发 + 权威数据全量重算」的幂等模式维护 hotScore 投影分：
// hotScore = (likeCount - dislikeCount) + 2 * replyCount（commentmodel.HotScoreFor）。
// 不做 $inc 增量（重放会漂移）、不引入 Redis 排行（R-CMT01 教训）。
type CommentHotScoreProjector struct {
	replySummaries commentports.ReplySummaryReader
	reactions      CommentReactionProjectionReader
	writer         CommentHotScoreWriter
}

func NewCommentHotScoreProjector(
	replySummaries commentports.ReplySummaryReader,
	reactions CommentReactionProjectionReader,
	writer CommentHotScoreWriter,
) *CommentHotScoreProjector {
	return &CommentHotScoreProjector{
		replySummaries: replySummaries,
		reactions:      reactions,
		writer:         writer,
	}
}

// Publish 实现 Comment outbox relay 的 publisher：
// 回复创建、删除、隐藏或恢复会改变父评论的 active replyCount，
// 因而必须触发父评论 hotScore 重算。
func (p *CommentHotScoreProjector) Publish(ctx context.Context, event commentports.OutboxEvent) error {
	if p == nil || p.writer == nil {
		return fmt.Errorf("Comment hot score projector is not configured")
	}
	if event.EventType != commentCreatedEventType &&
		event.EventType != commentDeletedEventType &&
		event.EventType != commentModeratedEventType {
		return nil
	}
	var payload struct {
		ParentCommentID string `json:"parentCommentId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode Comment hot score event: %w", err)
	}
	parentCommentID := strings.TrimSpace(payload.ParentCommentID)
	if parentCommentID == "" {
		// 一级评论创建/删除不改变任何已有评论的 hotScore 输入。
		return nil
	}
	return p.recompute(ctx, parentCommentID)
}

// PublishReactionFact 实现 ContentReaction outbox relay 的 publisher：
// 评论赞踩变化触发目标评论 hotScore 重算。
func (p *CommentHotScoreProjector) PublishReactionFact(
	ctx context.Context,
	fact reactionports.OutboxFact,
) error {
	if p == nil || p.writer == nil {
		return fmt.Errorf("Comment hot score projector is not configured")
	}
	var payload struct {
		TargetKind string `json:"targetKind"`
		TargetID   string `json:"targetId"`
	}
	if err := json.Unmarshal(fact.Payload, &payload); err != nil {
		return fmt.Errorf("decode ContentReaction hot score fact: %w", err)
	}
	if payload.TargetKind != string(reactiondomain.TargetKindComment) {
		return nil
	}
	targetID := strings.TrimSpace(payload.TargetID)
	if targetID == "" {
		return fmt.Errorf("ContentReaction comment fact has no targetId")
	}
	return p.recompute(ctx, targetID)
}

// recompute 从权威数据（reaction counts + reply count）重算单条评论 hotScore；
// 幂等，可安全重放。目标评论已不存在时静默收敛（写端返回 false）。
func (p *CommentHotScoreProjector) recompute(ctx context.Context, commentID string) error {
	counts, err := p.reactions.ReadCommentReactionCounts(ctx, []string{commentID})
	if err != nil {
		return fmt.Errorf("read reaction counts for hot score: %w", err)
	}
	summaries, err := p.replySummaries.ReadReplySummaries(
		ctx,
		[]string{commentID},
		1,
		nil,
	)
	if err != nil {
		return fmt.Errorf("read reply count for hot score: %w", err)
	}
	reaction := counts[commentID]
	score := commentmodel.HotScoreFor(
		reaction.LikeCount,
		reaction.DislikeCount,
		summaries[commentID].Count,
	)
	if _, err := p.writer.SetCommentHotScore(ctx, commentID, score); err != nil {
		return fmt.Errorf("write comment hot score projection: %w", err)
	}
	return nil
}

var _ commentports.OutboxPublisher = (*CommentHotScoreProjector)(nil)

// reactionFactPublisher 把 projector 适配为 ContentReaction relay 的 publisher。
type reactionFactPublisher struct {
	projector *CommentHotScoreProjector
}

// NewReactionHotScorePublisher 返回消费 ContentReaction 事实的 hotScore publisher。
func NewReactionHotScorePublisher(projector *CommentHotScoreProjector) reactionports.OutboxPublisher {
	return reactionFactPublisher{projector: projector}
}

func (p reactionFactPublisher) Publish(ctx context.Context, fact reactionports.OutboxFact) error {
	return p.projector.PublishReactionFact(ctx, fact)
}
