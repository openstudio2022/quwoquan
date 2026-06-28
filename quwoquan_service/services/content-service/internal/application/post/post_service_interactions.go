package post

import (
	"context"
	"encoding/base64"
	"fmt"
	"go.opentelemetry.io/otel/attribute"
	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/content-service/internal/application/identity"
	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"sort"
	"strconv"
	"strings"
	"time"
)

func generateArticleSummary(title, body string) string {
	t := strings.TrimSpace(title)
	b := strings.TrimSpace(body)
	if b == "" {
		return t
	}
	if len(b) > 100 {
		b = b[:100]
	}
	if t == "" {
		return b
	}
	return t + "：" + b
}

func (s *PostService) GenerateArticleSummary(title, body string) string {
	return generateArticleSummary(title, body)
}

func (s *PostService) GetPostOrTombstone(ctx context.Context, postID string) (*postmodel.Post, bool, bool) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if ok {
		if strings.EqualFold(strings.TrimSpace(post.Status), "deleted") {
			return nil, false, true
		}
		return normalizePostForRead(post), true, false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	_, deleted := s.tombstones[strings.TrimSpace(postID)]
	return nil, false, deleted
}

func (s *PostService) GetPostForViewer(
	ctx context.Context,
	postID, viewerID string,
	viewerCircleIDs []string,
) (*postmodel.Post, bool, bool, bool) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.GetPostForViewer",
		attribute.String("post.id", postID))
	defer func() { rtobs.EndSpan(span, nil) }()
	post, ok, deleted := s.GetPostOrTombstone(ctx, postID)
	if !ok {
		return nil, false, deleted, false
	}
	if !canViewPost(post, viewerID, viewerCircleIDs) {
		return nil, false, false, true
	}
	return post, true, false, false
}

// LikePost 点赞（幂等 upsert）。actor 维度由 userID（账号）优先、否则 deviceActorID
// （隐私安全派生设备标识，游客设备维度）解析；账号维度与设备维度独立计数、不并账。
func (s *PostService) LikePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	actorKey := identity.ReactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[actorKey]
	changed := !state.Liked
	if changed {
		state.Liked = true
		byPost[actorKey] = state
		post.LikeCount++
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.LikeCount, changed, nil
}

// UnlikePost 取消点赞（幂等）。actor 维度解析与 LikePost 一致。
func (s *PostService) UnlikePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	actorKey := identity.ReactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[actorKey]
	changed := state.Liked
	if changed {
		state.Liked = false
		byPost[actorKey] = state
		if post.LikeCount > 0 {
			post.LikeCount--
		}
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.LikeCount, changed, nil
}

// GetReactionState 读取当前 actor 的互动状态。actor 维度由 userID（账号）优先、
// 否则 deviceActorID（游客设备维度）解析，使游客也能读回自身设备态点赞/分享。
func (s *PostService) GetReactionState(postID, userID, deviceActorID string) (liked, shared bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	normalizedPostID := strings.TrimSpace(postID)
	actorKey := identity.ReactionActorKey(userID, deviceActorID)
	shared = hasActiveShareForUser(s.reshares[normalizedPostID], actorKey)
	byPost, ok := s.reactions[normalizedPostID]
	if !ok {
		return false, shared
	}
	state, ok := byPost[actorKey]
	if !ok {
		return false, shared
	}
	return state.Liked, shared
}

