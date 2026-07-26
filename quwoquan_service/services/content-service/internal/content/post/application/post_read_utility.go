package post

import (
	"context"
	"strings"

	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

// generateArticleSummary 纯函数：标题 + 正文截断的兜底摘要。
func generateArticleSummary(title, body string) string {
	t := strings.TrimSpace(title)
	b := strings.TrimSpace(body)
	if b == "" {
		return t
	}
	if len(b) > 100 {
		b = b[:100]
	}
	if t == "" {
		return b
	}
	return t + "：" + b
}

func (s *PostService) GenerateArticleSummary(title, body string) string {
	return generateArticleSummary(title, body)
}

// GetPostOrTombstone 是 transport hydration 辅助读（author impact evidence 等）：
// 返回 (post, ok, deleted)。删除保留期的完整墓碑语义（410 + 保留窗口）由
// PostQueryFacade + TombstoneReader 承担，此处仅按 status=deleted 短路。
func (s *PostService) GetPostOrTombstone(ctx context.Context, postID string) (*postmodel.Post, bool, bool) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, false, false
	}
	if strings.EqualFold(strings.TrimSpace(post.Status), "deleted") {
		return nil, false, true
	}
	return normalizePostForRead(post), true, false
}
