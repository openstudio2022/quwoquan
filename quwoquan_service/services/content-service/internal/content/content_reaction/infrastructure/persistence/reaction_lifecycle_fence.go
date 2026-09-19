package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

// lifecycleFenceBuckets 是每个 target 内固定的写栅栏桶数。
// 单行栅栏会把该 target 的全部互动写集中到一行；固定分桶既分散正常写热点，
// 又允许删除在一次事务里把全部桶一起封闭。测试基线为 16，运行期不热变。
const lifecycleFenceBuckets = 16

// ErrTargetLifecycleClosed 表示目标已被其 owner 撤权，桶已封闭。
// 这是确定拒绝：晚到的互动不得再新增活跃贡献。
var ErrTargetLifecycleClosed = errors.New("content reaction target lifecycle is closed")

// lifecycleFenceDocument 是一个 target 内单个桶的写栅栏。
// Like 在自己的事务里真实更新所属桶，删除在一次事务里封闭全部桶：
// 两者因此在同一份文档上产生真实写冲突，而不是「只在事务里读墓碑」。
type lifecycleFenceDocument struct {
	ID          string    `bson:"_id"`
	TargetKind  string    `bson:"targetKind"`
	TargetID    string    `bson:"targetId"`
	Bucket      int       `bson:"bucket"`
	Closed      bool      `bson:"closed"`
	CloseSource string    `bson:"closeSource,omitempty"`
	CommitMark  int64     `bson:"commitMark"`
	UpdatedAt   time.Time `bson:"updatedAt"`
}

// lifecycleFenceID 是 target 与桶序号的稳定复合身份。
func lifecycleFenceID(target reactiondomain.Target, bucket int) string {
	return fmt.Sprintf("%s|%s|%d", target.Kind, target.ID, bucket)
}

// lifecycleFenceBucketFor 按 reaction identity 稳定路由到固定桶。
func lifecycleFenceBucketFor(aggregateID string) int {
	digest := sha256.Sum256([]byte(aggregateID))
	return int(binary.BigEndian.Uint32(digest[:4]) % uint32(lifecycleFenceBuckets))
}

// markLifecycleFenceOpen 在命令事务内真实更新所属桶并确认它仍 open。
// 桶不存在时惰性创建；已封闭时返回确定拒绝，且不留下任何活跃贡献。
func markLifecycleFenceOpen(
	ctx context.Context,
	fences *mongo.Collection,
	target reactiondomain.Target,
	aggregateID string,
	now time.Time,
) error {
	bucket := lifecycleFenceBucketFor(aggregateID)
	documentID := lifecycleFenceID(target, bucket)
	result, err := fences.UpdateOne(
		ctx,
		bson.D{{Key: "_id", Value: documentID}, {Key: "closed", Value: false}},
		bson.D{
			{Key: "$inc", Value: bson.D{{Key: "commitMark", Value: int64(1)}}},
			{Key: "$set", Value: bson.D{{Key: "updatedAt", Value: now}}},
			{Key: "$setOnInsert", Value: bson.D{
				{Key: "targetKind", Value: string(target.Kind)},
				{Key: "targetId", Value: target.ID},
				{Key: "bucket", Value: bucket},
				{Key: "closed", Value: false},
			}},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			// upsert 与并发封闭同时命中同一 _id：该桶已被封闭。
			return ErrTargetLifecycleClosed
		}
		return fmt.Errorf("mark content reaction lifecycle fence: %w", err)
	}
	if result.MatchedCount == 0 && result.UpsertedCount == 0 {
		return ErrTargetLifecycleClosed
	}
	return nil
}

// closeLifecycleFences 在一次事务里封闭该 target 的全部固定桶，含尚未创建的桶。
// 只封闭已存在的桶会让晚到的 upsert 重新建出一个 open 桶。
func closeLifecycleFences(
	ctx context.Context,
	fences *mongo.Collection,
	target reactiondomain.Target,
	closeSource string,
	now time.Time,
) error {
	models := make([]mongo.WriteModel, 0, lifecycleFenceBuckets)
	for bucket := 0; bucket < lifecycleFenceBuckets; bucket++ {
		models = append(models, mongo.NewUpdateOneModel().
			SetFilter(bson.D{{Key: "_id", Value: lifecycleFenceID(target, bucket)}}).
			SetUpsert(true).
			SetUpdate(bson.D{
				{Key: "$set", Value: bson.D{
					{Key: "closed", Value: true},
					{Key: "closeSource", Value: closeSource},
					{Key: "updatedAt", Value: now},
				}},
				{Key: "$setOnInsert", Value: bson.D{
					{Key: "targetKind", Value: string(target.Kind)},
					{Key: "targetId", Value: target.ID},
					{Key: "bucket", Value: bucket},
					{Key: "commitMark", Value: int64(0)},
				}},
			}))
	}
	if _, err := fences.BulkWrite(ctx, models, options.BulkWrite().SetOrdered(false)); err != nil {
		return fmt.Errorf("close content reaction lifecycle fences: %w", err)
	}
	return nil
}
