package post

import (
	"context"
	"testing"

	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

func TestMediaAssetVisibilityReaderUsesPublishedPostVisibilityAndBlocks(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		viewerID   string
		candidates []postports.MediaReferencedPostSlice
		blocked    bool
		want       bool
	}{
		{
			name:     "public approved Post grants viewer",
			viewerID: "viewer-1",
			candidates: []postports.MediaReferencedPostSlice{{
				PostID: "post-public", AuthorPersonaID: "author-1",
				Status: "published", Visibility: "public", ModerationStatus: "approved",
			}},
			want: true,
		},
		{
			name:     "private Post only grants its owner",
			viewerID: "viewer-1",
			candidates: []postports.MediaReferencedPostSlice{{
				PostID: "post-private", AuthorPersonaID: "author-1",
				Status: "published", Visibility: "private", ModerationStatus: "approved",
			}},
			want: false,
		},
		{
			name:     "private Post grants its owner",
			viewerID: "author-1",
			candidates: []postports.MediaReferencedPostSlice{{
				PostID: "post-private", AuthorPersonaID: "author-1",
				Status: "published", Visibility: "private", ModerationStatus: "approved",
			}},
			want: true,
		},
		{
			name:     "unapproved Post never grants",
			viewerID: "viewer-1",
			candidates: []postports.MediaReferencedPostSlice{{
				PostID: "post-review", AuthorPersonaID: "author-1",
				Status: "published", Visibility: "public", ModerationStatus: "pending",
			}},
			want: false,
		},
		{
			name:     "blocked viewer never grants",
			viewerID: "viewer-1",
			candidates: []postports.MediaReferencedPostSlice{{
				PostID: "post-blocked", AuthorPersonaID: "author-1",
				Status: "published", Visibility: "public", ModerationStatus: "approved",
			}},
			blocked: true,
			want:    false,
		},
	}

	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			reader := NewMediaAssetVisibilityReader(
				fakeMediaReferencedPostReader{posts: testCase.candidates},
				fakeMediaViewerBlockReader{blocked: testCase.blocked},
			)
			got, err := reader.CanViewerAccessPublishedMedia(
				context.Background(),
				"mas-1",
				testCase.viewerID,
			)
			if err != nil {
				t.Fatalf("resolve Post media visibility: %v", err)
			}
			if got != testCase.want {
				t.Fatalf("visibility=%v want %v", got, testCase.want)
			}
		})
	}
}

type fakeMediaReferencedPostReader struct {
	posts []postports.MediaReferencedPostSlice
}

func (r fakeMediaReferencedPostReader) ListPostsReferencingMedia(
	context.Context,
	string,
) ([]postports.MediaReferencedPostSlice, error) {
	return r.posts, nil
}

type fakeMediaViewerBlockReader struct {
	blocked bool
}

func (r fakeMediaViewerBlockReader) IsBlockedBetween(
	context.Context,
	postports.PersonaID,
	postports.PersonaID,
) (bool, error) {
	return r.blocked, nil
}
