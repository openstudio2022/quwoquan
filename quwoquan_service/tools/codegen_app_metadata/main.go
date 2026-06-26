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
	var integrationServiceDir string
	var rtcServiceDir string
	var chatServiceDir string
	var userServiceDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&appDir, "app-dir", "../quwoquan_app", "app root directory")
	flag.StringVar(&integrationServiceDir, "integration-service-dir", "", "integration-service root (optional, generates Go location_metadata.go)")
	flag.StringVar(&rtcServiceDir, "rtc-service-dir", "", "rtc-service root (optional, generates Go rtc errors.go)")
	flag.StringVar(&chatServiceDir, "chat-service-dir", "", "chat-service root (optional, generates Go chat errors.go)")
	flag.StringVar(&userServiceDir, "user-service-dir", "", "user-service root (optional, generates Go user greeting errors.go)")
	flag.Parse()

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
	writableFields := findWritableFields(service.APIRoutes, "CreatePost")
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
	writeFile(filepath.Join(contentGenDir, "comment_dto.g.dart"), renderCommentDtoDart())
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
		if chatServiceDir != "" {
			writeFile(
				filepath.Join(chatServiceDir, "internal", "generated", "errors.go"),
				renderChatErrorsGo(chatErrsDef),
			)
		}
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
		if userServiceDir != "" {
			writeFile(
				filepath.Join(userServiceDir, "internal", "generated", "errors.go"),
				renderUserErrorsGo(userErrsDef),
			)
		}
	}

	// 2b. 生成 integration/location 元数据（路径、response key）
	locDir := filepath.Join(metadataDir, "integration", "location")
	if locSvc, err := readIntegrationLocationService(filepath.Join(locDir, "service.yaml")); err == nil {
		locOut := renderIntegrationLocationMetadataDart(locSvc)
		writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "integration", "integration_location_metadata.g.dart"), locOut)

		// 2b-go. 可选：生成 integration-service Go 元数据
		if integrationServiceDir != "" {
			locProjPath := filepath.Join(locDir, "projections", "location_poi.yaml")
			var projFields []projectionFieldDef
			if proj, err := readProjection(locProjPath); err == nil {
				projFields = proj.ClientProjection.Fields
			}
			goOut := renderIntegrationLocationMetadataGo(locSvc, projFields)
			writeFile(filepath.Join(integrationServiceDir, "internal", "generated", "location_metadata.go"), goOut)
		}
	}

	// 2b2. 生成 integration/location errors（IntegrationLocationErrorCode + integration-service errors.go）
	if locErrs, err := readErrors(filepath.Join(locDir, "errors.yaml")); err == nil {
		locErrOut := renderIntegrationLocationErrorsDart(locErrs)
		writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "integration", "integration_location_errors.g.dart"), locErrOut)
		if integrationServiceDir != "" {
			locErrGoOut := renderIntegrationLocationErrorsGo(locErrs)
			writeFile(filepath.Join(integrationServiceDir, "internal", "generated", "errors.go"), locErrGoOut)
		}
	}

	// 2c. 生成 integration/location projections（无 base_class 的 standalone DTO，如 LocationPoiDto）
	locProjDir := filepath.Join(locDir, "projections")
	if locProjEntries, err := os.ReadDir(locProjDir); err == nil {
		for _, e := range locProjEntries {
			if e.IsDir() || !strings.HasSuffix(e.Name(), ".yaml") {
				continue
			}
			p, err := readProjection(filepath.Join(locProjDir, e.Name()))
			if err != nil || len(p.ClientProjection.Fields) == 0 {
				continue
			}
			if p.ClientProjection.BaseClass != "" {
				continue // 有 base_class 的不在此处理
			}
			sourcePath := fmt.Sprintf("integration/location/projections/%s", e.Name())
			out := renderStandaloneDtoDart(p.ClientProjection, sourcePath)
			relPath := p.ClientProjection.OutputPath
			if relPath == "" {
				continue
			}
			writeFile(filepath.Join(appDir, "lib", relPath), out)
			generatedStandaloneProjectionPaths[relPath] = true
		}
	}

	// 3. 生成带 base_class 的 typed post DTOs（photo/video/article/moment）
	// 规范路径：contracts/metadata/content/post/projections/
	projDir := filepath.Join(postDir, "projections")

	entries, err := os.ReadDir(projDir)
	if err != nil {
		exitErr(err)
	}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".yaml") {
			continue
		}
		if e.Name() == "discovery_feed.yaml" {
			continue // already handled above
		}
		p, err := readProjection(filepath.Join(projDir, e.Name()))
		if err != nil {
			exitErr(err)
		}
		if p.ClientProjection.BaseClass == "" || len(p.ClientProjection.Fields) == 0 {
			continue
		}
		out := renderTypedPostDtoDart(p.ClientProjection, e.Name())
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
	writeEntityHomepageMutationWiresFromMetadata(metadataDir, appDir)

	// 3b. 生成其他 domain projections（无 base_class 的 standalone DTO，如 chat inbox）。
	// 用户域 Auth/Invite/Greeting 等 wire 读模型见：
	//   user/user_profile/projections/*.yaml
	//   user/invite_record/projections/*.yaml
	//   user/greeting_request/projections/*.yaml
	err = filepath.WalkDir(metadataDir, func(path string, d os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if d.IsDir() || !strings.HasSuffix(d.Name(), ".yaml") {
			return nil
		}
		if filepath.Base(filepath.Dir(path)) != "projections" {
			return nil
		}
		p, readErr := readProjection(path)
		if readErr != nil || len(p.ClientProjection.Fields) == 0 {
			return nil
		}
		if strings.TrimSpace(p.ClientProjection.BaseClass) != "" {
			return nil
		}
		relPath := strings.TrimSpace(p.ClientProjection.OutputPath)
		if relPath == "" || generatedStandaloneProjectionPaths[relPath] {
			return nil
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
		return nil
	})
	if err != nil {
		exitErr(err)
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
		renderAuthPolicyDart(domainRoutes),
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
	// rtc errors（RtcErrorCode Dart enum + rtc-service Go errors.go），唯一真相源 errors.yaml
	if rtcErrs, err := readErrors(filepath.Join(metadataDir, "rtc", "call_session", "errors.yaml")); err == nil {
		writeFile(
			filepath.Join(appDir, "lib", "cloud", "rtc", "generated", "rtc_errors.g.dart"),
			renderRtcErrorsDart(rtcErrs),
		)
		if rtcServiceDir != "" {
			writeFile(
				filepath.Join(rtcServiceDir, "internal", "generated", "errors.go"),
				renderRtcErrorsGo(rtcErrs),
			)
		}
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
	svcRoot, err := filepath.Abs(".")
	if err != nil {
		exitErr(err)
	}
	if err := generateAssistantWireGoPoC(metadataDir, svcRoot); err != nil {
		exitErr(err)
	}
}

// ── readers ───────────────────────────────────────────────────────────────────
