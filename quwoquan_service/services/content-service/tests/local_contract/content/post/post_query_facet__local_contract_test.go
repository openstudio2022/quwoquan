// readiness_case: get-post-local
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005
// readiness_case: list-user-posts-local
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
	detail  postports.PostDetailSlice
	found   bool
	err     error
	calls   int
	request postports.PostDetailReadRequest
}

func (r *fakePostDetailReader) FindPostDetail(
	_ context.Context,
	_ postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	r.calls++
	return r.detail, r.found, r.err
}

func (r *fakePostDetailReader) FindReleaseBoundPostDetail(
	_ context.Context,
	request postports.PostDetailReadRequest,
) (postports.PostDetailSlice, bool, error) {
	r.calls++
	r.request = request
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

const queryFenceManifestDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

type fakeQueryActiveSupplyReader struct {
	snapshot postports.ActiveSupplySnapshot
	err      error
	calls    int
}

func (r *fakeQueryActiveSupplyReader) ActiveSupplySnapshot(
	context.Context,
) (postports.ActiveSupplySnapshot, error) {
	r.calls++
	return r.snapshot, r.err
}

func readyQueryActiveSupply(releaseClass string) postports.ActiveSupplySnapshot {
	return postports.ActiveSupplySnapshot{
		Environment:     "alpha",
		SourceOwner:     "qwq_data",
		Status:          "active",
		ActiveReleaseID: "rel-query-active",
		ManifestDigest:  queryFenceManifestDigest,
		ReleaseClass:    releaseClass,
		ReadbackStatus:  "passed",
		Posts:           3,
	}
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-032
func TestPublicPostQueriesDenyNonResearchBeforeReaderForResearchRelease(t *testing.T) {
	active := &fakeQueryActiveSupplyReader{snapshot: readyQueryActiveSupply("research")}
	detail := &fakePostDetailReader{}
	author := &fakeAuthorPostReader{}
	gathering := &fakeGatheringPostReaderForQueryFence{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: detail, Author: author, Gathering: gathering, ActiveSupply: active,
	})

	for name, invoke := range map[string]func() error{
		"GetPost": func() error {
			_, err := facade.GetPost(context.Background(), postports.NewPostDetailQuery(
				postports.NewPostID("research-post"), queryViewer("persona-member"), false,
			))
			return err
		},
		"ListUserPosts": func() error {
			_, err := facade.ListUserPosts(context.Background(), postports.NewAuthorPostPageQuery(
				postports.NewPersonaID("research-author"), queryViewer("persona-member"),
				"", "", "", "", 20, false,
			))
			return err
		},
		"ListPostsByGathering": func() error {
			_, err := facade.ListPostsByGathering(context.Background(),
				postports.NewGatheringPostPageQuery("gathering-research", "", 20, false),
			)
			return err
		},
	} {
		t.Run(name, func(t *testing.T) {
			assertPostQueryErrorCode(t, invoke(), contentgenerated.AppErrorFromPostNotFound(""))
		})
	}
	if detail.calls != 0 || author.calls != 0 || gathering.calls != 0 {
		t.Fatalf("non-research principal reached content readers: detail=%d author=%d gathering=%d", detail.calls, author.calls, gathering.calls)
	}
}

type fakeGatheringPostReaderForQueryFence struct {
	calls   int
	request postports.GatheringPostReadRequest
}

func (r *fakeGatheringPostReaderForQueryFence) ListGatheringPosts(
	_ context.Context,
	request postports.GatheringPostReadRequest,
) (postports.GatheringPostPageSlice, error) {
	r.calls++
	r.request = request
	return postports.GatheringPostPageSlice{Items: []postports.AuthorPostItemSlice{}}, nil
}

func TestResearchPrincipalQueriesUseExactActiveReleaseFence(t *testing.T) {
	active := &fakeQueryActiveSupplyReader{snapshot: readyQueryActiveSupply("research")}
	detail := &fakePostDetailReader{found: true, detail: postports.PostDetailSlice{
		PostID: "research-post", AuthorPersonaID: "research-author",
		Status: "published", Visibility: "public", ModerationStatus: "approved",
	}}
	author := &fakeAuthorPostReader{page: postports.AuthorPostPageSlice{Items: []postports.AuthorPostItemSlice{}}}
	gathering := &fakeGatheringPostReaderForQueryFence{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: detail, Author: author, Gathering: gathering, ActiveSupply: active,
	})

	if _, err := facade.GetPost(context.Background(), postports.NewPostDetailQuery(
		"research-post", queryViewer("persona-research"), true,
	)); err != nil {
		t.Fatal(err)
	}
	if _, err := facade.ListUserPosts(context.Background(), postports.NewAuthorPostPageQuery(
		"research-author", queryViewer("persona-research"), "", "", "", "", 20, true,
	)); err != nil {
		t.Fatal(err)
	}
	if _, err := facade.ListPostsByGathering(context.Background(),
		postports.NewGatheringPostPageQuery("gathering-research", "", 20, true),
	); err != nil {
		t.Fatal(err)
	}

	for name, binding := range map[string][2]string{
		"detail":    {detail.request.ActiveReleaseID(), detail.request.ManifestDigest()},
		"author":    {author.request.ActiveReleaseID(), author.request.ManifestDigest()},
		"gathering": {gathering.request.ActiveReleaseID(), gathering.request.ManifestDigest()},
	} {
		if binding[0] != "rel-query-active" || binding[1] != queryFenceManifestDigest {
			t.Fatalf("%s binding=(%q,%q), want exact active identity", name, binding[0], binding[1])
		}
	}
}

