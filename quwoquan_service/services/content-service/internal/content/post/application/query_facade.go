package post

import (
	"context"
	"errors"
	"fmt"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	presentation "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	appports "quwoquan_service/services/content-service/internal/content/post/application/ports"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// PostQueryDependencies 是 canonical Post 查询 Facade 的显式装配输入。
// 其中没有 AggregateStore 或 CollectionReader：查询面不能回退到聚合扫描。
// Tombstones 承载删除保留期 410 语义（content.DeletedPostTombstone 具名读端口）。
// ViewerBlocks 消费 user 域 PersonaBlocked 事实投影，在服务端强制
// 「拉黑双方互不可见对方作品」；nil 表示装配缺失（fail-open 仅限测试组合）。
type PostQueryDependencies struct {
	Detail       postports.PostDetailReader
	Author       postports.AuthorPostReader
	Gathering    postports.GatheringPostReader
	SocialProof  appports.GatheringSocialProofProjectionReader
	Tombstones   postports.TombstoneReader
	ViewerBlocks postports.ViewerBlockReader
	ActiveSupply postports.ActiveSupplyReader
}

// PostQueryFacade 为 GetPost、ListUserPosts、ListPostsByGathering 提供
// 强类型查询入口。它只依赖显式 reader ports，供 handler/composition 直接装配。
type PostQueryFacade struct {
	detail       postports.PostDetailReader
	author       postports.AuthorPostReader
	gathering    postports.GatheringPostReader
	socialProof  appports.GatheringSocialProofProjectionReader
	tombstones   postports.TombstoneReader
	viewerBlocks postports.ViewerBlockReader
	activeSupply postports.ActiveSupplyReader
}

func NewPostQueryFacade(dependencies PostQueryDependencies) *PostQueryFacade {
	return &PostQueryFacade{
		detail:       dependencies.Detail,
		author:       dependencies.Author,
		gathering:    dependencies.Gathering,
		socialProof:  dependencies.SocialProof,
		tombstones:   dependencies.Tombstones,
		viewerBlocks: dependencies.ViewerBlocks,
		activeSupply: dependencies.ActiveSupply,
	}
}

func (f *PostQueryFacade) GetPost(
	ctx context.Context,
	query postports.PostDetailQuery,
) (postports.PostDetailSlice, error) {
	if query.PostID() == "" {
		return postports.PostDetailSlice{}, invalidPostQueryArgument("GetPost requires postId")
	}
	if f == nil || f.detail == nil {
		return postports.PostDetailSlice{}, postQueryReaderUnavailable("GetPost detail reader is not configured")
	}

	binding, err := f.admitPublicReleaseRead(ctx, "GetPost")
	if err != nil {
		return postports.PostDetailSlice{}, err
	}
	detail, found, err := f.findPostDetail(
		ctx,
		postports.NewPostDetailReadRequest(
			query.PostID(),
			binding.ActiveReleaseID,
			binding.ManifestDigest,
		),
	)
	if err != nil {
		return postports.PostDetailSlice{}, postQueryReadFailure("GetPost", err)
	}
	if found && strings.EqualFold(strings.TrimSpace(string(detail.Status)), "deleted") {
		// 软删文档仍在：保留期内按墓碑语义返回 410 content_deleted。
		return postports.PostDetailSlice{}, contentgenerated.AppErrorFromContentDeleted(
			"GetPost target was deleted by its author",
		)
	}
	if !found {
		if f.tombstones != nil {
			if _, deleted, tombstoneErr := f.tombstones.FindTombstone(
				ctx,
				string(query.PostID()),
			); tombstoneErr == nil && deleted {
				return postports.PostDetailSlice{}, contentgenerated.AppErrorFromContentDeleted(
					"GetPost target was deleted by its author",
				)
			}
		}
		return postports.PostDetailSlice{}, contentgenerated.AppErrorFromPostNotFound(
			"GetPost target is missing or not visible to viewer",
		)
	}
	if query.Viewer().IsAuthenticated() &&
		!query.Viewer().IsOwner(detail.AuthorPersonaID) &&
		f.viewerBlocks != nil {
		blocked, blockErr := f.viewerBlocks.IsBlockedBetween(
			ctx,
			query.Viewer().PersonaID(),
			detail.AuthorPersonaID,
		)
		if blockErr != nil {
			return postports.PostDetailSlice{}, postQueryReadFailure("GetPost", blockErr)
		}
		if blocked {
			// 详情读同样返回 not_found，避免向任一方泄露内容或拉黑关系存在性。
			return postports.PostDetailSlice{}, contentgenerated.AppErrorFromPostNotFound(
				"GetPost target is missing or not visible to viewer",
			)
		}
	}
	if !canViewerReadPostDetail(detail, query.Viewer()) {
		// 私有内容对外同样返回 not_found，避免把资源存在性暴露给未授权主体。
		return postports.PostDetailSlice{}, contentgenerated.AppErrorFromPostNotFound(
			"GetPost target is missing or not visible to viewer",
		)
	}
	// 能力判定排在可见性之后：presentation_unsupported 只描述「可见但这一版渲染
	// 不了」，不能替代 not_found/content_deleted，也不能泄露不可见对象的存在性。
	if err := admitPostDetailPresentation(
		detail,
		query.ClientPresentationContract(),
	); err != nil {
		return postports.PostDetailSlice{}, err
	}
	return detail, nil
}

// postDetailOpenSurface 是某个内容类型在详情面的目的面。它是 Content 自己的
// 呈现决定：图文/视频进沉浸面，文章进阅读器面。闭集外类型没有目的面。
func postDetailOpenSurface(
	contentType postports.ContentType,
) (presentation.ContentUiSurface, presentation.ContentType, bool) {
	switch strings.ToLower(strings.TrimSpace(string(contentType))) {
	case "image":
		return presentation.ContentUiSurfaceMediaImmersive, presentation.ContentTypeImage, true
	case "video":
		return presentation.ContentUiSurfaceMediaImmersive, presentation.ContentTypeVideo, true
	case "article":
		return presentation.ContentUiSurfaceArticleReader, presentation.ContentTypeArticle, true
	default:
		return "", "", false
	}
}

// admitPostDetailPresentation 判定已授权可见的详情能否在客户端声明的能力内打开。
// contract 为 nil 表示这条读路径不面向客户端渲染（内部 persisted query、SSR），
// 不做能力裁决；面向客户端的入口必须携带声明，不存在「未声明即全能力」。
func admitPostDetailPresentation(
	detail postports.PostDetailSlice,
	contract *presentation.ClientContentPresentationContract,
) error {
	if contract == nil {
		return nil
	}
	if err := admitClientPresentationContract(contract); err != nil {
		return err
	}
	surface, contentType, known := postDetailOpenSurface(detail.ContentType)
	if !known {
		return contentgenerated.AppErrorFromPresentationUnsupported(fmt.Sprintf(
			"GetPost target declares contentType %q, which has no client open surface",
			detail.ContentType,
		))
	}
	if !declaredMember(contract.ContentTypes, contentType) ||
		!declaredMember(contract.OpenSurfaces, surface) {
		return contentgenerated.AppErrorFromPresentationUnsupported(fmt.Sprintf(
			"GetPost target needs contentType %q on surface %q, which presentation contract %s does not declare",
			contentType,
			surface,
			contract.ContractDigest,
		))
	}
	return nil
}

// admitClientPresentationContract 服务端独立重算 canonical digest 并与自报值
// 比较。非法成员、重复成员或伪造摘要都是非法入参，不允许退回固定基线继续读。
func admitClientPresentationContract(
	contract *presentation.ClientContentPresentationContract,
) error {
	if contract == nil {
		return nil
	}
	if err := presentation.ValidateClientContentPresentationContract(*contract); err != nil {
		return invalidPostQueryArgument(
			"client presentation contract is invalid: " + err.Error(),
		)
	}
	return nil
}

func declaredMember[member comparable](declared []member, value member) bool {
	for _, candidate := range declared {
		if candidate == value {
			return true
		}
	}
	return false
}

// GetHelperRead 只从具名 Post detail projection 读取公开文章。公开端点必须
// 与 GetPost 共享 published/public/approved 门禁，避免按可猜测 ID 读取私有、
// 待审核或已删除内容。
func (f *PostQueryFacade) GetHelperRead(
	ctx context.Context,
	postID string,
) (postports.HelperReadSlice, error) {
	canonicalPostID := postports.PostID(strings.TrimSpace(postID))
	if canonicalPostID == "" {
		return postports.HelperReadSlice{}, contentgenerated.AppErrorFromPostNotFound(
			"GetHelperRead target is missing or not visible",
		)
	}
	if f == nil || f.detail == nil {
		return postports.HelperReadSlice{}, postQueryReaderUnavailable(
			"GetHelperRead detail reader is not configured",
		)
	}

	binding, err := f.admitPublicReleaseRead(
		ctx,
		"GetHelperRead",
	)
	if err != nil {
		return postports.HelperReadSlice{}, err
	}
	detail, found, err := f.findPostDetail(
		ctx,
		postports.NewPostDetailReadRequest(
			canonicalPostID,
			binding.ActiveReleaseID,
			binding.ManifestDigest,
		),
	)
	if err != nil {
		return postports.HelperReadSlice{}, postQueryReadFailure("GetHelperRead", err)
	}
	if !found ||
		!canViewerReadPostDetail(detail, postports.ViewerContext{}) ||
		!strings.EqualFold(strings.TrimSpace(string(detail.ContentType)), "article") {
		return postports.HelperReadSlice{}, contentgenerated.AppErrorFromPostNotFound(
			"GetHelperRead target is missing or not visible",
		)
	}

	summary := strings.TrimSpace(detail.HelperReadSummary)
	if summary == "" {
		summary = strings.TrimSpace(detail.Summary)
	}
	if summary == "" {
		summary = truncateTextRunes(strings.TrimSpace(detail.Body), 200)
	}
	return postports.HelperReadSlice{
		PostID:      detail.PostID,
		ContentType: detail.ContentType,
		Title:       detail.Title,
		Summary:     summary,
	}, nil
}

func (f *PostQueryFacade) ListUserPosts(
	ctx context.Context,
	query postports.AuthorPostPageQuery,
) (postports.AuthorPostPageSlice, error) {
	if query.AuthorPersonaID() == "" {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(
			"ListUserPosts requires author persona",
		)
	}
	if f == nil || f.author == nil {
		return postports.AuthorPostPageSlice{}, postQueryReaderUnavailable(
			"ListUserPosts author reader is not configured",
		)
	}
	binding, err := f.admitPublicReleaseRead(
		ctx,
		"ListUserPosts",
	)
	if err != nil {
		return postports.AuthorPostPageSlice{}, err
	}

	limit, err := normalizePostQueryLimit(query.Limit())
	if err != nil {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(err.Error())
	}
	contentType, err := normalizePostQueryContentType(query.ContentType())
	if err != nil {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(err.Error())
	}
	visibility, err := normalizePostQueryVisibility(query.Visibility())
	if err != nil {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(err.Error())
	}
	cursor, err := postports.ParseAuthorPostCursor(query.Cursor())
	if err != nil {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(
			"ListUserPosts cursor is invalid",
		)
	}

	accessScope := postports.AuthorPostAccessPublic
	if query.Viewer().IsOwner(query.AuthorPersonaID()) {
		accessScope = postports.AuthorPostAccessOwner
	} else if visibility == postports.PostVisibility("private") {
		return postports.AuthorPostPageSlice{}, contentgenerated.AppErrorFromUnauthorized(
			"ListUserPosts non-owner requested non-public visibility",
		)
	}
	if accessScope == postports.AuthorPostAccessPublic &&
		f.viewerBlocks != nil && query.Viewer().IsAuthenticated() {
		blocked, blockErr := f.viewerBlocks.IsBlockedBetween(
			ctx,
			query.Viewer().PersonaID(),
			query.AuthorPersonaID(),
		)
		if blockErr != nil {
			return postports.AuthorPostPageSlice{}, postQueryReadFailure("ListUserPosts", blockErr)
		}
		if blocked {
			// 拉黑双方在作者主页读路径互不可见：返回空页而不是 403，
			// 避免把 block 关系的存在性泄露给被拉黑方。
			return postports.AuthorPostPageSlice{
				Items:   []postports.AuthorPostItemSlice{},
				HasMore: false,
			}, nil
		}
	}

	// 有效能力摘要进入 cursor scope：客户端换一份能力声明后旧续页立即失配，
	// 不会把按另一种能力算出的 keyset 位置当成本次请求的进度。
	presentationDigest := ""
	if contract := query.ClientPresentationContract(); contract != nil {
		if contractErr := admitClientPresentationContract(contract); contractErr != nil {
			return postports.AuthorPostPageSlice{}, contractErr
		}
		presentationDigest = contract.ContractDigest
	}
	unpagedRequest := postports.NewAuthorPostReadRequest(
		query.AuthorPersonaID(),
		accessScope,
		contentType,
		visibility,
		postports.AuthorPostCursor{},
		limit,
		binding.ActiveReleaseID,
		binding.ManifestDigest,
	).WithClientPresentationContractDigest(presentationDigest)
	if cursor.IsSet() && cursor.Scope() != unpagedRequest.CursorScope() {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(
			"ListUserPosts cursor does not match query",
		)
	}
	request := postports.NewAuthorPostReadRequest(
		query.AuthorPersonaID(),
		accessScope,
		contentType,
		visibility,
		cursor,
		limit,
		binding.ActiveReleaseID,
		binding.ManifestDigest,
	).WithClientPresentationContractDigest(presentationDigest)

	page, err := f.author.ListAuthorPosts(ctx, request)
	if err != nil {
		return postports.AuthorPostPageSlice{}, postQueryReadFailure("ListUserPosts", err)
	}
	if err := validateAuthorPostPage(page, request); err != nil {
		return postports.AuthorPostPageSlice{}, postQueryReadFailure("ListUserPosts", err)
	}
	return page, nil
}

// ListPostsByGathering 是行动详情共同经历聚合区的公开读入口。
// 只返回 public + published + approved 且作者主动写入 gatheringRef 的内容；
// 作者删除或转私密即从聚合区消失，无 viewer 私有分支。
func (f *PostQueryFacade) ListPostsByGathering(
	ctx context.Context,
	query postports.GatheringPostPageQuery,
) (postports.GatheringPostPageSlice, error) {
	if query.GatheringID() == "" {
		return postports.GatheringPostPageSlice{}, invalidPostQueryArgument(
			"ListPostsByGathering requires gatheringId",
		)
	}
	if f == nil || f.gathering == nil {
		return postports.GatheringPostPageSlice{}, postQueryReaderUnavailable(
			"ListPostsByGathering gathering reader is not configured",
		)
	}
	binding, err := f.admitPublicReleaseRead(
		ctx,
		"ListPostsByGathering",
	)
	if err != nil {
		return postports.GatheringPostPageSlice{}, err
	}
	limit, err := normalizePostQueryLimit(query.Limit())
	if err != nil {
		return postports.GatheringPostPageSlice{}, invalidPostQueryArgument(err.Error())
	}
	cursor, err := postports.ParseAuthorPostCursor(query.Cursor())
	if err != nil {
		return postports.GatheringPostPageSlice{}, invalidPostQueryArgument(
			"ListPostsByGathering cursor is invalid",
		)
	}
	unpagedRequest := postports.NewGatheringPostReadRequest(
		query.GatheringID(),
		postports.AuthorPostCursor{},
		limit,
		binding.ActiveReleaseID,
		binding.ManifestDigest,
	)
	if cursor.IsSet() && cursor.Scope() != unpagedRequest.CursorScope() {
		return postports.GatheringPostPageSlice{}, invalidPostQueryArgument(
			"ListPostsByGathering cursor does not match query",
		)
	}
	request := postports.NewGatheringPostReadRequest(
		query.GatheringID(),
		cursor,
		limit,
		binding.ActiveReleaseID,
		binding.ManifestDigest,
	)
	page, err := f.gathering.ListGatheringPosts(ctx, request)
	if err != nil {
		return postports.GatheringPostPageSlice{}, postQueryReadFailure(
			"ListPostsByGathering",
			err,
		)
	}
	return page, nil
}

// PublicPostIDLister 是 sitemap 的持久化窄端口；release admission 与
// 具体 Mongo filter 仍分别由 application 和 infrastructure 持有。
type PublicPostIDLister interface {
	ListPublicPostIDs(
		ctx context.Context,
		limit int,
		activeReleaseBinding ...string,
	) ([]string, error)
}

func (f *PostQueryFacade) findPostDetail(
	ctx context.Context,
	request postports.PostDetailReadRequest,
) (postports.PostDetailSlice, bool, error) {
	if releaseBound, ok := f.detail.(postports.ReleaseBoundPostDetailReader); ok {
		return releaseBound.FindReleaseBoundPostDetail(ctx, request)
	}
	if request.ActiveReleaseID() != "" || request.ManifestDigest() != "" {
		return postports.PostDetailSlice{}, false, errors.New(
			"Post detail reader cannot enforce active release binding",
		)
	}
	return f.detail.FindPostDetail(ctx, request.PostID())
}

func (f *PostQueryFacade) ListPublicPostIDs(
	ctx context.Context,
	lister PublicPostIDLister,
	limit int,
) ([]string, error) {
	if lister == nil {
		return nil, postQueryReaderUnavailable("sitemap post reader is not configured")
	}
	binding, err := f.admitPublicReleaseRead(
		ctx,
		"ListPublicPostIDs",
	)
	if err != nil {
		return nil, err
	}
	ids, err := lister.ListPublicPostIDs(
		ctx,
		limit,
		binding.ActiveReleaseID,
		binding.ManifestDigest,
	)
	if err != nil {
		return nil, postQueryReadFailure("ListPublicPostIDs", err)
	}
	return ids, nil
}

func (f *PostQueryFacade) admitPublicReleaseRead(
	ctx context.Context,
	operation string,
) (postports.ActiveSupplySnapshot, error) {
	if f == nil {
		return postports.ActiveSupplySnapshot{}, postQueryReaderUnavailable(
			operation + " query facade is not configured",
		)
	}
	if f.activeSupply == nil {
		return postports.ActiveSupplySnapshot{}, nil
	}
	snapshot, err := f.activeSupply.ActiveSupplySnapshot(ctx)
	if err != nil {
		return postports.ActiveSupplySnapshot{}, postQueryReadFailure(operation, err)
	}
	if snapshot.IsEmpty() {
		return snapshot, nil
	}
	if !snapshot.ReleaseBoundReadbackReady() {
		return postports.ActiveSupplySnapshot{}, postQueryReaderUnavailable(
			operation + " active release binding is inconsistent",
		)
	}
	return snapshot, nil
}

var allowedSocialProofAnchors = map[string]struct{}{
	"organizer": {},
	"entity":    {},
	"content":   {},
	"creator":   {},
}

// GetGatheringSocialProof 是四锚点两级诚实社会证明的 App 代理读面：
// 计数由 recommendation 聚合投影派生，Content 只透传不落副本。
func (f *PostQueryFacade) GetGatheringSocialProof(
	ctx context.Context,
	anchorKind string,
	objectID string,
) (appports.GatheringSocialProofSummary, error) {
	normalizedAnchor := strings.TrimSpace(anchorKind)
	normalizedObject := strings.TrimSpace(objectID)
	if _, allowed := allowedSocialProofAnchors[normalizedAnchor]; !allowed ||
		normalizedObject == "" {
		return appports.GatheringSocialProofSummary{}, invalidPostQueryArgument(
			"GetGatheringSocialProof anchorKind or objectId is invalid",
		)
	}
	if f == nil || f.socialProof == nil {
		return appports.GatheringSocialProofSummary{}, postQueryReaderUnavailable(
			"GetGatheringSocialProof reader is not configured",
		)
	}
	summary, err := f.socialProof.GetGatheringSocialProof(
		ctx,
		normalizedAnchor,
		normalizedObject,
	)
	if err != nil {
		return appports.GatheringSocialProofSummary{}, postQueryReadFailure(
			"GetGatheringSocialProof",
			err,
		)
	}
	return summary, nil
}

func canViewerReadPostDetail(
	detail postports.PostDetailSlice,
	viewer postports.ViewerContext,
) bool {
	if strings.EqualFold(strings.TrimSpace(string(detail.Status)), "deleted") {
		return false
	}
	if viewer.IsOwner(detail.AuthorPersonaID) {
		return true
	}
	if !strings.EqualFold(strings.TrimSpace(detail.ModerationStatus), "approved") {
		return false
	}
	if !strings.EqualFold(strings.TrimSpace(string(detail.Status)), "published") {
		return false
	}

	return postports.PostVisibility(strings.ToLower(strings.TrimSpace(string(detail.Visibility)))) ==
		postports.PostVisibility("public")
}

func validateAuthorPostPage(
	page postports.AuthorPostPageSlice,
	request postports.AuthorPostReadRequest,
) error {
	for _, item := range page.Items {
		if item.AuthorPersonaID != request.AuthorPersonaID() {
			return errors.New("author post reader returned item for another persona")
		}
		if request.AccessScope() == postports.AuthorPostAccessOwner {
			continue
		}
		if !strings.EqualFold(strings.TrimSpace(string(item.Status)), "published") {
			return errors.New("non-owner author post reader returned unpublished item")
		}
		if postports.PostVisibility(strings.ToLower(strings.TrimSpace(string(item.Visibility)))) !=
			postports.PostVisibility("public") {
			return errors.New("author post reader returned item outside public visibility scope")
		}
	}
	return nil
}

func normalizePostQueryLimit(limit int) (int, error) {
	switch {
	case limit == 0:
		return postports.DefaultPostQueryPageSize, nil
	case limit < 0:
		return 0, errors.New("query limit must be positive")
	case limit > postports.MaxPostQueryPageSize:
		return 0, errors.New("query limit exceeds maximum")
	default:
		return limit, nil
	}
}

// normalizePostQueryContentType 只接受 canonical ContentType 闭集。展示别名
// （photo/note）与退役成员（micro）一律 fail-closed，读侧不翻译第二套词汇。
func normalizePostQueryContentType(
	value postports.ContentType,
) (postports.ContentType, error) {
	normalized := strings.ToLower(strings.TrimSpace(string(value)))
	if normalized == "" {
		return "", nil
	}
	if _, allowed := contentgenerated.AllowedContentTypes[normalized]; !allowed {
		return "", errors.New("content type is unsupported")
	}
	return postports.ContentType(normalized), nil
}

func normalizePostQueryVisibility(
	value postports.PostVisibility,
) (postports.PostVisibility, error) {
	switch strings.ToLower(strings.TrimSpace(string(value))) {
	case "":
		return "", nil
	case "public", "private":
		return postports.PostVisibility(strings.ToLower(strings.TrimSpace(string(value)))), nil
	default:
		return "", errors.New("visibility is unsupported")
	}
}

func invalidPostQueryArgument(debugMessage string) error {
	return contentgenerated.AppErrorFromInvalidArgument(debugMessage).WithContextAttributes(
		rterr.RuntimeErrorContextAttribute{Key: "facet", Value: "PostQueryFacade"},
	)
}

func postQueryReaderUnavailable(debugMessage string) error {
	return contentgenerated.AppErrorFromRequiredDependencyUnavailable(debugMessage).WithContextAttributes(
		rterr.RuntimeErrorContextAttribute{Key: "facet", Value: "PostQueryFacade"},
	)
}

func postQueryReadFailure(operation string, err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromStorageReadFailed(
		"PostQueryFacade "+operation+" reader failed: "+err.Error(),
	).WithContextAttributes(
		rterr.RuntimeErrorContextAttribute{Key: "facet", Value: "PostQueryFacade"},
		rterr.RuntimeErrorContextAttribute{Key: "operation", Value: operation},
	)
}
