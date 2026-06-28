package post

import (
	"context"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/application/identity"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"strings"
	"time"
)

func (s *PostService) applyShareRecordLocked(
	ctx context.Context,
	post *postmodel.Post,
	shareKey string,
	userID string,
	active bool,
) (int64, bool, bool) {
	if post == nil {
		return 0, false, false
	}
	shares, ok := s.reshares[post.ID]
	if !ok {
		shares = map[string]bool{}
		s.reshares[post.ID] = shares
	}
	wasActive := shares[shareKey]
	changed := wasActive != active
	if changed {
		if active {
			shares[shareKey] = true
			post.ShareCount++
		} else {
			delete(shares, shareKey)
			if post.ShareCount > 0 {
				post.ShareCount--
			}
		}
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.ShareCount, changed, hasActiveShareForUser(shares, userID)
}

// SharePost 写入权威分享记录（幂等）。actor 维度由 userID（账号）优先、否则
// deviceActorID（游客设备维度）解析；账号维度与设备维度独立累加、不并账。
func (s *PostService) SharePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if strings.EqualFold(post.Status, "deleted") {
		return 0, false, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
		)
	}
	actorKey := identity.ReactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	shareCount, changed, shared := s.applyShareRecordLocked(
		ctx,
		post,
		directShareKey(actorKey),
		actorKey,
		true)
	s.mu.Unlock()
	return shareCount, changed, shared, nil
}

// UnsharePost 取消权威分享记录（幂等）。actor 维度解析与 SharePost 一致。
func (s *PostService) UnsharePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	actorKey := identity.ReactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	shareCount, changed, shared := s.applyShareRecordLocked(
		ctx,
		post,
		directShareKey(actorKey),
		actorKey,
		false)
	s.mu.Unlock()
	return shareCount, changed, shared, nil
}

func (s *PostService) RepostToCircle(ctx context.Context, postID, userID, circleID, quote string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if strings.EqualFold(post.Status, "deleted") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
		)
	}
	if !supportsCircleDistribution(post.Visibility) {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布到圈子前需设置为公开或圈内可见",
			"visibility must be public or circle_visible",
		)
	}
	circleID = strings.TrimSpace(circleID)
	if circleID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "圈子不能为空", "missing circleId")
	}
	if userID == "" {
		userID = identity.AnonymousFallbackSubAccountID
	}
	key := circleID + ":" + userID
	s.mu.Lock()
	shareCount, changed, _ := s.applyShareRecordLocked(
		ctx,
		post,
		key,
		userID,
		true)
	s.mu.Unlock()
	return map[string]any{
		"postId":         post.ID,
		"sourcePostId":   post.ID,
		"resharerUserId": userID,
		"circleId":       circleID,
		"quoteText":      strings.TrimSpace(quote),
		"type":           "moment",
		"shareCount":     shareCount,
		"changed":        changed,
	}, nil
}
