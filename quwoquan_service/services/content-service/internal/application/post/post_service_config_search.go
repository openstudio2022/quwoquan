package post

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"go.opentelemetry.io/otel/attribute"
	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"strings"
	"time"
)

func (s *PostService) GetAppConfig() map[string]any {
	runtimeConfig := normalizeStoryRuntimeConfig(s.storyRuntime)
	canaryMatrix := make([]any, 0, len(runtimeConfig.CanaryMatrix))
	for _, stage := range runtimeConfig.CanaryMatrix {
		canaryMatrix = append(canaryMatrix, map[string]any{
			"stage":          stage.Stage,
			"rolloutPercent": stage.RolloutPercent,
		})
	}
	featureFlags := make(map[string]any, len(runtimeConfig.FeatureFlags))
	for key, value := range runtimeConfig.FeatureFlags {
		featureFlags[key] = value
	}
	payload := map[string]any{
		"schemaVersion":  "app_remote_config.v1",
		"packageVersion": "embedded-content-service",
		"fetchedAt":      time.Now().UTC().Format(time.RFC3339),
		"maxAgeSec":      21600,
		"activationPolicy": map[string]any{
			"default":       "next_session",
			"kill_switches": "immediate",
		},
		"content": map[string]any{
			"feature_flags": featureFlags,
			"gray_release": map[string]any{
				"experiment_bucket": runtimeConfig.ExperimentBucket,
				"current_stage":     runtimeConfig.CurrentStage,
				"canary_matrix":     canaryMatrix,
			},
		},
	}
	payload["configHash"] = appConfigHash(payload)
	return payload
}

func appConfigHash(payload map[string]any) string {
	clone := map[string]any{}
	for key, value := range payload {
		if key == "configHash" || key == "fetchedAt" {
			continue
		}
		clone[key] = value
	}
	data, _ := json.Marshal(clone)
	sum := sha256.Sum256(data)
	return "sha256:" + hex.EncodeToString(sum[:])
}

func (s *PostService) GetCounters(ctx context.Context, postID string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	// 评论数取 DB 权威 count（含二级、排除软删），与 ListComments.totalCount 同源；
	// post.CommentCount 仅作 feed/详情页去规范化加速器。读路径机会式自愈：发现加速器
	// 与权威 count 漂移时按权威值单 $set 收敛（无整文档改写），保证最终一致。
	if s.commentCounts == nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent,
			"互动计数加载失败，请稍后重试",
			"Comment CountReader is required",
		)
	}
	commentCount := post.CommentCount
	if n, err := s.commentCounts.CountByPost(ctx, post.ID); err == nil {
		commentCount = n
		if n != post.CommentCount {
			if _, serr := s.store.SetCommentCount(ctx, post.ID, n); serr != nil {
				s.logger.Warn("GetCounters: self-heal comment count failed", "postId", post.ID, "error", serr.Error())
			}
		}
	} else {
		s.logger.Warn("GetCounters: authoritative comment count failed", "postId", post.ID, "error", err.Error())
	}
	return map[string]any{
		"like":    post.LikeCount,
		"comment": commentCount,
		"share":   post.ShareCount,
	}, nil
}

type SearchPostsRequest struct {
	Query         string
	Identity      string
	RequestedType string
	CategoryID    string
	SubCategory   string
	Cursor        string
	Limit         int
}

