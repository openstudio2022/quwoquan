package http

import (
	rthealth "quwoquan_service/runtime/health"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

func WithBulkImportService(svc *application.BulkImportService) ContentHandlerOption {
	return func(h *ContentHandler) { h.importService = svc }
}

func WithHealthChecker(c *rthealth.Checker) ContentHandlerOption {
	return func(h *ContentHandler) { h.healthChecker = c }
}

// WithIntersectionService 注入交集统一体验服务（事实/概率合并、冷却窗口、已读水位）。
func WithIntersectionService(svc *application.IntersectionService) ContentHandlerOption {
	return func(h *ContentHandler) { h.intersectionService = svc }
}

func WithAuthorImpactStore(store *persistence.AuthorImpactStore) ContentHandlerOption {
	return func(h *ContentHandler) { h.authorImpactStore = store }
}
