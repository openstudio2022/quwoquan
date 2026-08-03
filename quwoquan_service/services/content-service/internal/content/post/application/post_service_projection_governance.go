package post

import (
	"context"
	"fmt"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	"quwoquan_service/runtime/commandmeta"
	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
	"strings"
	"time"
)

func (s *PostService) ApplySemanticMentionGovernanceEvent(
	ctx context.Context,
	event postsemantic.GovernanceEvent,
) (SemanticMentionReprojectionReport, error) {
	report := SemanticMentionReprojectionReport{
		CandidateID: strings.TrimSpace(event.CandidateID),
		Status:      strings.ToLower(strings.TrimSpace(event.Status)),
	}
	if err := postsemantic.ValidateGovernanceEvent(event); err != nil {
		return report, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"语义标注治理事件不合法",
			err.Error(),
		)
	}

	now := time.Now().UTC()
	posts, err := s.store.ListAll(ctx)
	if err != nil {
		return report, contentgenerated.AppErrorFromStorageReadFailed(err.Error())
	}
	for _, stored := range posts {
		updatedMentions, updatedCount, err := postsemantic.ApplyGovernanceEvent(
			stored.SemanticMentions,
			event,
		)
		if err != nil {
			return report, err
		}
		if updatedCount == 0 {
			continue
		}
		report.MatchedPosts++
		report.UpdatedMentions += updatedCount

		post := stored
		beforeEntityRefs := append([]string(nil), post.EntityRefs...)
		beforeTagRefs := append([]string(nil), post.TagRefs...)
		post.SemanticMentions = updatedMentions
		projectSemanticMentionRefs(&post)
		if !sameStringSet(beforeEntityRefs, post.EntityRefs) || !sameStringSet(beforeTagRefs, post.TagRefs) {
			report.ActiveReferenceChanges++
		}
		post.UpdatedAt = now
		if _, err := s.commitPostCommand(
			commandmeta.WithIdempotencyKey(
				ctx,
				semanticGovernanceIdempotencyKey(event, post.ID, post.Version),
			),
			&post,
			post.Version,
			"ApplySemanticMentionGovernanceEvent",
			map[string]any{
				"candidateId": event.CandidateID,
				"status":      event.Status,
				"postId":      post.ID,
				"version":     post.Version,
			},
			"PostUpdated",
			projectionPayloadForPost(&post),
			now,
		); err != nil {
			return report, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
				"语义标注回填失败",
				err.Error(),
			)
		}
	}
	return report, nil
}

func semanticGovernanceIdempotencyKey(
	event postsemantic.GovernanceEvent,
	postID string,
	version int64,
) string {
	return "post-semantic-governance:" + strings.TrimSpace(event.CandidateID) + ":" +
		strings.TrimSpace(event.Status) + ":" +
		strings.TrimSpace(postID) + ":" +
		fmt.Sprintf("%d", version)
}
