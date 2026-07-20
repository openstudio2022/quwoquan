package main

import (
	"context"
	"database/sql"
	"log"
	"log/slog"
	"time"

	rthealth "quwoquan_service/runtime/health"
	rtredis "quwoquan_service/runtime/redis"
	moderationapp "quwoquan_service/services/content-service/internal/application/moderation"
	"quwoquan_service/services/content-service/internal/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

// buildReportRuntime 装配举报事实的 PostgreSQL 存储、独立 outbox 消费者与健康检查。
func buildReportRuntime(
	ctx context.Context,
	cfg config,
	router *rtredis.Router,
	eventPub *messaging.RedisEventPublisher,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
	moderationFacades *moderationapp.Facades,
	postQueryReader *persistence.MongoPostQueryReader,
	authoritativeSignalSink *recinfra.AuthoritativeSignalSink,
) (*persistence.PGReportStore, func()) {
	reportDSN := resolveReportDSN(cfg)
	if reportDSN == "" {
		return nil, nil
	}

	db, err := sql.Open("postgres", reportDSN)
	if err != nil {
		log.Fatalf("content-service report postgres open failed: %v", err)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(3)
	db.SetConnMaxLifetime(30 * time.Minute)

	reportStore, err := persistence.NewPGReportStore(db)
	if err != nil {
		log.Fatalf("content-service report postgres init failed: %v", err)
	}
	healthChecker.Register("report-postgres", func(hctx context.Context) error {
		return db.PingContext(hctx)
	})
	startReportOutboxRelay(ctx, reportStore, reportStore,
		messaging.NewReportOutboxPublisher(eventPub),
		"content-report-runtime-events", "report_outbox_events", healthChecker, logger)
	startReportOutboxRelay(ctx, reportStore, reportStore,
		messaging.NewReportNotificationStreamPublisher(router.Scene("general")),
		"content-report-notification-stream", "report_notification_stream",
		healthChecker, logger)

	// 举报 → 审核闭环：第二个具名 consumer 独立 checkpoint，把 post 目标的
	// content.report.created 事实幂等投影为 PostModerationCase（同 revision 归并）。
	if moderationFacades != nil && postQueryReader != nil {
		startReportOutboxRelay(ctx, reportStore, reportStore,
			moderationapp.NewReportCaseOpener(moderationFacades, postQueryReader),
			"content-report-moderation-projection", "report_moderation_projection",
			healthChecker, logger)
	}
	// N0-3 report 负信号：服务端确认的举报事实进 HotPath 负反馈集 + 特征轨 + 学习标签。
	if authoritativeSignalSink != nil {
		startReportOutboxRelay(ctx, reportStore, reportStore,
			recinfra.NewReportSignalProjector(authoritativeSignalSink),
			"content-report-recommend-signal", "report_recommend_signal",
			healthChecker, logger)
	}
	log.Printf("content-service report storage=postgres")

	return reportStore, func() {
		_ = db.Close()
	}
}

// startCommentReportModerationProjection 在 Comment command facade 完成装配后，
// 为已核实的 comment 举报启动独立 checkpoint；与 Post moderation case 投影互不共享进度。
func startCommentReportModerationProjection(
	ctx context.Context,
	reportStore *persistence.PGReportStore,
	comments moderationapp.CommentModerationCommandFacet,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) {
	if reportStore == nil || comments == nil {
		return
	}
	startReportOutboxRelay(
		ctx,
		reportStore,
		reportStore,
		moderationapp.NewCommentReportResolutionProjector(comments),
		"content-report-comment-moderation",
		"report_comment_moderation",
		healthChecker,
		logger,
	)
}
