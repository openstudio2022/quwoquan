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
	var fieldBindingReportPath string
	var assistantRuntimeEnumsGoOutput string
	var checkAssistantRuntimeEnumsGo bool
	var citationDestinationsGoOutput string
	var checkCitationDestinationsGo bool
	var realtimeContractsOnly bool
	var shellNavigationMetadataOnly bool
	var checkShellNavigationMetadata bool
	var shellNavigationManifestPath string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&appDir, "app-dir", "../quwoquan_app", "app root directory")
	flag.StringVar(&contractGraphPath, "contract-graph", "generated/contract_graph.json", "fixed ContractGraph JSON bundle")
	flag.StringVar(&contractGraphLockPath, "contract-graph-lock", "../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json", "accepted App ContractGraph lock")
	flag.StringVar(&generatedManifestPath, "generated-manifest", "../quwoquan_app/tool/cloud_codegen/generated_manifest.json", "App generated output manifest")
	flag.StringVar(
		&fieldBindingReportPath,
		"emit-field-binding-report",
		"../quwoquan_app/tool/cloud_codegen/field_binding_report.json",
		"contract enum_ref to generated Dart field binding report consumed by the enum typed-binding gate",
	)
	flag.StringVar(
		&shellNavigationManifestPath,
		"shell-navigation-manifest",
		"",
		"shell/navigation metadata-only generated output manifest",
	)
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
	flag.BoolVar(
		&realtimeContractsOnly,
		"realtime-contracts-only",
		false,
		"generate only the cloud-contracts realtime payloads and tagged event catalog without accepting or rewriting global ContractGraph outputs",
	)
	flag.BoolVar(
		&shellNavigationMetadataOnly,
		"shell-navigation-metadata-only",
		false,
		"generate only App shell/navigation metadata outputs without reading the App ContractGraph handoff lock",
	)
	flag.BoolVar(
		&checkShellNavigationMetadata,
		"check-shell-navigation-metadata",
		false,
		"verify shell/navigation metadata-only outputs and manifest are current",
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
		assistantRuntimeEnumsGoOutput != "" ||
			citationDestinationsGoOutput != "" ||
			realtimeContractsOnly
	if checkShellNavigationMetadata && !shellNavigationMetadataOnly {
		exitErr(fmt.Errorf(
			"--check-shell-navigation-metadata requires --shell-navigation-metadata-only",
		))
	}
	if shellNavigationMetadataOnly && serviceOutputRequested {
		exitErr(fmt.Errorf(
			"--shell-navigation-metadata-only cannot be combined with service output modes",
		))
	}
	if shellNavigationMetadataOnly {
		if err := runShellNavigationMetadataMode(
			metadataDir,
			appDir,
			shellNavigationManifestPath,
			checkShellNavigationMetadata,
		); err != nil {
			exitErr(err)
		}
		return
	}
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
	if realtimeContractsOnly {
		if err := writeRtcSignalPayloads(appDir, metadataDir); err != nil {
			exitErr(err)
		}
		if err := writeChatRealtimeEventPayloads(appDir, metadataDir); err != nil {
			exitErr(err)
		}
		if err := writeRecommendationFeedPatches(appDir, metadataDir); err != nil {
			exitErr(err)
		}
		if err := writeRealtimeEventCatalog(appDir); err != nil {
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
	if (searchContract == nil) != (searchObjects == nil) {
		exitErr(fmt.Errorf(
			"canonical Search metadata requires both search_contract.yaml and search_objects.yaml",
		))
	}
	if searchContract != nil {
		if err := validateCanonicalSearchMetadata(searchContract, searchObjects); err != nil {
			exitErr(err)
		}
	}
	// Domain-centric path: services/content-service/contracts/content/post/
	postDir := filepath.Join(metadataDir, "content", "content", "post")
	fields, err := readFields(filepath.Join(postDir, "fields.yaml"))
	if err != nil {
		exitErr(err)
	}
	uiDef, uiErr := readUIConfig(
		filepath.Join(postDir, "ui_config.yaml"),
		true,
	)
	if uiErr != nil {
		exitErr(fmt.Errorf("read ui_config.yaml: %w", uiErr))
	}
	if uiDef == nil {
		exitErr(fmt.Errorf("content ui_config.yaml is empty"))
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

	postSnapshotFieldByteLimits, err := buildPostSnapshotFieldByteLimits(
		post.Fields,
		projection,
	)
	if err != nil {
		exitErr(fmt.Errorf("derive Post snapshot field byte limits: %w", err))
	}
	contentTypes := shared.Enums["ContentType"]
	if len(contentTypes) == 0 {
		contentTypes = []string{"image", "video", "micro", "article"}
	}
	feedDefaultLimit := paginationLimitDefault(shared, 20)
	feedCategoryToType := uiDef.FeedRequestTypeByCategory

	if err := writeCanonicalContentMetadata(
		appDir,
		feedCategoryToType,
		contentTypes,
		postSnapshotFieldByteLimits,
	); err != nil {
		exitErr(err)
	}
	generatedStandaloneProjectionPaths := map[string]bool{}

	if err := writePostReadPresentationArtifacts(appDir, filepath.Join(postDir, "projections")); err != nil {
		exitErr(err)
	}

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
		writeFile(runtimeErrorOutputPath(appDir, "chat", "chat_errors.g.dart"), out)
	}

	// 3a3. 生成 assistant/circle/entity 客户端 *ErrorCode 枚举（端云错误码全集一致）。
	// 这三个域此前缺少客户端 typed enum，导致端侧只能硬编码字符串比对错误码；
	// 统一通过 renderSimpleErrorsDart 生成，唯一真相源各自 errors.yaml。
	if assistantErrs, err := readErrors(filepath.Join(metadataDir, "assistant", "assistant", "assistant_run", "errors.yaml")); err == nil {
		writeFile(
			runtimeErrorOutputPath(appDir, "assistant", "assistant_errors.g.dart"),
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
		runtimeErrorOutputPath(appDir, "circle", "circle_errors.g.dart"),
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
		runtimeErrorOutputPath(appDir, "circle", "circle_membership_errors.g.dart"),
		renderSimpleErrorsDart("CircleMembershipErrorCode", "circle/circle_management/circle_membership/errors.yaml", "圈子成员关系暂时不可用，请稍后重试", circleMembershipErrs),
	)
	if entityErrs, err := readMergedErrors([]string{
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage", "errors.yaml"),
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage_claim_request", "errors.yaml"),
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage_review", "errors.yaml"),
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage_status_report", "errors.yaml"),
	}); err == nil {
		writeFile(
			runtimeErrorOutputPath(appDir, "entity", "entity_errors.g.dart"),
			renderSimpleErrorsDart("EntityErrorCode", "entity/*/errors.yaml", "主页服务异常，请稍后重试", entityErrs),
		)
	}
	if notificationErrs, err := readErrors(filepath.Join(metadataDir, "notification", "notification_delivery", "notification", "errors.yaml")); err == nil {
		writeFile(
			runtimeErrorOutputPath(appDir, "notification", "notification_errors.g.dart"),
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
		runtimeErrorOutputPath(appDir, "ops", "ops_event_record_errors.g.dart"),
		renderSimpleErrorsDart("OpsEventRecordErrorCode", "ops/product_ops/event_record/errors.yaml", "启动诊断暂时不可用，请稍后重试", opsEventErrs),
	)
	if searchErrs, err := readMergedErrors([]string{
		filepath.Join(metadataDir, "search", "search", "search_request_fact", "errors.yaml"),
		filepath.Join(metadataDir, "search", "search", "recent_search_state", "errors.yaml"),
	}); err == nil {
		writeFile(
			runtimeErrorOutputPath(appDir, "search", "search_errors.g.dart"),
			renderSimpleErrorsDart("SearchErrorCode", "search/**/errors.yaml", "搜索服务异常，请稍后重试", searchErrs),
		)
	}
	if tagErrs, err := readMergedErrors([]string{
		filepath.Join(metadataDir, "tag", "tag", "tag_node_view", "errors.yaml"),
		filepath.Join(metadataDir, "tag", "tag", "tag_feedback_fact", "errors.yaml"),
		filepath.Join(metadataDir, "tag", "tag", "tag_taxonomy_release", "errors.yaml"),
	}); err == nil {
		writeFile(
			runtimeErrorOutputPath(appDir, "tag", "tag_errors.g.dart"),
			renderSimpleErrorsDart("TagErrorCode", "tag/**/errors.yaml", "标签服务异常，请稍后重试", tagErrs),
		)
	}

	// 3b. 生成 content_ui_config.g.dart（ContentUIConfig + DiscoveryTabConfig）
	out := renderContentUIConfigDart(uiDef)
	writeFile(
		contentPostPresentationOutputPath(appDir, "content_ui_config.g.dart"),
		out,
	)
	contentMediaPlaybackPolicy, err := renderContentMediaPlaybackPolicyDart(uiDef)
	if err != nil {
		exitErr(err)
	}
	writeFile(
		contentPostPublicGeneratedOutputPath(
			appDir,
			"content_media_playback_policy.g.dart",
		),
		contentMediaPlaybackPolicy,
	)

	publicationPolicy, policyErr := readContentPublicationPolicy(
		filepath.Join(postDir, "publication_policy.yaml"),
	)
	if policyErr != nil {
		exitErr(fmt.Errorf("read content publication policy: %w", policyErr))
	}
	writeFile(
		contentPostDomainOutputPath(
			appDir,
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
		contentMediaUploadSessionApplicationOutputPath(
			appDir,
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
		contentMediaAssetApplicationOutputPath(
			appDir,
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
		writeFile(
			userAccountPresentationOutputPath(
				appDir,
				"user_profile_ui_config.g.dart",
			),
			out,
		)
	}
	writeEntityCircleUIConfigs(metadataDir, appDir)
	if userErrsDef, err := readUserDomainErrors(metadataDir); err == nil {
		writeFile(
			runtimeErrorOutputPath(appDir, "user", "user_errors.g.dart"),
			renderUserErrorsDart(userErrsDef),
		)
	}

	// 2b. 生成 integration/external_integration/location 客户端 errors；
	// 路径、方法与鉴权统一由 canonical operation registry 提供。
	locDir := filepath.Join(metadataDir, "integration", "external_integration", "location")
	if locErrs, err := readErrors(filepath.Join(locDir, "errors.yaml")); err == nil {
		locErrOut := renderIntegrationLocationErrorsDart(locErrs)
		writeFile(runtimeErrorOutputPath(appDir, "integration", "integration_location_errors.g.dart"), locErrOut)
	}

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
	defaultsOut := renderCloudAPIDefaultsDart(feedDefaultLimit)
	writeFile(
		runtimeTransportSharedOutputPath(appDir, "cloud_api_defaults.g.dart"),
		defaultsOut,
	)
	for domain, routes := range domainRoutes {
		pageIDsOut := renderDomainRequestPageIDsDart(domain, routes)
		writeFile(
			runtimeTransportOutputPath(
				appDir,
				domain,
				fmt.Sprintf("%s_request_page_ids.g.dart", domain),
			),
			pageIDsOut,
		)
	}
	if err := writeRtcSignalPayloads(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	if err := writeChatRealtimeEventPayloads(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	if err := writeRecommendationFeedPatches(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	if err := writeRealtimeEventCatalog(appDir); err != nil {
		exitErr(err)
	}
	intersectionSource, intersectionRegistry, err :=
		readIntersectionGeneratedMetadata(metadataDir)
	if err != nil {
		exitErr(err)
	}
	writeIntersectionFeedbackContracts(
		appDir,
		intersectionSource,
		intersectionRegistry,
	)
	writeCanonicalIntersectionMetadata(
		appDir,
		intersectionSource,
		intersectionRegistry,
	)
	if err := writeImpactHelpTypeMetadata(appDir, metadataDir); err != nil {
		exitErr(err)
	}
	// RTC 客户端 errors；Service 产物由领域 codegen 所有。
	if rtcErrs, err := readErrors(filepath.Join(metadataDir, "rtc", "rtc", "call_session", "errors.yaml")); err == nil {
		writeFile(
			runtimeErrorOutputPath(appDir, "rtc", "rtc_errors.g.dart"),
			renderRtcErrorsDart(rtcErrs),
		)
	}
	writeFile(
		runtimeObservabilityOutputPath(appDir, "app_telemetry_catalog.g.dart"),
		renderAppTelemetryCatalogDart(telemetryCatalog),
	)
	if searchContract != nil {
		if err := writeCanonicalSearchMetadata(
			appDir,
			searchContract,
			searchObjects,
		); err != nil {
			exitErr(err)
		}
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
	if err := generateCanonicalSearchClientModels(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	if err := generateContentPreviewTrackManifestContract(appDir); err != nil {
		exitErr(err)
	}
	if err := generateAssistantRuntimeArtifacts(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	if err := generateAssistantOperationContracts(metadataDir, appDir); err != nil {
		exitErr(err)
	}
	providedResponseModels, err := generateDomainOperationContracts(
		metadataDir,
		appDir,
		activeContractLock,
	)
	if err != nil {
		exitErr(err)
	}
	if err := generateDomainOperationPublicBarrels(appDir, activeContractLock); err != nil {
		exitErr(err)
	}
	requestArtifacts, err := writeGeneratedOperationRequests(
		appDir,
		activeContractLock,
		providedResponseModels,
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
	if err := removeUntrackedGeneratedOutputs(); err != nil {
		exitErr(err)
	}
	if err := writeFieldBindingReport(fieldBindingReportPath); err != nil {
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
		runtimeErrorOutputPath(appDir, "content", "content_errors.g.dart"),
		renderContentErrorsDart(errorsDefinition),
	)
	return nil
}

// ── readers ───────────────────────────────────────────────────────────────────