func (s *PostService) SearchPosts(
	ctx context.Context,
	req SearchPostsRequest,
) ([]postmodel.PostSearchItemView, string, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.SearchPosts",
		attribute.String("search.query", req.Query),
		attribute.String("search.identity", req.Identity),
		attribute.String("search.requested_type", req.RequestedType))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	query := strings.TrimSpace(strings.ToLower(req.Query))
	expectedIdentity := normalizeRequestedIdentity(req.Identity)
	expectedType := normalizeRequestType(req.RequestedType)
	posts := s.store.ListPublished(ctx, limit*8, req.Cursor)
	type indexedPost struct {
		post        postmodel.Post
		categoryID  string
		subCategory string
		summary     string
		coverURL    string
	}
	index := map[string]indexedPost{}
	docs := make([]rtsearch.Document, 0, len(posts))
	for _, stored := range posts {
		post := *normalizePostForRead(&stored)
		postIdentity := strings.TrimSpace(strings.ToLower(post.ContentIdentity))
		if expectedIdentity != "" && postIdentity != expectedIdentity {
			continue
		}
		if expectedType != "" {
			viewType := mapContentTypeToViewType(post.ContentType)
			if expectedIdentity != "moment" && viewType != expectedType {
				continue
			}
		}
		summary := strings.TrimSpace(post.Summary)
		if summary == "" {
			summary = strings.TrimSpace(post.Body)
		}
		coverURL := strings.TrimSpace(post.CoverUrl)
		if coverURL == "" {
			coverURL = strings.TrimSpace(post.VideoUrl)
		}
		categoryID, subCategory := deriveSearchTopicCategories(
			asStringSlice(post.TagRefs),
			req.CategoryID,
			req.SubCategory,
		)
		index[post.ID] = indexedPost{
			post:        post,
			categoryID:  categoryID,
			subCategory: subCategory,
			summary:     summary,
			coverURL:    coverURL,
		}
		visibility := strings.TrimSpace(post.Visibility)
		if visibility == "" {
			visibility = "public"
		}
		docs = append(docs, rtsearch.Document{
			ObjectType:   rtsearch.ObjectTypeContentPost,
			ObjectID:     post.ID,
			Title:        post.Title,
			Summary:      strings.TrimSpace(post.Summary),
			Body:         post.Body,
			SourceDomain: "content",
			ContentType:  post.ContentType,
			Visibility:   visibility,
			BadgeLabel:   "内容",
			Popularity:   float64(post.LikeCount + post.CommentCount + post.ShareCount),
			Freshness:    post.PublishedAt,
			Fields: map[string]string{
				"tagRefs":           strings.Join(asStringSlice(post.TagRefs), " "),
				"entityRefs":        strings.Join(asStringSlice(post.EntityRefs), " "),
				"authorDisplayName": post.AuthorDisplayNameSnapshot,
				"locationName":      post.LocationName,
			},
		})
	}
	searchResp := rtsearch.Execute(rtsearch.Request{
		Query:       query,
		Mode:        rtsearch.ModeResult,
		ObjectTypes: []string{rtsearch.ObjectTypeContentPost},
		Limit:       limit,
	}, docs)
	results := make([]postmodel.PostSearchItemView, 0, len(searchResp.Hits))
	for _, hit := range searchResp.Hits {
		item, ok := index[hit.ObjectID]
		if !ok {
			continue
		}
		post := item.post
		results = append(results, postmodel.PostSearchItemView{
			PostId:            post.ID,
			ContentType:       post.ContentType,
			ContentIdentity:   post.ContentIdentity,
			Title:             post.Title,
			Summary:           item.summary,
			CoverUrl:          item.coverURL,
			AuthorId:          post.AuthorId,
			AuthorDisplayName: post.AuthorDisplayNameSnapshot,
			AuthorAvatarUrl:   post.AuthorAvatarUrlSnapshot,
			CategoryId:        item.categoryID,
			SubCategory:       item.subCategory,
			LikeCount:         post.LikeCount,
			HighlightText:     hit.Snippet,
			MatchedField:      normalizeSearchMatchedField(hit.MatchedField, post),
			PublishedAt:       post.PublishedAt,
		})
	}
	nextCursor := ""
	if len(results) == limit {
		nextCursor = results[len(results)-1].PostId
	}
	return results, nextCursor, nil
}

func deriveSearchTopicCategories(tagRefs []string, fallbackCategory string, fallbackSubCategory string) (string, string) {
	topics := make([]string, 0, 2)
	seen := map[string]struct{}{}
	addTopic := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		if _, ok := seen[value]; ok {
			return
		}
		seen[value] = struct{}{}
		topics = append(topics, value)
	}
	for _, raw := range tagRefs {
		tag := strings.Trim(strings.TrimSpace(raw), "/")
		if tag == "" {
			continue
		}
		parts := strings.Split(tag, "/")
		if len(parts) < 2 || !strings.EqualFold(strings.TrimSpace(parts[0]), "Topic") {
			continue
		}
		for _, part := range parts[1:] {
			addTopic(part)
			if len(topics) >= 2 {
				break
			}
		}
		if len(topics) >= 2 {
			break
		}
	}
	category := strings.TrimSpace(fallbackCategory)
	subCategory := strings.TrimSpace(fallbackSubCategory)
	if len(topics) > 0 {
		category = topics[0]
	}
	if len(topics) > 1 {
		subCategory = topics[1]
	}
	return category, subCategory
}
