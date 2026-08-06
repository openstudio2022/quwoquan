package recommendation

// N0-3 服务端权威信号注入：like / comment / report 的高权重信号
// （SignalWeights: like 2.0 / comment 2.5 / report -10.0）此前零供给——like 被
// 行为端点显式拒收、comment/report 无注入方。本文件把三个对象服务 outbox 的
// 服务端确认事实转为 BehaviorSignal，注入：
//  1. SignalProcessor（HotPath 实时会话特征 / 负反馈集）；
//  2. ContentBehaviorFact 对象存储与 typed stream。
// Recommendation 独立消费 typed fact，形成自己的反馈与特征投影；Content
// 禁止再写本地学习事实或 Recommendation 存储。
//
// 事实源为对象 outbox（服务端确认后的事实），不依赖端侧补报，天然防伪造。
// relay at-least-once 重放由 rm_behavior_events 的 userId+clientEventId 唯一索引
// 兜底幂等（clientEventId 取事实 EventID，确定性）。

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

// AuthoritativeSignalSink 统一 Content 自有实时状态和事实出口。
type AuthoritativeSignalSink struct {
	signals rtrec.SignalProcessor
	events  ports.BehaviorEventStore
	posts   *mongo.Collection
}

func NewAuthoritativeSignalSink(
	db *mongo.Database,
	signals rtrec.SignalProcessor,
	events ports.BehaviorEventStore,
) *AuthoritativeSignalSink {
	sink := &AuthoritativeSignalSink{
		signals: signals,
		events:  events,
	}
	if db != nil {
		sink.posts = db.Collection("posts")
	}
	return sink
}

// postSignalContext 从 posts 集合补齐信号的推荐上下文（tags 驱动 HotPath
// TagWeights；authorId/contentType 驱动特征投影维度）。post 不存在时返回零值
// （信号仍然注入，只是无 tag 维度）。
func (s *AuthoritativeSignalSink) postSignalContext(ctx context.Context, postID string) (tags []string, authorID, contentType string) {
	if s.posts == nil || strings.TrimSpace(postID) == "" {
		return nil, "", ""
	}
	var doc struct {
		TagRefs     []string `bson:"tagRefs"`
		AuthorID    string   `bson:"authorId"`
		ContentType string   `bson:"contentType"`
	}
	err := s.posts.FindOne(ctx, bson.M{"_id": postID},
		options.FindOne().SetProjection(bson.M{"tagRefs": 1, "authorId": 1, "contentType": 1}),
	).Decode(&doc)
	if err != nil {
		return nil, "", ""
	}
	return doc.TagRefs, strings.TrimSpace(doc.AuthorID), strings.TrimSpace(doc.ContentType)
}

func (s *AuthoritativeSignalSink) Emit(ctx context.Context, signal rtrec.BehaviorSignal) error {
	if signal.UserID == "" || signal.ContentID == "" || signal.Action == "" {
		return nil
	}
	if signal.Timestamp.IsZero() {
		signal.Timestamp = time.Now().UTC()
	}
	if s.signals != nil {
		if err := s.signals.ProcessSignalBatch(ctx, []rtrec.BehaviorSignal{signal}); err != nil {
			return fmt.Errorf("authoritative signal hotpath (%s): %w", signal.Action, err)
		}
	}
	if s.events != nil {
		raw := ports.RawBehaviorEvent{
			ClientEventID:  signal.ClientEventID,
			UserID:         signal.UserID,
			SessionID:      signal.SessionID,
			ContentID:      signal.ContentID,
			Action:         signal.Action,
			ContentType:    signal.ContentType,
			Tags:           signal.Tags,
			AuthorID:       signal.AuthorID,
			ReferralSource: signal.ReferralSource,
			OccurredAt:     signal.Timestamp.UTC().Format(time.RFC3339),
			CreatedAt:      signal.Timestamp.UTC(),
		}
		if err := s.events.InsertBatch(ctx, []ports.RawBehaviorEvent{raw}); err != nil {
			return fmt.Errorf("authoritative signal event store (%s): %w", signal.Action, err)
		}
	}
	rtrec.RecordBehaviorIngest(signal)
	return nil
}

// ---------------------------------------------------------------------------
// Reaction → like 信号
// ---------------------------------------------------------------------------

// reactionSignalFact 与 reactionapp.reactionStateChangedFact 的 wire JSON 对齐
// （跨包解码 outbox payload；字段名以事实 JSON 为契约）。
type reactionSignalFact struct {
	TargetKind     string    `json:"targetKind"`
	TargetID       string    `json:"targetId"`
	TargetAuthorID string    `json:"targetAuthorId"`
	ActorID        string    `json:"actorId"`
	Reaction       string    `json:"reaction"`
	OccurredAt     time.Time `json:"occurredAt"`
}

// ReactionSignalProjector 实现 reaction outbox 的 OutboxPublisher 形状
// （Publish(ctx, fact)）。ContentReactionSet + reaction=like + target=post
// 注入正信号；Cleared / 非 like / 非 post 事实忽略（unlike 不产生负信号）。
type ReactionSignalProjector struct {
	sink *AuthoritativeSignalSink
}

func NewReactionSignalProjector(sink *AuthoritativeSignalSink) *ReactionSignalProjector {
	return &ReactionSignalProjector{sink: sink}
}

// Publish 实现 reactionports.OutboxPublisher。
func (p *ReactionSignalProjector) Publish(ctx context.Context, fact reactionports.OutboxFact) error {
	return p.publishFact(ctx, fact.EventID, fact.EventType, fact.Payload)
}

