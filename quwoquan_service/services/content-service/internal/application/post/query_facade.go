package post

import (
	"context"
	"errors"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

// PostQueryDependencies 是 canonical Post 查询 Facade 的显式装配输入。
// 其中没有 AggregateStore 或 CollectionReader：查询面不能回退到聚合扫描。
type PostQueryDependencies struct {
	Detail postports.PostDetailReader
	Author postports.AuthorPostReader
	Search postports.PostSearchReader
}

// PostQueryFacade 为 GetPost、ListUserPosts、SearchPosts 提供强类型查询入口。
// 它只依赖显式 reader ports，供 handler/composition 直接装配。
type PostQueryFacade struct {
	detail postports.PostDetailReader
	author postports.AuthorPostReader
	search postports.PostSearchReader
}

func NewPostQueryFacade(dependencies PostQueryDependencies) *PostQueryFacade {
	return &PostQueryFacade{
		detail: dependencies.Detail,
		author: dependencies.Author,
		search: dependencies.Search,
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

	detail, found, err := f.detail.FindPostDetail(ctx, query.PostID())
	if err != nil {
		return postports.PostDetailSlice{}, postQueryReadFailure("GetPost", err)
	}
	if !found {
		return postports.PostDetailSlice{}, contentgenerated.AppErrorFromPostNotFound(
			"GetPost target is missing, deleted, or not visible to viewer",
		)
	}
	if !canViewerReadPostDetail(detail, query.Viewer()) {
		// 私有内容对外同样返回 not_found，避免把资源存在性暴露给未授权主体。
		return postports.PostDetailSlice{}, contentgenerated.AppErrorFromPostNotFound(
			"GetPost target is missing, deleted, or not visible to viewer",
		)
	}
	return detail, nil
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

	limit, err := normalizePostQueryLimit(query.Limit())
	if err != nil {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(err.Error())
	}
	identity, err := normalizePostQueryIdentity(query.Identity())
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

	unpagedRequest := postports.NewAuthorPostReadRequest(
		query.AuthorPersonaID(),
		accessScope,
		identity,
		contentType,
		visibility,
		postports.AuthorPostCursor{},
		limit,
	)
	if cursor.IsSet() && cursor.Scope() != unpagedRequest.CursorScope() {
		return postports.AuthorPostPageSlice{}, invalidPostQueryArgument(
			"ListUserPosts cursor does not match query",
		)
	}
	request := postports.NewAuthorPostReadRequest(
		query.AuthorPersonaID(),
		accessScope,
		identity,
		contentType,
		visibility,
		cursor,
		limit,
	)

	page, err := f.author.ListAuthorPosts(ctx, request)
	if err != nil {
		return postports.AuthorPostPageSlice{}, postQueryReadFailure("ListUserPosts", err)
	}
	if err := validateAuthorPostPage(page, request); err != nil {
		return postports.AuthorPostPageSlice{}, postQueryReadFailure("ListUserPosts", err)
	}
	return page, nil
}

func (f *PostQueryFacade) SearchPosts(
	ctx context.Context,
	query postports.PostSearchQuery,
) (postports.PostSearchResultSlice, error) {
	if !query.Viewer().IsAuthenticated() {
		return postports.PostSearchResultSlice{}, contentgenerated.AppErrorFromUnauthorized(
			"SearchPosts requires authenticated persona",
		)
	}
	if strings.TrimSpace(query.Terms()) == "" {
		return postports.PostSearchResultSlice{}, invalidPostQueryArgument(
			"SearchPosts requires non-empty query",
		)
	}
	if f == nil || f.search == nil {
		// 搜索永不回退到 Mongo/aggregate ListPublished；未装配索引 reader 必须失败关闭。
		return postports.PostSearchResultSlice{}, postQueryReaderUnavailable(
			"SearchPosts search reader is not configured",
		)
	}

	limit, err := normalizePostQueryLimit(query.Limit())
	if err != nil {
		return postports.PostSearchResultSlice{}, invalidPostQueryArgument(err.Error())
	}
	identity, err := normalizePostQueryIdentity(query.Identity())
	if err != nil {
		return postports.PostSearchResultSlice{}, invalidPostQueryArgument(err.Error())
	}
	contentType, err := normalizePostQueryContentType(query.ContentType())
	if err != nil {
		return postports.PostSearchResultSlice{}, invalidPostQueryArgument(err.Error())
	}

	unpagedRequest := postports.NewPostSearchReadRequest(
		query.Viewer().PersonaID(),
		query.Terms(),
		identity,
		contentType,
		query.CategoryID(),
		query.SubCategory(),
		postports.PostSearchCursor{},
		limit,
	)
	cursor, err := postports.ParsePostSearchCursor(query.Cursor())
	if err != nil {
		return postports.PostSearchResultSlice{}, invalidPostQueryArgument(
			"SearchPosts cursor is invalid",
		)
	}
	if cursor.IsSet() && cursor.Scope() != unpagedRequest.CursorScope() {
		return postports.PostSearchResultSlice{}, invalidPostQueryArgument(
			"SearchPosts cursor does not match query",
		)
	}
	request := postports.NewPostSearchReadRequest(
		query.Viewer().PersonaID(),
		query.Terms(),
		identity,
		contentType,
		query.CategoryID(),
		query.SubCategory(),
		cursor,
		limit,
	)

	results, err := f.search.SearchPosts(ctx, request)
	if err != nil {
		return postports.PostSearchResultSlice{}, postQueryReadFailure("SearchPosts", err)
	}
	return results, nil
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

func normalizePostQueryIdentity(
	value postports.ContentIdentity,
) (postports.ContentIdentity, error) {
	switch strings.ToLower(strings.TrimSpace(string(value))) {
	case "":
		return "", nil
	case "moment", "work":
		return postports.ContentIdentity(strings.ToLower(strings.TrimSpace(string(value)))), nil
	default:
		return "", errors.New("content identity is unsupported")
	}
}

func normalizePostQueryContentType(
	value postports.ContentType,
) (postports.ContentType, error) {
	switch strings.ToLower(strings.TrimSpace(string(value))) {
	case "":
		return "", nil
	case "photo":
		return postports.ContentType("image"), nil
	case "note":
		return postports.ContentType("article"), nil
	case "micro", "image", "video", "article":
		return postports.ContentType(strings.ToLower(strings.TrimSpace(string(value)))), nil
	default:
		return "", errors.New("content type is unsupported")
	}
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
