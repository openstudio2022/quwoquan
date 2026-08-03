package post

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"time"

	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/runtime/commandmeta"
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
	idempotencyKey := commandmeta.IdempotencyKey(ctx)
	if idempotencyKey == "" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"idempotencyKey 必填",
			commandName+" requires Idempotency-Key",
		)
	}
	commandJSON, err := json.Marshal(commandPayload)
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleContent, "内容提交失败", err.Error())
	}
	commandHash := sha256.Sum256(commandJSON)
	eventJSON, err := json.Marshal(eventPayload)
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleContent, "内容事件生成失败", err.Error())
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
	for _, option := range commitOptions {
		option(&commit)
	}
	result, err := s.store.ports.Aggregate.Commit(ctx, commit)
	if err != nil {
		return nil, err
	}
	if result.Post == nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent,
			"内容提交失败",
			fmt.Sprintf("%s returned an empty aggregate", commandName),
		)
	}
	return result.Post, nil
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
		SemanticMentions []postmodel.PostSemanticMention
	}{
		ContentType:      post.ContentType,
		Title:            post.Title,
		Body:             post.Body,
		Summary:          post.Summary,
		MediaAssetIDs:    append([]string(nil), post.MediaAssetIds...),
		ArticleMarkdown:  post.ArticleMarkdown,
		SemanticMentions: post.SemanticMentions,
	})
	digest := sha256.Sum256(contentJSON)
	return "sha256:" + hex.EncodeToString(digest[:])
}
