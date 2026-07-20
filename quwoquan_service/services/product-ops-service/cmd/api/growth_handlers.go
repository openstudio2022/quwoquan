package main

import (
	"net/http"
	"strconv"
	"strings"

	"quwoquan_service/services/product-ops-service/internal/application"
	productopsgenerated "quwoquan_service/services/product-ops-service/internal/generated"
)

// handleGetPageExperience 返回按 pageName 聚合的页面体验矩阵（热力图数据源）：
// 打开次数、逐页 TTI（readyMs 均值）、停留均值与 runtime_exception 计数。
func (s *productService) handleGetPageExperience(w http.ResponseWriter, r *http.Request) {
	from, err := parseOptionalTime(r.URL.Query().Get("from"))
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	to, err := parseOptionalTime(r.URL.Query().Get("to"))
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	items, err := s.telemetry.GetPageExperience(r.Context(), application.PageExperienceQuery{From: from, To: to})
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"source": "telemetry_events",
	})
}

// handleGetGrowthOverview 返回运营增长总览：DAU 序列、PV/UV、WAU/MAU 与
// D1/D7 留存。数据源是 user_activity_daily 聚合（sessionId actor 段派生的
// actorHash 去重），不消费任何合成数据。
func (s *productService) handleGetGrowthOverview(w http.ResponseWriter, r *http.Request) {
	if s.growth == nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable("growth aggregation is not configured"))
		return
	}
	days := 30
	if raw := strings.TrimSpace(r.URL.Query().Get("days")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 || parsed > 90 {
			writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid("days must be 1..90"))
			return
		}
		days = parsed
	}
	overview, err := s.growth.Overview(r.Context(), days)
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, overview)
}
