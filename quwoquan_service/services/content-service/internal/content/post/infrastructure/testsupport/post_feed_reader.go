package testsupport

import (
	"context"
	"strings"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// PostFeedReader 仅供 local_contract 使用，模拟生产具名 PostFeedReader 的
// identity/type/keyset 语义；生产装配必须使用 MongoPostQueryReader。
type PostFeedReader struct {
	store *PostStore
}

func NewPostFeedReader(store *PostStore) *PostFeedReader {
	return &PostFeedReader{store: store}
}

func (r *PostFeedReader) FindPublishedFeedPost(
	ctx context.Context,
	postID postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	post, found := r.store.FindByID(ctx, string(postID))
	if !found || !isPublishedPublicPost(*post) {
		return postports.PostFeedItemSlice{}, false, nil
	}
	return postFeedSliceFromModel(*post), true, nil
}

// FindPublishedFeedPosts 与生产 Mongo $in 批量读同语义（N3-1）：未命中缺席。
func (r *PostFeedReader) FindPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	postIDs := request.PostIDs()
	out := make(map[postports.PostID]postports.PostFeedItemSlice, len(postIDs))
	for _, id := range postIDs {
		if _, exists := out[id]; exists {
			continue
		}
		slice, ok, err := r.FindPublishedFeedPost(ctx, id)
		if err != nil {
			return nil, err
		}
		if ok {
			if activeReleaseID := strings.TrimSpace(request.ActiveReleaseID()); activeReleaseID != "" {
				slice.SourceOwner = "qwq_data"
				slice.ReleaseID = activeReleaseID
				slice.ManifestDigest = strings.TrimSpace(request.ManifestDigest())
				slice.LifecycleStatus = "active"
			}
			out[id] = slice
		}
	}
	return out, nil
}

func (r *PostFeedReader) ListPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	posts, err := r.store.ListAll(ctx)
	if err != nil {
		return postports.PostFeedSlice{}, err
	}
	items := make([]postports.PostFeedItemSlice, 0, request.Limit())
	started := request.CursorPostID() == ""
	for _, post := range posts {
		if !isPublishedPublicPost(post) || !postMatchesFeedRequest(post, request) {
			continue
		}
		if !started {
			if post.ID == string(request.CursorPostID()) {
				started = true
			}
			continue
		}
		item := postFeedSliceFromModel(post)
		if activeReleaseID := strings.TrimSpace(request.ActiveReleaseID()); activeReleaseID != "" {
			item.SourceOwner = "qwq_data"
			item.ReleaseID = activeReleaseID
			item.ManifestDigest = strings.TrimSpace(request.ManifestDigest())
			item.LifecycleStatus = "active"
		}
		items = append(items, item)
		if len(items) >= request.Limit() {
			break
		}
	}
	return postports.PostFeedSlice{Items: items}, nil
}

func postMatchesFeedRequest(post postmodel.Post, request postports.PostFeedReadRequest) bool {
	identity := strings.TrimSpace(string(request.Identity()))
	if identity != "" && resolvedTestPostIdentity(post) != identity {
		return false
	}
	contentType := strings.TrimSpace(string(request.ContentType()))
	return contentType == "" || strings.EqualFold(strings.TrimSpace(post.ContentType), contentType)
}

func resolvedTestPostIdentity(post postmodel.Post) string {
	identity := strings.ToLower(strings.TrimSpace(post.ContentIdentity))
	if identity == "moment" || identity == "work" {
		return identity
	}
	if strings.EqualFold(strings.TrimSpace(post.ContentType), "micro") {
		return "moment"
	}
	return "work"
}

func isPublishedPublicPost(post postmodel.Post) bool {
	return strings.EqualFold(strings.TrimSpace(post.Status), "published") &&
		strings.EqualFold(strings.TrimSpace(post.Visibility), "public")
}

func postFeedSliceFromModel(post postmodel.Post) postports.PostFeedItemSlice {
	return postports.PostFeedItemSlice{
		PostID:           postports.NewPostID(post.ID),
		AuthorPersonaID:  postports.NewPersonaID(post.AuthorId),
		ContentType:      postports.ContentType(post.ContentType),
		ContentIdentity:  postports.ContentIdentity(post.ContentIdentity),
		Title:            post.Title,
		Body:             post.Body,
		MediaURLs:        append([]string(nil), post.MediaUrls...),
		VideoURL:         post.VideoUrl,
		CoverURL:         post.CoverUrl,
		ThumbnailURL:     post.ThumbnailUrl,
		CoverStrategy:    post.CoverStrategy,
		CoverFrameTimeMS: post.CoverFrameTimeMs,
		DurationMS:       post.DurationMs,
		TagRefs:          append([]string(nil), post.TagRefs...),
		EntityRefs:       append([]string(nil), post.EntityRefs...),
		ContentVertical:  post.ContentVertical,
		SourceTaskID:     post.SourceTaskId,
		LikeCount:        post.LikeCount,
		CommentCount:     post.CommentCount,
		ShareCount:       post.ShareCount,
		CreatedAt:        post.CreatedAt,
		UpdatedAt:        post.UpdatedAt,
		PublishedAt:      post.PublishedAt,
	}
}

var _ postports.PostFeedReader = (*PostFeedReader)(nil)
