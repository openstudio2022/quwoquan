// readiness_case: get-post-local
// readiness_case: list-user-posts-local
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
package http_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	presentation "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type presentationContractDetailReader struct {
	detail postports.PostDetailSlice
}

func (reader presentationContractDetailReader) FindPostDetail(
	_ context.Context,
	_ postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	return reader.detail, true, nil
}

// signedPresentationContract 用生成的 canonical digest 补齐一份合法声明。
// 测试永远不手写摘要字面量：那会把服务端重算的判定退化成字符串比对。
func signedPresentationContract(
	t *testing.T,
	contract presentation.ClientContentPresentationContract,
) presentation.ClientContentPresentationContract {
	t.Helper()
	digest, err := presentation.DigestClientContentPresentationContract(contract)
	if err != nil {
		t.Fatalf("digest presentation contract: %v", err)
	}
	contract.ContractDigest = digest
	return contract
}

func presentationContractQuery(
	t *testing.T,
	contract presentation.ClientContentPresentationContract,
) string {
	t.Helper()
	raw, err := json.Marshal(contract)
	if err != nil {
		t.Fatalf("encode presentation contract: %v", err)
	}
	return "?clientPresentationContract=" + url.QueryEscape(string(raw))
}

// mediaOnlyPresentationContract 是一份不声明 article 能力的合法声明：
// 图文/视频可渲染，文章阅读器面缺席。
func mediaOnlyPresentationContract(
	t *testing.T,
) presentation.ClientContentPresentationContract {
	t.Helper()
	return signedPresentationContract(t, presentation.ClientContentPresentationContract{
		ContentTypes:        []presentation.ContentType{"image", "video"},
		ListObjectKinds:     []presentation.ListObjectKind{"post"},
		OpenSurfaces:        []presentation.ContentUiSurface{"media_immersive"},
		PresentationRecipes: []presentation.FeedPresentationRecipe{"cover_media_card"},
	})
}

func newPresentationContractRoutes(
	contentType postports.ContentType,
) http.Handler {
	return NewContentHandler(
		nil,
		nil,
		postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
			Detail: presentationContractDetailReader{detail: postports.PostDetailSlice{
				PostID:           postports.NewPostID("post_presentation_contract"),
				ContentType:      contentType,
				Status:           postports.PostStatus("published"),
				Visibility:       postports.PostVisibility("public"),
				ModerationStatus: "approved",
			}},
		}),
		nil,
		nil,
		nil,
		nil,
	).Routes()
}

func requirePresentationErrorCode(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error envelope: %v", err)
	}
	if response.Code != code {
		t.Fatalf("code=%s want=%s body=%s", response.Code, code, recorder.Body.String())
	}
}

func TestGetPostRejectsContentOutsideDeclaredPresentationCapability(t *testing.T) {
	t.Parallel()

	recorder := httptest.NewRecorder()
	newPresentationContractRoutes(postports.ContentType("article")).ServeHTTP(
		recorder,
		httptest.NewRequest(
			http.MethodGet,
			"/content/posts/post_presentation_contract"+
				presentationContractQuery(t, mediaOnlyPresentationContract(t)),
			nil,
		),
	)

	requirePresentationErrorCode(
		t,
		recorder,
		http.StatusUpgradeRequired,
		"CONTENT.USER.presentation_unsupported",
	)
}

func TestGetPostServesContentInsideDeclaredPresentationCapability(t *testing.T) {
	t.Parallel()

	recorder := httptest.NewRecorder()
	newPresentationContractRoutes(postports.ContentType("image")).ServeHTTP(
		recorder,
		httptest.NewRequest(
			http.MethodGet,
			"/content/posts/post_presentation_contract"+
				presentationContractQuery(t, mediaOnlyPresentationContract(t)),
			nil,
		),
	)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

// 整份缺席只落到生成的 MissingDeclaration 固定基线：基线声明 article_reader，
// 所以文章可读；缺席绝不等于「全能力」，也不等于「无能力」。
func TestGetPostWithoutDeclarationUsesMissingDeclarationBaseline(t *testing.T) {
	t.Parallel()

	baseline := presentation.MissingDeclarationContentPresentationContract()
	if !containsSurface(baseline.OpenSurfaces, "article_reader") ||
		containsSurface(baseline.OpenSurfaces, "home_feed") {
		t.Fatalf("missing-declaration baseline drifted: %+v", baseline)
	}

	for _, contentType := range []string{"article", "image"} {
		recorder := httptest.NewRecorder()
		newPresentationContractRoutes(postports.ContentType(contentType)).ServeHTTP(
			recorder,
			httptest.NewRequest(
				http.MethodGet,
				"/content/posts/post_presentation_contract",
				nil,
			),
		)
		if recorder.Code != http.StatusOK {
			t.Fatalf("contentType=%s status=%d body=%s", contentType, recorder.Code, recorder.Body.String())
		}
	}
}

func containsSurface(
	surfaces []presentation.ContentUiSurface,
	value presentation.ContentUiSurface,
) bool {
	for _, surface := range surfaces {
		if surface == value {
			return true
		}
	}
	return false
}

// 伪造摘要必须在服务端重算时落地为非法入参，而不是被当成一份能力声明使用。
func TestClientPresentationContractRejectsForgedDigestOnEveryReadEntry(t *testing.T) {
	t.Parallel()

	forged := mediaOnlyPresentationContract(t)
	forged.ContractDigest = "sha256:" +
		"0000000000000000000000000000000000000000000000000000000000000000"
	query := presentationContractQuery(t, forged)

	for name, path := range map[string]string{
		"GetPost":       "/content/posts/post_presentation_contract" + query,
		"ListUserPosts": "/content/personas/persona_presentation/posts" + query,
	} {
		t.Run(name, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			newPresentationContractRoutes(postports.ContentType("image")).ServeHTTP(
				recorder,
				httptest.NewRequest(http.MethodGet, path, nil),
			)
			requirePresentationErrorCode(
				t,
				recorder,
				http.StatusBadRequest,
				"CONTENT.USER.invalid_argument",
			)
		})
	}
}

// 闭集外成员由 operation binder 在解码前拒绝：读侧不得先放行再猜。
func TestClientPresentationContractRejectsMembersOutsideClosedSet(t *testing.T) {
	t.Parallel()

	recorder := httptest.NewRecorder()
	newPresentationContractRoutes(postports.ContentType("image")).ServeHTTP(
		recorder,
		httptest.NewRequest(
			http.MethodGet,
			"/content/posts/post_presentation_contract?clientPresentationContract="+
				url.QueryEscape(`{"contentTypes":["micro"],"listObjectKinds":["post"],`+
					`"openSurfaces":["media_immersive"],"presentationRecipes":["cover_media_card"],`+
					`"contractDigest":"sha256:`+
					`0000000000000000000000000000000000000000000000000000000000000000"}`),
			nil,
		),
	)

	requirePresentationErrorCode(
		t,
		recorder,
		http.StatusBadRequest,
		"CONTENT.USER.invalid_argument",
	)
}
