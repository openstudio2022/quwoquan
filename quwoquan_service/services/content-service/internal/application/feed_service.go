package application

import (
	"context"
	"encoding/base64"
	"sort"
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type postReader interface {
	GetByID(ctx context.Context, id string) (*postmodel.Post, bool)
}

type publishedPostReader interface {
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
}

type FeedService struct {
	engine     *rtrec.Engine
	postReader postReader
}

func NewFeedService(engine *rtrec.Engine, reader postReader) *FeedService {
	return &FeedService{
		engine:     engine,
		postReader: reader,
	}
}

type ListFeedRequest struct {
	UserID          string
	SessionID       string
	Identity        string
	Type            string
	Sort            string
	SubCategory     string
	Cursor          string
	Limit           int
	BlockedUserIDs  []string
	BlockedKeywords []string
}

type FeedItemView struct {
	ID           string   `json:"id"`
	PostID       string   `json:"postId"`
	WireID       string   `json:"_id"`
	Type         string   `json:"type"`
	ContentType  string   `json:"contentType"`
	AuthorID     string   `json:"authorId"`
	Title        string   `json:"title,omitempty"`
	Body         string   `json:"body,omitempty"`
	Images       []string `json:"images,omitempty"`
	VideoURL     string   `json:"videoUrl,omitempty"`
	CoverURL     string   `json:"coverUrl,omitempty"`
	LikeCount    int64    `json:"likesCount"`
	CommentCount int64    `json:"commentsCount"`
	SaveCount    int64    `json:"savesCount"`
	ShareCount   int64    `json:"shares"`
	CreatedAt    string   `json:"createdAt"`
}

type ListFeedResponse struct {
	Items      []FeedItemView `json:"items"`
	NextCursor string         `json:"nextCursor,omitempty"`
	Cursor     string         `json:"cursor,omitempty"`
}

func (s *FeedService) ListFeed(ctx context.Context, req ListFeedRequest) (*ListFeedResponse, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	req.UserID = normalizeAnonymousSubAccountID(req.UserID)
	views := make([]FeedItemView, 0, limit)
	requestedIdentity := normalizeRequestedIdentity(req.Identity)
	requestedType := normalizeRequestType(req.Type)
	blockedUsers := toLowerSet(req.BlockedUserIDs)
	blockedKeywords := toLowerSet(req.BlockedKeywords)

	requestedCursor := strings.TrimSpace(req.Cursor)
	repositoryCursor := decodeRepositoryFeedCursor(requestedCursor)
	cursor := requestedCursor
	nextCursor := ""
	seenPostIDs := map[string]struct{}{}
	_, cursorIsPostID := s.postReader.GetByID(ctx, repositoryCursor)
	useRepositoryPagination := cursorIsPostID || requestedType != "" || requestedIdentity != ""
	appendPost := func(post *postmodel.Post) bool {
		if post == nil {
			return false
		}
		if _, seen := seenPostIDs[post.ID]; seen {
			return false
		}
		if _, blocked := blockedUsers[strings.ToLower(strings.TrimSpace(post.AuthorId))]; blocked {
			return false
		}
		if containsBlockedKeyword(post, blockedKeywords) {
			return false
		}
		postIdentity := resolvedContentIdentity(post.ContentType, post.ContentIdentity)
		if requestedIdentity != "" && postIdentity != requestedIdentity {
			return false
		}
		viewType := mapContentTypeToViewType(post.ContentType)
		if requestedType != "" && requestedIdentity != "moment" && viewType != requestedType {
			return false
		}
		seenPostIDs[post.ID] = struct{}{}
		views = append(views, FeedItemView{
			ID:           post.ID,
			PostID:       post.ID,
			WireID:       post.ID,
			Type:         viewType,
			ContentType:  post.ContentType,
			AuthorID:     post.AuthorId,
			Title:        post.Title,
			Body:         post.Body,
			Images:       toStringSlice(post.MediaUrls),
			VideoURL:     post.VideoUrl,
			CoverURL:     post.CoverUrl,
			LikeCount:    post.LikeCount,
			CommentCount: post.CommentCount,
			SaveCount:    post.FavoriteCount,
			ShareCount:   post.ShareCount,
			CreatedAt:    post.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
		})
		return true
	}
	for attempt := 0; !useRepositoryPagination && attempt < 4 && len(views) < limit; attempt++ {
		recResp, err := s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
			UserID:    req.UserID,
			SessionID: req.SessionID,
			FeedType:  rtrec.FeedDiscovery,
			Sort:      normalizeFeedSort(req.Sort),
			Cursor:    cursor,
			Limit:     limit,
		})
		if err != nil {
			return nil, err
		}
		nextCursor = recResp.NextCursor
		for _, item := range recResp.Items {
			post, ok := s.postReader.GetByID(ctx, item.ContentID)
			if !ok {
				continue
			}
			appendPost(post)
			if len(views) >= limit {
				break
			}
		}
		if nextCursor == "" {
			break
		}
		cursor = nextCursor
	}
	if len(views) < limit {
		if publishedReader, ok := s.postReader.(publishedPostReader); ok {
			fallbackCursor := repositoryCursor
			for attempt := 0; attempt < 4 && len(views) < limit; attempt++ {
				posts := publishedReader.ListPublished(ctx, limit*2, fallbackCursor)
				if len(posts) == 0 {
					break
				}
				for i := range posts {
					post := posts[i]
					if appendPost(&post) && len(views) >= limit {
						nextCursor = encodeRepositoryFeedCursor(post.ID)
						break
					}
				}
				if len(views) >= limit || len(posts) < limit*2 {
					break
				}
				fallbackCursor = posts[len(posts)-1].ID
			}
		}
	}
	return &ListFeedResponse{Items: views, NextCursor: nextCursor, Cursor: nextCursor}, nil
}

