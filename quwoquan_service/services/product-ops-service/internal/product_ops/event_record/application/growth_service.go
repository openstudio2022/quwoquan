package application

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"log"
	"sort"
	"strings"
	"time"
)

// DailyActivity 是 user_activity_daily 聚合事实：一天内的活跃用户集合与
// 流量计数。actorHashes 与遥测/日志的 actorHash 同派生域（sha256(actorId)），
// 由 sessionId 的 actor 段解码后哈希得出，不存任何明文用户标识。
type DailyActivity struct {
	Date         string    `json:"date" bson:"_id"`
	ActorHashes  []string  `json:"-" bson:"actorHashes"`
	DAU          int       `json:"dau" bson:"dau"`
	PV           int64     `json:"pv" bson:"pv"`
	SessionCount int64     `json:"sessionCount" bson:"sessionCount"`
	NewActors    int       `json:"newActors" bson:"newActors"`
	UpdatedAt    time.Time `json:"updatedAt" bson:"updatedAt"`
}

// GrowthStore 持久化天级活跃聚合与用户首见事实（留存 cohort 的基础）。
type GrowthStore interface {
	UpsertDailyActivity(context.Context, DailyActivity) error
	ListDailyActivity(ctx context.Context, fromDate, toDate string) ([]DailyActivity, error)
	// EnsureActorFirstSeen 以 setOnInsert 语义登记首见日期（幂等）。
	EnsureActorFirstSeen(ctx context.Context, date string, actorHashes []string) error
	// ListActorFirstSeen 返回给定日期首见的 actor 集合（新增口径与留存分母）。
	ListActorFirstSeen(ctx context.Context, date string) ([]string, error)
}

// ActiveSessionLister 由事件仓库实现：返回窗口内 distinct sessionId 与事件总数。
// SLS 用 SQL 聚合，memory/postgres 遍历；上限保护防止无界拉取。
type ActiveSessionLister interface {
	ListDistinctSessions(ctx context.Context, from, to time.Time, limit int) (sessions []string, totalEvents int64, err error)
}

type GrowthOverview struct {
	Days        []DailyActivity `json:"days"`
	TodayPV     int64           `json:"todayPv"`
	TodayDAU    int             `json:"todayDau"`
	WAU         int             `json:"wau"`
	MAU         int             `json:"mau"`
	D1Retention float64         `json:"d1RetentionPercent"`
	D7Retention float64         `json:"d7RetentionPercent"`
	Source      string          `json:"source"`
	GeneratedAt string          `json:"generatedAt"`
}

const maxDailyDistinctSessions = 200000

type GrowthService struct {
	store    GrowthStore
	sessions ActiveSessionLister
	now      func() time.Time
}

func NewGrowthService(store GrowthStore, sessions ActiveSessionLister) *GrowthService {
	if store == nil || sessions == nil {
		panic("growth service requires growth store and session lister")
	}
	return &GrowthService{store: store, sessions: sessions, now: time.Now}
}

// AggregateDay 聚合指定自然日（UTC）的活跃事实并幂等落库。
func (s *GrowthService) AggregateDay(ctx context.Context, day time.Time) error {
	dayStart := day.UTC().Truncate(24 * time.Hour)
	dayEnd := dayStart.Add(24 * time.Hour)
	date := dayStart.Format("2006-01-02")

	sessions, totalEvents, err := s.sessions.ListDistinctSessions(ctx, dayStart, dayEnd, maxDailyDistinctSessions)
	if err != nil {
		return fmt.Errorf("list distinct sessions for %s: %w", date, err)
	}
	actorSet := map[string]struct{}{}
	for _, sessionID := range sessions {
		actorHash, ok := actorHashFromSessionID(sessionID)
		if !ok {
			continue
		}
		actorSet[actorHash] = struct{}{}
	}
	actorHashes := make([]string, 0, len(actorSet))
	for actorHash := range actorSet {
		actorHashes = append(actorHashes, actorHash)
	}
	sort.Strings(actorHashes)

	if err := s.store.EnsureActorFirstSeen(ctx, date, actorHashes); err != nil {
		return fmt.Errorf("ensure actor first seen for %s: %w", date, err)
	}
	// newActors 以首见事实全量为准（而非本次插入数），保证重复聚合幂等。
	firstSeenToday, err := s.store.ListActorFirstSeen(ctx, date)
	if err != nil {
		return fmt.Errorf("list actor first seen for %s: %w", date, err)
	}
	newActors := len(firstSeenToday)
	return s.store.UpsertDailyActivity(ctx, DailyActivity{
		Date:         date,
		ActorHashes:  actorHashes,
		DAU:          len(actorHashes),
		PV:           totalEvents,
		SessionCount: int64(len(sessions)),
		NewActors:    newActors,
		UpdatedAt:    s.now().UTC(),
	})
}

