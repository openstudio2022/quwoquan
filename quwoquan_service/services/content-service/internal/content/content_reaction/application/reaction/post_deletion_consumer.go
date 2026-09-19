package reaction

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	"quwoquan_service/runtime/commandmeta"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const postDeletionReactionBatchSize = 500

type postDeletedFact struct {
	PostID         string  `json:"postId"`
	AuthorID       string  `json:"authorId"`
	ContentType    string  `json:"contentType"`
	Status         string  `json:"status"`
	DeletedAt      string  `json:"deletedAt"`
	Environment    *string `json:"environment"`
	SourceOwner    *string `json:"sourceOwner"`
	ReleaseID      *string `json:"releaseId"`
	ManifestDigest *string `json:"manifestDigest"`
	ReleaseDigest  *string `json:"releaseDigest"`
	SourceVersion  int64   `json:"sourceVersion"`
	SafetyRevision int64   `json:"safetyRevision"`
}

// TargetLifecycleCloser 在 Reaction 自有 scope 内封闭一个 target 的全部写栅栏桶。
// 它由已验证的 owner lifecycle 事件驱动，不跨写 Post 私有存储。
type TargetLifecycleCloser interface {
	CloseTargetLifecycle(ctx context.Context, target reactiondomain.Target, closeSource string) error
}

// PostDeletionConsumer 是 Post 与 ContentReaction 之间的唯一删除生命周期边界。
// 它不跨聚合直删 Mongo，而是先封闭写栅栏，再让每个 active relation 按自己的
// 版本、receipt 和 outbox 迁移到 removed。
type PostDeletionConsumer struct {
	service *Service
	reader  ActivePostReactionReader
	fences  TargetLifecycleCloser
	jobs    LifecycleCleanupJobStore
	now     func() time.Time
}

func NewPostDeletionConsumer(
	service *Service,
	reader ActivePostReactionReader,
	fences ...TargetLifecycleCloser,
) *PostDeletionConsumer {
	consumer := &PostDeletionConsumer{service: service, reader: reader, now: func() time.Time { return time.Now().UTC() }}
	if len(fences) > 0 {
		consumer.fences = fences[0]
		if jobs, ok := fences[0].(LifecycleCleanupJobStore); ok {
			consumer.jobs = jobs
		}
	}
	if consumer.jobs == nil {
		if jobs, ok := reader.(LifecycleCleanupJobStore); ok {
			consumer.jobs = jobs
		}
	}
	return consumer
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
	// 必须先封闭全部写栅栏桶再扫描成员：否则「目标检查通过 → 删除扫空 →
	// 晚到 Like 提交」会复活一个活跃贡献。
	if c.fences != nil {
		if err := c.fences.CloseTargetLifecycle(
			ctx,
			reactiondomain.Target{Kind: reactiondomain.TargetKindPost, ID: payload.PostID},
			"post-deleted:"+event.EventID,
		); err != nil {
			return fmt.Errorf("close ContentReaction lifecycle fences for deleted Post: %w", err)
		}
	}
	if c.jobs == nil {
		return fmt.Errorf("Post deletion cleanup job store is not configured")
	}
	jobID := "post-deleted:" + event.EventID + fmt.Sprintf(":v%d", payload.SourceVersion)
	job, err := c.jobs.Ensure(ctx, LifecycleCleanupJob{ID: jobID, Target: reactiondomain.Target{Kind: reactiondomain.TargetKindPost, ID: payload.PostID}, SourceVersion: payload.SourceVersion, Deadline: c.now().Add(2 * time.Second)})
	if err != nil {
		return err
	}
	if job.Completed {
		return nil
	}
	for c.now().Before(job.Deadline) {
		job, claimed, claimErr := c.jobs.Claim(ctx, jobID, c.now(), 5*time.Second)
		if claimErr != nil {
			return claimErr
		}
		if !claimed {
			return nil
		}
		identities, listErr := c.reader.ListActiveReactionsForPost(ctx, payload.PostID, postDeletionReactionBatchSize)
		if listErr != nil {
			return fmt.Errorf("list active ContentReaction for deleted Post: %w", listErr)
		}
		if len(identities) == 0 {
			return c.jobs.Advance(ctx, jobID, job.LeaseEpoch, job.Cursor, job.Checkpoint, true)
		}
		cursor := job.Cursor
		for _, identity := range identities {
			if identity.Target.Kind != reactiondomain.TargetKindPost || identity.Target.ID != payload.PostID {
				return fmt.Errorf("Post deletion reader returned a foreign ContentReaction")
			}
			aggregate, found, loadErr := c.service.data.Aggregate.Load(ctx, identity.AggregateID())
			if loadErr != nil {
				return loadErr
			}
			if !found {
				continue
			}
			commandContext := commandmeta.WithIdempotencyKey(ctx, fmt.Sprintf("post-deleted:%s:v%d:%s:m%d", event.EventID, payload.SourceVersion, identity.AggregateID(), aggregate.Version()))
			if err := c.service.removeForDeletedPost(commandContext, identity); err != nil {
				return fmt.Errorf("remove ContentReaction %q for deleted Post: %w", identity.AggregateID(), err)
			}
			cursor = identity.AggregateID()
		}
		if err := c.jobs.Advance(ctx, jobID, job.LeaseEpoch, cursor, job.Checkpoint+int64(len(identities)), false); err != nil {
			return err
		}
	}
	return nil
}

func decodePostDeletedFact(event postports.OutboxEvent) (postDeletedFact, error) {
	if strings.TrimSpace(event.EventID) == "" || event.AggregateType != "Post" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 ||
		event.OccurredAt.IsZero() {
		return postDeletedFact{}, fmt.Errorf("PostDeleted outbox identity is incomplete")
	}
	var presence map[string]json.RawMessage
	if err := json.Unmarshal(event.Payload, &presence); err != nil {
		return postDeletedFact{}, err
	}
	for _, key := range []string{"environment", "sourceOwner", "releaseId", "manifestDigest", "releaseDigest", "sourceVersion"} {
		if _, ok := presence[key]; !ok {
			return postDeletedFact{}, fmt.Errorf("PostDeleted required source field missing: %s", key)
		}
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
	if payload.SourceVersion != event.AggregateVersion || payload.SafetyRevision < 1 {
		return postDeletedFact{}, fmt.Errorf("PostDeleted source version differs from committed envelope")
	}
	if payload.Environment != nil || payload.SourceOwner != nil || payload.ReleaseID != nil || payload.ManifestDigest != nil || payload.ReleaseDigest != nil {
		return postDeletedFact{}, fmt.Errorf("Data PostDeleted requires authoritative source safety binding")
	}
	deletedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.DeletedAt))
	if err != nil || deletedAt.IsZero() || payload.PostID != event.AggregateID ||
		strings.TrimSpace(payload.AuthorID) == "" || strings.TrimSpace(payload.Status) == "" {
		return postDeletedFact{}, fmt.Errorf("PostDeleted lifecycle fact is invalid")
	}
	return payload, nil
}

var _ postports.OutboxPublisher = (*PostDeletionConsumer)(nil)
