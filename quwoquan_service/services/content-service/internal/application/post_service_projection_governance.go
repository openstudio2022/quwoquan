package application

import (
	"context"
	rterr "quwoquan_service/runtime/errors"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
	"strings"
	"time"
)

func (s *PostService) GetHelperRead(ctx context.Context, postID string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if strings.TrimSpace(post.ContentType) != "article" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"仅支持文章类型的辅助阅读",
			"helper-read only for articles",
		)
	}
	summary := post.Summary
	if summary == "" {
		body := strings.TrimSpace(post.Body)
		if len(body) > 200 {
			body = body[:200]
		}
		summary = body
	}
	return map[string]any{
		"postId":      post.ID,
		"contentType": post.ContentType,
		"title":       post.Title,
		"summary":     summary,
	}, nil
}

func (s *PostService) RebuildProjectionDryRun(
	ctx context.Context,
	apply bool,
) (ProjectionRebuildReport, error) {
	report := ProjectionRebuildReport{DryRun: !apply}
	posts := s.store.ListAll(ctx)
	now := time.Now().UTC()
	for _, stored := range posts {
		rawIdentity := strings.TrimSpace(strings.ToLower(stored.ContentIdentity))
		rawAssistantUsePolicy := strings.TrimSpace(strings.ToLower(stored.AssistantUsePolicy))
		rawEntityRefs := append([]string(nil), stored.EntityRefs...)
		rawTagRefs := append([]string(nil), stored.TagRefs...)
		post := normalizePostForRead(&stored)
		if post == nil {
			continue
		}
		if postsemantic.Present(stored.SemanticMentions) {
			report.SemanticMentionPosts++
			projection := postsemantic.Project(stored.SemanticMentions)
			report.InvalidPublishedMentions += projection.InvalidPublishedCount
			if !sameStringSet(rawEntityRefs, post.EntityRefs) || !sameStringSet(rawTagRefs, post.TagRefs) {
				report.ActiveReferenceChanges++
			}
		}
		report.TotalPosts++
		switch strings.TrimSpace(strings.ToLower(post.Status)) {
		case "deleted":
			report.DeletedPosts++
		case "published":
			report.PublishedPosts++
		default:
			report.DraftPosts++
		}
		switch normalizeVisibility(post.Visibility) {
		case "private":
			report.PrivatePosts++
		case "circle_visible":
			report.CircleVisiblePosts++
		default:
			report.PublicPosts++
		}
		if rawIdentity == "" {
			report.BackfilledContentIdentity++
		}
		if rawAssistantUsePolicy == "" {
			report.BackfilledAssistantUsePolicy++
		}
		if strings.EqualFold(post.AssistantUsePolicy, "exclude") {
			report.AssistantExcludedPosts++
		}
		if strings.EqualFold(post.Status, "published") && normalizeVisibility(post.Visibility) == "public" {
			report.DiscoveryEligiblePosts++
		} else {
			report.DiscoveryRevokedPosts++
		}
		if !apply {
			continue
		}
		if postsemantic.Present(stored.SemanticMentions) &&
			(!sameStringSet(rawEntityRefs, post.EntityRefs) || !sameStringSet(rawTagRefs, post.TagRefs)) {
			post.UpdatedAt = now
			if !s.store.Update(ctx, post.ID, post) {
				return report, rterr.NewAppError(
					rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
					"语义引用回填失败",
					"post disappeared while rebuilding semantic mention projection",
				)
			}
		}
		eventType := projectionEventTypeForPost(post)
		s.projectPostEvent(ctx, eventType, post, projectionPayloadForPost(post), now)
	}
	return report, nil
}

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
	for _, stored := range s.store.ListAll(ctx) {
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
		if !s.store.Update(ctx, post.ID, &post) {
			return report, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
				"语义标注回填失败",
				"post disappeared while applying semantic mention governance event",
			)
		}

		payload := projectionPayloadForPost(&post)
		s.publishPostEvent(ctx, "PostUpdated", &post, payload, now)
		s.projectPostEvent(ctx, projectionEventTypeForPost(&post), &post, payload, now)
	}
	return report, nil
}
