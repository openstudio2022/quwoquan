// Package followconsumer 消费 user-service 的 SubjectFollowStateChanged 流
// （Redis Stream events.user.subject_follow），把 homepage 主体的关注事实投影
// 到 Homepage 的 follower 状态（viewerFollowsHomepage / followerCount）。
// 关注真相源是 user.SubjectFollow；本 consumer 只维护本地读投影。
package followconsumer

import (
	"context"
	"log/slog"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	subjectFollowStream = "events.user.subject_follow"
	consumerGroup       = "entity.homepage_follow_projector"
)

// HomepageFollowProjection 是 entity 域内的投影应用端口。
type HomepageFollowProjection interface {
	ApplySubjectFollowState(ctx context.Context, homepageID, personaID string, following bool) error
}

type Consumer struct {
	client     rtredis.Client
	projection HomepageFollowProjection
	consumerID string
}

func NewConsumer(client rtredis.Client, projection HomepageFollowProjection, consumerID string) *Consumer {
	if client == nil || projection == nil {
		panic("subject follow consumer requires redis client and projection")
	}
	if strings.TrimSpace(consumerID) == "" {
		consumerID = "entity-service"
	}
	return &Consumer{client: client, projection: projection, consumerID: consumerID}
}

// Run 以 consumer group 语义消费；Ack 前投影必须成功，故障时消息保持
// pending 由 XAutoClaim 重新认领（至少一次 + 投影幂等）。
func (c *Consumer) Run(ctx context.Context) {
	if err := c.client.XGroupCreateMkStream(ctx, subjectFollowStream, consumerGroup, "0"); err != nil {
		slog.WarnContext(ctx, "subject follow consumer group create", "err", err)
	}
	for ctx.Err() == nil {
		if err := c.drainOnce(ctx); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "subject follow consumer drain failed", "err", err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
		}
	}
}

func (c *Consumer) drainOnce(ctx context.Context) error {
	// 先补偿认领超时 pending（其它实例崩溃遗留），再读新消息。
	claimed, _, err := c.client.XAutoClaim(
		ctx, subjectFollowStream, consumerGroup, c.consumerID, time.Minute, "0-0", 50,
	)
	if err == nil && len(claimed) > 0 {
		if err := c.apply(ctx, claimed); err != nil {
			return err
		}
	}
	messages, err := c.client.XReadGroup(
		ctx,
		consumerGroup,
		c.consumerID,
		map[string]string{subjectFollowStream: ">"},
		50,
		2*time.Second,
	)
	if err != nil {
		return err
	}
	return c.apply(ctx, messages)
}

func (c *Consumer) apply(ctx context.Context, messages []rtredis.StreamMessage) error {
	for _, message := range messages {
		if strings.TrimSpace(message.Values["subjectType"]) == "homepage" {
			following := strings.TrimSpace(message.Values["state"]) == "following"
			if err := c.projection.ApplySubjectFollowState(
				ctx,
				message.Values["subjectId"],
				message.Values["personaId"],
				following,
			); err != nil {
				return err
			}
		}
		if err := c.client.XAck(ctx, subjectFollowStream, consumerGroup, message.ID); err != nil {
			return err
		}
	}
	return nil
}
