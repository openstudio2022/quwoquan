package searchprojection

import (
	"context"
	"strconv"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
)

type PublishedPostReader interface {
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
}

// PostCandidateSource adapts the content store into a rtsearch.CandidateSource.
type PostCandidateSource struct {
	Reader PublishedPostReader
}

func (PostCandidateSource) SourceName() string { return "content" }

func (s PostCandidateSource) Candidates(ctx context.Context, plan rtsearch.RetrievePlan) ([]rtsearch.Document, error) {
	if s.Reader == nil || !plan.WantsAny(rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo) {
		return nil, nil
	}
	limit := plan.Limit
	if limit <= 0 {
		limit = 20
	}
	posts := s.Reader.ListPublished(ctx, limit*8, "")
	docs := make([]rtsearch.Document, 0, len(posts))
	for _, stored := range posts {
		docs = append(docs, ProjectPostToSearchDocument(stored))
	}
	return docs, nil
}

// ProjectPostToSearchDocument is the single source of truth for post -> search
// Document mapping, shared by native retrieve and ES indexing.
func ProjectPostToSearchDocument(stored postmodel.Post) rtsearch.Document {
	post := normalizePostForSearchRead(stored)
	summary := strings.TrimSpace(post.Summary)
	if summary == "" {
		summary = strings.TrimSpace(post.Body)
	}
	visibility := strings.TrimSpace(post.Visibility)
	if visibility == "" {
		visibility = "public"
	}
	coverAssetID, coverAccessMode := postCoverDelivery(post)
	doc := rtsearch.Document{
		ObjectType:   rtsearch.ObjectTypeContentPost,
		ObjectID:     post.ID,
		Title:        post.Title,
		Summary:      summary,
		Body:         post.Body,
		SourceDomain: "content",
		ContentType:  post.ContentType,
		Visibility:   visibility,
		BadgeLabel:   "内容",
		Tags:         stringSlice(post.TagRefs),
		Entities:     stringSlice(post.EntityRefs),
		Popularity:   float64(post.LikeCount + post.CommentCount + post.ShareCount),
		Freshness:    post.PublishedAt,
		Fields: map[string]string{
			"authorId":          post.AuthorId,
			"authorName":        post.AuthorDisplayNameSnapshot,
			"authorDisplayName": post.AuthorDisplayNameSnapshot,
			"authorAvatarUrl":   post.AuthorAvatarUrlSnapshot,
			"contentIdentity":   post.ContentIdentity,
			"coverUrl":          post.CoverUrl,
			// 封面的配对媒体资产标识与交付访问模式（DEC-033）。research 相位的
			// coverUrl 是相对私有 CAS 引用而非公开 URL，搜索结果卡必须按
			// coverAssetId 换短签才渲染得出来；只投影 URL 等于让私有封面在
			// 搜索面整片空白。
			"coverAssetId":    coverAssetID,
			"coverAccessMode": coverAccessMode,
			"coverWidth":      strconv.FormatInt(post.Width, 10),
			"coverHeight":     strconv.FormatInt(post.Height, 10),
			"likeCount":       strconv.FormatInt(post.LikeCount, 10),
			"placeName":       post.LocationName,
		},
	}
	if !post.PublishedAt.IsZero() {
		doc.Fields["publishedAt"] = post.PublishedAt.UTC().Format(time.RFC3339Nano)
	}
	if post.Location.Latitude != 0 || post.Location.Longitude != 0 {
		doc.Geo = &rtsearch.GeoPoint{Lat: post.Location.Latitude, Lng: post.Location.Longitude}
	}
	return doc
}

// postCoverDelivery 把封面 URL 配对回 mediaItems 的 typed 交付声明（DEC-033）。
//
// 视频封面与视频本体是两个资产：封面优先取同条目的 coverAssetId，取不到才回落
// 到该条目自身的 mediaAssetId。配不上任何条目即两字段都缺席（契约 NULLABLE），
// 不猜一个 accessMode——猜 public 会让私有封面走公开直连。
func postCoverDelivery(post postmodel.Post) (string, string) {
	cover := strings.TrimSpace(post.CoverUrl)
	if cover == "" {
		return "", ""
	}
	for _, media := range post.MediaItems {
		if strings.TrimSpace(media.CoverUrl) == cover {
			assetID := strings.TrimSpace(media.CoverAssetId)
			if assetID == "" {
				assetID = strings.TrimSpace(media.MediaAssetId)
			}
			return assetID, strings.TrimSpace(media.AccessMode)
		}
	}
	for _, media := range post.MediaItems {
		if strings.TrimSpace(media.Url) == cover {
			return strings.TrimSpace(media.MediaAssetId), strings.TrimSpace(media.AccessMode)
		}
	}
	return "", ""
}

func normalizePostForSearchRead(post postmodel.Post) postmodel.Post {
	if strings.TrimSpace(post.ContentIdentity) == "" {
		if strings.TrimSpace(strings.ToLower(post.ContentType)) == "micro" {
			post.ContentIdentity = "moment"
		} else {
			post.ContentIdentity = "work"
		}
	}
	if strings.TrimSpace(post.Visibility) == "" {
		post.Visibility = "public"
	}
	return post
}

func stringSlice(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			if s, ok := item.(string); ok {
				if trimmed := strings.TrimSpace(s); trimmed != "" {
					out = append(out, trimmed)
				}
			}
		}
		return out
	default:
		return nil
	}
}
