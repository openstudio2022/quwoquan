package reaction

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const postDeletionReactionBatchSize = 500

type postDeletedFact struct {
	PostID          string   `json:"postId"`
	AuthorID        string   `json:"authorId"`
	ContentType     string   `json:"contentType"`
	ContentIdentity string   `json:"contentIdentity"`
	Status          string   `json:"status"`
	CircleIDs       []string `json:"circleIds"`
	DeletedAt       string   `json:"deletedAt"`
}

// PostDeletionConsumer 是 Post 与 ContentReaction 之间的唯一删除生命周期边界。
// 它不跨聚合直删 Mongo，而是让每个 active relation 按自己的版本、
// receipt 和 outbox 迁移到 removed。
type PostDeletionConsumer struct {
	service *Service
	reader  ActivePostReactionReader
}

func NewPostDeletionConsumer(
	service *Service,
	reader ActivePostReactionReader,
) *PostDeletionConsumer {
	return &PostDeletionConsumer{service: service, reader: reader}
}

func (c *PostDeletionConsumer) Publish(
	ctx context.Context,
	event postports.OutboxEvent,
) error {
	if event.EventType != "PostDeleted" {
		return nil
	}
	if c == nil || c.service == nil || c.reader == nil {
		return fmt.Errorf("Post deletion ContentReaction consumer is not configured")
	}
	payload, err := decodePostDeletedFact(event)
	if err != nil {
		return err
	}
	for {
		identities, err := c.reader.ListActiveReactionsForPost(
			ctx,
			payload.PostID,
			postDeletionReactionBatchSize,
		)
		if err != nil {
			return fmt.Errorf("list active ContentReaction for deleted Post: %w", err)
		}
		if len(identities) == 0 {
			return nil
		}
		for _, identity := range identities {
			if identity.Target.Kind != reactiondomain.TargetKindPost || identity.Target.ID != payload.PostID {
				return fmt.Errorf("Post deletion reader returned a foreign ContentReaction")
			}
			commandContext := commandmeta.WithIdempotencyKey(
				ctx,
				"post-deleted:"+event.EventID+":"+identity.AggregateID(),
			)
			if err := c.service.removeForDeletedPost(commandContext, identity); err != nil {
				return fmt.Errorf(
					"remove ContentReaction %q for deleted Post: %w",
					identity.AggregateID(),
					err,
				)
			}
		}
	}
}

func decodePostDeletedFact(event postports.OutboxEvent) (postDeletedFact, error) {
	if strings.TrimSpace(event.EventID) == "" || event.AggregateType != "Post" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 ||
		event.OccurredAt.IsZero() {
		return postDeletedFact{}, fmt.Errorf("PostDeleted outbox identity is incomplete")
	}
	var payload postDeletedFact
	decoder := json.NewDecoder(bytes.NewReader(event.Payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return postDeletedFact{}, fmt.Errorf("decode PostDeleted lifecycle fact: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return postDeletedFact{}, fmt.Errorf("PostDeleted lifecycle fact contains trailing JSON")
	}
	deletedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.DeletedAt))
	if err != nil || deletedAt.IsZero() || payload.PostID != event.AggregateID ||
		strings.TrimSpace(payload.AuthorID) == "" || strings.TrimSpace(payload.Status) == "" {
		return postDeletedFact{}, fmt.Errorf("PostDeleted lifecycle fact is invalid")
	}
	return payload, nil
}

var _ postports.OutboxPublisher = (*PostDeletionConsumer)(nil)
