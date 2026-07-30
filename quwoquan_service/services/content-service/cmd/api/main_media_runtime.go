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
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	iplocation "quwoquan_service/services/content-service/internal/content/post/application/iplocation"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	mediainfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media"
	mediaprocinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media/processing"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/objectstorage"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	mediareprocess "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	uploadsession "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	uploadsessionstorage "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/objectstorage"
	uploadsessionpersistence "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/persistence"

	runtimeconfig "quwoquan_service/runtime/config"
)

type mediaRuntimeComposition struct {
	mediaService               *mediaapp.Facades
	mediaUploadSessionService  *uploadsession.UseCases
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
	mediaUploadSessionStore *uploadsessionpersistence.MongoStore,
	commentDataAdapter *persistence.MongoCommentDataAdapter,
	reactionStore *persistence.MongoContentReactionStore,
	recDB *mongo.Database,
	postMediaReader postports.MediaReferencedPostReader,
	viewerBlockReader *recinfra.PersonaBlockReader,
) (mediaRuntimeComposition, func()) {
	ossBinding, err := objectstorage.LoadBinding(appEnv, runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("content-service object storage binding invalid: %v", err)
	}
	storageConfig := runtimemedia.ObjectStorageConfig{
		Endpoint:        contentOSSEndpoint(ossBinding.Endpoint, cfg.OSS.UseSSL),
		Bucket:          getenvOrDefault("CONTENT_OSS_BUCKET", cfg.OSS.Bucket),
		Region:          getenvOrDefault("CONTENT_OSS_REGION", cfg.OSS.Region),
		AccessKeyID:     ossBinding.AccessKeyID,
		AccessKeySecret: ossBinding.AccessKeySecret,
		MediaDeliveryBaseURL: getenvOrDefault(
			"CONTENT_MEDIA_DELIVERY_BASE_URL",
			cfg.OSS.MediaDeliveryBaseURL,
		),
		MediaUploadBaseURL: getenvOrDefault(
			"CONTENT_MEDIA_UPLOAD_BASE_URL",
			cfg.OSS.MediaUploadBaseURL,
		),
		CDNSignKey: getenvOrDefault("CONTENT_CDN_SIGN_KEY", cfg.OSS.CDNSignKey),
		PresignTTL: time.Duration(cfg.OSS.PresignTTLMin) * time.Minute,
		CDNTTL:     time.Duration(cfg.OSS.CDNTTLMin) * time.Minute,
	}
	if storageConfig.PresignTTL == 0 {
		storageConfig.PresignTTL = 15 * time.Minute
	}
	if storageConfig.CDNTTL == 0 {
		storageConfig.CDNTTL = 60 * time.Minute
	}
	if strings.TrimSpace(storageConfig.Endpoint) == "" || strings.TrimSpace(storageConfig.Bucket) == "" ||
		strings.TrimSpace(storageConfig.Region) == "" || strings.TrimSpace(storageConfig.AccessKeyID) == "" ||
		strings.TrimSpace(storageConfig.AccessKeySecret) == "" || strings.TrimSpace(storageConfig.MediaDeliveryBaseURL) == "" ||
		strings.TrimSpace(storageConfig.MediaUploadBaseURL) == "" ||
		strings.TrimSpace(storageConfig.CDNSignKey) == "" {
		log.Fatal("content-service OSS endpoint, bucket, region, credentials, media delivery/upload bases and signing key are required")
	}
	objectClient := runtimemedia.NewS3PresignClient(storageConfig)
	log.Printf(
		"content-service object-storage adapter=%s presigner=s3 endpoint=%s bucket=%s",
		ossBinding.AdapterID,
		storageConfig.Endpoint,
		storageConfig.Bucket,
	)

	mediaObjectGateway, err := mediainfra.NewObjectGateway(mediainfra.ObjectGatewayConfig{
		Bucket: storageConfig.Bucket, MediaDeliveryBaseURL: storageConfig.MediaDeliveryBaseURL, CDNSignKey: storageConfig.CDNSignKey, DeliveryTTL: storageConfig.CDNTTL,
	}, objectClient)
	if err != nil {
		log.Fatalf("content-service media object gateway invalid: %v", err)
	}
	if mediaStore == nil {
		log.Fatal("content-service MediaUploadSession/MediaAsset store is not configured")
	}
	if mediaUploadSessionStore == nil {
		log.Fatal("content-service MediaUploadSession store is not configured")
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
	mediaUploadSessionGateway, err := uploadsessionstorage.NewGateway(
		uploadsessionstorage.Config{
			Bucket:        storageConfig.Bucket,
			UploadBaseURL: storageConfig.MediaUploadBaseURL,
		},
		objectClient,
	)
	if err != nil {
		log.Fatalf("content-service media upload session object gateway invalid: %v", err)
	}
	mediaUploadSessionService := uploadsession.NewUseCases(
		mediaUploadSessionStore,
		mediaUploadSessionGateway,
	)

	// Media processing worker 是 media outbox 的唯一生产消费者。图片与视频发布
	// 都依赖 processing -> ready/rejected 的确定终态，因此生产组合不提供禁用或内存回退。
	mediaProcessor, processorErr := mediaprocinfra.NewFFmpegMediaProcessor(
		objectClient,
		mediaprocinfra.Config{
			Bucket:              storageConfig.Bucket,
			FFmpegPath:          cfg.MediaProcessing.FFmpegPath,
			FFprobePath:         cfg.MediaProcessing.FFprobePath,
			EnableHLSCMAF:       cfg.MediaProcessing.HLSCMAFEnabled,
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
		mediaprocessing.WithArtifactCleanup(mediaStore, mediaObjectGateway),
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
		mediaUploadSessionService:  mediaUploadSessionService,
		mediaImageReprocessService: mediaImageReprocessService,
		mediaObjectGateway:         mediaObjectGateway,
		commentServiceCore:         commentServiceCore,
	}, closeIPLocationResolver
}
