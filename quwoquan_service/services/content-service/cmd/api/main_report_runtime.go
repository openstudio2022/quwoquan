package bootstrap

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"log/slog"
	"time"

	rthealth "quwoquan_service/runtime/health"
	rtredis "quwoquan_service/runtime/redis"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	postmessaging "quwoquan_service/services/content-service/internal/content/post/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	reportmessaging "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/messaging"
	reportpersistence "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/persistence"
)

// buildReportRuntime 装配举报事实的 PostgreSQL 存储、独立 outbox 消费者与健康检查。
func buildReportRuntime(
	ctx context.Context,
	workers *workerRegistry,
	cfg config,
	router *rtredis.Router,
	eventPub *postmessaging.RedisEventPublisher,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
	moderationFacades *moderationapp.Facades,
	postQueryReader *persistence.MongoPostQueryReader,
	authoritativeSignalSink *recinfra.AuthoritativeSignalSink,
) (*reportpersistence.PGReportStore, func(), error) {
	// DSN 的在场由声明式 required 校验保证，举报事实存储是启动必需依赖。
	db, err := sql.Open("postgres", cfg.Postgres.ReportDSN)
	if err != nil {
		return nil, nil, fmt.Errorf("content-service report postgres open failed: %w", err)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(3)
	db.SetConnMaxLifetime(30 * time.Minute)

	reportStore, err := reportpersistence.NewPGReportStore(db)
	if err != nil {
		_ = db.Close()
		return nil, nil, fmt.Errorf("content-service report postgres init failed: %w", err)
	}
	healthChecker.Register("report-postgres", func(hctx context.Context) error {
		return db.PingContext(hctx)
	})
	startReportOutboxRelay(ctx, workers, reportStore, reportStore,
		reportmessaging.NewReportOutboxPublisher(eventPub),
		"content-report-runtime-events", "report_outbox_events", healthChecker, logger)
	startReportOutboxRelay(ctx, workers, reportStore, reportStore,
		reportmessaging.NewReportNotificationStreamPublisher(router.Scene("general")),
		"content-report-notification-stream", "report_notification_stream",
		healthChecker, logger)

	// 举报 → 审核闭环：第二个具名 consumer 独立 checkpoint，把 post 目标的
	// content.report.ReportCreated 事实幂等投影为 PostModerationCase（同 revision 归并）。
	if moderationFacades != nil && postQueryReader != nil {
		startReportOutboxRelay(ctx, workers, reportStore, reportStore,
			moderationapp.NewReportModerationHandler(moderationFacades, postQueryReader),
			"content-report-moderation-projection", "report_moderation_projection",
			healthChecker, logger)
	}
	// N0-3 report 负信号：服务端确认的举报事实进 HotPath 负反馈集 + 特征轨 + 学习标签。
	if authoritativeSignalSink != nil {
		startReportOutboxRelay(ctx, workers, reportStore, reportStore,
			recinfra.NewReportSignalProjector(authoritativeSignalSink),
			"content-report-recommend-signal", "report_recommend_signal",
			healthChecker, logger)
	}
	log.Printf("content-service report storage=postgres")

	return reportStore, func() {
		_ = db.Close()
	}, nil
}

// startCommentReportModerationProjection 在 Comment command facade 完成装配后，
// 为已核实的 comment 举报启动独立 checkpoint；与 Post moderation case 投影互不共享进度。
func startCommentReportModerationProjection(
	ctx context.Context,
	workers *workerRegistry,
	reportStore *reportpersistence.PGReportStore,
	comments commentapp.CommentModerationCommandFacet,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) {
	if reportStore == nil || comments == nil {
		return
	}
	startReportOutboxRelay(
		ctx,
		workers,
		reportStore,
		reportStore,
		commentapp.NewReportResolutionPublisher(
			commentapp.NewCommentReportResolutionHandler(comments),
		),
		"content-report-comment-moderation",
		"report_comment_moderation",
		healthChecker,
		logger,
	)
}
