package recommendation

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postevent "quwoquan_service/services/content-service/internal/domain/post/event"
)

func embeddingTextSHA(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}

const (
	// EmbeddingDailyBudgetDefault 每日 Embedding API 调用量护栏（成本控制，B5）。
	// 超限后写入跳过并记录，由回填任务在预算恢复后补齐；护栏计数经 Redis
	// 按 UTC 日滚动。
	EmbeddingDailyBudgetDefault = 5000

	embeddingBudgetKeyPrefix = "rec:embed:budget:"
	embeddingTextMaxRunes    = 2048
)

// EmbeddingWriter 是 posts.embedding 的写入端口（W8 S0 基建）。
// 写入侧与读侧（VectorRecallSource / Atlas vector index）共享同一字段契约
// （contracts/metadata/_vectors/content_embedding.yaml）；读侧召回通道由
// cfg.Embedding.Enabled + 引擎源接线控制（S0 flag-off，S1 内容池阈值开启）。
type EmbeddingProjector struct {
	coll        *mongo.Collection
	embedder    EmbeddingProvider
	budget      rtredis.Client
	dailyBudget int
	logger      *slog.Logger
	now         func() time.Time
}

type EmbeddingProjectorOption func(*EmbeddingProjector)

// WithEmbeddingDailyBudget 覆盖每日调用量护栏（<=0 使用默认值）。
func WithEmbeddingDailyBudget(budget int) EmbeddingProjectorOption {
	return func(p *EmbeddingProjector) {
		if budget > 0 {
			p.dailyBudget = budget
		}
	}
}

func NewEmbeddingProjector(
	db *mongo.Database,
	embedder EmbeddingProvider,
	budget rtredis.Client,
	logger *slog.Logger,
	opts ...EmbeddingProjectorOption,
) *EmbeddingProjector {
	if logger == nil {
		logger = slog.Default()
	}
	p := &EmbeddingProjector{
		coll:        db.Collection("posts"),
		embedder:    embedder,
		budget:      budget,
		dailyBudget: EmbeddingDailyBudgetDefault,
		logger:      logger,
		now:         func() time.Time { return time.Now().UTC() },
	}
	for _, opt := range opts {
		opt(p)
	}
	return p
}

func (p *EmbeddingProjector) EventTypes() []string {
	return []string{postevent.PostPublished}
}

// Project 在 PostPublished 时生成内容 embedding 并写入 posts.embedding。
// 幂等：documentSha 未变且 embedding 已存在时跳过；失败返回错误由 outbox
// relay checkpoint 重放（不推进水位）。
func (p *EmbeddingProjector) Project(ctx context.Context, event ProjectorEvent) error {
	if p == nil || p.coll == nil || p.embedder == nil {
		return nil
	}
	if strings.TrimSpace(event.Type) != postevent.PostPublished {
		return nil
	}
	postID := firstNonEmpty(strVal(event.Payload, "postId"), event.AggregateID)
	if postID == "" {
		return nil
	}

	var doc struct {
		Title            string    `bson:"title"`
		Body             string    `bson:"body"`
		TagRefs          []string  `bson:"tagRefs"`
		Status           string    `bson:"status"`
		Embedding        []float64 `bson:"embedding"`
		EmbeddingTextSHA string    `bson:"embeddingTextSha"`
	}
	err := p.coll.FindOne(
		ctx,
		bson.M{"_id": postID},
		options.FindOne().SetProjection(bson.M{
			"title": 1, "body": 1, "tagRefs": 1, "status": 1,
			"embedding": bson.M{"$slice": 1}, "embeddingTextSha": 1,
		}),
	).Decode(&doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil
		}
		return fmt.Errorf("embedding projector load post %s: %w", postID, err)
	}
	if doc.Status != "published" {
		return nil
	}
	text := buildEmbeddingText(doc.Title, doc.Body, doc.TagRefs)
	if text == "" {
		return nil
	}
	textSHA := embeddingTextSHA(text)
	if len(doc.Embedding) > 0 && doc.EmbeddingTextSHA == textSHA {
		return nil
	}
	if !p.consumeBudget(ctx) {
		// 预算耗尽：跳过并推进水位（不可重放堆积），回填任务补齐。
		rtrec.RecordEmbeddingProjection("budget_exhausted")
		p.logger.Warn("embedding daily budget exhausted, skipping",
			slog.String("postId", postID))
		return nil
	}
	vector, err := p.embedder.Embed(ctx, text)
	if err != nil {
		rtrec.RecordEmbeddingProjection("api_error")
		return fmt.Errorf("embedding projector embed post %s: %w", postID, err)
	}
	if len(vector) == 0 {
		rtrec.RecordEmbeddingProjection("skipped")
		return nil
	}
	_, err = p.coll.UpdateOne(ctx,
		bson.M{"_id": postID},
		bson.M{"$set": bson.M{
			"embedding":          vector,
			"embeddingTextSha":   textSHA,
			"embeddingUpdatedAt": p.now(),
		}},
	)
	if err != nil {
		return fmt.Errorf("embedding projector write post %s: %w", postID, err)
	}
	rtrec.RecordEmbeddingProjection("success")
	return nil
}

// BackfillMissing 扫描已发布但缺 embedding 的内容并补齐（受同一日预算护栏约束）。
// 返回成功写入数；供运维任务/gamma 演练调用。
func (p *EmbeddingProjector) BackfillMissing(ctx context.Context, limit int) (int, error) {
	if p == nil || p.coll == nil || p.embedder == nil || limit <= 0 {
		return 0, nil
	}
	cursor, err := p.coll.Find(ctx,
		bson.M{
			"status":    "published",
			"embedding": bson.M{"$exists": false},
		},
		options.Find().
			SetProjection(bson.M{"_id": 1}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return 0, err
	}
	defer cursor.Close(ctx)
	var ids []struct {
		ID string `bson:"_id"`
	}
	if err := cursor.All(ctx, &ids); err != nil {
		return 0, err
	}
	written := 0
	for _, doc := range ids {
		err := p.Project(ctx, ProjectorEvent{
			Type:        postevent.PostPublished,
			AggregateID: doc.ID,
		})
		if err != nil {
			p.logger.Warn("embedding backfill item failed",
				slog.String("postId", doc.ID), slog.String("err", err.Error()))
			continue
		}
		written++
	}
	return written, nil
}

func (p *EmbeddingProjector) consumeBudget(ctx context.Context) bool {
	if p.budget == nil || p.dailyBudget <= 0 {
		return true
	}
	key := embeddingBudgetKeyPrefix + p.now().Format("20060102")
	count, err := p.budget.Incr(ctx, key)
	if err != nil {
		// 护栏计数不可用时放行（护栏是成本保护，不是正确性约束）。
		return true
	}
	if count == 1 {
		_ = p.budget.Expire(ctx, key, 48*time.Hour)
	}
	return count <= int64(p.dailyBudget)
}

func buildEmbeddingText(title, body string, tagRefs []string) string {
	parts := make([]string, 0, 3)
	if t := strings.TrimSpace(title); t != "" {
		parts = append(parts, t)
	}
	if b := strings.TrimSpace(body); b != "" {
		parts = append(parts, b)
	}
	if len(tagRefs) > 0 {
		parts = append(parts, strings.Join(tagRefs, " "))
	}
	text := strings.Join(parts, "\n")
	runes := []rune(text)
	if len(runes) > embeddingTextMaxRunes {
		text = string(runes[:embeddingTextMaxRunes])
	}
	return strings.TrimSpace(text)
}