func (p *ReactionSignalProjector) publishFact(ctx context.Context, eventID, eventType string, payload []byte) error {
	if p == nil || p.sink == nil {
		return fmt.Errorf("reaction signal projector is not configured")
	}
	if eventType != "ContentReactionSet" {
		return nil
	}
	var fact reactionSignalFact
	if err := json.Unmarshal(payload, &fact); err != nil {
		return fmt.Errorf("decode reaction fact for signal: %w", err)
	}
	if fact.TargetKind != "post" || fact.Reaction != "like" {
		return nil
	}
	tags, authorID, contentType := p.sink.postSignalContext(ctx, fact.TargetID)
	if authorID == "" {
		authorID = strings.TrimSpace(fact.TargetAuthorID)
	}
	return p.sink.Emit(ctx, rtrec.BehaviorSignal{
		ClientEventID:  "authoritative:" + eventID,
		UserID:         fact.ActorID,
		ContentID:      fact.TargetID,
		Action:         "like",
		ContentType:    contentType,
		Tags:           tags,
		AuthorID:       authorID,
		ReferralSource: "server_authoritative",
		Timestamp:      fact.OccurredAt,
	})
}

// ---------------------------------------------------------------------------
// Comment → comment 信号
// ---------------------------------------------------------------------------

type commentSignalFact struct {
	CommentID    string    `json:"commentId"`
	PostID       string    `json:"postId"`
	PostAuthorID string    `json:"postAuthorId"`
	AuthorID     string    `json:"authorId"`
	CreatedAt    time.Time `json:"createdAt"`
}

// CommentSignalProjector 消费 CommentCreated 事实注入 comment 正信号。
type CommentSignalProjector struct {
	sink *AuthoritativeSignalSink
}

func NewCommentSignalProjector(sink *AuthoritativeSignalSink) *CommentSignalProjector {
	return &CommentSignalProjector{sink: sink}
}

// Publish 实现 commentports.OutboxPublisher。
func (p *CommentSignalProjector) Publish(ctx context.Context, event commentports.OutboxEvent) error {
	return p.publishFact(ctx, event.EventID, event.EventType, event.Payload)
}

func (p *CommentSignalProjector) publishFact(ctx context.Context, eventID, eventType string, payload []byte) error {
	if p == nil || p.sink == nil {
		return fmt.Errorf("comment signal projector is not configured")
	}
	if eventType != "CommentCreated" {
		return nil
	}
	var fact commentSignalFact
	if err := json.Unmarshal(payload, &fact); err != nil {
		return fmt.Errorf("decode comment fact for signal: %w", err)
	}
	if strings.TrimSpace(fact.PostID) == "" || strings.TrimSpace(fact.AuthorID) == "" {
		return nil
	}
	tags, postAuthorID, contentType := p.sink.postSignalContext(ctx, fact.PostID)
	if postAuthorID == "" {
		postAuthorID = strings.TrimSpace(fact.PostAuthorID)
	}
	return p.sink.Emit(ctx, rtrec.BehaviorSignal{
		ClientEventID:  "authoritative:" + eventID,
		UserID:         fact.AuthorID,
		ContentID:      fact.PostID,
		Action:         "comment",
		ContentType:    contentType,
		Tags:           tags,
		AuthorID:       postAuthorID,
		ReferralSource: "server_authoritative",
		Timestamp:      fact.CreatedAt,
	})
}

// ---------------------------------------------------------------------------
// Report → report 负信号
// ---------------------------------------------------------------------------

type reportSignalFact struct {
	ReportID   string `json:"reportId"`
	ReporterID string `json:"reporterId"`
	TargetType string `json:"targetType"`
	TargetID   string `json:"targetId"`
	Reason     string `json:"reason"`
}

// ReportSignalProjector 消费 content.report.ReportCreated 事实注入 report 负信号
// （HotPath 负反馈集 + 特征投影 + 训练标签）。
type ReportSignalProjector struct {
	sink *AuthoritativeSignalSink
}

func NewReportSignalProjector(sink *AuthoritativeSignalSink) *ReportSignalProjector {
	return &ReportSignalProjector{sink: sink}
}

// Publish 实现 reportports.OutboxPublisher。
func (p *ReportSignalProjector) Publish(ctx context.Context, event reportports.OutboxEvent) error {
	return p.publishFact(ctx, event.EventID, event.EventType, event.Payload, event.OccurredAt)
}

func (p *ReportSignalProjector) publishFact(ctx context.Context, eventID, eventType string, payload []byte, occurredAt time.Time) error {
	if p == nil || p.sink == nil {
		return fmt.Errorf("report signal projector is not configured")
	}
	if eventType != "content.report.ReportCreated" {
		return nil
	}
	var fact reportSignalFact
	if err := json.Unmarshal(payload, &fact); err != nil {
		return fmt.Errorf("decode report fact for signal: %w", err)
	}
	if fact.TargetType != "post" || strings.TrimSpace(fact.ReporterID) == "" {
		return nil
	}
	tags, authorID, contentType := p.sink.postSignalContext(ctx, fact.TargetID)
	return p.sink.Emit(ctx, rtrec.BehaviorSignal{
		ClientEventID:  "authoritative:" + eventID,
		UserID:         fact.ReporterID,
		ContentID:      fact.TargetID,
		Action:         "report",
		ContentType:    contentType,
		Tags:           tags,
		AuthorID:       authorID,
		ReferralSource: "server_authoritative",
		Timestamp:      occurredAt,
	})
}
