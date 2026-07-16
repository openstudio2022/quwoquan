package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type fakePostDetailReader struct {
	detail postports.PostDetailSlice
	found  bool
	err    error
	calls  int
}

func (r *fakePostDetailReader) FindPostDetail(
	_ context.Context,
	_ postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	r.calls++
	return r.detail, r.found, r.err
}

type fakeAuthorPostReader struct {
	page    postports.AuthorPostPageSlice
	err     error
	calls   int
	request postports.AuthorPostReadRequest
}

func (r *fakeAuthorPostReader) ListAuthorPosts(
	_ context.Context,
	request postports.AuthorPostReadRequest,
) (postports.AuthorPostPageSlice, error) {
	r.calls++
	r.request = request
	return r.page, r.err
}

type fakePostSearchReader struct {
	result                   postports.PostSearchResultSlice
	err                      error
	calls                    int
	request                  postports.PostSearchReadRequest
	aggregateCollectionCalls int
}

func (r *fakePostSearchReader) SearchPosts(
	_ context.Context,
	request postports.PostSearchReadRequest,
) (postports.PostSearchResultSlice, error) {
	r.calls++
	r.request = request
	return r.result, r.err
}

// 这个 fake 同时实现 aggregate CollectionReader；SearchPosts 若错误地向下转型并扫描
// 聚合集合，测试会立即失败。它仅用于证明 Query Facade 不存在这种降级路径。
func (r *fakePostSearchReader) ListAll(_ context.Context) ([]postmodel.Post, error) {
	r.aggregateCollectionCalls++
	return nil, errors.New("aggregate collection reader must not serve SearchPosts")
}

func (r *fakePostSearchReader) ListPublished(
	_ context.Context,
	_ int,
	_ string,
) []postmodel.Post {
	r.aggregateCollectionCalls++
	return nil
}

func (r *fakePostSearchReader) ListByAuthor(
	_ context.Context,
	_ string,
	_ int,
	_ string,
) []postmodel.Post {
	r.aggregateCollectionCalls++
	return nil
}

var _ postports.CollectionReader = (*fakePostSearchReader)(nil)

func queryViewer(personaID string) postports.ViewerContext {
	return postports.NewViewerContext(postports.NewPersonaID(personaID))
}

func assertPostQueryErrorCode(t *testing.T, err error, want *rterr.AppError) {
	t.Helper()
	if err == nil {
		t.Fatal("expected structured query error")
	}
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("expected Runtime AppError, got %T: %v", err, err)
	}
	if got := appError.Code.String(); got != want.Code.String() {
		t.Fatalf("error code = %q, want %q", got, want.Code.String())
	}
}

func TestPostDetailAllowsOnlyPublicOrOwnerVisibility(t *testing.T) {
	ctx := context.Background()
	reader := &fakePostDetailReader{
		found: true,
		detail: postports.PostDetailSlice{
			PostID:          postports.NewPostID("post-retired-visibility"),
			AuthorPersonaID: postports.NewPersonaID("persona-author"),
			Status:          postports.PostStatus("published"),
			Visibility:      postports.PostVisibility("circle_visible"),
		},
	}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: reader,
	})

	_, err := facade.GetPost(
		ctx,
		postports.NewPostDetailQuery(
			postports.NewPostID("post-retired-visibility"),
			queryViewer("persona-member"),
		),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromPostNotFound(""))

	reader.detail = postports.PostDetailSlice{
		PostID:          postports.NewPostID("post-draft"),
		AuthorPersonaID: postports.NewPersonaID("persona-author"),
		Status:          postports.PostStatus("draft"),
		Visibility:      postports.PostVisibility("private"),
	}
	_, err = facade.GetPost(
		ctx,
		postports.NewPostDetailQuery(
			postports.NewPostID("post-draft"),
			queryViewer("persona-author"),
		),
	)
	if err != nil {
		t.Fatalf("owner persona must read own draft/private post: %v", err)
	}
	_, err = facade.GetPost(
		ctx,
		postports.NewPostDetailQuery(
			postports.NewPostID("post-draft"),
			queryViewer("persona-outsider"),
		),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromPostNotFound(""))
}