func TestPublicPostQueriesFailClosedOnMalformedActiveRelease(t *testing.T) {
	active := &fakeQueryActiveSupplyReader{snapshot: readyQueryActiveSupply("research")}
	active.snapshot.ManifestDigest = "invalid"
	detail := &fakePostDetailReader{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: detail, ActiveSupply: active,
	})
	_, err := facade.GetPost(context.Background(), postports.NewPostDetailQuery(
		"research-post", queryViewer("persona-research"), true,
	))
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromRequiredDependencyUnavailable(""))
	if detail.calls != 0 {
		t.Fatalf("malformed active release reached detail reader: calls=%d", detail.calls)
	}
}

func TestPublicPostQueryActiveSupplyReadFailureFailsBeforeContentReader(t *testing.T) {
	active := &fakeQueryActiveSupplyReader{err: errors.New("active pointer unavailable")}
	detail := &fakePostDetailReader{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: detail, ActiveSupply: active,
	})
	_, err := facade.GetPost(context.Background(), postports.NewPostDetailQuery(
		"research-post", queryViewer("persona-research"), true,
	))
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromStorageReadFailed(""))
	if detail.calls != 0 {
		t.Fatalf("active supply failure reached detail reader: calls=%d", detail.calls)
	}
}

type fakePublicPostIDLister struct {
	calls          int
	releaseID      string
	manifestDigest string
}

func (lister *fakePublicPostIDLister) ListPublicPostIDs(
	_ context.Context,
	_ int,
	activeReleaseBinding ...string,
) ([]string, error) {
	lister.calls++
	if len(activeReleaseBinding) > 0 {
		lister.releaseID = activeReleaseBinding[0]
	}
	if len(activeReleaseBinding) > 1 {
		lister.manifestDigest = activeReleaseBinding[1]
	}
	return []string{"post-active"}, nil
}

func TestSitemapReleaseGateDeniesAnonymousResearchAndBindsExplicitResearch(t *testing.T) {
	active := &fakeQueryActiveSupplyReader{snapshot: readyQueryActiveSupply("research")}
	lister := &fakePublicPostIDLister{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{ActiveSupply: active})

	_, err := facade.ListPublicPostIDs(context.Background(), lister, 500, false)
	assertPostQueryErrorCode(t, err, contentgenerated.AppErrorFromPostNotFound(""))
	if lister.calls != 0 {
		t.Fatalf("anonymous research sitemap reached lister: calls=%d", lister.calls)
	}

	ids, err := facade.ListPublicPostIDs(context.Background(), lister, 500, true)
	if err != nil {
		t.Fatal(err)
	}
	if len(ids) != 1 || lister.releaseID != "rel-query-active" ||
		lister.manifestDigest != queryFenceManifestDigest {
		t.Fatalf("research sitemap not exact-release-bound: ids=%v lister=%+v", ids, lister)
	}
}
