package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	rtmetrics "quwoquan_service/runtime/metrics"
	guidehttp "quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/adapters/inbound/http"
	guideapplication "quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/application"
	guidepersistence "quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/infrastructure/persistence"
	guideuserpersona "quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/infrastructure/userpersona"
	maphttp "quwoquan_service/services/travel-service/internal/travel/trip_map_view/adapters/inbound/http"
	mapapplication "quwoquan_service/services/travel-service/internal/travel/trip_map_view/application"
	mappersistence "quwoquan_service/services/travel-service/internal/travel/trip_map_view/infrastructure/persistence"
	membershiphttp "quwoquan_service/services/travel-service/internal/travel/trip_membership/adapters/inbound/http"
	membershipapplication "quwoquan_service/services/travel-service/internal/travel/trip_membership/application"
	membershipmodel "quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	membershippersistence "quwoquan_service/services/travel-service/internal/travel/trip_membership/infrastructure/persistence"
	membershipsourcereference "quwoquan_service/services/travel-service/internal/travel/trip_membership/infrastructure/sourcereference"
	momenthttp "quwoquan_service/services/travel-service/internal/travel/trip_moment/adapters/inbound/http"
	momentapplication "quwoquan_service/services/travel-service/internal/travel/trip_moment/application"
	momentobjectreference "quwoquan_service/services/travel-service/internal/travel/trip_moment/infrastructure/objectreference"
	momentpersistence "quwoquan_service/services/travel-service/internal/travel/trip_moment/infrastructure/persistence"
	triphttp "quwoquan_service/services/travel-service/internal/travel/trip_plan/adapters/inbound/http"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	eventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/eventing"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/identifier"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/persistence"
	triptemplatesource "quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/templatesource"
	contentlinkhttp "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/adapters/inbound/http"
	contentlinkapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/application"
	contentlinkcontentpost "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/infrastructure/contentpost"
	contentlinkpersistence "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/infrastructure/persistence"
	placementhttp "quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/adapters/inbound/http"
	placementapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/application"
	placementpersistence "quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/infrastructure/persistence"
	placementsurfaceauthority "quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/infrastructure/surfaceauthority"
	revisiontransaction "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/adapters/inbound/transaction"
	revisionapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/application"
	revisionpersistence "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/infrastructure/persistence"
	templatehttp "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/adapters/inbound/http"
	templateapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/application"
	templatecontentreference "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/infrastructure/contentreference"
	templatepersistence "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/infrastructure/persistence"
	sharehttp "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/adapters/inbound/http"
	shareapplication "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/application"
	sharepersistence "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/infrastructure/persistence"
	sharesource "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/infrastructure/source"
	timelinehttp "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/adapters/inbound/http"
	timelineapplication "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/application"
	timelinemessaging "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/infrastructure/messaging"
	timelinepersistence "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/infrastructure/persistence"
)

func main() {
	if err := run(); err != nil {
		log.Printf("travel-service stopped: %v", err)
		os.Exit(1)
	}
}

