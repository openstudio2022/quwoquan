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
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&appDir, "app-dir", "../quwoquan_app", "app root directory")
	flag.StringVar(&contractGraphPath, "contract-graph", "generated/contract_graph.json", "fixed ContractGraph JSON bundle")
	flag.StringVar(&contractGraphLockPath, "contract-graph-lock", "../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json", "accepted App ContractGraph lock")
	flag.StringVar(&generatedManifestPath, "generated-manifest", "../quwoquan_app/tool/cloud_codegen/generated_manifest.json", "App generated output manifest")
	flag.Parse()
	if err := initializeContractGraphBundle(
		metadataDir,
		contractGraphPath,
		contractGraphLockPath,
	); err != nil {
		exitErr(err)
	}
	beginGeneratedManifest(appDir, activeContractSHA256)
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
		filepath.Join(metadataDir, "ops", "event_record", "event_catalog.yaml"),
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
	// Domain-centric path: contracts/metadata/content/post/
	postDir := filepath.Join(metadataDir, "content", "post")
	fields, err := readFields(filepath.Join(postDir, "fields.yaml"))
	if err != nil {
		exitErr(err)
	}
	service, err := readService(filepath.Join(postDir, "service.yaml"))
	if err != nil {
		exitErr(err)
	}
	// discovery_feed projection: contracts/metadata/content/post/projections/
	feedProjPath := filepath.Join(postDir, "projections", "discovery_feed.yaml")
	projection, err := readProjection(feedProjPath)
	if err != nil {
		exitErr(err)
	}

	post, ok := fields.Entities["Post"]
	if !ok {
		exitErr(fmt.Errorf("Post entity not found in fields.yaml"))
	}

	defaults := buildPostDefaults(post.Fields)
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
	writableFields := findWritableFields(service.APIRoutes, "SubmitPostPublication")
	likeRoutes := buildMutationRoutes(service.APIRoutes,
		[]string{"LikePost", "UnlikePost", "FavoritePost", "UnfavoritePost"})

	// 1. 生成 content_metadata.g.dart（原 post_runtime_metadata.g.dart）
	metaOut := renderContentMetadataDart(
		defaults,
		feedDefaults,
		contentTypeMapping,
		feedCategoryToType,
		appTabToCategory,
		feedRoute,
		getPostRoute,
		feedDefaultLimit,
		writableFields,
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
	writeFile(filepath.Join(contentGenDir, "post_search_item_view_dto.g.dart"), renderPostSearchItemViewDtoDart())
	writeFile(filepath.Join(contentGenDir, "report_create_request_wire.g.dart"), renderCreateReportRequestWireDart())

	if err := writePostReadPresentationArtifacts(appDir, filepath.Join(postDir, "projections")); err != nil {
		exitErr(err)
	}
	writeContentAppConfigClientDart(filepath.Join(contentGenDir, "content_app_config_client_dto.g.dart"))

	// 3a. 生成 content_errors.g.dart（ContentErrorCode enum + messages）
	if errsDef, err := readErrors(filepath.Join(postDir, "errors.yaml")); err == nil {
		out := renderContentErrorsDart(errsDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_errors.g.dart"), out)
	}

	// 3a2. 生成 chat_errors.g.dart（ChatErrorCode enum + messages）
	chatConversationDir := filepath.Join(metadataDir, "messages", "conversation")
	if chatErrsDef, err := readErrors(filepath.Join(chatConversationDir, "errors.yaml")); err == nil {
		out := renderChatErrorsDart(chatErrsDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "chat", "generated", "chat_errors.g.dart"), out)
	}

	// 3a3. 生成 assistant/circle/entity 客户端 *ErrorCode 枚举（端云错误码全集一致）。
	// 这三个域此前缺少客户端 typed enum，导致端侧只能硬编码字符串比对错误码；
	// 统一通过 renderSimpleErrorsDart 生成，唯一真相源各自 errors.yaml。
	if assistantErrs, err := readErrors(filepath.Join(metadataDir, "assistant", "assistant_run", "errors.yaml")); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "assistant", "generated", "assistant_errors.g.dart"),
			renderSimpleErrorsDart("AssistantErrorCode", "assistant/assistant_run/errors.yaml", "找私助暂时不可用，请稍后重试", assistantErrs),
		)
	}
	if circleErrs, err := readErrors(filepath.Join(metadataDir, "social", "circle", "errors.yaml")); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "circle", "generated", "circle_errors.g.dart"),
			renderSimpleErrorsDart("CircleErrorCode", "social/circle/errors.yaml", "圈子服务异常，请稍后重试", circleErrs),
		)
	}
	if entityErrs, err := readErrors(filepath.Join(metadataDir, "entity", "homepage", "errors.yaml")); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "entity", "generated", "entity_errors.g.dart"),
			renderSimpleErrorsDart("EntityErrorCode", "entity/homepage/errors.yaml", "主页服务异常，请稍后重试", entityErrs),
		)
	}
	opsEventErrs, err := readErrors(
		filepath.Join(metadataDir, "ops", "event_record", "errors.yaml"),
	)
	if err != nil {
		exitErr(fmt.Errorf("read ops event-record errors: %w", err))
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "ops", "ops_event_record_errors.g.dart"),
		renderSimpleErrorsDart("OpsEventRecordErrorCode", "ops/event_record/errors.yaml", "启动诊断暂时不可用，请稍后重试", opsEventErrs),
	)

	// 3b. 生成 content_behaviors.g.dart（ContentBehaviorTracker）
	if behDef, err := readBehaviors(filepath.Join(postDir, "behaviors.yaml")); err == nil {
		out := renderContentBehaviorsDart(behDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_behaviors.g.dart"), out)
	}

	// 3c. 生成 content_privacy_policy.g.dart（sanitizeForLog）
	if privDef, err := readPrivacy(filepath.Join(postDir, "privacy.yaml")); err == nil {
		out := renderContentPrivacyDart(privDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_privacy_policy.g.dart"), out)
	}

	// 3d. 生成 content_ui_config.g.dart（ContentUIConfig + DiscoveryTabConfig）
	uiDef, uiErr := readUIConfig(filepath.Join(postDir, "ui_config.yaml"))
	if uiErr != nil {
		exitErr(fmt.Errorf("read ui_config.yaml: %w", uiErr))
	}
	if uiDef != nil {
		out := renderContentUIConfigDart(uiDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_ui_config.g.dart"), out)
	}

	prefabUserDef, err := readPrefabUserProvenance(
		filepath.Join(metadataDir, "_shared", "prefab_user_provenance.yaml"),
	)
	if err != nil {
		exitErr(fmt.Errorf("read _shared/prefab_user_provenance.yaml: %w", err))
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "user", "generated", "prefab_user_metadata.g.dart"),
		renderPrefabUserMetadataDart(prefabUserDef),
	)

	userProfileDir := filepath.Join(metadataDir, "user", "user_profile")
	userUIDef, userUIErr := readUIConfig(filepath.Join(userProfileDir, "ui_config.yaml"))
	if userUIErr != nil && !os.IsNotExist(userUIErr) {
		exitErr(fmt.Errorf("read user/user_profile/ui_config.yaml: %w", userUIErr))
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

	// 2b. 生成 integration/location 元数据（路径、response key）
	locDir := filepath.Join(metadataDir, "integration", "location")
	if locSvc, err := readIntegrationLocationService(filepath.Join(locDir, "service.yaml")); err == nil {
		locOut := renderIntegrationLocationMetadataDart(locSvc)
		writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "integration", "integration_location_metadata.g.dart"), locOut)

	}

	// 2b2. 生成 integration/location 客户端 errors；Service 产物由领域 codegen 所有。
	if locErrs, err := readErrors(filepath.Join(locDir, "errors.yaml")); err == nil {
		locErrOut := renderIntegrationLocationErrorsDart(locErrs)
		writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "integration", "integration_location_errors.g.dart"), locErrOut)
	}

	// 2c. 生成 integration/location projections（无 base_class 的 standalone DTO，如 LocationPoiDto）
	for _, projectionPath := range metadataDocumentPaths("integration/location/projections", ".yaml") {
		p, err := readProjection(projectionPath)
		if err != nil || len(p.ClientProjection.Fields) == 0 {
			continue
		}
		if p.ClientProjection.BaseClass != "" {
			continue
		}
		sourcePath := fmt.Sprintf(
			"integration/location/projections/%s",
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
	// 规范路径：contracts/metadata/content/post/projections/
	for _, projectionPath := range metadataDocumentPaths("content/post/projections", ".yaml") {
		if filepath.Base(projectionPath) == "discovery_feed.yaml" {
			continue // already handled above
		}
		p, err := readProjection(projectionPath)
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
	postWireFieldTypes := make(map[string]string, len(post.Fields))
	for _, f := range post.Fields {
		postWireFieldTypes[f.Name] = strings.TrimSpace(f.Type)
	}
	writeContentPostMutationWires(filepath.Join(contentGenDir, "content_post_mutation_wires.g.dart"), service, postWireFieldTypes)
	if err := writeEntityHomepageMutationWiresFromMetadata(metadataDir, appDir); err != nil {
		exitErr(err)
	}

	// 3b. 生成其他 domain projections（无 base_class 的 standalone DTO，如 chat inbox）。
	// 用户域 Auth/Invite/Greeting 等 wire 读模型见：
	//   user/user_profile/projections/*.yaml
	//   user/invite_record/projections/*.yaml
	//   user/greeting_request/projections/*.yaml
	for _, path := range metadataDocumentPaths("", ".yaml") {
		if filepath.Base(filepath.Dir(path)) != "projections" {
			continue
		}
		p, readErr := readProjection(path)
		if readErr != nil || len(p.ClientProjection.Fields) == 0 {
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
	if err := writeRtcRequestWires(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	// RTC 客户端 errors；Service 产物由领域 codegen 所有。
	if rtcErrs, err := readErrors(filepath.Join(metadataDir, "rtc", "call_session", "errors.yaml")); err == nil {
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
			renderLinkTemplatesDart(linkTemplates),
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
	if searchObjects != nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "search", "search_registry.g.dart"),
			renderSearchRegistryDart(searchObjects),
		)
	}
	if circleWireKeysOut, err := renderCircleWriteWireWritableKeysDart(metadataDir); err != nil {
		exitErr(err)
	} else {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "circle", "circle_write_wire_writable_keys.g.dart"),
			circleWireKeysOut,
		)
	}
	if err := generateAssistantRuntimeArtifacts(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	if err := generateAssistantCloudApiWireDart(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	writeGeneratedOperationContracts(appDir, activeContractLock)
	if err := writeGeneratedManifest(generatedManifestPath); err != nil {
		exitErr(err)
	}
}

// ── readers ───────────────────────────────────────────────────────────────────
