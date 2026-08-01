// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/helper-read-summary/spec.md#gwt-001
package post_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"unicode/utf8"

	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

type helperReadDetailReader struct {
	detail postports.PostDetailSlice
	found  bool
	err    error
}

func (r helperReadDetailReader) FindPostDetail(
	_ context.Context,
	_ postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	return r.detail, r.found, r.err
}

func newHelperReadFacade(
	reader postports.PostDetailReader,
) *postapp.PostQueryFacade {
	return postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: reader,
	})
}

func publishedArticleDetail() postports.PostDetailSlice {
	return postports.PostDetailSlice{
		PostID:            postports.PostID("post_helper_read"),
		ContentType:       postports.ContentType("article"),
		Title:             "川西环线",
		Body:              "这是文章正文。",
		Summary:           "作者确认的摘要",
		HelperReadSummary: "投影生成的帮读摘要",
		Status:            postports.PostStatus("published"),
		Visibility:        postports.PostVisibility("public"),
		ModerationStatus:  "approved",
	}
}

func TestGenerateArticleSummaryIsDeterministicRuneSafeAndSideEffectFree(
	t *testing.T,
) {
	store := testsupport.NewPostStore([]postmodel.Post{{
		ID: "existing_post", Version: 1, ContentType: "article",
		Status: "published", Visibility: "public", ModerationStatus: "approved",
	}})
	service := postapp.NewPostService(postapp.BindDataPorts(store))
	body := strings.Repeat("川", 101)

	first := service.GenerateArticleSummary("  标题  ", "  "+body+"  ")
	second := service.GenerateArticleSummary("标题", body)

	if first != second {
		t.Fatalf("same normalized input must replay the same summary: %q != %q", first, second)
	}
	if !utf8.ValidString(first) {
		t.Fatalf("summary truncation split a UTF-8 rune: %q", first)
	}
	if got, want := utf8.RuneCountInString(first), 2+1+100; got != want {
		t.Fatalf("summary rune count=%d want=%d: %q", got, want, first)
	}
	posts, err := store.ListAll(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 || posts[0].ID != "existing_post" {
		t.Fatalf("draft summary computation must not mutate Post state: %+v", posts)
	}
}

func TestGetHelperReadUsesNamedProjectionAndHelperSummary(t *testing.T) {
	detail := publishedArticleDetail()
	facade := newHelperReadFacade(helperReadDetailReader{
		detail: detail,
		found:  true,
	})

	result, err := facade.GetHelperRead(context.Background(), string(detail.PostID))
	if err != nil {
		t.Fatal(err)
	}
	if result.PostID != detail.PostID ||
		result.ContentType != detail.ContentType ||
		result.Title != detail.Title ||
		result.Summary != detail.HelperReadSummary {
		t.Fatalf("helper-read projection mismatch: %+v", result)
	}
}

func TestGetHelperReadRejectsAnythingOutsidePublicArticleScope(t *testing.T) {
	base := publishedArticleDetail()
	testCases := []struct {
		name   string
		mutate func(*postports.PostDetailSlice)
		found  bool
	}{
		{
			name: "missing",
			mutate: func(*postports.PostDetailSlice) {
			},
			found: false,
		},
		{
			name: "private",
			mutate: func(detail *postports.PostDetailSlice) {
				detail.Visibility = postports.PostVisibility("private")
			},
			found: true,
		},
		{
			name: "unpublished",
			mutate: func(detail *postports.PostDetailSlice) {
				detail.Status = postports.PostStatus("pending_review")
			},
			found: true,
		},
		{
			name: "unapproved",
			mutate: func(detail *postports.PostDetailSlice) {
				detail.ModerationStatus = "pending"
			},
			found: true,
		},
		{
			name: "non-article",
			mutate: func(detail *postports.PostDetailSlice) {
				detail.ContentType = postports.ContentType("image")
			},
			found: true,
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			detail := base
			testCase.mutate(&detail)
			facade := newHelperReadFacade(helperReadDetailReader{
				detail: detail,
				found:  testCase.found,
			})

			_, err := facade.GetHelperRead(
				context.Background(),
				string(base.PostID),
			)
			requireHelperReadErrorCode(t, err, "CONTENT.USER.post_not_found")
		})
	}
}

func TestGetHelperReadMapsProjectionFailureToCanonicalStorageError(t *testing.T) {
	facade := newHelperReadFacade(helperReadDetailReader{
		err: errors.New("controlled projection read failure"),
	})

	_, err := facade.GetHelperRead(context.Background(), "post_helper_read")

	requireHelperReadErrorCode(t, err, "CONTENT.SYSTEM.storage_read_failed")
}

func requireHelperReadErrorCode(t *testing.T, err error, expected string) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected AppError %s, got %T: %v", expected, err, err)
	}
	if got := appErr.Code.String(); got != expected {
		t.Fatalf("error code=%s want=%s", got, expected)
	}
}
