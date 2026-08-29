package bootstrap

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"strings"
	"time"

	rthealth "quwoquan_service/runtime/health"
	runtimemedia "quwoquan_service/runtime/media"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	iplocation "quwoquan_service/services/content-service/internal/content/comment/application/iplocation"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	accessinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/accesscontrol"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/objectstorage"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediaprocessing "quwoquan_service/services/content-service/internal/media/media_asset/application/processing"
	mediainfra "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/media"
	mediaprocinfra "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/media/processing"
	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
	mediareprocess "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	mediareprocesspersistence "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/infrastructure/persistence"
	originalaccessaudit "quwoquan_service/services/content-service/internal/media/media_original_access_fact/adapters/inbound/audit"
	originalaccessapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	originalaccesspersistence "quwoquan_service/services/content-service/internal/media/media_original_access_fact/infrastructure/persistence"
	uploadsession "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	uploadsessionstorage "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/objectstorage"
	uploadsessionpersistence "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/persistence"
	originalaccessquotaapp "quwoquan_service/services/content-service/internal/media/original_access_quota/application"
	originalaccessquotapersistence "quwoquan_service/services/content-service/internal/media/original_access_quota/infrastructure/persistence"

	runtimeconfig "quwoquan_service/runtime/config"
)

type mediaRuntimeComposition struct {
	mediaService               *mediaapp.Facades
	mediaUploadSessionService  *uploadsession.UseCases
	mediaImageReprocessService *mediareprocess.Service
	originalAccessQuotaService *originalaccessquotaapp.Service
	originalAccessAuditQuery   *originalaccessquotaapp.AuditQueryFacade
	mediaObjectGateway         *mediainfra.ObjectGateway
	commentServiceCore         *commentapp.CommentService
	// mediaDeliveryAuthHandler 是边缘 forward_auth 的验签端点（DEC-031）：
	// 与签发方消费同一 CDNSignKey，在字节交付边缘复算签名真伪与到期。
	mediaDeliveryAuthHandler http.Handler
}

// activeResearchReleaseSupplyAdapter 把 content post 的 ActiveSupplySnapshot
// 缩窄成 grant 分流需要的单一事实（DEC-031）：只有 status=active 且
// releaseClass=research 的 canonical release 参与 membership 判定。
type activeResearchReleaseSupplyAdapter struct {
	reader postports.ActiveSupplyReader
}

func (adapter activeResearchReleaseSupplyAdapter) ActiveResearchReleaseID(
	ctx context.Context,
) (string, bool, error) {
	if adapter.reader == nil {
		return "", false, fmt.Errorf("active supply reader is not configured")
	}
	snapshot, err := adapter.reader.ActiveSupplySnapshot(ctx)
	if err != nil {
		return "", false, err
	}
	if strings.TrimSpace(snapshot.Status) != "active" ||
		strings.TrimSpace(snapshot.ReleaseClass) != "research" ||
		strings.TrimSpace(snapshot.ActiveReleaseID) == "" {
		return "", false, nil
	}
	return strings.TrimSpace(snapshot.ActiveReleaseID), true, nil
}