func TestPostQueryFacadeListAuthorPostsScopesOwnerAndValidatesCursor(t *testing.T) {
	ctx := context.Background()
	authorID := postports.NewPersonaID("persona-author")
	reader := &fakeAuthorPostReader{
		page: postports.AuthorPostPageSlice{
			Items: []postports.AuthorPostItemSlice{{
				PostID:          postports.NewPostID("post-private-draft"),
				AuthorPersonaID: authorID,
				Status:          postports.PostStatus("draft"),
				Visibility:      postports.PostVisibility("private"),
			}},
		},
	}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Author: reader,
	})

	ownerQuery := postports.NewAuthorPostPageQuery(
		authorID,
		queryViewer("persona-author"),
		"",
		"",
		"",
		"",
		10,
	)
	page, err := facade.ListUserPosts(ctx, ownerQuery)
	if err != nil {
		t.Fatalf("owner list must include own draft/private items: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].PostID != postports.NewPostID("post-private-draft") {
		t.Fatalf("unexpected owner page: %+v", page)
	}
	if reader.request.AccessScope() != postports.AuthorPostAccessOwner {
		t.Fatalf("owner list scope = %q, want owner", reader.request.AccessScope())
	}

	outsiderPrivateQuery := postports.NewAuthorPostPageQuery(
		authorID,
		queryViewer("persona-outsider"),
		"",
		"",
		postports.PostVisibility("private"),
		"",
		10,
	)
	_, err = facade.ListUserPosts(ctx, outsiderPrivateQuery)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromUnauthorized(""))
	if reader.calls != 1 {
		t.Fatalf("non-owner private query must not call reader, calls=%d", reader.calls)
	}

	reader.page = postports.AuthorPostPageSlice{
		Items: []postports.AuthorPostItemSlice{{
			PostID:          postports.NewPostID("post-public"),
			AuthorPersonaID: authorID,
			Status:          postports.PostStatus("published"),
			Visibility:      postports.PostVisibility("public"),
		}},
	}
	unpaged := postports.NewAuthorPostReadRequest(
		authorID,
		postports.AuthorPostAccessPublic,
		"",
		"",
		"",
		postports.AuthorPostCursor{},
		10,
	)
	validCursor := postports.NewAuthorPostCursor(
		unpaged.CursorScope(),
		time.Date(2026, time.July, 13, 10, 0, 0, 0, time.UTC),
		postports.NewPostID("post-before"),
	).Encode()
	_, err = facade.ListUserPosts(
		ctx,
		postports.NewAuthorPostPageQuery(
			authorID,
			queryViewer("persona-outsider"),
			"",
			"",
			"",
			validCursor,
			10,
		),
	)
	if err != nil {
		t.Fatalf("valid public author cursor must be accepted: %v", err)
	}
	if got := reader.request.Cursor().PostID(); got != postports.NewPostID("post-before") {
		t.Fatalf("reader cursor post id = %q, want post-before", got)
	}
}

func TestPostQueryFacadeRejectsMalformedCursorBeforeReader(t *testing.T) {
	reader := &fakeAuthorPostReader{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Author: reader,
	})

	_, err := facade.ListUserPosts(
		context.Background(),
		postports.NewAuthorPostPageQuery(
			postports.NewPersonaID("persona-author"),
			queryViewer("persona-outsider"),
			"",
			"",
			"",
			"not-a-canonical-cursor",
			10,
		),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromInvalidArgument(""))
	if reader.calls != 0 {
		t.Fatalf("malformed cursor must not reach reader, calls=%d", reader.calls)
	}
}

