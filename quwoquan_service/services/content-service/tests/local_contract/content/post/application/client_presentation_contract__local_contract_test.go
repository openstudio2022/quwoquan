// readiness_case: get-post-local
// readiness_case: list-user-posts-local
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
package post_test

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	presentation "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type presentationDetailReader struct {
	detail postports.PostDetailSlice
}

func (reader presentationDetailReader) FindPostDetail(
	_ context.Context,
	_ postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	return reader.detail, true, nil
}

type presentationAuthorReader struct {
	request postports.AuthorPostReadRequest
}

func (reader *presentationAuthorReader) ListAuthorPosts(
	_ context.Context,
	request postports.AuthorPostReadRequest,
) (postports.AuthorPostPageSlice, error) {
	reader.request = request
	return postports.AuthorPostPageSlice{Items: []postports.AuthorPostItemSlice{}}, nil
}

func signedContract(
	t *testing.T,
	contentTypes []presentation.ContentType,
	surfaces []presentation.ContentUiSurface,
) presentation.ClientContentPresentationContract {
	t.Helper()
	contract := presentation.ClientContentPresentationContract{
		ContentTypes:        contentTypes,
		ListObjectKinds:     []presentation.ListObjectKind{"post"},
		OpenSurfaces:        surfaces,
		PresentationRecipes: []presentation.FeedPresentationRecipe{"cover_media_card"},
	}
	digest, err := presentation.DigestClientContentPresentationContract(contract)
	if err != nil {
		t.Fatalf("digest contract: %v", err)
	}
	contract.ContractDigest = digest
	return contract
}

func publishedDetail(contentType string) postports.PostDetailSlice {
	return postports.PostDetailSlice{
		PostID:           postports.NewPostID("post_presentation"),
		ContentType:      postports.ContentType(contentType),
		Status:           postports.PostStatus("published"),
		Visibility:       postports.PostVisibility("public"),
		ModerationStatus: "approved",
	}
}

func requirePresentationCode(t *testing.T, err error, expected string) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected AppError %s, got %T: %v", expected, err, err)
	}
	if got := appErr.Code.String(); got != expected {
		t.Fatalf("error code=%s want=%s", got, expected)
	}
}

// application 是能力裁决点：typed 能力从入口一直传到这里，
// 「可见但这一版渲染不了」是独立终态，不是 not_found、也不是空投影。
func TestGetPostApplicationRejectsUnsupportedPresentation(t *testing.T) {
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: presentationDetailReader{detail: publishedDetail("article")},
	})

	_, err := facade.GetPost(context.Background(), postports.NewPostDetailQuery(
		postports.NewPostID("post_presentation"),
		postports.NewViewerContext(postports.NewPersonaID("")),
	).WithClientPresentationContract(signedContract(
		t,
		[]presentation.ContentType{"image", "video"},
		[]presentation.ContentUiSurface{"media_immersive"},
	)))

	requirePresentationCode(t, err, "CONTENT.USER.presentation_unsupported")
}

func TestGetPostApplicationServesDeclaredPresentation(t *testing.T) {
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: presentationDetailReader{detail: publishedDetail("article")},
	})

	if _, err := facade.GetPost(context.Background(), postports.NewPostDetailQuery(
		postports.NewPostID("post_presentation"),
		postports.NewViewerContext(postports.NewPersonaID("")),
	).WithClientPresentationContract(signedContract(
		t,
		[]presentation.ContentType{"article"},
		[]presentation.ContentUiSurface{"article_reader"},
	))); err != nil {
		t.Fatalf("declared article presentation must be served: %v", err)
	}
}

// 不面向客户端渲染的读路径（内部 persisted query、SSR）不携带声明，
// 也因此不被能力裁决；这与「客户端声明缺席」不是同一件事。
func TestGetPostWithoutPresentationContractSkipsCapabilityAdmission(t *testing.T) {
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: presentationDetailReader{detail: publishedDetail("article")},
	})

	if _, err := facade.GetPost(context.Background(), postports.NewPostDetailQuery(
		postports.NewPostID("post_presentation"),
		postports.NewViewerContext(postports.NewPersonaID("")),
	)); err != nil {
		t.Fatalf("non-client read path must not be capability-gated: %v", err)
	}
}

// 服务端独立重算摘要：伪造声明在 application 也必须被拒，
// 不允许退回固定基线继续读。
func TestPostQueriesRejectForgedPresentationDigest(t *testing.T) {
	forged := signedContract(
		t,
		[]presentation.ContentType{"image"},
		[]presentation.ContentUiSurface{"media_immersive"},
	)
	forged.ContractDigest = "sha256:" +
		"0000000000000000000000000000000000000000000000000000000000000000"

	detailFacade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: presentationDetailReader{detail: publishedDetail("image")},
	})
	_, detailErr := detailFacade.GetPost(context.Background(), postports.NewPostDetailQuery(
		postports.NewPostID("post_presentation"),
		postports.NewViewerContext(postports.NewPersonaID("")),
	).WithClientPresentationContract(forged))
	requirePresentationCode(t, detailErr, "CONTENT.USER.invalid_argument")

	authorFacade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Author: &presentationAuthorReader{},
	})
	_, authorErr := authorFacade.ListUserPosts(context.Background(), postports.NewAuthorPostPageQuery(
		postports.NewPersonaID("persona_presentation"),
		postports.NewViewerContext(postports.NewPersonaID("")),
		postports.ContentType(""),
		postports.PostVisibility(""),
		"",
		20,
	).WithClientPresentationContract(forged))
	requirePresentationCode(t, authorErr, "CONTENT.USER.invalid_argument")
}

// 有效能力摘要进入 keyset cursor scope：按一份能力算出的续页位置不得被
// 另一份能力复用，否则两种能力会共享同一条分页进度。
func TestListUserPostsBindsCursorScopeToPresentationDigest(t *testing.T) {
	mediaContract := signedContract(
		t,
		[]presentation.ContentType{"image", "video"},
		[]presentation.ContentUiSurface{"media_immersive"},
	)
	articleContract := signedContract(
		t,
		[]presentation.ContentType{"article"},
		[]presentation.ContentUiSurface{"article_reader"},
	)
	if mediaContract.ContractDigest == articleContract.ContractDigest {
		t.Fatal("distinct capabilities must produce distinct digests")
	}

	reader := &presentationAuthorReader{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{Author: reader})
	query := func(
		contract presentation.ClientContentPresentationContract,
		cursor string,
	) postports.AuthorPostPageQuery {
		return postports.NewAuthorPostPageQuery(
			postports.NewPersonaID("persona_presentation"),
			postports.NewViewerContext(postports.NewPersonaID("")),
			postports.ContentType(""),
			postports.PostVisibility(""),
			cursor,
			20,
		).WithClientPresentationContract(contract)
	}

	if _, err := facade.ListUserPosts(context.Background(), query(mediaContract, "")); err != nil {
		t.Fatalf("first page: %v", err)
	}
	mediaScope := reader.request.CursorScope()
	mediaCursor := postports.NewAuthorPostCursor(
		mediaScope,
		time.Date(2026, time.September, 1, 0, 0, 0, 0, time.UTC),
		postports.NewPostID("post_presentation"),
	).Encode()

	if _, err := facade.ListUserPosts(
		context.Background(),
		query(mediaContract, mediaCursor),
	); err != nil {
		t.Fatalf("same capability must continue its own page: %v", err)
	}

	_, err := facade.ListUserPosts(
		context.Background(),
		query(articleContract, mediaCursor),
	)
	requirePresentationCode(t, err, "CONTENT.USER.invalid_argument")
}
