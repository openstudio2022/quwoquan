package post

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	rterr "quwoquan_service/runtime/errors"
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
		"schema":         "app_remote_config",
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