func run() error {
	identity, err := resolveRuntimeIdentity()
	if err != nil {
		return fmt.Errorf("runtime identity invalid: %w", err)
	}
	cfg, err := loadRuntimeConfig(identity)
	if err != nil {
		return fmt.Errorf("runtime config invalid: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		identity.ServiceName,
		identity.AppEnv,
		identity.ConfigRoot,
		identity.ConfigVersion,
		identity.ImageVersion,
	)

	configProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	accessConfig, err := rtauth.LoadAccessTokenConfig(configProvider)
	if err != nil {
		return fmt.Errorf("access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessConfig)
	if err != nil {
		return fmt.Errorf("access token verifier invalid: %w", err)
	}
	deviceConfig, err := rtauth.LoadDeviceTicketConfig(configProvider)
	if err != nil {
		return fmt.Errorf("device ticket config invalid: %w", err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceConfig)
	if err != nil {
		return fmt.Errorf("device ticket verifier invalid: %w", err)
	}
	authorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		identity.ServiceName,
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return fmt.Errorf("account security authority credentials invalid: %w", err)
	}
	mediaReferenceCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessConfig,
		identity.ServiceName,
		[]string{"content.media.reference.read"},
	)
	if err != nil {
		return fmt.Errorf("Content MediaAsset reference credentials invalid: %w", err)
	}
	membershipSourceCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessConfig,
		identity.ServiceName,
		[]string{"travel.trip.read"},
	)
	if err != nil {
		return fmt.Errorf("TripMembership source credentials invalid: %w", err)
	}
	authorityTimeout := time.Duration(cfg.AccountSecurityAuthority.TimeoutMs) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     strings.TrimSpace(cfg.AccountSecurityAuthority.BaseURL),
			HTTPClient:  &http.Client{Timeout: authorityTimeout},
			Credentials: authorityCredentials,
			Timeout:     authorityTimeout,
		},
	)
	if err != nil {
		return fmt.Errorf("account security authority invalid: %w", err)
	}

	ctx := context.Background()
	redisRouter, redisSceneModes := buildTravelRedisRouter(cfg)
	defer func() {
		if closeErr := redisRouter.Close(); closeErr != nil {
			log.Printf("travel-service Redis disconnect: %v", closeErr)
		}
	}()
	messageTransport, err := requireTravelAPIMessageTransport(
		ctx, identity.AppEnv, redisRouter, redisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("Travel message transport unavailable: %w", err)
	}
	mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{
		URI: cfg.Mongo.URI, Database: cfg.Mongo.Database,
	}, identity.ServiceName)
	defer func() {
		if disconnectErr := mongoClient.Disconnect(ctx); disconnectErr != nil {
			log.Printf("travel-service mongo disconnect: %v", disconnectErr)
		}
	}()
	database := mongoClient.Database(cfg.Mongo.Database)
	revisionStore := revisionpersistence.NewMongoStore(database)
	if err := revisionStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripPlanRevision indexes unavailable: %w", err)
	}
	revisionReader := revisionapplication.NewReader(revisionStore)
	revisionAppender := revisiontransaction.NewAppender(
		revisionapplication.NewAppender(revisionStore),
	)
	templateStore := templatepersistence.NewMongoStore(database)
	if err := templateStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripPlanTemplate indexes unavailable: %w", err)
	}
	store := persistence.NewMongoStore(database, revisionAppender)
	if err := store.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripPlan indexes unavailable: %w", err)
	}
	tripService := application.NewService(
		store, revisionReader, triptemplatesource.NewStoreReader(templateStore),
		identifier.Generator{}, time.Now,
	)
	membershipStore := membershippersistence.NewMongoStore(database)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripMembership indexes unavailable: %w", err)
	}
	conversationSourceResolver, err := membershipsourcereference.NewConversationResolver(
		cfg.ChatSourceAuthority.BaseURL,
		&http.Client{
			Timeout:       time.Duration(cfg.ChatSourceAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		},
		membershipSourceCredentials,
	)
	if err != nil {
		return fmt.Errorf("TripMembership Conversation source authority invalid: %w", err)
	}
	circleSourceResolver, err := membershipsourcereference.NewCircleMembershipResolver(
		cfg.CircleSourceAuthority.BaseURL,
		&http.Client{
			Timeout:       time.Duration(cfg.CircleSourceAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		},
		membershipSourceCredentials,
	)
	if err != nil {
		return fmt.Errorf("TripMembership Circle source authority invalid: %w", err)
	}
	gatheringSourceResolver, err := membershipsourcereference.NewGatheringResolver(
		cfg.CircleSourceAuthority.BaseURL,
		&http.Client{
			Timeout:       time.Duration(cfg.CircleSourceAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		},
		membershipSourceCredentials,
	)
	if err != nil {
		return fmt.Errorf("TripMembership Gathering source authority invalid: %w", err)
	}
	membershipService := membershipapplication.NewService(
		membershipStore,
		tripService,
		membershipapplication.NewSourceAuthority(map[membershipmodel.SourceKind]membershipapplication.MembershipSourceResolver{
			membershipmodel.SourceConversation: conversationSourceResolver,
			membershipmodel.SourceCircle:       circleSourceResolver,
			membershipmodel.SourceGathering:    gatheringSourceResolver,
		}),
		identifier.Generator{},
		time.Now,
	)
	placementStore := placementpersistence.NewMongoStore(database)
	if err := placementStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripPlanPlacement indexes unavailable: %w", err)
	}
	placementSurfaceAuthority, err := placementsurfaceauthority.NewHTTPAuthority(
		cfg.ChatSourceAuthority.BaseURL,
		cfg.CircleSourceAuthority.BaseURL,
		&http.Client{
			Timeout:       time.Duration(cfg.ChatSourceAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		},
		&http.Client{
			Timeout:       time.Duration(cfg.CircleSourceAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
		},
		membershipSourceCredentials,
	)
	if err != nil {
		return fmt.Errorf("TripPlanPlacement surface authority invalid: %w", err)
	}
	placementService := placementapplication.NewService(
		placementStore,
		tripService,
		membershipService,
		placementSurfaceAuthority,
		identifier.Generator{},
		time.Now,
	)
	momentStore := momentpersistence.NewMongoStore(database)
	if err := momentStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripMoment indexes unavailable: %w", err)
	}
	momentContentResolver, err := momentobjectreference.NewContentResolver(
		cfg.ContentPublicAuthority.BaseURL,
		&http.Client{
			Timeout: time.Duration(cfg.ContentPublicAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
		mediaReferenceCredentials,
	)
	if err != nil {
		return fmt.Errorf("TripMoment Content reference authority invalid: %w", err)
	}
	momentHomepageResolver, err := momentobjectreference.NewHomepageResolver(
		cfg.EntityPublicAuthority.BaseURL,
		&http.Client{
			Timeout: time.Duration(cfg.EntityPublicAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	)
	if err != nil {
		return fmt.Errorf("TripMoment Homepage reference authority invalid: %w", err)
	}
	momentService := momentapplication.NewService(
		momentStore,
		membershipService,
		tripService,
		revisionReader,
		momentapplication.NewReferenceAuthority(map[string]momentapplication.ObjectReferenceResolver{
			"content.MediaAsset": momentContentResolver,
			"content.Post":       momentContentResolver,
			"entity.Homepage":    momentHomepageResolver,
		}),
		identifier.Generator{},
		time.Now,
	)
	contentLinkStore := contentlinkpersistence.NewMongoStore(database)
	if err := contentLinkStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripPlanContentLink indexes unavailable: %w", err)
	}
	contentLinkPostResolver, err := contentlinkcontentpost.NewPublicPostResolver(
		cfg.ContentPublicAuthority.BaseURL,
		&http.Client{
			Timeout: time.Duration(cfg.ContentPublicAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	)
	if err != nil {
		return fmt.Errorf("TripPlanContentLink public Post authority invalid: %w", err)
	}
	contentLinkService := contentlinkapplication.NewService(
		contentLinkStore,
		membershipService,
		tripService,
		revisionReader,
		contentlinkapplication.NewPostAuthority(contentLinkPostResolver),
		identifier.Generator{},
		time.Now,
	)
	publicPostResolver, err := templatecontentreference.NewPublicPostResolver(
		cfg.ContentPublicAuthority.BaseURL,
		&http.Client{
			Timeout: time.Duration(cfg.ContentPublicAuthority.TimeoutMs) * time.Millisecond,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	)
	if err != nil {
		return fmt.Errorf("TripPlanTemplate public Post authority invalid: %w", err)
	}
	templateService := templateapplication.NewService(
		templateStore,
		templateapplication.NewReferenceAuthority(publicPostResolver),
		identifier.Generator{},
		time.Now,
	)
	guideStore := guidepersistence.NewMongoStore(database)
	if err := guideStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripGuideAssignment indexes unavailable: %w", err)
	}
	publicPersonaResolver, err := guideuserpersona.NewPublicPersonaResolver(
		cfg.AccountSecurityAuthority.BaseURL,
		&http.Client{
			Timeout: authorityTimeout,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	)
	if err != nil {
		return fmt.Errorf("TripGuideAssignment public Persona authority invalid: %w", err)
	}
	guideService := guideapplication.NewService(
		guideStore,
		tripService,
		membershipService,
		guideapplication.NewPersonaAuthority(publicPersonaResolver),
		identifier.Generator{},
		time.Now,
	)
	projectionStore := timelinepersistence.NewMongoStore(database)
	if err := projectionStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("Trip Timeline/Map projection indexes unavailable: %w", err)
	}
	mapStore := mappersistence.NewMongoStore(database)
	if err := mapStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripMapView indexes unavailable: %w", err)
	}
	timelineReader := timelineapplication.NewReader(projectionStore, membershipService)
	mapReader := mapapplication.NewReader(mapStore, membershipService)
	shareStore := sharepersistence.NewMongoStore(database)
	if err := shareStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("TripShareSnapshot indexes unavailable: %w", err)
	}
	shareService := shareapplication.NewService(
		shareStore,
		sharesource.NewProjectionReader(projectionStore, mapStore, membershipService),
		identifier.Generator{},
		time.Now,
	)
	projector := timelineapplication.NewProjector(
		projectionStore, store, revisionStore, momentStore, contentLinkStore, time.Now,
	)
	streamPublisher, err := eventing.NewStreamPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("Travel event publisher unavailable: %w", err)
	}
	instanceID, _ := os.Hostname()
	if strings.TrimSpace(instanceID) == "" {
		instanceID = identity.ServiceName
	}
	outboxRelay, err := eventing.NewOutboxRelay(
		eventing.NewMongoOutboxStore(database), streamPublisher,
		instanceID+"-outbox", 30*time.Second, slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("Travel outbox relay unavailable: %w", err)
	}
	projectionConsumer, err := timelinemessaging.NewConsumer(
		messageTransport, projector, instanceID+"-projection", slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("Travel projection consumer unavailable: %w", err)
	}
	workerCtx, stopWorkers := context.WithCancel(ctx)
	defer stopWorkers()
	go outboxRelay.Run(workerCtx, 500*time.Millisecond)
	go projectionConsumer.Run(workerCtx, 500*time.Millisecond)
	routes := http.NewServeMux()
	triphttp.NewHandler(tripService).RegisterRoutes(routes)
	membershiphttp.NewHandler(membershipService).RegisterRoutes(routes)
	placementhttp.NewHandler(placementService).RegisterRoutes(routes)
	momenthttp.NewHandler(momentService).RegisterRoutes(routes)
	contentlinkhttp.NewHandler(contentLinkService).RegisterRoutes(routes)
	templatehttp.NewHandler(templateService).RegisterRoutes(routes)
	guidehttp.NewHandler(guideService).RegisterRoutes(routes)
	timelinehttp.NewHandler(timelineReader).RegisterRoutes(routes)
	maphttp.NewHandler(mapReader).RegisterRoutes(routes)
	sharehttp.NewHandler(shareService).RegisterRoutes(routes)
	guarded := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("travel"),
	)(routes)

	// Compose / k8s liveness stays shallow: process is up. Deep worker and
	// authority probes belong on /readyz so a slow first outbox/projector scan
	// cannot keep the container unhealthy for the full start_period window.
	readiness := rthealth.NewChecker()
	readiness.Register("mongodb", func(checkCtx context.Context) error {
		return mongoClient.Ping(checkCtx, nil)
	})
	readiness.Register("redis", redisRouter.PingAll)
	readiness.Register("travel-outbox-relay", func(context.Context) error {
		return outboxRelay.Healthy(15 * time.Second)
	})
	readiness.Register("travel-timeline-map-projector", func(context.Context) error {
		return projectionConsumer.Healthy(15 * time.Second)
	})
	readiness.Register("account-security-authority", func(checkCtx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(checkCtx)
	})
	root := http.NewServeMux()
	root.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	root.HandleFunc("/readyz", readiness.Handler())
	root.Handle("/metrics", rtmetrics.Handler())
	root.Handle("/", guarded)

	server, cleanup, err := newHTTPServer(identity, cfg, root, rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		DeviceTicketVerifier:     deviceVerifier,
		AccountSecurityAuthority: accountSecurityAuthority,
	})
	if err != nil {
		return err
	}
	defer cleanup()
	log.Printf("travel-service listening on %s (env=%s)", cfg.Service.HTTP.Addr, identity.AppEnv)
	return serveGracefully(server)
}
