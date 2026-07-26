package http

import (
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	"quwoquan_service/services/content-service/internal/content/post/application/authorimpact"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

func (h *ContentHandler) handleGetAuthorImpact(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	if h.authorImpactEvidenceStore == nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"AuthorImpact evidence store is not configured",
			),
		)
		return
	}
	authorID := strings.TrimSpace(r.PathValue("subAccountId"))
	if authorID == "" {
		authorID = authorImpactPathSubAccountID(r.URL.Path)
	}
	if authorID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid author id", "missing subAccountId path segment"))
		return
	}
	limit := int64(12)
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.ParseInt(raw, 10, 64)
		if err != nil || parsed <= 0 || parsed > 50 {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "无效的 limit", "limit must be an integer within [1,50]"))
			return
		}
		limit = parsed
	}
	summary, err := h.authorImpactEvidenceStore.GetSummary(
		r.Context(),
		authorID,
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	viewerID := strings.TrimSpace(ResolveUserID(r))
	summary = authorimpact.DecorateAuthorImpact(summary, viewerID != "" && viewerID == authorID)
	writeJSON(w, http.StatusOK, summary)
}

func authorImpactPathSubAccountID(path string) string {
	const prefix = "/content/sub-accounts/"
	const suffix = "/author-impact"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	return strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix))
}

// handleListAuthorImpactEvidence pages the underlying facts behind one author
// impact count (drill-down; R-ID03). Content-anchored, privacy-safe (no actor
// identity surfaced), read-path hydrates content title/cover for the view.
func (h *ContentHandler) handleListAuthorImpactEvidence(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	authorID := authorImpactEvidencePathSubAccountID(r.URL.Path)
	if authorID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid author id", "missing subAccountId path segment"))
		return
	}
	q := r.URL.Query()
	impactID := strings.TrimSpace(q.Get("impactId"))
	if impactID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "缺少 impactId", "impactId query param is required"))
		return
	}
	snapshotID := strings.TrimSpace(q.Get("evidenceSnapshotId"))
	cursor := strings.TrimSpace(q.Get("cursor"))
	if snapshotID == "" {
		snapshotID = impactID
	} else if snapshotID != impactID {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "无效的 evidenceSnapshotId", "evidenceSnapshotId must match impactId"))
		return
	}
	limit := int64(20)
	if raw := strings.TrimSpace(q.Get("limit")); raw != "" {
		parsed, err := strconv.ParseInt(raw, 10, 64)
		if err != nil || parsed <= 0 || parsed > 50 {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "无效的 limit", "limit must be an integer within [1,50]"))
			return
		}
		limit = parsed
	}
	viewerID := strings.TrimSpace(ResolveUserID(r))
	viewerIsAuthor := viewerID != "" && viewerID == authorID
	if h.authorImpactEvidenceStore == nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"AuthorImpact evidence store is not configured",
			),
		)
		return
	}
	raws, nextCursor, hasMore, total, err := h.authorImpactEvidenceStore.ListPageWithTotal(r.Context(), authorID, impactID, cursor, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	posts := make(map[string]*postmodel.Post, len(raws))
	if h.postService != nil {
		for _, raw := range raws {
			cid := strings.TrimSpace(raw.ContentID)
			if cid == "" {
				continue
			}
			if _, exists := posts[cid]; exists {
				continue
			}
			if post, ok, _ := h.postService.GetPostOrTombstone(r.Context(), cid); ok {
				posts[cid] = post
			}
		}
	}
	page := authorimpact.BuildAuthorImpactEvidencePage(
		raws, posts, nil,
		impactID, snapshotID, nextCursor, total, hasMore, viewerIsAuthor,
	)
	writeJSON(w, http.StatusOK, page)
}

func authorImpactEvidencePathSubAccountID(path string) string {
	const prefix = "/content/sub-accounts/"
	const suffix = "/author-impact/evidence"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	return strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix))
}
