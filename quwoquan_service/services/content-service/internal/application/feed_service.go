package application

import (
	"context"
	"sort"
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type postReader interface {
	GetByID(ctx context.Context, id string) (*postmodel.Post, bool)
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
	UserID      string
	SessionID   string
	Type        string
	SubCategory string
	Cursor      string
	Limit       int
	BlockedUserIDs  []string
	BlockedKeywords []string
}

type FeedItemView struct {
	ID           string   `json:"id"`
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
}

func (s *FeedService) ListFeed(ctx context.Context, req ListFeedRequest) (*ListFeedResponse, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	if req.UserID == "" {
		req.UserID = "guest"
	}
	recResp, err := s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
		UserID:    req.UserID,
		SessionID: req.SessionID,
		FeedType:  rtrec.FeedDiscovery,
		Cursor:    req.Cursor,
		Limit:     limit * 2,
	})
	if err != nil {
		return nil, err
	}

	views := make([]FeedItemView, 0, limit)
	requestedType := normalizeRequestType(req.Type)
	blockedUsers := toLowerSet(req.BlockedUserIDs)
	blockedKeywords := toLowerSet(req.BlockedKeywords)
	for _, item := range recResp.Items {
		post, ok := s.postReader.GetByID(ctx, item.ContentID)
		if !ok {
			continue
		}
		if _, blocked := blockedUsers[strings.ToLower(strings.TrimSpace(post.AuthorId))]; blocked {
			continue
		}
		if containsBlockedKeyword(post, blockedKeywords) {
			continue
		}
		viewType := mapContentTypeToViewType(post.ContentType)
		if requestedType != "" && viewType != requestedType {
			continue
		}
		views = append(views, FeedItemView{
			ID:           post.ID,
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
		if len(views) >= limit {
			break
		}
	}
	next := ""
	if len(views) == limit {
		next = views[len(views)-1].ID
	}
	return &ListFeedResponse{Items: views, NextCursor: next}, nil
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
	if userID == "" {
		userID = "guest"
	}
	return s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
		UserID:    userID,
		SessionID: strings.TrimSpace(req.SessionID),
		FeedType:  rtrec.FeedDiscovery,
		Cursor:    strings.TrimSpace(req.Cursor),
		Limit:     limit,
	})
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
	default:
		return strings.TrimSpace(strings.ToLower(t))
	}
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