func (s *PostService) ListProfileInteractionActivities(
	ctx context.Context,
	profileSubjectID string,
	viewerID string,
	direction string,
	cursor string,
	limit int,
) ([]postmodel.ProfileInteractionActivityView, string, bool, error) {
	profileSubjectID = strings.TrimSpace(profileSubjectID)
	viewerID = strings.TrimSpace(viewerID)
	direction = strings.TrimSpace(direction)
	if profileSubjectID == "" {
		return []postmodel.ProfileInteractionActivityView{}, "", false, nil
	}
	if direction == "" {
		direction = "received"
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > profileInteractionActivityMaxLimit {
		limit = profileInteractionActivityMaxLimit
	}

	// 点赞/转发仍为进程内互动：读锁内只做轻量快照（不触达外部 store、不构造投影）。
	refs := s.snapshotProfileInteractionRefs(profileSubjectID, direction)
	// 评论互动已迁出内存：经 commentStore 持久化读取（Mongo+Redis 或内存降级）。
	commentRefs, err := s.gatherCommentInteractionRefs(ctx, profileSubjectID, direction)
	if err != nil {
		return nil, "", false, err
	}
	refs = append(refs, commentRefs...)

	// viewer 对互动评论的真实三态反应：一次性批量解析（避免 N+1）。
	commentIDs := make([]string, 0, len(commentRefs))
	for _, ref := range commentRefs {
		if ref.commentModel != nil {
			commentIDs = append(commentIDs, ref.commentModel.ID)
		}
	}
	viewerReactions := map[string]commentdomain.Reaction{}
	if viewerID != "" && len(commentIDs) > 0 {
		if m, rerr := s.commentReactionStore.ReactionsForUser(ctx, viewerID, commentIDs); rerr == nil {
			viewerReactions = m
		} else {
			s.logger.Warn("ListProfileInteractionActivities: viewer reactions failed", "error", rerr.Error())
		}
	}

	// 按 postID 去重 hydrate（每条作品仅取一次），再投影 / 归属过滤 / 排序 / 截断。
	postCache := make(map[string]*postmodel.Post, len(refs))
	items := make([]postmodel.ProfileInteractionActivityView, 0, len(refs))
	for _, ref := range refs {
		post, cached := postCache[ref.postID]
		if !cached {
			post, _ = s.store.FindByID(ctx, ref.postID)
			postCache[ref.postID] = post
		}
		if post == nil {
			continue
		}
		if direction == "received" && post.AuthorId != profileSubjectID {
			continue
		}
		createdAt := post.UpdatedAt
		viewerReaction := ""
		if ref.activityType == "comment" && ref.commentModel != nil {
			createdAt = ref.commentModel.CreatedAt
			viewerReaction = string(viewerReactions[ref.commentModel.ID])
		}
		items = append(items, buildProfileInteractionActivityView(profileInteractionProjectionInput{
			ActivityID:         ref.activityID,
			ActivityType:       ref.activityType,
			Direction:          direction,
			ActorID:            ref.actorID,
			TargetSubAccountID: post.AuthorId,
			Post:               post,
			Comment:            ref.commentModel,
			ViewerReaction:     viewerReaction,
			CreatedAt:          createdAt,
		}))
	}

	// 稳定全序：先按 createdAt 倒序，并以 activityId 倒序做确定性 tiebreak（keyset 游标依赖确定全序）。
	sort.Slice(items, func(i, j int) bool {
		if !items[i].CreatedAt.Equal(items[j].CreatedAt) {
			return items[i].CreatedAt.After(items[j].CreatedAt)
		}
		return items[i].ActivityId > items[j].ActivityId
	})

	// keyset 游标：解析失败（空/损坏）等价于首页，不静默吞 token；不存在“截断丢弃尾部”旧缺陷。
	if cursorTime, cursorID, ok := decodeProfileInteractionCursor(cursor); ok {
		filtered := items[:0:0]
		for _, item := range items {
			if profileInteractionActivityAfterCursor(item, cursorTime, cursorID) {
				filtered = append(filtered, item)
			}
		}
		items = filtered
	}

	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	nextCursor := ""
	if hasMore && len(items) > 0 {
		last := items[len(items)-1]
		nextCursor = encodeProfileInteractionCursor(last.CreatedAt, last.ActivityId)
	}
	return items, nextCursor, hasMore, nil
}

// profileInteractionActivityMaxLimit clamp 上界（单页页大小）：杜绝调用方传入超大 limit 触发无界单页；
// 完整历史经 keyset 游标分页逐页拉取，不再以单页硬上限静默丢弃尾部。
const profileInteractionActivityMaxLimit = 50

// profileInteractionActivityGatherCap 物化候选集上界（内存护栏）：点赞/转发本就全量在内存，
// 评论经 commentStore 游标 drain 至该上界。深翻越界为极端长尾，受控且可观测，远优于旧 50 条静默截断。
const profileInteractionActivityGatherCap = 1000

// profileInteractionActivityAfterCursor 判定 item 是否严格落在游标之后（倒序全序下的“下一页”侧）。
func profileInteractionActivityAfterCursor(item postmodel.ProfileInteractionActivityView, cursorTime time.Time, cursorID string) bool {
	if item.CreatedAt.Before(cursorTime) {
		return true
	}
	if item.CreatedAt.Equal(cursorTime) {
		return item.ActivityId < cursorID
	}
	return false
}

// encodeProfileInteractionCursor 生成 opaque keyset token（createdAtUnixNano|activityId 的 base64）。
func encodeProfileInteractionCursor(createdAt time.Time, activityID string) string {
	raw := fmt.Sprintf("%d|%s", createdAt.UTC().UnixNano(), activityID)
	return base64.RawURLEncoding.EncodeToString([]byte(raw))
}

// decodeProfileInteractionCursor 解析 keyset token；空或损坏返回 ok=false（等价首页，不报错不吞默认）。
func decodeProfileInteractionCursor(cursor string) (time.Time, string, bool) {
	cursor = strings.TrimSpace(cursor)
	if cursor == "" {
		return time.Time{}, "", false
	}
	decoded, err := base64.RawURLEncoding.DecodeString(cursor)
	if err != nil {
		return time.Time{}, "", false
	}
	parts := strings.SplitN(string(decoded), "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", false
	}
	nanos, perr := strconv.ParseInt(parts[0], 10, 64)
	if perr != nil {
		return time.Time{}, "", false
	}
	return time.Unix(0, nanos).UTC(), parts[1], true
}

// profileInteractionRef 是轻量互动引用；不携带作品/投影，hydrate 推迟到后续阶段。
// 评论互动携带强类型评论模型（R04），点赞/转发互动不携带评论。
type profileInteractionRef struct {
	activityID   string
	activityType string
	actorID      string
	postID       string
	commentModel *postmodel.Comment
}

// gatherCommentInteractionRefs 经 commentStore 收集匹配方向的评论互动引用：
// sent = 主页主体发表的评论；received = 他人对主页主体作品发表的评论。
// 评论权威存储已迁出进程内存（R-CMT01），此处读取持久化层而非内存快照。
func (s *PostService) gatherCommentInteractionRefs(
	ctx context.Context,
	profileSubjectID string,
	direction string,
) ([]profileInteractionRef, error) {
	var comments []postmodel.Comment
	if direction == "sent" {
		drained, err := s.drainProfileInteractionComments(func(cursor string, limit int) (commentdomain.Page, error) {
			return s.commentStore.ListByAuthor(ctx, profileSubjectID, cursor, limit)
		})
		if err != nil {
			return nil, rterr.NewUnavailable(
				rterr.ModuleContent, "互动加载失败，请稍后重试", "gather sent comment interactions failed: "+err.Error(),
			)
		}
		comments = drained
	} else {
		authored := s.store.ListByAuthor(ctx, profileSubjectID, 10000, "")
		postIDs := make([]string, 0, len(authored))
		for _, p := range authored {
			postIDs = append(postIDs, p.ID)
		}
		if len(postIDs) == 0 {
			return nil, nil
		}
		drained, err := s.drainProfileInteractionComments(func(cursor string, limit int) (commentdomain.Page, error) {
			return s.commentStore.ListReceivedByPostAuthor(ctx, profileSubjectID, postIDs, cursor, limit)
		})
		if err != nil {
			return nil, rterr.NewUnavailable(
				rterr.ModuleContent, "互动加载失败，请稍后重试", "gather received comment interactions failed: "+err.Error(),
			)
		}
		comments = drained
	}
	refs := make([]profileInteractionRef, 0, len(comments))
	for i := range comments {
		c := comments[i]
		actorID := strings.TrimSpace(c.AuthorId)
		if !profileInteractionActorMatches(direction, actorID, profileSubjectID) {
			continue
		}
		model := c
		refs = append(refs, profileInteractionRef{
			activityID:   fmt.Sprintf("comment:%s", c.ID),
			activityType: "comment",
			actorID:      actorID,
			postID:       strings.TrimSpace(c.PostId),
			commentModel: &model,
		})
	}
	return refs, nil
}

// drainProfileInteractionComments 经评论存储游标逐页 drain 至物化上界（内存护栏），
// 供主页互动列表 keyset 分页物化稳定全序；替换旧的“单次 50 条 + 静默丢尾”读取。
func (s *PostService) drainProfileInteractionComments(
	fetch func(cursor string, limit int) (commentdomain.Page, error),
) ([]postmodel.Comment, error) {
	const batch = 100
	comments := make([]postmodel.Comment, 0, batch)
	cursor := ""
	for len(comments) < profileInteractionActivityGatherCap {
		page, err := fetch(cursor, batch)
		if err != nil {
			return nil, err
		}
		comments = append(comments, page.Comments...)
		if page.NextCursor == "" || len(page.Comments) == 0 {
			break
		}
		cursor = page.NextCursor
	}
	if len(comments) > profileInteractionActivityGatherCap {
		comments = comments[:profileInteractionActivityGatherCap]
	}
	return comments, nil
}

// snapshotProfileInteractionRefs 在读锁内收集匹配方向/主页主体的点赞/转发互动引用。
// 仅做内存遍历与方向侧（actor）过滤，不调用外部 post store；received 的作者归属在锁外
// hydrate 后再校验。评论互动改由 gatherCommentInteractionRefs 经持久化层收集。
func (s *PostService) snapshotProfileInteractionRefs(
	profileSubjectID string,
	direction string,
) []profileInteractionRef {
	s.mu.RLock()
	defer s.mu.RUnlock()

	refs := make([]profileInteractionRef, 0)

	for postID, byUser := range s.reactions {
		pid := strings.TrimSpace(postID)
		for actorID, state := range byUser {
			if !state.Liked {
				continue
			}
			if !profileInteractionActorMatches(direction, actorID, profileSubjectID) {
				continue
			}
			refs = append(refs, profileInteractionRef{
				activityID:   fmt.Sprintf("like:%s:%s", pid, actorID),
				activityType: "like",
				actorID:      actorID,
				postID:       pid,
			})
		}
	}

	for postID, shares := range s.reshares {
		pid := strings.TrimSpace(postID)
		for shareKey, active := range shares {
			if !active {
				continue
			}
			actorID := shareActorID(shareKey)
			if actorID == "" {
				continue
			}
			if !profileInteractionActorMatches(direction, actorID, profileSubjectID) {
				continue
			}
			refs = append(refs, profileInteractionRef{
				activityID:   fmt.Sprintf("share:%s:%s", pid, actorID),
				activityType: "share",
				actorID:      actorID,
				postID:       pid,
			})
		}
	}

	return refs
}

// profileInteractionActorMatches 仅做方向侧（actor）匹配：sent 要求 actor 即主页主体；
// received 要求 actor 非主页主体（作者归属在锁外 hydrate 后再校验）。
func profileInteractionActorMatches(direction, actorID, profileSubjectID string) bool {
	actorID = strings.TrimSpace(actorID)
	if direction == "sent" {
		return actorID == profileSubjectID
	}
	return actorID != profileSubjectID
}

func shareActorID(shareKey string) string {
	parts := strings.Split(strings.TrimSpace(shareKey), ":")
	if len(parts) == 0 {
		return ""
	}
	return strings.TrimSpace(parts[len(parts)-1])
}

// prepareCommentAttachments locks the in-memory media asset table only for the
// duration of attachment binding (asset table is the last in-process state).
