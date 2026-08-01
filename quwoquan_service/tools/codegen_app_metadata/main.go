package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	var metadataDir string
	var appDir string
	var contractGraphPath string
	var contractGraphLockPath string
	var generatedManifestPath string
	var assistantRuntimeEnumsGoOutput string
	var checkAssistantRuntimeEnumsGo bool
	var citationDestinationsGoOutput string
	var checkCitationDestinationsGo bool
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&appDir, "app-dir", "../quwoquan_app", "app root directory")
	flag.StringVar(&contractGraphPath, "contract-graph", "generated/contract_graph.json", "fixed ContractGraph JSON bundle")
	flag.StringVar(&contractGraphLockPath, "contract-graph-lock", "../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json", "accepted App ContractGraph lock")
	flag.StringVar(&generatedManifestPath, "generated-manifest", "../quwoquan_app/tool/cloud_codegen/generated_manifest.json", "App generated output manifest")
	flag.StringVar(
		&assistantRuntimeEnumsGoOutput,
		"assistant-runtime-enums-go-output",
		"",
		"write Assistant runtime Go enums to this service-owned generated file",
	)
	flag.BoolVar(
		&checkAssistantRuntimeEnumsGo,
		"check-assistant-runtime-enums-go",
		false,
		"verify the Assistant runtime Go enum output is current",
	)
	flag.StringVar(
		&citationDestinationsGoOutput,
		"citation-destinations-go-output",
		"",
		"write metadata-registered citation destinations to this Go file",
	)
	flag.BoolVar(
		&checkCitationDestinationsGo,
		"check-citation-destinations-go",
		false,
		"verify the citation destination Go output is current",
	)
	flag.Parse()
	if checkAssistantRuntimeEnumsGo && assistantRuntimeEnumsGoOutput == "" {
		exitErr(fmt.Errorf(
			"--check-assistant-runtime-enums-go requires --assistant-runtime-enums-go-output",
		))
	}
	if checkCitationDestinationsGo && citationDestinationsGoOutput == "" {
		exitErr(fmt.Errorf(
			"--check-citation-destinations-go requires --citation-destinations-go-output",
		))
	}
	serviceOutputRequested :=
		assistantRuntimeEnumsGoOutput != "" || citationDestinationsGoOutput != ""
	if serviceOutputRequested {
		if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
			exitErr(err)
		}
	}
	if assistantRuntimeEnumsGoOutput != "" {
		if err := generateAssistantRuntimeEnumsGo(
			metadataDir,
			assistantRuntimeEnumsGoOutput,
			checkAssistantRuntimeEnumsGo,
		); err != nil {
			exitErr(err)
		}
	}
	if citationDestinationsGoOutput != "" {
		if err := generateCitationDestinationsGo(
			metadataDir,
			citationDestinationsGoOutput,
			checkCitationDestinationsGo,
		); err != nil {
			exitErr(err)
		}
	}
	if serviceOutputRequested {
		return
	}
	if err := initializeContractGraphBundle(
		metadataDir,
		contractGraphPath,
		contractGraphLockPath,
	); err != nil {
		exitErr(err)
	}
	beginGeneratedManifest(appDir, activeContractSHA256)
	removeRetiredGeneratedOutputs(appDir)
	shared, err := readShared(filepath.Join(metadataDir, "_shared", "types.yaml"))
	if err != nil {
		exitErr(err)
	}
	requestContext, err := readRequestContext(filepath.Join(metadataDir, "_shared", "request_context.yaml"))
	if err != nil && !os.IsNotExist(err) {
		exitErr(err)
	}
	if requestContext != nil {
		sharedRequestContext = *requestContext
	}
	appRoutes, err := readAppRoutes(filepath.Join(metadataDir, "_shared", "app_routes.yaml"))
	if err != nil && !os.IsNotExist(err) {
		exitErr(err)
	}
	linkTemplates, err := readLinkTemplates(filepath.Join(metadataDir, "_shared", "link_templates.yaml"))
	if err != nil && !os.IsNotExist(err) {
		exitErr(fmt.Errorf("read link_templates.yaml: %w", err))
	}
	uiSurfaces, err := readUISurfaces(filepath.Join(metadataDir, "_shared", "ui_surfaces.yaml"))
	if err != nil && !os.IsNotExist(err) {
		exitErr(err)
	}
	appPages, err := readAppPages(filepath.Join(metadataDir, "_shared", "app_pages.yaml"))
	if err != nil {
		exitErr(fmt.Errorf("read app_pages.yaml: %w", err))
	}
	telemetryCatalog, err := readTelemetryEventCatalog(
		filepath.Join(
			metadataDir,
			"ops",
			"product_ops",
			"event_record",
			"event_catalog.yaml",
		),
	)
	if err != nil {
		exitErr(fmt.Errorf("read telemetry event_catalog.yaml: %w", err))
	}
	if err := validateTelemetryMetadata(telemetryCatalog, appPages, appRoutes); err != nil {
		exitErr(err)
	}
	searchContract, err := readSearchContract(filepath.Join(metadataDir, "_shared", "search_contract.yaml"))
	if err != nil && !os.IsNotExist(err) {
		exitErr(err)
	}
	searchObjects, err := readSearchObjects(filepath.Join(metadataDir, "_shared", "search_objects.yaml"))
	if err != nil && !os.IsNotExist(err) {
		exitErr(err)
	}
	// Domain-centric path: services/content-service/contracts/content/post/
	postDir := filepath.Join(metadataDir, "content", "content", "post")
	fields, err := readFields(filepath.Join(postDir, "fields.yaml"))
	if err != nil {
		exitErr(err)
	}
	service, err := readService(filepath.Join(postDir, "operations.yaml"))
	if err != nil {
		exitErr(err)
	}
	// discovery_feed projection: services/content-service/contracts/content/post/projections/
	feedProjPath := filepath.Join(postDir, "projections", "discovery_feed.yaml")
	projection, err := readValidatedProjection(feedProjPath, shared.Enums)
	if err != nil {
		exitErr(err)
	}

	post, ok := fields.Entities["Post"]
	if !ok {
		exitErr(fmt.Errorf("Post entity not found in fields.yaml"))
	}

	defaults := buildPostDefaults(post.Fields)
	postSnapshotFieldByteLimits := buildPostSnapshotFieldByteLimits(
		post.Fields,
		projection.ClientProjection.Fields,
	)
	feedDefaults := buildFeedDefaults(defaults)
	contentTypes := shared.Enums["ContentType"]
	if len(contentTypes) == 0 {
		contentTypes = []string{"image", "video", "micro", "article"}
	}
	contentTypeMapping := buildContentTypeToRender(contentTypes)
	feedCategoryToType, appTabToCategory := buildDiscoveryMappings(contentTypes)
	feedRoute := findRoute(service.APIRoutes, "GetFeed")
	getPostRoute := findRoute(service.APIRoutes, "GetPost")
	feedDefaultLimit := paginationLimitDefault(shared, 20)
	likeRoutes := buildMutationRoutes(service.APIRoutes,
		[]string{"LikePost", "UnlikePost", "FavoritePost", "UnfavoritePost"})

	// 1. 生成 content_metadata.g.dart（原 post_runtime_metadata.g.dart）
	metaOut := renderContentMetadataDart(
		defaults,
		postSnapshotFieldByteLimits,
		feedDefaults,
		contentTypeMapping,
		feedCategoryToType,
		appTabToCategory,
		feedRoute,
		getPostRoute,
		feedDefaultLimit,
		likeRoutes,
	)
	metaPath := filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "content", "content_metadata.g.dart")
	writeFile(metaPath, metaOut)
	generatedStandaloneProjectionPaths := map[string]bool{}

	// 2. 生成 feed_item_dto.g.dart（FeedItemDto 强类型 DTO）
	if len(projection.ClientProjection.Fields) > 0 {
		dtoOut := renderFeedItemDtoDart(projection.ClientProjection)
		dtoRelPath := projection.ClientProjection.OutputPath
		if dtoRelPath == "" {
			dtoRelPath = "cloud/runtime/generated/content/feed_item_dto.g.dart"
		}
		dtoPath := filepath.Join(appDir, "lib", dtoRelPath)
		writeFile(dtoPath, dtoOut)
		generatedStandaloneProjectionPaths[dtoRelPath] = true
	}

	contentGenDir := filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "content")
	writeFile(filepath.Join(contentGenDir, "report_create_request_wire.g.dart"), renderCreateReportRequestWireDart())

	if err := writePostReadPresentationArtifacts(appDir, filepath.Join(postDir, "projections")); err != nil {
		exitErr(err)
	}
	writeContentAppConfigClientDart(filepath.Join(contentGenDir, "content_app_config_client_dto.g.dart"))

	// 3a. 生成 content_errors.g.dart（ContentErrorCode enum + messages）。
	// content 域错误码按对象目录拆分登记，此处按固定顺序合并为域级客户端枚举；
	// code 必须全域唯一（由 verify_error_code_endcloud_parity 与 codegen 共同锁定）。
	if err := writeContentErrorsDart(metadataDir, appDir); err != nil {
		exitErr(err)
	}

	// 3a2. 生成 chat_errors.g.dart（ChatErrorCode enum + messages）
	chatConversationDir := filepath.Join(metadataDir, "chat", "chat", "conversation")
	if chatErrsDef, err := readErrors(filepath.Join(chatConversationDir, "errors.yaml")); err == nil {
		out := renderChatErrorsDart(chatErrsDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "chat", "generated", "chat_errors.g.dart"), out)
	}

	// 3a3. 生成 assistant/circle/entity 客户端 *ErrorCode 枚举（端云错误码全集一致）。
	// 这三个域此前缺少客户端 typed enum，导致端侧只能硬编码字符串比对错误码；
	// 统一通过 renderSimpleErrorsDart 生成，唯一真相源各自 errors.yaml。
	if assistantErrs, err := readErrors(filepath.Join(metadataDir, "assistant", "assistant", "assistant_run", "errors.yaml")); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "assistant", "generated", "assistant_errors.g.dart"),
			renderSimpleErrorsDart("AssistantErrorCode", "assistant/assistant/assistant_run/errors.yaml", "找私助暂时不可用，请稍后重试", assistantErrs),
		)
	}
	circleErrorsPath := filepath.Join(
		metadataDir,
		"circle",
		"circle_management",
		"circle",
		"errors.yaml",
	)
	circleErrs, err := readErrors(circleErrorsPath)
	if err != nil {
		exitErr(fmt.Errorf("read Circle errors metadata: %w", err))
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "circle", "generated", "circle_errors.g.dart"),
		renderSimpleErrorsDart("CircleErrorCode", "circle/circle_management/circle/errors.yaml", "圈子服务异常，请稍后重试", circleErrs),
	)
	circleMembershipErrorsPath := filepath.Join(
		metadataDir,
		"circle",
		"circle_management",
		"circle_membership",
		"errors.yaml",
	)
	circleMembershipErrs, err := readErrors(circleMembershipErrorsPath)
	if err != nil {
		exitErr(fmt.Errorf("read CircleMembership errors metadata: %w", err))
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "circle", "generated", "circle_membership_errors.g.dart"),
		renderSimpleErrorsDart("CircleMembershipErrorCode", "circle/circle_management/circle_membership/errors.yaml", "圈子成员关系暂时不可用，请稍后重试", circleMembershipErrs),
	)
	if entityErrs, err := readMergedErrors([]string{
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage", "errors.yaml"),
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage_claim_request", "errors.yaml"),
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage_review", "errors.yaml"),
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage_status_report", "errors.yaml"),
	}); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "entity", "generated", "entity_errors.g.dart"),
			renderSimpleErrorsDart("EntityErrorCode", "entity/*/errors.yaml", "主页服务异常，请稍后重试", entityErrs),
		)
	}
	if notificationErrs, err := readErrors(filepath.Join(metadataDir, "notification", "notification_delivery", "notification", "errors.yaml")); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "notification", "notification_errors.g.dart"),
			renderSimpleErrorsDart("NotificationErrorCode", "notification/notification_delivery/notification/errors.yaml", "通知服务异常，请稍后重试", notificationErrs),
		)
	}
	opsEventErrs, err := readErrors(
		filepath.Join(metadataDir, "ops", "product_ops", "event_record", "errors.yaml"),
	)
	if err != nil {
		exitErr(fmt.Errorf("read ops event-record errors: %w", err))
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "ops", "ops_event_record_errors.g.dart"),
		renderSimpleErrorsDart("OpsEventRecordErrorCode", "ops/product_ops/event_record/errors.yaml", "启动诊断暂时不可用，请稍后重试", opsEventErrs),
	)
	if searchErrs, err := readMergedErrors([]string{
		filepath.Join(metadataDir, "search", "search", "search_request_fact", "errors.yaml"),
		filepath.Join(metadataDir, "search", "search", "recent_search_state", "errors.yaml"),
	}); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "search", "search_errors.g.dart"),
			renderSimpleErrorsDart("SearchErrorCode", "search/**/errors.yaml", "搜索服务异常，请稍后重试", searchErrs),
		)
	}
	if tagErrs, err := readMergedErrors([]string{
		filepath.Join(metadataDir, "tag", "tag", "tag_node_view", "errors.yaml"),
		filepath.Join(metadataDir, "tag", "tag", "tag_feedback_fact", "errors.yaml"),
		filepath.Join(metadataDir, "tag", "tag", "tag_taxonomy_release", "errors.yaml"),
	}); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "tag", "tag_errors.g.dart"),
			renderSimpleErrorsDart("TagErrorCode", "tag/**/errors.yaml", "标签服务异常，请稍后重试", tagErrs),
		)
	}

	// 3b. 生成 content_behaviors.g.dart（ContentBehaviorTracker）。
	// 行为事实是独立对象（content_behavior_fact），不是 post 的子文档：一次行为事件的
	// 生命周期与可见性与被作用的帖子无关，因此契约归 content_behavior_fact 而非 post。
	behaviorsPath := filepath.Join(metadataDir, "content", "content", "content_behavior_fact", "behaviors.yaml")
	behDef, err := readBehaviors(behaviorsPath)
	if err != nil {
		exitErr(fmt.Errorf("read content behaviors.yaml: %w", err))
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_behaviors.g.dart"),
		renderContentBehaviorsDart(behDef),
	)

	// 3c. 生成 content_privacy_policy.g.dart（sanitizeForLog）
	if privDef, err := readPrivacy(filepath.Join(postDir, "privacy.yaml")); err == nil {
		out := renderContentPrivacyDart(privDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_privacy_policy.g.dart"), out)
	}

	// 3d. 生成 content_ui_config.g.dart（ContentUIConfig + DiscoveryTabConfig）
	uiDef, uiErr := readUIConfig(
		filepath.Join(postDir, "ui_config.yaml"),
		true,
	)
	if uiErr != nil {
		exitErr(fmt.Errorf("read ui_config.yaml: %w", uiErr))
	}
	if uiDef != nil {
		out := renderContentUIConfigDart(uiDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_ui_config.g.dart"), out)
	}

	publicationPolicy, policyErr := readContentPublicationPolicy(
		filepath.Join(postDir, "publication_policy.yaml"),
	)
	if policyErr != nil {
		exitErr(fmt.Errorf("read content publication policy: %w", policyErr))
	}
	writeFile(
		filepath.Join(
			appDir,
			"lib",
			"cloud",
			"content",
			"generated",
			"content_publication_policy.g.dart",
		),
		renderContentPublicationPolicyDart(publicationPolicy),
	)

	mediaUploadPolicy, mediaUploadPolicyErr := readContentMediaUploadPolicy(
		filepath.Join(
			metadataDir,
			"content",
			"media",
			"media_upload_session",
			"upload_policy.yaml",
		),
	)
	if mediaUploadPolicyErr != nil {
		exitErr(fmt.Errorf("read content media upload policy: %w", mediaUploadPolicyErr))
	}
	writeFile(
		filepath.Join(
			appDir,
			"lib",
			"application",
			"content",
			"media",
			"generated",
			"content_media_upload_policy.g.dart",
		),
		renderContentMediaUploadPolicyDart(mediaUploadPolicy),
	)

	imageVariantPolicy, imageVariantPolicyErr := readContentImageVariantPolicy(
		filepath.Join(
			metadataDir,
			"content",
			"media",
			"media_asset",
			"image_variant_policy.yaml",
		),
	)
	if imageVariantPolicyErr != nil {
		exitErr(fmt.Errorf("read content image variant policy: %w", imageVariantPolicyErr))
	}
	writeFile(
		filepath.Join(
			appDir,
			"lib",
			"application",
			"content",
			"media",
			"generated",
			"content_image_variant_policy.g.dart",
		),
		renderContentImageVariantPolicyDart(imageVariantPolicy),
	)

	userProfileDir := filepath.Join(metadataDir, "user", "account", "user_account")
	userUIDef, userUIErr := readUIConfig(
		filepath.Join(userProfileDir, "ui_config.yaml"),
		false,
	)
	if userUIErr != nil && !os.IsNotExist(userUIErr) {
		exitErr(fmt.Errorf("read user/account/user_account/ui_config.yaml: %w", userUIErr))
	}
	if userUIDef != nil {
		out := renderUserProfileUIConfigDart(userUIDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "user", "generated", "user_profile_ui_config.g.dart"), out)
	}
	writeEntityCircleUIConfigs(metadataDir, appDir)
	if userErrsDef, err := readUserDomainErrors(metadataDir); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "user", "user_errors.g.dart"),
			renderUserErrorsDart(userErrsDef),
		)
	}

	// 2b. 生成 integration/external_integration/location 元数据（路径、response key）
	locDir := filepath.Join(metadataDir, "integration", "external_integration", "location")
	if locSvc, err := readIntegrationLocationService(filepath.Join(locDir, "operations.yaml")); err == nil {
		locOut := renderIntegrationLocationMetadataDart(locSvc)
		writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "integration", "integration_location_metadata.g.dart"), locOut)

	}

	// 2b2. 生成 integration/external_integration/location 客户端 errors；Service 产物由领域 codegen 所有。
	if locErrs, err := readErrors(filepath.Join(locDir, "errors.yaml")); err == nil {
		locErrOut := renderIntegrationLocationErrorsDart(locErrs)
		writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "integration", "integration_location_errors.g.dart"), locErrOut)
	}

	// 2c. 生成 integration/external_integration/location projections（无 base_class 的 standalone DTO，如 LocationPoiDto）
	for _, projectionPath := range metadataDocumentPaths("integration/external_integration/location/projections", ".yaml") {
		p, err := readValidatedProjection(projectionPath, shared.Enums)
		if err != nil {
			exitErr(err)
		}
		if len(p.ClientProjection.Fields) == 0 {
			continue
		}
		if p.ClientProjection.BaseClass != "" {
			continue
		}
		sourcePath := fmt.Sprintf(
			"integration/external_integration/location/projections/%s",
			filepath.Base(projectionPath),
		)
		out := renderStandaloneDtoDart(p.ClientProjection, sourcePath)
		relPath := p.ClientProjection.OutputPath
		if relPath == "" {
			continue
		}
		writeFile(filepath.Join(appDir, "lib", relPath), out)
		generatedStandaloneProjectionPaths[relPath] = true
	}

	// 3. 生成带 base_class 的 typed post DTOs（photo/video/article/moment）
	// 规范路径：services/content-service/contracts/content/post/projections/
	for _, projectionPath := range metadataDocumentPaths("content/content/post/projections", ".yaml") {
		if filepath.Base(projectionPath) == "discovery_feed.yaml" {
			continue // already handled above
		}
		p, err := readValidatedProjection(projectionPath, shared.Enums)
		if err != nil {
			exitErr(err)
		}
		if p.ClientProjection.BaseClass == "" || len(p.ClientProjection.Fields) == 0 {
			continue
		}
		out := renderTypedPostDtoDart(p.ClientProjection, filepath.Base(projectionPath))
		relPath := p.ClientProjection.OutputPath
		if relPath == "" {
			continue
		}
		dtoPath := filepath.Join(appDir, "lib", relPath)
		writeFile(dtoPath, out)
	}

	writeFile(filepath.Join(contentGenDir, "content_dtos.dart"), renderContentDtosBarrelDart())

	// 3b. 生成其他 domain projections（无 base_class 的 standalone DTO，如 chat inbox）。
	// 用户域 Auth/Invite/Greeting 等 wire 读模型见：
	//   user/account/user_account/projections/*.yaml
	//   user/invite_record/projections/*.yaml
	//   user/relationship/greeting_request/projections/*.yaml
	for _, path := range metadataDocumentPaths("", ".yaml") {
		if filepath.Base(filepath.Dir(path)) != "projections" {
			continue
		}
		p, readErr := readValidatedProjection(path, shared.Enums)
		if readErr != nil {
			exitErr(readErr)
		}
		if len(p.ClientProjection.Fields) == 0 {
			continue
		}
		if strings.TrimSpace(p.ClientProjection.BaseClass) != "" {
			continue
		}
		relPath := strings.TrimSpace(p.ClientProjection.OutputPath)
		if relPath == "" || generatedStandaloneProjectionPaths[relPath] {
			continue
		}
		relSourcePath, relErr := filepath.Rel(metadataDir, path)
		if relErr != nil {
			relSourcePath = path
		}
		out := renderStandaloneDtoDart(
			p.ClientProjection,
			filepath.ToSlash(relSourcePath),
		)
		writeFile(filepath.Join(appDir, "lib", relPath), out)
		generatedStandaloneProjectionPaths[relPath] = true
	}

	domainRoutes, err := collectDomainServiceRoutes(metadataDir)
	if err != nil {
		exitErr(err)
	}
	responseModelByReadModel, err := collectProjectionReadModelDartClass(metadataDir)
	if err != nil {
		exitErr(err)
	}
	defaultsOut := renderCloudAPIDefaultsDart(feedDefaultLimit)
	writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "cloud_api_defaults.g.dart"), defaultsOut)
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "auth", "auth_policy.g.dart"),
		renderCanonicalAuthPolicyDart(activeContractLock),
	)
	for domain, routes := range domainRoutes {
		metaOut := renderDomainAPIMetadataDart(domain, routes, responseModelByReadModel)
		pageIDsOut := renderDomainRequestPageIDsDart(domain, routes)
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", domain, fmt.Sprintf("%s_api_metadata.g.dart", domain)),
			metaOut,
		)
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", domain, fmt.Sprintf("%s_request_page_ids.g.dart", domain)),
			pageIDsOut,
		)
	}
	if err := writeRtcCallSessionDtos(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	if err := writeRtcSignalPayloads(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	if err := writeRecommendationFeedPatches(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	if err := writeIntersectionKindMetadata(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	if err := writeImpactHelpTypeMetadata(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	// RTC 客户端 errors；Service 产物由领域 codegen 所有。
	if rtcErrs, err := readErrors(filepath.Join(metadataDir, "rtc", "rtc", "call_session", "errors.yaml")); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "rtc", "generated", "rtc_errors.g.dart"),
			renderRtcErrorsDart(rtcErrs),
		)
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "app_request_page_ids.g.dart"),
		renderStandaloneRequestPageIDsDart(sharedRequestContext.StandalonePageIDs),
	)
	if appRoutes != nil {
		writeFile(
			filepath.Join(appDir, "lib", "app", "navigation", "generated", "app_route_paths.g.dart"),
			renderAppRoutePathsDart(appRoutes.Routes),
		)
	}
	if linkTemplates != nil {
		if appRoutes == nil {
			exitErr(fmt.Errorf("link_templates.yaml requires app_routes.yaml"))
		}
		if err := validateLinkTemplates(appRoutes, linkTemplates); err != nil {
			exitErr(err)
		}
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "link_templates.g.dart"),
			renderLinkTemplatesDart(linkTemplates, appRoutes),
		)
	}
	if uiSurfaces != nil {
		writeFile(
			filepath.Join(appDir, "lib", "app", "navigation", "generated", "app_ui_surfaces.g.dart"),
			renderAppUISurfacesDart(uiSurfaces.Surfaces),
		)
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "ops", "app_telemetry_catalog.g.dart"),
		renderAppTelemetryCatalogDart(telemetryCatalog),
	)
	writeFile(
		filepath.Join(appDir, "lib", "app", "navigation", "generated", "app_pages.g.dart"),
		renderAppPagesDart(appPages, appRoutes),
	)
	writeFile(
		filepath.Join(appDir, "lib", "app", "navigation", "generated", "page_access_internal_routes.g.dart"),
		renderPageAccessInternalRoutesDart(appPages),
	)
	if searchContract != nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "search", "search_contract.g.dart"),
			renderSearchContractDart(searchContract),
		)
	}
	if feedbackEventTypes := shared.Enums["SearchFeedbackEventType"]; len(feedbackEventTypes) > 0 {
		writeFile(
			filepath.Join(
				appDir,
				"packages",
				"quwoquan_cloud_contracts",
				"lib",
				"src",
				"generated",
				"search_feedback_event_type.g.dart",
			),
			renderSearchFeedbackEventTypeDart(feedbackEventTypes),
		)
	}
	canonicalCircleFields, canonicalCircleFieldsErr := readFields(filepath.Join(
		metadataDir,
		"circle",
		"circle_management",
		"circle",
		"fields.yaml",
	))
	if canonicalCircleFieldsErr != nil {
		exitErr(fmt.Errorf("read canonical Circle fields: %w", canonicalCircleFieldsErr))
	}
	circleMembershipFields, circleMembershipFieldsErr := readFields(filepath.Join(
		metadataDir,
		"circle",
		"circle_management",
		"circle_membership",
		"fields.yaml",
	))
	if circleMembershipFieldsErr != nil {
		exitErr(fmt.Errorf("read PersonaCircleSlice fields: %w", circleMembershipFieldsErr))
	}
	circleEnumRefs, circleEnumRefsErr := personaCircleSliceEnumRefs(
		canonicalCircleFields,
		circleMembershipFields,
	)
	if circleEnumRefsErr != nil {
		exitErr(circleEnumRefsErr)
	}
	if circleContractEnums, renderErr := renderCircleContractEnumsDart(shared.Enums, circleEnumRefs); renderErr != nil {
		exitErr(renderErr)
	} else {
		writeFile(
			filepath.Join(
				appDir,
				"packages",
				"quwoquan_cloud_contracts",
				"lib",
				"src",
				"generated",
				"circle_contract_enums.g.dart",
			),
			circleContractEnums,
		)
	}
	if userContractEnums, renderErr := renderSharedContractEnumsDart(
		shared.Enums,
		[]string{"FollowSubjectKind"},
	); renderErr != nil {
		exitErr(renderErr)
	} else {
		writeFile(
			filepath.Join(
				appDir,
				"packages",
				"quwoquan_cloud_contracts",
				"lib",
				"src",
				"generated",
				"user_contract_enums.g.dart",
			),
			userContractEnums,
		)
	}
	if chatContractEnums, renderErr := renderSharedContractEnumsDart(
		shared.Enums,
		[]string{"MessageType"},
	); renderErr != nil {
		exitErr(renderErr)
	} else {
		writeFile(
			filepath.Join(
				appDir,
				"packages",
				"quwoquan_cloud_contracts",
				"lib",
				"src",
				"generated",
				"chat_contract_enums.g.dart",
			),
			chatContractEnums,
		)
	}
	if contentContractEnums, renderErr := renderSharedContractEnumsDart(
		shared.Enums,
		[]string{"ContentType", "ContentIdentity"},
	); renderErr != nil {
		exitErr(renderErr)
	} else {
		writeFile(
			filepath.Join(
				appDir,
				"packages",
				"quwoquan_cloud_contracts",
				"lib",
				"src",
				"generated",
				"content_contract_enums.g.dart",
			),
			contentContractEnums,
		)
	}
	if err := generateCanonicalSearchClientModels(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	if searchObjects != nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "search", "search_registry.g.dart"),
			renderSearchRegistryDart(searchObjects),
		)
	}
	if err := generateAssistantRuntimeArtifacts(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	if err := generateAssistantCloudApiWireDart(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	requestArtifacts, err := writeGeneratedOperationRequests(
		appDir,
		activeContractLock,
	)
	if err != nil {
		exitErr(err)
	}
	if err := writeGeneratedOperationContracts(
		appDir,
		activeContractLock,
		requestArtifacts,
	); err != nil {
		exitErr(err)
	}
	if err := writeGeneratedManifest(generatedManifestPath); err != nil {
		exitErr(err)
	}
}

func writeContentErrorsDart(metadataDir string, appDir string) error {
	errorsDefinition, err := readMergedErrors(contentDomainErrorsPaths(metadataDir))
	if err != nil {
		return fmt.Errorf("read Content errors metadata: %w", err)
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_errors.g.dart"),
		renderContentErrorsDart(errorsDefinition),
	)
	return nil
}

func removeRetiredGeneratedOutputs(appDir string) {
	retired := []string{
		filepath.Join("lib", "cloud", "user", "generated", "prefab_user_metadata.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "content", "post_publication_receipt_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_claim_request_record.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_content_preview.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_geo_point.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_introduction.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_introduction_asset.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_introduction_section.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_introduction_timeline_item.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_question_preview.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_related_group_summary.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_review_summary_data.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_source.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "entity", "homepage_status_report_record.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "integration", "location_poi_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "contact_discovery_match_wire_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "following_subject_item_view_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "following_subject_visit_result_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "persona_create_request_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "persona_lifecycle_guard_wire_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "persona_management_item_wire_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "persona_management_quota_wire_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "persona_management_summary_wire_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "persona_update_request_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "user_profile_stats_wire_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "content", "post_search_item_view_dto.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "rtc", "rtc_request_wires.g.dart"),
		filepath.Join("lib", "cloud", "runtime", "generated", "user", "profile_interaction_activity_wire_dto.g.dart"),
		filepath.Join("lib", "assistant", "generated", "enums", "assistant_runtime_enums.g.dart"),
	}
	for _, relativePath := range retired {
		path := filepath.Join(appDir, relativePath)
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			exitErr(fmt.Errorf("remove retired generated output %s: %w", path, err))
		}
	}
}

// ── readers ───────────────────────────────────────────────────────────────────
