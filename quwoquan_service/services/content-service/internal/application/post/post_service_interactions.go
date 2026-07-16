package post

import (
	"context"
	"encoding/base64"
	"fmt"
	rterr "quwoquan_service/runtime/errors"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	postdomain "quwoquan_service/services/content-service/internal/domain/post"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
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

	// 点赞来自 ContentReaction 权威聚合的公开 persona Slice；分享来自
	// OutboundShareFact 消费者维护的耐久 projection。两者都禁止回退进程内状态。
	reactionRefs, err := s.gatherReactionInteractionRefs(ctx, profileSubjectID, direction)
	if err != nil {
		return nil, "", false, err
	}
	shareRefs, err := s.gatherShareInteractionRefs(ctx, profileSubjectID, direction)
	if err != nil {
		return nil, "", false, err
	}
	refs := append(reactionRefs, shareRefs...)
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
	viewerReactions := map[string]reactiondomain.Value{}
	if viewerID != "" && len(commentIDs) > 0 {
		if s.commentReactionValues == nil {
			return nil, "", false, rterr.NewUnavailable(
				rterr.ModuleContent, "互动加载失败，请稍后重试", "CommentReactionValueReader is required",
			)
		}
		viewerActor, actorErr := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, viewerID)
		if actorErr != nil {
			return nil, "", false, rterr.NewInvalidArgument(rterr.ModuleContent, "互动身份无效", actorErr.Error())
		}
		if m, rerr := s.commentReactionValues.ReadCommentReactionValues(ctx, viewerActor, commentIDs); rerr == nil {
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
		if !ref.occurredAt.IsZero() {
			createdAt = ref.occurredAt
		}
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
	occurredAt   time.Time
	commentModel *commentmodel.ReadModel
}

func (s *PostService) gatherReactionInteractionRefs(
	ctx context.Context,
	profileSubjectID string,
	direction string,
) ([]profileInteractionRef, error) {
	if s.reactionActivityReader == nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent,
			"互动加载失败，请稍后重试",
			"ContentReaction profile activity reader is required",
		)
	}
	actorID := ""
	if direction == "sent" {
		actorID = profileSubjectID
	}
	slices, err := s.reactionActivityReader.ListActiveProfileReactions(
		ctx,
		actorID,
		profileInteractionActivityGatherCap,
	)
	if err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent,
			"互动加载失败，请稍后重试",
			"gather ContentReaction profile activities failed: "+err.Error(),
		)
	}
	refs := make([]profileInteractionRef, 0, len(slices))
	for _, slice := range slices {
		if !profileInteractionActorMatches(direction, slice.ActorID, profileSubjectID) {
			continue
		}
		refs = append(refs, profileInteractionRef{
			activityID:   "like:" + strings.TrimSpace(slice.ReactionID),
			activityType: "like",
			actorID:      strings.TrimSpace(slice.ActorID),
			postID:       strings.TrimSpace(slice.PostID),
			occurredAt:   slice.OccurredAt.UTC(),
		})
	}
	return refs, nil
}

// gatherCommentInteractionRefs 经 commentStore 收集匹配方向的评论互动引用：
// sent = 主页主体发表的评论；received = 他人对主页主体作品发表的评论。
// 评论权威存储已迁出进程内存（R-CMT01），此处读取持久化层而非内存快照。
func (s *PostService) gatherCommentInteractionRefs(
	ctx context.Context,
	profileSubjectID string,
	direction string,
) ([]profileInteractionRef, error) {
	if s.commentAuthorPage == nil || s.commentReceivedPage == nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "互动加载失败，请稍后重试", "Comment profile readers are required",
		)
	}
	var comments []commentmodel.ReadModel
	if direction == "sent" {
		drained, err := s.drainProfileInteractionComments(func(cursor string, limit int) (commentmodel.Page, error) {
			return s.commentAuthorPage.ListByAuthor(
				ctx, profileSubjectID, commentports.PageRequest{Cursor: cursor, Limit: limit},
			)
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
		drained, err := s.drainProfileInteractionComments(func(cursor string, limit int) (commentmodel.Page, error) {
			return s.commentReceivedPage.ListReceivedByPostAuthor(
				ctx, profileSubjectID, postIDs,
				commentports.PageRequest{Cursor: cursor, Limit: limit},
			)
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
		actorID := strings.TrimSpace(c.AuthorID)
		if !profileInteractionActorMatches(direction, actorID, profileSubjectID) {
			continue
		}
		model := c
		refs = append(refs, profileInteractionRef{
			activityID:   fmt.Sprintf("comment:%s", c.ID),
			activityType: "comment",
			actorID:      actorID,
			postID:       strings.TrimSpace(c.PostID),
			occurredAt:   c.CreatedAt.UTC(),
			commentModel: &model,
		})
	}
	return refs, nil
}

// drainProfileInteractionComments 经评论存储游标逐页 drain 至物化上界（内存护栏），
// 供主页互动列表 keyset 分页物化稳定全序；替换旧的“单次 50 条 + 静默丢尾”读取。
func (s *PostService) drainProfileInteractionComments(
	fetch func(cursor string, limit int) (commentmodel.Page, error),
) ([]commentmodel.ReadModel, error) {
	const batch = 100
	comments := make([]commentmodel.ReadModel, 0, batch)
	cursor := ""
	for len(comments) < profileInteractionActivityGatherCap {
		page, err := fetch(cursor, batch)
		if err != nil {
			return nil, err
		}
		comments = append(comments, page.Items...)
		if page.NextCursor == "" || len(page.Items) == 0 {
			break
		}
		cursor = page.NextCursor
	}
	if len(comments) > profileInteractionActivityGatherCap {
		comments = comments[:profileInteractionActivityGatherCap]
	}
	return comments, nil
}

func (s *PostService) gatherShareInteractionRefs(
	ctx context.Context,
	profileSubjectID string,
	direction string,
) ([]profileInteractionRef, error) {
	if s.shareInteractionStore == nil {
		return nil, contentgenerated.AppErrorFromInteractionReadModelUnavailable(
			"OutboundShareFact interaction projection is not configured",
		)
	}
	occurrences, _, err := s.shareInteractionStore.List(ctx, postdomain.ShareInteractionQuery{
		SubAccountID: strings.TrimSpace(profileSubjectID),
		Direction:    direction,
		Limit:        profileInteractionActivityGatherCap,
	})
	if err != nil {
		return nil, contentgenerated.AppErrorFromInteractionReadModelUnavailable(err.Error())
	}
	refs := make([]profileInteractionRef, 0, len(occurrences))
	for _, item := range occurrences {
		refs = append(refs, profileInteractionRef{
			activityID: item.InteractionID, activityType: "share",
			actorID: item.ActorSubAccountID, postID: item.TargetContentID,
			occurredAt: item.OccurredAt,
		})
	}
	return refs, nil
}

// profileInteractionActorMatches 仅做方向侧（actor）匹配：sent 要求 actor 即主页主体；
// received 要求 actor 非主页主体（作者归属在锁外 hydrate 后再校验）。
func profileInteractionActorMatches(direction, actorID, profileSubjectID string) bool {
	actorID = strings.TrimSpace(actorID)
	if direction == "sent" {
		return actorID == strings.TrimSpace(profileSubjectID)
	}
	return actorID != strings.TrimSpace(profileSubjectID)
}

// prepareCommentAttachments locks the in-memory media asset table only for the
// duration of attachment binding (asset table is the last in-process state).
