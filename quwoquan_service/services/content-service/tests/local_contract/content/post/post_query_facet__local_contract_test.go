package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
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
		PostID:           postports.NewPostID("post-moderation-rejected"),
		AuthorPersonaID:  postports.NewPersonaID("persona-author"),
		Status:           postports.PostStatus("published"),
		Visibility:       postports.PostVisibility("public"),
		ModerationStatus: "rejected",
	}
	_, err = facade.GetPost(
		ctx,
		postports.NewPostDetailQuery(
			postports.NewPostID("post-moderation-rejected"),
			queryViewer("persona-outsider"),
		),
	)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromPostNotFound(""))
	if _, err = facade.GetPost(
		ctx,
		postports.NewPostDetailQuery(
			postports.NewPostID("post-moderation-rejected"),
			queryViewer("persona-author"),
		),
	); err != nil {
		t.Fatalf("owner persona must retain access to rejected Post: %v", err)
	}
	reader.detail.ModerationStatus = "approved"
	if _, err = facade.GetPost(
		ctx,
		postports.NewPostDetailQuery(
			postports.NewPostID("post-moderation-rejected"),
			queryViewer("persona-outsider"),
		),
	); err != nil {
		t.Fatalf("approved public Post must be visible again: %v", err)
	}

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
}

type fakeViewerBlockReader struct {
	blockedPairs map[string]bool
	err          error
	calls        int
}

func (r *fakeViewerBlockReader) IsBlockedBetween(
	_ context.Context,
	viewer postports.PersonaID,
	author postports.PersonaID,
) (bool, error) {
	r.calls++
	if r.err != nil {
		return false, r.err
	}
	return r.blockedPairs[string(viewer)+"|"+string(author)], nil
}

func TestGetPostEnforcesBlockServerSide(t *testing.T) {
	ctx := context.Background()
	detailReader := &fakePostDetailReader{
		found: true,
		detail: postports.PostDetailSlice{
			PostID:           postports.NewPostID("post-blocked-detail"),
			AuthorPersonaID:  postports.NewPersonaID("persona-author"),
			Status:           postports.PostStatus("published"),
			Visibility:       postports.PostVisibility("public"),
			ModerationStatus: "approved",
		},
	}
	blocks := &fakeViewerBlockReader{blockedPairs: map[string]bool{
		"persona-blocked-viewer|persona-author": true,
	}}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail:       detailReader,
		ViewerBlocks: blocks,
	})

	_, err := facade.GetPost(ctx, postports.NewPostDetailQuery(
		postports.NewPostID("post-blocked-detail"),
		queryViewer("persona-blocked-viewer"),
	))
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromPostNotFound(""))
	if detailReader.calls != 1 {
		t.Fatalf("detail reader calls=%d want=1", detailReader.calls)
	}

	blocks.calls = 0
	if _, err = facade.GetPost(ctx, postports.NewPostDetailQuery(
		postports.NewPostID("post-blocked-detail"),
		queryViewer("persona-author"),
	)); err != nil {
		t.Fatalf("owner must retain detail access: %v", err)
	}
	if blocks.calls != 0 {
		t.Fatalf("owner detail read must bypass block guard, calls=%d", blocks.calls)
	}

	blocks.err = errors.New("projection unavailable")
	_, err = facade.GetPost(ctx, postports.NewPostDetailQuery(
		postports.NewPostID("post-blocked-detail"),
		queryViewer("persona-other"),
	))
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromStorageReadFailed(""))
}

// GWT: Given author 拉黑了 viewer（或反向），When viewer 拉取作者主页作品列表，
// Then 服务端返回空页且不触达 author reader，也不向被拉黑方泄露 block 存在性。
func TestListUserPostsEnforcesBlockServerSide(t *testing.T) {
	ctx := context.Background()
	authorReader := &fakeAuthorPostReader{
		page: postports.AuthorPostPageSlice{
			Items: []postports.AuthorPostItemSlice{{
				PostID:          postports.NewPostID("post-1"),
				AuthorPersonaID: postports.NewPersonaID("persona-author"),
				Status:          postports.PostStatus("published"),
				Visibility:      postports.PostVisibility("public"),
			}},
		},
	}
	blocks := &fakeViewerBlockReader{blockedPairs: map[string]bool{
		"persona-blocked-viewer|persona-author": true,
	}}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Author:       authorReader,
		ViewerBlocks: blocks,
	})

	page, err := facade.ListUserPosts(ctx, postports.NewAuthorPostPageQuery(
		postports.NewPersonaID("persona-author"),
		queryViewer("persona-blocked-viewer"),
		"", "", "", "", 10,
	))
	if err != nil {
		t.Fatalf("blocked viewer must receive empty page, not error: %v", err)
	}
	if len(page.Items) != 0 || page.HasMore || page.NextCursor != "" {
		t.Fatalf("blocked viewer must not see author posts: %+v", page)
	}
	if authorReader.calls != 0 {
		t.Fatalf("blocked viewer must not reach author reader, calls=%d", authorReader.calls)
	}

	// 非拉黑 viewer 正常读取。
	page, err = facade.ListUserPosts(ctx, postports.NewAuthorPostPageQuery(
		postports.NewPersonaID("persona-author"),
		queryViewer("persona-friend"),
		"", "", "", "", 10,
	))
	if err != nil {
		t.Fatalf("unblocked viewer read failed: %v", err)
	}
	if len(page.Items) != 1 {
		t.Fatalf("unblocked viewer must see author posts: %+v", page)
	}

	// owner 自读不经过 block guard。
	blocks.calls = 0
	if _, err = facade.ListUserPosts(ctx, postports.NewAuthorPostPageQuery(
		postports.NewPersonaID("persona-author"),
		queryViewer("persona-author"),
		"", "", "", "", 10,
	)); err != nil {
		t.Fatalf("owner read failed: %v", err)
	}
	if blocks.calls != 0 {
		t.Fatalf("owner read must bypass block guard, calls=%d", blocks.calls)
	}

	// 匿名 viewer（游客）不经过 block guard，仍可读公开作品。
	if _, err = facade.ListUserPosts(ctx, postports.NewAuthorPostPageQuery(
		postports.NewPersonaID("persona-author"),
		queryViewer(""),
		"", "", "", "", 10,
	)); err != nil {
		t.Fatalf("guest read failed: %v", err)
	}
	if blocks.calls != 0 {
		t.Fatalf("guest read must bypass block guard, calls=%d", blocks.calls)
	}

	// block 判定失败必须 fail-closed 为结构化读错误，不能放行。
	blocks.err = errors.New("projection unavailable")
	_, err = facade.ListUserPosts(ctx, postports.NewAuthorPostPageQuery(
		postports.NewPersonaID("persona-author"),
		queryViewer("persona-blocked-viewer"),
		"", "", "", "", 10,
	))
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromStorageReadFailed(""))
}