func encodeRepositoryFeedCursor(postID string) string {
	trimmed := strings.TrimSpace(postID)
	if trimmed == "" {
		return ""
	}
	return "repo:" + base64.RawURLEncoding.EncodeToString([]byte(trimmed))
}

func decodeRepositoryFeedCursor(cursor string) string {
	trimmed := strings.TrimSpace(cursor)
	if strings.HasPrefix(trimmed, "repo:") {
		decoded, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(trimmed, "repo:"))
		if err == nil {
			return strings.TrimSpace(string(decoded))
		}
		return ""
	}
	return trimmed
}

func (s *FeedService) GetPost(ctx context.Context, id string) (*postmodel.Post, bool) {
	return s.postReader.GetByID(ctx, id)
}

type RecommendRequest struct {
	UserID    string `json:"userId"`
	SessionID string `json:"sessionId"`
	Cursor    string `json:"cursor"`
	Limit     int    `json:"limit"`
}

func (s *FeedService) Recommend(ctx context.Context, req RecommendRequest) (*rtrec.FeedResponse, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	userID := strings.TrimSpace(req.UserID)
	userID = normalizeAnonymousSubAccountID(userID)
	return s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
		UserID:    userID,
		SessionID: strings.TrimSpace(req.SessionID),
		FeedType:  rtrec.FeedDiscovery,
		Sort:      rtrec.FeedSortRecommend,
		Cursor:    strings.TrimSpace(req.Cursor),
		Limit:     limit,
	})
}

func normalizeFeedSort(sortValue string) string {
	switch strings.TrimSpace(strings.ToLower(sortValue)) {
	case "", rtrec.FeedSortRecommend:
		return rtrec.FeedSortRecommend
	default:
		return rtrec.FeedSortRecommend
	}
}

func mapContentTypeToViewType(contentType string) string {
	switch strings.TrimSpace(contentType) {
	case "micro":
		return "moment"
	case "image":
		return "image"
	case "video":
		return "video"
	case "article":
		return "article"
	default:
		return "image"
	}
}

func normalizeRequestType(t string) string {
	switch strings.TrimSpace(strings.ToLower(t)) {
	case "", "recommended", "following":
		return ""
	case "photo":
		return "image"
	case "note":
		return "article"
	default:
		return strings.TrimSpace(strings.ToLower(t))
	}
}

func normalizeRequestedIdentity(identity string) string {
	switch strings.TrimSpace(strings.ToLower(identity)) {
	case "moment", "work":
		return strings.TrimSpace(strings.ToLower(identity))
	default:
		return ""
	}
}

func resolvedContentIdentity(contentType, contentIdentity string) string {
	normalized := strings.TrimSpace(strings.ToLower(contentIdentity))
	if normalized == "moment" || normalized == "work" {
		return normalized
	}
	if strings.TrimSpace(strings.ToLower(contentType)) == "micro" {
		return "moment"
	}
	return "work"
}

func toStringSlice(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			s := strings.TrimSpace(toString(item))
			if s != "" {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

func toString(v any) string {
	switch vv := v.(type) {
	case string:
		return vv
	default:
		return ""
	}
}

func toLowerSet(items []string) map[string]struct{} {
	out := make(map[string]struct{}, len(items))
	for _, item := range items {
		v := strings.ToLower(strings.TrimSpace(item))
		if v != "" {
			out[v] = struct{}{}
		}
	}
	return out
}

func containsBlockedKeyword(post *postmodel.Post, blocked map[string]struct{}) bool {
	if len(blocked) == 0 {
		return false
	}
	targets := []string{
		post.Title,
		post.Body,
	}
	if tags := toStringSlice(post.Tags); len(tags) > 0 {
		targets = append(targets, tags...)
	}
	for _, text := range targets {
		normalized := strings.ToLower(strings.TrimSpace(text))
		if normalized == "" {
			continue
		}
		for keyword := range blocked {
			if strings.Contains(normalized, keyword) {
				return true
			}
		}
	}
	return false
}

func SortPostsByCreatedAtDesc(posts []postmodel.Post) {
	sort.Slice(posts, func(i, j int) bool {
		return posts[i].CreatedAt.After(posts[j].CreatedAt)
	})
}
