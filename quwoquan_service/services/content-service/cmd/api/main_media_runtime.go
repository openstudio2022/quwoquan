package main

import (
	"context"
	"log"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	rthealth "quwoquan_service/runtime/health"
	runtimemedia "quwoquan_service/runtime/media"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	iplocation "quwoquan_service/services/content-service/internal/application/iplocation"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/application/media/processing"
	mediareprocess "quwoquan_service/services/content-service/internal/application/media/reprocess"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	mediainfra "quwoquan_service/services/content-service/internal/infrastructure/content/media"
	mediaprocinfra "quwoquan_service/services/content-service/internal/infrastructure/content/media/processing"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

type mediaRuntimeComposition struct {
	mediaService               *mediaapp.Facades
	mediaImageReprocessService *mediareprocess.Service
	mediaObjectGateway         *mediainfra.ObjectGateway
	commentServiceCore         *commentapp.CommentService
}

// buildMediaRuntime 装配 OSS、媒体对象 Facade、处理 worker 与评论属地依赖。
func buildMediaRuntime(
	ctx context.Context,
	cfg config,
	appEnv string,
	instanceID string,
	logger *slog.Logger,
	healthChecker *rthealth.Checker,
	mediaStore *persistence.MongoMediaStore,
	commentDataAdapter *persistence.MongoCommentDataAdapter,
	reactionStore *persistence.MongoContentReactionStore,
	recDB *mongo.Database,
	postMediaReader postports.MediaReferencedPostReader,
	viewerBlockReader *recinfra.PersonaBlockReader,
) (mediaRuntimeComposition, func()) {
	ossCfg := runtimemedia.OSSConfig{
		Endpoint:        contentOSSEndpoint(getenvOrDefault("CONTENT_OSS_ENDPOINT", cfg.OSS.Endpoint), cfg.OSS.UseSSL),
		Bucket:          getenvOrDefault("CONTENT_OSS_BUCKET", cfg.OSS.Bucket),
		Region:          getenvOrDefault("CONTENT_OSS_REGION", cfg.OSS.Region),
		AccessKeyID:     getenvOrDefault("CONTENT_OSS_ACCESS_KEY_ID", cfg.OSS.AccessKeyID),
		AccessKeySecret: getenvOrDefault("CONTENT_OSS_ACCESS_KEY_SECRET", cfg.OSS.AccessKeySecret),
		CDNDomain:       getenvOrDefault("CONTENT_CDN_DOMAIN", cfg.OSS.CDNDomain),
		CDNSignKey:      getenvOrDefault("CONTENT_CDN_SIGN_KEY", cfg.OSS.CDNSignKey),
		PresignTTL:      time.Duration(cfg.OSS.PresignTTLMin) * time.Minute,
		CDNTTL:          time.Duration(cfg.OSS.CDNTTLMin) * time.Minute,
	}
	if ossCfg.PresignTTL == 0 {
		ossCfg.PresignTTL = 15 * time.Minute
	}
	if ossCfg.CDNTTL == 0 {
		ossCfg.CDNTTL = 60 * time.Minute
	}
	if strings.TrimSpace(ossCfg.Endpoint) == "" || strings.TrimSpace(ossCfg.Bucket) == "" ||
		strings.TrimSpace(ossCfg.Region) == "" || strings.TrimSpace(ossCfg.AccessKeyID) == "" ||
		strings.TrimSpace(ossCfg.AccessKeySecret) == "" || strings.TrimSpace(ossCfg.CDNDomain) == "" ||
		strings.TrimSpace(ossCfg.CDNSignKey) == "" {
		log.Fatal("content-service OSS endpoint, bucket, region, credentials, CDN domain and signing key are required")
	}
	ossPresigner := runtimemedia.NewS3PresignClient(ossCfg)
	log.Printf("content-service oss presigner=s3 endpoint=%s bucket=%s", ossCfg.Endpoint, ossCfg.Bucket)

	mediaObjectGateway, err := mediainfra.NewObjectGateway(mediainfra.ObjectGatewayConfig{
		Bucket: ossCfg.Bucket, CDNDomain: ossCfg.CDNDomain, CDNSignKey: ossCfg.CDNSignKey, DeliveryTTL: ossCfg.CDNTTL,
	}, ossPresigner)
	if err != nil {
		log.Fatalf("content-service media object gateway invalid: %v", err)
	}
	if mediaStore == nil {
		log.Fatal("content-service MediaUploadSession/MediaAsset store is not configured")
	}
	if postMediaReader == nil || viewerBlockReader == nil {
		log.Fatal("content-service Post media visibility reader is not configured")
	}
	mediaServiceCore := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(mediaStore),
		mediaObjectGateway,
		mediaapp.WithOriginalAccessPostVisibilityReader(
			postapp.NewMediaAssetVisibilityReader(postMediaReader, viewerBlockReader),
		),
	)
	mediaService := mediaapp.BindFacades(mediaServiceCore)

	// Media processing worker 是 media outbox 的唯一生产消费者。图片与视频发布
	// 都依赖 processing -> ready/rejected 的确定终态，因此生产组合不提供禁用或内存回退。
	mediaProcessor, processorErr := mediaprocinfra.NewFFmpegMediaProcessor(
		ossPresigner,
		mediaprocinfra.Config{
			Bucket:              ossCfg.Bucket,
			FFmpegPath:          cfg.MediaProcessing.FFmpegPath,
			FFprobePath:         cfg.MediaProcessing.FFprobePath,
			WorkDir:             cfg.MediaProcessing.WorkDir,
			JobTimeout:          time.Duration(cfg.MediaProcessing.JobTimeoutMs) * time.Millisecond,
			MinWorkDirFreeBytes: cfg.MediaProcessing.MinWorkDirFreeBytes,
		},
	)
	if processorErr != nil {
		log.Fatalf("content-service media processing pipeline unavailable: %v", processorErr)
	}
	mediaProcessingWorker := mediaprocessing.NewWorker(
		mediaStore,
		mediaStore,
		mediaStore,
		mediaProcessor,
		mediaServiceCore,
		mediaStore,
		mediaprocessing.WithObserver(mediaprocinfra.NewMetricsObserver()),
	)
	workerInterval := time.Duration(cfg.MediaProcessing.IntervalMs) * time.Millisecond
	if workerInterval <= 0 {
		workerInterval = 2 * time.Second
	}
	go func() {
		if err := mediaProcessingWorker.Run(ctx, workerInterval); err != nil && ctx.Err() == nil {
			logger.Error("content media processing worker stopped", "error", err)
		}
	}()
	healthChecker.Register("content_media_processing_worker", func(_ context.Context) error {
		return mediaProcessingWorker.Ready(15 * time.Minute)
	})
	log.Printf("content-service media processing worker enabled interval=%s", workerInterval)

	// Image reprocess shares the trusted FFmpeg processor and MediaAsset command
	// facet, but owns a separate operational run cursor/lease. It therefore can
	// later extract as a worker service without creating a second media state
	// machine or changing normal upload processing.
	mediaImageReprocessService := mediareprocess.NewService(mediaStore, mediaStore)
	mediaImageReprocessWorker := mediareprocess.NewWorker(
		mediaStore,
		mediaStore,
		mediaProcessor,
		mediaService,
		"content-media-image-reprocess-"+strings.TrimSpace(instanceID),
	)
	go func() {
		ticker := time.NewTicker(workerInterval)
		defer ticker.Stop()
		for {
			if _, err := mediaImageReprocessWorker.Drain(ctx, 10); err != nil && ctx.Err() == nil {
				logger.Error("content media image reprocess worker batch failed", "error", err)
			}
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}
		}
	}()
	log.Printf("content-service media image reprocess worker enabled interval=%s", workerInterval)

	commentIPLocationResolver, closeIPLocationResolver, err :=
		buildCommentIPLocationResolver(cfg, appEnv, newIP2RegionResolver)
	if err != nil {
		log.Fatalf("content-service comment IP location resolver unavailable: %v", err)
	}
	commentServiceCore := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			commentDataAdapter,
			persistence.NewCommentAttachmentReader(mediaStore, mediaObjectGateway),
			reactionStore,
			persistence.NewCommentViewerRelationMongoReader(recDB),
			viewerBlockReader,
		),
		commentapp.WithRateLimitConfig(commentapp.RateLimitConfig{
			BurstWindow: time.Duration(
				cfg.CommentRateLimit.BurstWindowSeconds,
			) * time.Second,
			BurstMax: cfg.CommentRateLimit.BurstMax,
			DailyWindow: time.Duration(
				cfg.CommentRateLimit.DailyWindowSeconds,
			) * time.Second,
			DailyMax: cfg.CommentRateLimit.DailyMax,
		}),
		// 属地只在创建时解析为省级/国家级快照；原始 IP 不进入 Comment。
		commentapp.WithIPLocationResolver(commentIPLocationResolver),
		commentapp.WithClientIPExtractor(iplocation.ClientIPFromContext),
	)

	return mediaRuntimeComposition{
		mediaService:               mediaService,
		mediaImageReprocessService: mediaImageReprocessService,
		mediaObjectGateway:         mediaObjectGateway,
		commentServiceCore:         commentServiceCore,
	}, closeIPLocationResolver
}