func TestPostQueryFacadeRejectsCursorOutsideQueryScope(t *testing.T) {
	authorReader := &fakeAuthorPostReader{}
	authorFacade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Author: authorReader,
	})
	wrongAuthorScope := postports.NewAuthorPostReadRequest(
		postports.NewPersonaID("another-persona"),
		postports.AuthorPostAccessPublic,
		"",
		"",
		"",
		postports.AuthorPostCursor{},
		10,
	)
	_, err := authorFacade.ListUserPosts(
		context.Background(),
		postports.NewAuthorPostPageQuery(
			postports.NewPersonaID("persona-author"),
			queryViewer("persona-outsider"),
			"",
			"",
			"",
			postports.NewAuthorPostCursor(
				wrongAuthorScope.CursorScope(),
				time.Date(2026, time.July, 13, 11, 0, 0, 0, time.UTC),
				postports.NewPostID("post-other-scope"),
			).Encode(),
			10,
		),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromInvalidArgument(""))
	if authorReader.calls != 0 {
		t.Fatalf("cross-scope author cursor must not reach reader, calls=%d", authorReader.calls)
	}

	searchReader := &fakePostSearchReader{}
	searchFacade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{Search: searchReader})
	viewer := queryViewer("persona-searcher")
	wrongSearchScope := postports.NewPostSearchReadRequest(
		viewer.PersonaID(),
		"另一查询",
		"",
		"",
		"",
		"",
		postports.PostSearchCursor{},
		10,
	)
	_, err = searchFacade.SearchPosts(
		context.Background(),
		postports.NewPostSearchQuery(
			viewer,
			"当前查询",
			"",
			"",
			"",
			"",
			postports.NewPostSearchCursor(
				wrongSearchScope.CursorScope(),
				"other-search-after",
			).Encode(),
			10,
		),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromInvalidArgument(""))
	if searchReader.calls != 0 {
		t.Fatalf("cross-scope search cursor must not reach reader, calls=%d", searchReader.calls)
	}
}

func TestPostQueryFacadeSearchUsesDedicatedReaderAndFailsClosed(t *testing.T) {
	ctx := context.Background()
	searchReader := &fakePostSearchReader{
		result: postports.PostSearchResultSlice{
			Items: []postports.PostSearchItemSlice{{
				PostID:      postports.NewPostID("post-search"),
				ContentType: postports.ContentType("article"),
				Title:       "搜索结果",
			}},
		},
	}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{Search: searchReader})
	viewer := queryViewer("persona-searcher")

	unpaged := postports.NewPostSearchReadRequest(
		viewer.PersonaID(),
		"川西",
		"",
		"",
		"",
		"",
		postports.PostSearchCursor{},
		10,
	)
	cursor := postports.NewPostSearchCursor(
		unpaged.CursorScope(),
		"search-after-fixture",
	).Encode()
	results, err := facade.SearchPosts(
		ctx,
		postports.NewPostSearchQuery(
			viewer,
			"川西",
			"",
			"",
			"",
			"",
			cursor,
			10,
		),
	)
	if err != nil {
		t.Fatalf("dedicated search reader failed: %v", err)
	}
	if len(results.Items) != 1 || searchReader.calls != 1 {
		t.Fatalf("search must call only dedicated reader: items=%+v calls=%d", results.Items, searchReader.calls)
	}
	if searchReader.aggregateCollectionCalls != 0 {
		t.Fatalf(
			"SearchPosts must not invoke aggregate CollectionReader, calls=%d",
			searchReader.aggregateCollectionCalls,
		)
	}
	if got := searchReader.request.Cursor().Token(); got != "search-after-fixture" {
		t.Fatalf("search reader cursor token = %q, want search-after-fixture", got)
	}

	searchReader.err = errors.New("search index unavailable")
	_, err = facade.SearchPosts(
		ctx,
		postports.NewPostSearchQuery(viewer, "川西", "", "", "", "", "", 10),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromStorageReadFailed(""))

	missingReaderFacade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{})
	_, err = missingReaderFacade.SearchPosts(
		ctx,
		postports.NewPostSearchQuery(viewer, "川西", "", "", "", "", "", 10),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromRequiredDependencyUnavailable(""))

	_, err = facade.SearchPosts(
		ctx,
		postports.NewPostSearchQuery(queryViewer(""), "川西", "", "", "", "", "", 10),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromUnauthorized(""))
	if searchReader.calls != 2 {
		t.Fatalf("unauthenticated search must not call search reader, calls=%d", searchReader.calls)
	}
}
