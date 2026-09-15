package post

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"time"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	semantic "quwoquan_service/services/content-service/generated/content/post/semantic_document"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func (s *PostService) commitPostCommand(
	ctx context.Context,
	post *postmodel.Post,
	expectedVersion int64,
	commandName string,
	commandPayload any,
	eventType string,
	eventPayload any,
	occurredAt time.Time,
	commitOptions ...func(*postports.Commit),
) (*postmodel.Post, error) {
	post, _, err := s.commitPostCommandWithResult(
		ctx,
		post,
		expectedVersion,
		commandName,
		commandPayload,
		eventType,
		eventPayload,
		occurredAt,
		commitOptions...,
	)
	return post, err
}

func (s *PostService) commitPostCommandWithResult(
	ctx context.Context,
	post *postmodel.Post,
	expectedVersion int64,
	commandName string,
	commandPayload any,
	eventType string,
	eventPayload any,
	occurredAt time.Time,
	commitOptions ...func(*postports.Commit),
) (*postmodel.Post, bool, error) {
	idempotencyKey := commandmeta.IdempotencyKey(ctx)
	if idempotencyKey == "" {
		return nil, false, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"idempotencyKey 必填",
			commandName+" requires Idempotency-Key",
		)
	}
	commandJSON, err := json.Marshal(commandPayload)
	if err != nil {
		return nil, false, contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error())
	}
	commandHash := sha256.Sum256(commandJSON)
	switch eventType {
	case "PostPublished", "PostUpdated", "PostSettingsUpdated", "PostPromotedToWork", "PostModerationRejected", "PostDeleted":
		source, ok := eventPayload.(map[string]any)
		if !ok {
			return nil, false, fmt.Errorf("Post lifecycle payload must be produced by owning mapper")
		}
		wire := make(map[string]any, len(source)+6)
		for key, value := range source {
			wire[key] = value
		}
		// 普通Post命令只拥有普通来源；Data行由persistence事务检查禁止降格覆盖。
		for _, key := range []string{"environment", "sourceOwner", "releaseId", "manifestDigest", "releaseDigest"} {
			if value, present := wire[key]; present && value != nil {
				return nil, false, fmt.Errorf("ordinary Post command cannot impersonate release source")
			}
			wire[key] = nil
		}
		wire["sourceVersion"] = expectedVersion + 1
		eventPayload = wire
	}
	eventJSON, err := json.Marshal(eventPayload)
	if err != nil {
		return nil, false, contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error())
	}
	events := []postports.OutboxEvent{}
	if eventType != "" {
		eventHash := sha256.Sum256([]byte(idempotencyKey + ":" + eventType))
		events = append(events, postports.OutboxEvent{
			EventID:          "evt_" + hex.EncodeToString(eventHash[:16]),
			EventType:        eventType,
			AggregateType:    "Post",
			AggregateID:      post.ID,
			AggregateVersion: expectedVersion + 1,
			Payload:          eventJSON,
			OccurredAt:       occurredAt,
		})
	}
	commit := postports.Commit{
		Post:             post,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    hex.EncodeToString(commandHash[:]),
		ReceiptExpiresAt: occurredAt.Add(24 * time.Hour),
		Events:           events,
	}
	if expectedVersion > 0 {
		if sourceReader, ok := s.store.ports.Aggregate.(postports.SourceMetadataReader); ok {
			metadata, err := sourceReader.LoadSourceMetadata(ctx, post.ID)
			if err != nil {
				return nil, false, err
			}
			commit.SourceMetadata = &metadata
		}
	}
	for _, option := range commitOptions {
		option(&commit)
	}
	result, err := s.store.ports.Aggregate.Commit(ctx, commit)
	if err != nil {
		return nil, false, err
	}
	if result.Post == nil {
		return nil, false, contentgenerated.AppErrorFromRequiredDependencyUnavailable(fmt.Sprintf("%s returned an empty aggregate", commandName))
	}
	return result.Post, result.Replayed, nil
}

func postContentDigest(post *postmodel.Post) string {
	if post == nil {
		return ""
	}
	contentJSON, _ := json.Marshal(struct {
		ContentType      string
		Title            string
		Body             string
		Summary          string
		MediaAssetIDs    []string
		ArticleMarkdown  string
		SemanticDocument semantic.DocumentEnvelope
		SemanticMentions []postmodel.PostSemanticMention
	}{
		ContentType:      post.ContentType,
		Title:            post.Title,
		Body:             post.Body,
		Summary:          post.Summary,
		MediaAssetIDs:    append([]string(nil), post.MediaAssetIds...),
		ArticleMarkdown:  post.ArticleMarkdown,
		SemanticDocument: post.SemanticDocument,
		SemanticMentions: post.SemanticMentions,
	})
	digest := sha256.Sum256(contentJSON)
	return "sha256:" + hex.EncodeToString(digest[:])
}