// Overview 产出增长总览：DAU 序列 + WAU/MAU（窗口 union 去重）+ D1/D7 留存
// （cohort = 首见于 D0 的用户；留存 = cohort 与 D0+N 活跃集合的交集比例）。
func (s *GrowthService) Overview(ctx context.Context, days int) (GrowthOverview, error) {
	if days <= 0 || days > 90 {
		days = 30
	}
	now := s.now().UTC()
	today := now.Truncate(24 * time.Hour)
	fromDate := today.AddDate(0, 0, -(days - 1)).Format("2006-01-02")
	toDate := today.Format("2006-01-02")

	items, err := s.store.ListDailyActivity(ctx, fromDate, toDate)
	if err != nil {
		return GrowthOverview{}, err
	}
	byDate := make(map[string]DailyActivity, len(items))
	for _, item := range items {
		byDate[item.Date] = item
	}

	out := GrowthOverview{
		Days:        make([]DailyActivity, 0, days),
		Source:      "user_activity_daily",
		GeneratedAt: now.Format(time.RFC3339),
	}
	for offset := days - 1; offset >= 0; offset-- {
		date := today.AddDate(0, 0, -offset).Format("2006-01-02")
		item, exists := byDate[date]
		if !exists {
			item = DailyActivity{Date: date}
		}
		item.ActorHashes = nil // wire 不暴露用户集合
		out.Days = append(out.Days, item)
	}

	unionWindow := func(windowDays int) int {
		union := map[string]struct{}{}
		for offset := 0; offset < windowDays; offset++ {
			date := today.AddDate(0, 0, -offset).Format("2006-01-02")
			for _, actorHash := range byDate[date].ActorHashes {
				union[actorHash] = struct{}{}
			}
		}
		return len(union)
	}
	out.WAU = unionWindow(7)
	out.MAU = unionWindow(30)
	todayItem := byDate[toDate]
	out.TodayDAU = todayItem.DAU
	out.TodayPV = todayItem.PV
	out.D1Retention = s.retention(ctx, byDate, today, 1)
	out.D7Retention = s.retention(ctx, byDate, today, 7)
	return out, nil
}

// retention 计算最近一个可评估 cohort 的 DN 留存：
// cohort 日 = today-N-1 之后最近一个有新增的日子会引入口径抖动，
// 固定取 cohort 日 = today-N（该日新增用户在 today 仍活跃的比例需要完整 N 天，
// 因此取 cohortDate = today - N，activeDate = today）。
func (s *GrowthService) retention(
	ctx context.Context,
	byDate map[string]DailyActivity,
	today time.Time,
	n int,
) float64 {
	cohortDate := today.AddDate(0, 0, -n).Format("2006-01-02")
	activeDate := today.Format("2006-01-02")
	cohort, err := s.store.ListActorFirstSeen(ctx, cohortDate)
	if err != nil || len(cohort) == 0 {
		return 0
	}
	active := map[string]struct{}{}
	for _, actorHash := range byDate[activeDate].ActorHashes {
		active[actorHash] = struct{}{}
	}
	retained := 0
	for _, actorHash := range cohort {
		if _, ok := active[actorHash]; ok {
			retained++
		}
	}
	return 100 * float64(retained) / float64(len(cohort))
}

// RunGrowthAggregationLoop 周期性聚合今天与昨天（跨日补偿），幂等 upsert。
func (s *GrowthService) RunGrowthAggregationLoop(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 30 * time.Minute
	}
	aggregate := func() {
		now := s.now().UTC()
		for _, day := range []time.Time{now, now.AddDate(0, 0, -1)} {
			if err := s.AggregateDay(ctx, day); err != nil {
				log.Printf("WARN: growth aggregation %s failed: %v", day.Format("2006-01-02"), err)
			}
		}
	}
	aggregate()
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			aggregate()
		}
	}
}

// actorHashFromSessionID 从 canonical sessionId（s.<base64url(actorId)>.<ts>）
// 提取 actor 段并哈希到与遥测/日志一致的 actorHash 域。
func actorHashFromSessionID(sessionID string) (string, bool) {
	if !strings.HasPrefix(sessionID, "s.") {
		return "", false
	}
	separator := strings.LastIndex(sessionID, ".")
	if separator <= 2 {
		return "", false
	}
	actorID, err := base64.RawURLEncoding.DecodeString(sessionID[2:separator])
	if err != nil || len(actorID) == 0 {
		return "", false
	}
	sum := sha256.Sum256(actorID)
	return hex.EncodeToString(sum[:]), true
}