// buildMediaRuntime 装配 OSS、媒体对象 Facade、处理 worker 与评论属地依赖。
func buildMediaRuntime(
	ctx context.Context,
	workers *workerRegistry,
	cfg config,
	appEnv string,
	instanceID string,
	logger *slog.Logger,
	healthChecker *rthealth.Checker,
	mediaStore *mediaassetpersistence.MongoMediaStore,
	mediaOriginalAccessStore *originalaccesspersistence.MongoStore,
	originalAccessQuotaStore *originalaccessquotapersistence.MongoStore,
	mediaImageReprocessStore *mediareprocesspersistence.MongoStore,
	mediaUploadSessionStore *uploadsessionpersistence.MongoStore,
	commentDataAdapter *commentpersistence.MongoCommentDataAdapter,
	reactionStore *reactionpersistence.MongoContentReactionStore,
	postMediaReader postports.MediaReferencedPostReader,
	viewerBlockReader *accessinfra.PersonaBlockReader,
	commentViewerRelationships *commentpersistence.CommentViewerRelationshipMongoProjection,
	activeSupplyReader postports.ActiveSupplyReader,
) (mediaRuntimeComposition, func(), error) {
	ossBinding, err := objectstorage.LoadBinding(appEnv, runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service object storage binding invalid: %w", err)
	}
	storageConfig := runtimemedia.ObjectStorageConfig{
		Endpoint:             contentOSSEndpoint(ossBinding.Endpoint, cfg.OSS.UseSSL),
		Bucket:               cfg.OSS.Bucket,
		Region:               cfg.OSS.Region,
		AccessKeyID:          ossBinding.AccessKeyID,
		AccessKeySecret:      ossBinding.AccessKeySecret,
		MediaDeliveryBaseURL: cfg.OSS.MediaDeliveryBaseURL,
		MediaUploadBaseURL:   cfg.OSS.MediaUploadBaseURL,
		CDNSignKey:           cfg.OSS.CDNSignKey,
		PresignTTL:           time.Duration(cfg.OSS.PresignTTLMin) * time.Minute,
		CDNTTL:               time.Duration(cfg.OSS.CDNTTLMin) * time.Minute,
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
		return mediaRuntimeComposition{}, nil, fmt.Errorf(
			"content-service OSS endpoint, bucket, region, credentials, media delivery/upload bases and signing key are required",
		)
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
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service media object gateway invalid: %w", err)
	}
	if mediaStore == nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service MediaUploadSession/MediaAsset store is not configured")
	}
	if mediaOriginalAccessStore == nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service MediaOriginalAccessFact store is not configured")
	}
	if originalAccessQuotaStore == nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service OriginalAccessQuota store is not configured")
	}
	if mediaImageReprocessStore == nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service MediaImageReprocessRun store is not configured")
	}
	if mediaUploadSessionStore == nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service MediaUploadSession store is not configured")
	}
	if postMediaReader == nil || viewerBlockReader == nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service Post media visibility reader is not configured")
	}
	if commentViewerRelationships == nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service Comment viewer relationship projection is not configured")
	}
	mediaServiceCore := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(mediaStore),
		mediaObjectGateway,
	)
	originalAccessQuotaService := originalaccessquotaapp.NewService(
		originalAccessQuotaStore,
		originalaccessaudit.NewAppender(
			originalaccessapp.NewService(mediaOriginalAccessStore),
		),
		mediaStore,
		postapp.NewMediaAssetVisibilityReader(postMediaReader, viewerBlockReader),
		mediaObjectGateway,
		originalaccessquotaapp.WithActiveResearchReleaseReader(
			activeResearchReleaseSupplyAdapter{reader: activeSupplyReader},
		),
	)
	originalAccessAuditQuery := originalaccessquotaapp.NewAuditQueryFacade(
		originalaccessaudit.NewReader(
			originalaccessapp.NewQueryService(mediaOriginalAccessStore),
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
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service media upload session object gateway invalid: %w", err)
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
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service media processing pipeline unavailable: %w", processorErr)
	}
	mediaProcessingHandler := mediaprocessing.NewMediaProcessingHandler(
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
	workers.Add(func(workerCtx context.Context) {
		if err := mediaProcessingHandler.Run(workerCtx, workerInterval); err != nil && workerCtx.Err() == nil {
			logger.Error("content media processing worker stopped", "error", err)
		}
	})
	healthChecker.Register("content_media_processing_worker", func(_ context.Context) error {
		return mediaProcessingHandler.Ready(15 * time.Minute)
	})
	log.Printf("content-service media processing worker enabled interval=%s", workerInterval)

	// Image reprocess shares the trusted FFmpeg processor and MediaAsset command
	// facet, but owns a separate operational run cursor/lease. It therefore can
	// later extract as a worker service without creating a second media state
	// machine or changing normal upload processing.
	mediaImageReprocessService := mediareprocess.NewService(mediaImageReprocessStore, mediaStore)
	mediaImageReprocessWorker := mediareprocess.NewWorker(
		mediaImageReprocessStore,
		mediaStore,
		mediaProcessor,
		mediaService,
		"content-media-image-reprocess-"+strings.TrimSpace(instanceID),
	)
	workers.Add(func(ctx context.Context) {
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
	})
	log.Printf("content-service media image reprocess worker enabled interval=%s", workerInterval)

	commentIPLocationResolver, closeIPLocationResolver, err :=
		buildCommentIPLocationResolver(cfg, appEnv, newIP2RegionResolver)
	if err != nil {
		return mediaRuntimeComposition{}, nil, fmt.Errorf("content-service comment IP location resolver unavailable: %w", err)
	}
	commentServiceCore := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			commentDataAdapter,
			commentpersistence.NewCommentAttachmentReader(mediaStore, mediaObjectGateway),
			reactionStore,
			commentViewerRelationships,
			commentViewerRelationships,
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
		originalAccessQuotaService: originalAccessQuotaService,
		originalAccessAuditQuery:   originalAccessAuditQuery,
		mediaObjectGateway:         mediaObjectGateway,
		commentServiceCore:         commentServiceCore,
		mediaDeliveryAuthHandler: runtimemedia.NewPrivateDeliveryAuthHandler(
			storageConfig.CDNSignKey,
			nil,
		),
	}, closeIPLocationResolver, nil
}
