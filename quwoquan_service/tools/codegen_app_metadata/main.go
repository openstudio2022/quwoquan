package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"gopkg.in/yaml.v3"
)

// ── shared/types.yaml ────────────────────────────────────────────────────────

type sharedTypes struct {
	Enums map[string][]string  `yaml:"enums"`
	Types map[string]sharedDef `yaml:"types"`
}

type sharedDef struct {
	Fields []sharedFieldDef `yaml:"fields"`
}

type sharedFieldDef struct {
	Name    string      `yaml:"name"`
	Default interface{} `yaml:"default"`
}

// ── post/fields.yaml ─────────────────────────────────────────────────────────

type fieldDef struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	Constraints []string `yaml:"constraints"`
}

type entityDef struct {
	Fields []fieldDef `yaml:"fields"`
}

type fieldsFile struct {
	Entities map[string]entityDef `yaml:"entities"`
}

// ── post/service.yaml ─────────────────────────────────────────────────────────

type routeDef struct {
	Method         string   `yaml:"method"`
	Path           string   `yaml:"path"`
	Operation      string   `yaml:"operation"`
	Description    string   `yaml:"description"`
	QueryParams    []string `yaml:"query_params"`
	WritableFields []string `yaml:"writable_fields"`
}

type serviceInfo struct {
	Name   string `yaml:"name"`
	Domain string `yaml:"domain"`
}

type serviceFile struct {
	Service   serviceInfo `yaml:"service"`
	APIRoutes []routeDef  `yaml:"api_routes"`
}

// integration/location/service.yaml 专用，含 response_list_key
type integrationLocationServiceFile struct {
	ResponseListKey string     `yaml:"response_list_key"`
	APIRoutes       []routeDef `yaml:"api_routes"`
}

// ── {domain}/{entity}/projections/*.yaml ─────────────────────────────────────

type projectionFieldDef struct {
	Name        string   `yaml:"name"`
	DartType    string   `yaml:"dart_type"`
	Nullable    bool     `yaml:"nullable"`
	Source      string   `yaml:"source"`
	Aliases     []string `yaml:"aliases"`
	Default     string   `yaml:"default"`
	Description string   `yaml:"description"`
}

type computedGetterDef struct {
	Name           string `yaml:"name"`
	DartReturnType string `yaml:"dart_return_type"`
	Nullable       bool   `yaml:"nullable"`
	Description    string `yaml:"description"`
	Body           string `yaml:"body"`
}

type clientProjection struct {
	DartClass       string               `yaml:"dart_class"`
	BaseClass       string               `yaml:"base_class"`
	OutputPath      string               `yaml:"output_path"`
	Fields          []projectionFieldDef `yaml:"fields"`
	ComputedGetters []computedGetterDef  `yaml:"computed_getters"`
}

type projectionFile struct {
	ReadModel        string           `yaml:"read_model"`
	ClientProjection clientProjection `yaml:"client_projection"`
}

// ── errors.yaml ───────────────────────────────────────────────────────────────

type errorDef struct {
	Code              string            `yaml:"code"`
	Kind              string            `yaml:"kind"`
	Reason            string            `yaml:"reason"`
	HTTPStatus        int               `yaml:"http_status"`
	Retryable         bool              `yaml:"retryable"`
	RetryAfterSeconds int               `yaml:"retry_after_seconds"`
	DartConst         string            `yaml:"dart_const"`
	GoConst           string            `yaml:"go_const"`
	L10nKey           string            `yaml:"l10n_key"` // AppLocalizations getter name for display message
	UserMessage       map[string]string `yaml:"user_message"`
}

type errorsFile struct {
	Domain string     `yaml:"domain"`
	Errors []errorDef `yaml:"errors"`
}

// ── behaviors.yaml ─────────────────────────────────────────────────────────────

type behaviorEventDef struct {
	Type           string   `yaml:"type"`
	Description    string   `yaml:"description"`
	Trigger        string   `yaml:"trigger"`
	Batch          bool     `yaml:"batch"`
	BatchRoute     string   `yaml:"batch_route"`
	DartMethod     string   `yaml:"dart_method"`
	DedicatedRoute string   `yaml:"dedicated_route"`
	PayloadFields  []string `yaml:"payload_fields"`
	MLSignal       string   `yaml:"ml_signal"`
}

type behaviorsFile struct {
	BehaviorEvents []behaviorEventDef `yaml:"behavior_events"`
}

// ── privacy.yaml ─────────────────────────────────────────────────────────────

type appLogPolicyDef struct {
	Field          string `yaml:"field"`
	Classification string `yaml:"classification"`
	AppLog         string `yaml:"app_log"`
	MaskStrategy   string `yaml:"mask_strategy"`
	TruncateChars  int    `yaml:"truncate_chars"`
	Description    string `yaml:"description"`
}

type privacyFile struct {
	AppLogPolicy []appLogPolicyDef `yaml:"app_log_policy"`
}

// ── ui_config.yaml ────────────────────────────────────────────────────────────

type discoveryTabDef struct {
	ID          string `yaml:"id"`
	LabelKey    string `yaml:"label_key"`
	Icon        string `yaml:"icon"`
	ContentType string `yaml:"content_type"`
	Layout      string `yaml:"layout"`
	Order       int    `yaml:"order"`
}

type discoveryRailDef struct {
	ID       string `yaml:"id"`
	LabelKey string `yaml:"label_key"`
	Identity string `yaml:"identity"`
	Default  bool   `yaml:"default"`
	Order    int    `yaml:"order"`
}

type identityFilterDef struct {
	ID       string `yaml:"id"`
	LabelKey string `yaml:"label_key"`
	Identity string `yaml:"identity"`
	Order    int    `yaml:"order"`
}

type workFormatFilterDef struct {
	ID          string `yaml:"id"`
	LabelKey    string `yaml:"label_key"`
	ContentType string `yaml:"content_type"`
	Order       int    `yaml:"order"`
}

type profileSubTabDef struct {
	ID          string `yaml:"id"`
	LabelKey    string `yaml:"label_key"`
	ContentType string `yaml:"content_type"`
	Order       int    `yaml:"order"`
}

type profileTabDef struct {
	ID               string              `yaml:"id"`
	LabelKey         string              `yaml:"label_key"`
	Order            int                 `yaml:"order"`
	Default          bool                `yaml:"default"`
	SubTabs          []profileSubTabDef  `yaml:"sub_tabs"`
	VisibilityFilter map[string][]string `yaml:"visibility_filter"`
	DirectionFilter  map[string][]string `yaml:"direction_filter"`
}

type profileHeaderLayoutDef struct {
	BaseHeightRatio       float64 `yaml:"base_height_ratio"`
	MaxStretchHeightRatio float64 `yaml:"max_stretch_height_ratio"`
	AvatarOverlapRatio    float64 `yaml:"avatar_overlap_ratio"`
}

type profileScrollMotionDef struct {
	CompactIdentityBar           bool   `yaml:"compact_identity_bar"`
	PrimaryTabStickyBelowToolbar bool   `yaml:"primary_tab_sticky_below_toolbar"`
	SecondaryTabInlineScroll     bool   `yaml:"secondary_tab_inline_scroll"`
	ReboundCurve                 string `yaml:"rebound_curve"`
	CollapseCurve                string `yaml:"collapse_curve"`
}

type shareTemplateProfileDef struct {
	ID                   string `yaml:"id"`
	TitleKey             string `yaml:"title_key"`
	SubtitleKey          string `yaml:"subtitle_key"`
	Layout               string `yaml:"layout"`
	CoverStrategy        string `yaml:"cover_strategy"`
	IncludeAuthor        bool   `yaml:"include_author"`
	IncludeTimeContext   bool   `yaml:"include_time_context"`
	IncludeCircleContext bool   `yaml:"include_circle_context"`
	IncludeTags          bool   `yaml:"include_tags"`
}

type articleDistributionProfileDef struct {
	ID               string `yaml:"id"`
	Surface          string `yaml:"surface"`
	Layout           string `yaml:"layout"`
	CoverMode        string `yaml:"cover_mode"`
	SummaryLineLimit int    `yaml:"summary_line_limit"`
}

type articleReaderProfileDef struct {
	ID                  string `yaml:"id"`
	StageLayout         string `yaml:"stage_layout"`
	PageIndicatorAnchor string `yaml:"page_indicator_anchor"`
	EdgeTreatment       string `yaml:"edge_treatment"`
	SupportsPageCurl    bool   `yaml:"supports_page_curl"`
}

type articleTemplateConfigDef struct {
	ID                string `yaml:"id"`
	DefaultFontPreset string `yaml:"default_font_preset"`
	PaperTexture      string `yaml:"paper_texture"`
	DecorationStyle   string `yaml:"decoration_style"`
	ChromeStyle       string `yaml:"chrome_style"`
}

type articleTemplateRecommendationDef struct {
	CategoryID                  string   `yaml:"category_id"`
	RecommendedArticleTemplates []string `yaml:"recommended_article_templates"`
}

type featureFlagDef struct {
	Flag        string `yaml:"flag"`
	Default     bool   `yaml:"default"`
	Description string `yaml:"description"`
}

type emptyStateDef struct {
	Illustration string `yaml:"illustration"`
	TitleKey     string `yaml:"title_key"`
	SubtitleKey  string `yaml:"subtitle_key"`
	CTALabelKey  string `yaml:"cta_label_key"`
}

type uiConfigFile struct {
	DiscoveryTabs                  []discoveryTabDef                  `yaml:"discovery_tabs"`
	DiscoveryRails                 []discoveryRailDef                 `yaml:"discovery_rails"`
	CreationIdentityFilters        []identityFilterDef                `yaml:"creation_identity_filters"`
	WorkFormatFilters              []workFormatFilterDef              `yaml:"work_format_filters"`
	HeaderLayout                   profileHeaderLayoutDef             `yaml:"header_layout"`
	ScrollMotion                   profileScrollMotionDef             `yaml:"scroll_motion"`
	ProfileTabs                    []profileTabDef                    `yaml:"profile_tabs"`
	ShareTemplateProfiles          []shareTemplateProfileDef          `yaml:"share_template_profiles"`
	ArticleDistributionProfiles    []articleDistributionProfileDef    `yaml:"article_distribution_profiles"`
	ArticleReaderProfiles          []articleReaderProfileDef          `yaml:"article_reader_profiles"`
	ArticleTemplateConfigs         []articleTemplateConfigDef         `yaml:"article_template_configs"`
	ArticleTemplateRecommendations []articleTemplateRecommendationDef `yaml:"article_template_recommendations"`
	FeatureFlags                   []featureFlagDef                   `yaml:"feature_flags"`
	EmptyStates                    map[string]emptyStateDef           `yaml:"empty_states"`
}

// ── _shared/request_context.yaml ──────────────────────────────────────────────

type requestContextFile struct {
	DomainOperationPageIDs map[string]map[string]string `yaml:"domain_operation_page_ids"`
	StandalonePageIDs      map[string]string            `yaml:"standalone_page_ids"`
}

var sharedRequestContext requestContextFile

type appRouteDef struct {
	ID          string   `yaml:"id"`
	Path        string   `yaml:"path"`
	QueryParams []string `yaml:"query_params"`
}

type appRoutesFile struct {
	Routes []appRouteDef `yaml:"routes"`
}

type uiSurfaceDef struct {
	ID           string   `yaml:"id"`
	Owner        string   `yaml:"owner"`
	RouteID      string   `yaml:"route_id"`
	PathTemplate string   `yaml:"path_template"`
	Description  string   `yaml:"description"`
	OperationIDs []string `yaml:"operation_ids"`
}

type uiSurfacesFile struct {
	Surfaces []uiSurfaceDef `yaml:"surfaces"`
}

type searchNamedValueDef struct {
	ID          string `yaml:"id"`
	Description string `yaml:"description"`
}

type searchContractDefaultsDef struct {
	SuggestLimit   int `yaml:"suggest_limit"`
	ResultLimit    int `yaml:"result_limit"`
	AssistantLimit int `yaml:"assistant_limit"`
}

type searchToolContractDef struct {
	Name                  string   `yaml:"name"`
	Description           string   `yaml:"description"`
	RequiredFields        []string `yaml:"required_fields"`
	OptionalFields        []string `yaml:"optional_fields"`
	InternalOptionalFields []string `yaml:"internal_optional_fields"`
}

type searchContractFile struct {
	Version             int                       `yaml:"version"`
	Modes               []searchNamedValueDef     `yaml:"modes"`
	ExecutionStrategies []searchNamedValueDef     `yaml:"execution_strategies"`
	ResolvedSources     []searchNamedValueDef     `yaml:"resolved_sources"`
	ConversationTypes   []searchNamedValueDef     `yaml:"conversation_types"`
	ContentTypeFilters  []searchNamedValueDef     `yaml:"content_type_filters"`
	Defaults            searchContractDefaultsDef `yaml:"defaults"`
	ToolContract        searchToolContractDef     `yaml:"tool_contract"`
}

type searchObjectTypeDef struct {
	ID                string `yaml:"id"`
	Label             string `yaml:"label"`
	Domain            string `yaml:"domain"`
	ExecutionStrategy string `yaml:"execution_strategy"`
	Provider          string `yaml:"provider"`
}

type searchSectionKindDef struct {
	ID                 string   `yaml:"id"`
	Title              string   `yaml:"title"`
	DefaultObjectTypes []string `yaml:"default_object_types"`
}

type searchObjectsFile struct {
	Version      int                    `yaml:"version"`
	ObjectTypes  []searchObjectTypeDef  `yaml:"object_types"`
	SectionKinds []searchSectionKindDef `yaml:"section_kinds"`
}

// ── main ──────────────────────────────────────────────────────────────────────

func main() {
	var metadataDir string
	var appDir string
	var integrationServiceDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&appDir, "app-dir", "../quwoquan_app", "app root directory")
	flag.StringVar(&integrationServiceDir, "integration-service-dir", "", "integration-service root (optional, generates Go location_metadata.go)")
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
	recommendRoute := findRoute(service.APIRoutes, "GetRecommendation")
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
		recommendRoute,
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

	// 3a. 生成 content_errors.g.dart（ContentErrorCode enum + messages）
	if errsDef, err := readErrors(filepath.Join(postDir, "errors.yaml")); err == nil {
		out := renderContentErrorsDart(errsDef)
		writeFile(filepath.Join(appDir, "lib", "cloud", "content", "generated", "content_errors.g.dart"), out)
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

	// 3b. 生成其他 domain projections（无 base_class 的 standalone DTO，如 chat inbox）
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
	defaultsOut := renderCloudAPIDefaultsDart(feedDefaultLimit)
	writeFile(filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "cloud_api_defaults.g.dart"), defaultsOut)
	for domain, routes := range domainRoutes {
		metaOut := renderDomainAPIMetadataDart(domain, routes)
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
	if err := generateAssistantRuntimeArtifacts(metadataDir, appDir); err != nil {
		exitErr(err)
	}
}

// ── readers ───────────────────────────────────────────────────────────────────

func readShared(path string) (*sharedTypes, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed sharedTypes
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readFields(path string) (*fieldsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed fieldsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readService(path string) (*serviceFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed serviceFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readIntegrationLocationService(path string) (*integrationLocationServiceFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed integrationLocationServiceFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readProjection(path string) (*projectionFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed projectionFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

// ── builders ──────────────────────────────────────────────────────────────────

func collectDomainServiceRoutes(metadataDir string) (map[string][]routeDef, error) {
	grouped := map[string][]routeDef{}
	seen := map[string]bool{}
	err := filepath.WalkDir(metadataDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || d.Name() != "service.yaml" {
			return nil
		}
		service, readErr := readService(path)
		if readErr != nil {
			return readErr
		}
		domain := strings.TrimSpace(service.Service.Domain)
		if domain == "" {
			return nil
		}
		for _, route := range service.APIRoutes {
			if strings.TrimSpace(route.Operation) == "" || strings.TrimSpace(route.Path) == "" {
				continue
			}
			key := domain + ":" + route.Operation
			if seen[key] {
				continue
			}
			seen[key] = true
			grouped[domain] = append(grouped[domain], route)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	for domain := range grouped {
		sort.Slice(grouped[domain], func(i, j int) bool {
			return grouped[domain][i].Operation < grouped[domain][j].Operation
		})
	}
	return grouped, nil
}

func buildPostDefaults(fields []fieldDef) map[string]string {
	defaults := map[string]string{}
	for _, f := range fields {
		if v, ok := parseDefaultValue(f.Constraints); ok {
			defaults[f.Name] = v
			continue
		}
		if strings.HasPrefix(f.Type, "[]") {
			defaults[f.Name] = dartEmptyListExpr(f.Type)
		}
	}
	return defaults
}

func dartEmptyListExpr(t string) string {
	switch t {
	case "[]float32", "[]float64":
		return "<double>[]"
	case "[]int":
		return "<int>[]"
	case "[]bool":
		return "<bool>[]"
	case "[]object":
		return "<Map<String, dynamic>>[]"
	default:
		return "<String>[]"
	}
}

func parseDefaultValue(constraints []string) (string, bool) {
	for _, c := range constraints {
		if !strings.HasPrefix(c, "DEFAULT_") {
			continue
		}
		raw := strings.TrimPrefix(c, "DEFAULT_")
		if raw == "FALSE" {
			return "false", true
		}
		if raw == "TRUE" {
			return "true", true
		}
		if n, err := strconv.Atoi(raw); err == nil {
			return strconv.Itoa(n), true
		}
		return fmt.Sprintf("'%s'", strings.ToLower(raw)), true
	}
	return "", false
}

func buildFeedDefaults(postDefaults map[string]string) map[string]string {
	get := func(key, fallback string) string {
		if v, ok := postDefaults[key]; ok && v != "" {
			return v
		}
		return fallback
	}
	// NOTE: These defaults are legacy Map<String,dynamic> compatibility constants.
	// New code should use FeedItemDto (feed_item_dto.g.dart) instead.
	return map[string]string{
		"coverUrl":         get("coverUrl", "''"),
		"isLocalGenerated": "true",
		"tags":             get("tags", "<String>[]"),
		"thumbnailUrl":     get("coverUrl", "''"),
		"videoUrl":         get("videoUrl", "''"),
		"visibility":       get("visibility", "'public'"),
	}
}

func buildContentTypeToRender(contentTypes []string) map[string]string {
	out := map[string]string{}
	for _, ct := range contentTypes {
		switch ct {
		case "micro":
			out[ct] = "moment"
		default:
			out[ct] = ct
		}
	}
	return out
}

func buildDiscoveryMappings(contentTypes []string) (map[string]string, map[string]string) {
	feedCategoryToType := map[string]string{
		"recommended": "moment",
		"following":   "moment",
	}
	for _, ct := range contentTypes {
		category := ct
		feedType := ct
		switch ct {
		case "micro":
			category = "moment"
			feedType = "moment"
		case "image":
			category = "images"
			feedType = "photo"
			feedCategoryToType["photo"] = "photo"
		}
		feedCategoryToType[category] = feedType
	}

	appTabToCategory := map[string]string{
		"moment":  "recommended",
		"photo":   "images",
		"video":   "video",
		"article": "article",
	}
	return feedCategoryToType, appTabToCategory
}

func buildMutationRoutes(routes []routeDef, operations []string) map[string]string {
	out := map[string]string{}
	for _, op := range operations {
		r := findRoute(routes, op)
		if r.Path != "" {
			out[op] = r.Path
		}
	}
	return out
}

func findRoute(routes []routeDef, operation string) routeDef {
	for _, r := range routes {
		if strings.EqualFold(r.Operation, operation) {
			return r
		}
	}
	return routeDef{}
}

func findWritableFields(routes []routeDef, operation string) []string {
	for _, r := range routes {
		if strings.EqualFold(r.Operation, operation) {
			return r.WritableFields
		}
	}
	return nil
}

func paginationLimitDefault(shared *sharedTypes, fallback int) int {
	pagination, ok := shared.Types["Pagination"]
	if !ok {
		return fallback
	}
	for _, f := range pagination.Fields {
		if f.Name != "limit" || f.Default == nil {
			continue
		}
		switch v := f.Default.(type) {
		case int:
			return v
		case int64:
			return int(v)
		case float64:
			return int(v)
		}
	}
	return fallback
}

func operationDefaultLimit(operation string, pageLimit int) int {
	switch operation {
	case "ListUserCircles":
		return 50
	case "SyncMessages":
		return 500
	default:
		return pageLimit
	}
}

// ── renderers ─────────────────────────────────────────────────────────────────

func renderCloudAPIDefaultsDart(pageLimit int) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata. DO NOT EDIT.\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class CloudApiDefaults {\n")
	b.WriteString("  const CloudApiDefaults._();\n\n")
	b.WriteString(fmt.Sprintf("  static const int pageLimit = %d;\n", pageLimit))
	b.WriteString(fmt.Sprintf("  static const int syncMessagesLimit = %d;\n", operationDefaultLimit("SyncMessages", pageLimit)))
	b.WriteString(fmt.Sprintf("  static const int userCirclesLimit = %d;\n", operationDefaultLimit("ListUserCircles", pageLimit)))
	b.WriteString("  static const int callMaxParticipants = 32;\n")
	b.WriteString("}\n")
	return b.String()
}

func renderDomainAPIMetadataDart(domain string, routes []routeDef) string {
	var b strings.Builder
	className := toDartExportedName(domain) + "ApiMetadata"
	hasPathParams := false
	b.WriteString(fmt.Sprintf("// Code generated by tools/codegen_app_metadata from %s domain service.yaml files. DO NOT EDIT.\n\n", domain))
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("import 'dart:core';\n\n")
	b.WriteString(fmt.Sprintf("class %s {\n", className))
	b.WriteString(fmt.Sprintf("  const %s._();\n\n", className))
	b.WriteString(fmt.Sprintf("  static const String domain = '%s';\n", domain))
	prefixes := collectRoutePrefixes(routes)
	b.WriteString("  static const List<String> apiPrefixes = <String>[\n")
	for _, prefix := range prefixes {
		b.WriteString(fmt.Sprintf("    '%s',\n", prefix))
	}
	b.WriteString("  ];\n\n")
	b.WriteString("  static const Map<String, String> operationToPathTemplate = <String, String>{\n")
	for _, route := range routes {
		b.WriteString(fmt.Sprintf("    '%s': '%s',\n", route.Operation, route.Path))
	}
	b.WriteString("  };\n\n")
	b.WriteString("  static const Map<String, String> operationToMethod = <String, String>{\n")
	for _, route := range routes {
		b.WriteString(fmt.Sprintf("    '%s': '%s',\n", route.Operation, strings.ToUpper(route.Method)))
	}
	b.WriteString("  };\n\n")
	for _, route := range routes {
		identifier := lowerCamel(route.Operation)
		b.WriteString(fmt.Sprintf("  static const String %sOperation = '%s';\n", identifier, route.Operation))
	}
	b.WriteString("\n")
	for _, route := range routes {
		identifier := lowerCamel(route.Operation)
		params := extractPathParams(route.Path)
		if len(params) == 0 {
			b.WriteString(fmt.Sprintf("  static const String %sPath = '%s';\n", identifier, route.Path))
			continue
		}
		hasPathParams = true
		b.WriteString(fmt.Sprintf("  static const String %sPathTemplate = '%s';\n", identifier, route.Path))
		b.WriteString(fmt.Sprintf("  static String %sPath({", identifier))
		for idx, param := range params {
			if idx > 0 {
				b.WriteString(", ")
			}
			b.WriteString(fmt.Sprintf("required String %s", param))
		}
		b.WriteString("}) {\n")
		b.WriteString(fmt.Sprintf("    return _fillPath(%sPathTemplate, <String, String>{\n", identifier))
		for _, param := range params {
			b.WriteString(fmt.Sprintf("      '%s': %s,\n", param, param))
		}
		b.WriteString("    });\n")
		b.WriteString("  }\n")
	}
	if hasPathParams {
		b.WriteString("\n  static String _fillPath(String template, Map<String, String> params) {\n")
		b.WriteString("    var path = template;\n")
		b.WriteString("    params.forEach((key, value) {\n")
		b.WriteString("      path = path.replaceAll('{$key}', Uri.encodeComponent(value));\n")
		b.WriteString("    });\n")
		b.WriteString("    return path;\n")
		b.WriteString("  }\n")
	}
	b.WriteString("}\n")
	return b.String()
}

func renderAppUISurfacesDart(surfaces []uiSurfaceDef) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from _shared/ui_surfaces.yaml. DO NOT EDIT.\n\n")
	b.WriteString("class AppUiSurface {\n")
	b.WriteString("  const AppUiSurface({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.owner,\n")
	b.WriteString("    required this.routeId,\n")
	b.WriteString("    required this.pathTemplate,\n")
	b.WriteString("    required this.description,\n")
	b.WriteString("    required this.operationIds,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String owner;\n")
	b.WriteString("  final String routeId;\n")
	b.WriteString("  final String pathTemplate;\n")
	b.WriteString("  final String description;\n")
	b.WriteString("  final List<String> operationIds;\n")
	b.WriteString("}\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class AppUiSurfaces {\n")
	b.WriteString("  const AppUiSurfaces._();\n\n")
	for _, surface := range surfaces {
		description := strings.ReplaceAll(surface.Description, "'", "\\'")
		b.WriteString(fmt.Sprintf("  static const AppUiSurface %s = AppUiSurface(\n", surface.ID))
		b.WriteString(fmt.Sprintf("    id: '%s',\n", surface.ID))
		b.WriteString(fmt.Sprintf("    owner: '%s',\n", surface.Owner))
		b.WriteString(fmt.Sprintf("    routeId: '%s',\n", surface.RouteID))
		b.WriteString(fmt.Sprintf("    pathTemplate: '%s',\n", surface.PathTemplate))
		b.WriteString(fmt.Sprintf("    description: '%s',\n", description))
		b.WriteString("    operationIds: <String>[\n")
		for _, operationID := range surface.OperationIDs {
			b.WriteString(fmt.Sprintf("      '%s',\n", operationID))
		}
		b.WriteString("    ],\n")
		b.WriteString("  );\n\n")
	}
	b.WriteString("  static const List<AppUiSurface> all = <AppUiSurface>[\n")
	for _, surface := range surfaces {
		b.WriteString(fmt.Sprintf("    %s,\n", surface.ID))
	}
	b.WriteString("  ];\n\n")
	b.WriteString("  static const Map<String, AppUiSurface> byId = <String, AppUiSurface>{\n")
	for _, surface := range surfaces {
		b.WriteString(fmt.Sprintf("    '%s': %s,\n", surface.ID, surface.ID))
	}
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}

func renderDomainRequestPageIDsDart(domain string, routes []routeDef) string {
	var b strings.Builder
	className := toDartExportedName(domain) + "RequestPageIds"
	b.WriteString(fmt.Sprintf("// Code generated by tools/codegen_app_metadata from %s domain service.yaml files. DO NOT EDIT.\n\n", domain))
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString(fmt.Sprintf("class %s {\n", className))
	b.WriteString(fmt.Sprintf("  const %s._();\n\n", className))
	b.WriteString("  static const Map<String, String> operationToPageId = <String, String>{\n")
	for _, route := range routes {
		b.WriteString(fmt.Sprintf("    '%s': '%s',\n", route.Operation, resolvePageID(domain, route.Operation)))
	}
	b.WriteString("  };\n\n")
	for _, route := range routes {
		b.WriteString(fmt.Sprintf("  static const String %s = '%s';\n", lowerCamel(route.Operation), resolvePageID(domain, route.Operation)))
	}
	b.WriteString("}\n")
	return b.String()
}

func renderStandaloneRequestPageIDsDart(pageIDs map[string]string) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from _shared/request_context.yaml. DO NOT EDIT.\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class AppRequestPageIds {\n")
	b.WriteString("  const AppRequestPageIds._();\n\n")
	b.WriteString("  static const Map<String, String> ids = <String, String>{\n")
	writeSortedStringMap(&b, pageIDs)
	b.WriteString("  };\n\n")
	keys := make([]string, 0, len(pageIDs))
	for key := range pageIDs {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		b.WriteString(fmt.Sprintf("  static const String %s = '%s';\n", key, pageIDs[key]))
	}
	b.WriteString("}\n")
	return b.String()
}

func renderAppRoutePathsDart(routes []appRouteDef) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from _shared/app_routes.yaml. DO NOT EDIT.\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class AppRoutePaths {\n")
	b.WriteString("  const AppRoutePaths._();\n\n")
	for _, route := range routes {
		if strings.TrimSpace(route.ID) == "" || strings.TrimSpace(route.Path) == "" {
			continue
		}
		identifier := route.ID
		params := extractPathParams(route.Path)
		segment := routeSegment(route.Path)
		if len(params) == 0 && len(route.QueryParams) == 0 {
			b.WriteString(fmt.Sprintf("  static const String %s = '%s';\n", identifier, route.Path))
		} else {
			b.WriteString(fmt.Sprintf("  static const String %sPathTemplate = '%s';\n", identifier, route.Path))
			b.WriteString(fmt.Sprintf("  static String %s({", identifier))
			args := []string{}
			for _, param := range params {
				args = append(args, fmt.Sprintf("required String %s", param))
			}
			for _, query := range route.QueryParams {
				args = append(args, fmt.Sprintf("String? %s", query))
			}
			b.WriteString(strings.Join(args, ", "))
			b.WriteString("}) {\n")
			b.WriteString(fmt.Sprintf("    return _buildPath(%sPathTemplate, <String, String>{\n", identifier))
			for _, param := range params {
				b.WriteString(fmt.Sprintf("      '%s': %s,\n", param, param))
			}
			b.WriteString("    }, <String, String?>{\n")
			for _, query := range route.QueryParams {
				b.WriteString(fmt.Sprintf("      '%s': %s,\n", query, query))
			}
			b.WriteString("    });\n")
			b.WriteString("  }\n")
		}
		if segment != "" {
			b.WriteString(fmt.Sprintf("  static const String %sSegment = '%s';\n", identifier, segment))
		}
		b.WriteString("\n")
	}
	b.WriteString("  static String _buildPath(String template, Map<String, String> params, Map<String, String?> query) {\n")
	b.WriteString("    var path = template;\n")
	b.WriteString("    params.forEach((key, value) {\n")
	b.WriteString("      path = path.replaceAll('{$key}', Uri.encodeComponent(value));\n")
	b.WriteString("    });\n")
	b.WriteString("    final qp = <String, String>{};\n")
	b.WriteString("    query.forEach((key, value) {\n")
	b.WriteString("      if (value != null && value.isNotEmpty) qp[key] = value;\n")
	b.WriteString("    });\n")
	b.WriteString("    return qp.isEmpty ? path : Uri(path: path, queryParameters: qp).toString();\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

func renderSearchContractDart(contract *searchContractFile) string {
	var b strings.Builder
	allSearchToolFields := mergeUniqueStringLists(
		contract.ToolContract.RequiredFields,
		contract.ToolContract.OptionalFields,
		contract.ToolContract.InternalOptionalFields,
	)
	b.WriteString("// Code generated by tools/codegen_app_metadata from _shared/search_contract.yaml. DO NOT EDIT.\n\n")
	b.WriteString("enum SearchMode {\n")
	for _, item := range contract.Modes {
		b.WriteString(fmt.Sprintf("  %s('%s'),\n", toDartValueName(item.ID), item.ID))
	}
	b.WriteString("  ;\n\n")
	b.WriteString("  const SearchMode(this.wireValue);\n\n")
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString("  static SearchMode fromWire(String? value) {\n")
	b.WriteString("    switch ((value ?? '').trim()) {\n")
	for _, item := range contract.Modes {
		b.WriteString(fmt.Sprintf("      case '%s':\n", item.ID))
		b.WriteString(fmt.Sprintf("        return SearchMode.%s;\n", toDartValueName(item.ID)))
	}
	defaultMode := "suggest"
	if len(contract.Modes) > 0 {
		defaultMode = toDartValueName(contract.Modes[0].ID)
	}
	b.WriteString("      default:\n")
	b.WriteString(fmt.Sprintf("        return SearchMode.%s;\n", defaultMode))
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	b.WriteString("enum SearchExecutionStrategy {\n")
	for _, item := range contract.ExecutionStrategies {
		b.WriteString(fmt.Sprintf("  %s('%s'),\n", toDartValueName(item.ID), item.ID))
	}
	b.WriteString("  ;\n\n")
	b.WriteString("  const SearchExecutionStrategy(this.wireValue);\n\n")
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString("  static SearchExecutionStrategy fromWire(String? value) {\n")
	b.WriteString("    switch ((value ?? '').trim()) {\n")
	for _, item := range contract.ExecutionStrategies {
		b.WriteString(fmt.Sprintf("      case '%s':\n", item.ID))
		b.WriteString(fmt.Sprintf("        return SearchExecutionStrategy.%s;\n", toDartValueName(item.ID)))
	}
	defaultStrategy := "remoteOnly"
	if len(contract.ExecutionStrategies) > 0 {
		defaultStrategy = toDartValueName(contract.ExecutionStrategies[0].ID)
	}
	b.WriteString("      default:\n")
	b.WriteString(fmt.Sprintf("        return SearchExecutionStrategy.%s;\n", defaultStrategy))
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	b.WriteString("enum SearchResolvedFrom {\n")
	for _, item := range contract.ResolvedSources {
		b.WriteString(fmt.Sprintf("  %s('%s'),\n", toDartValueName(item.ID), item.ID))
	}
	b.WriteString("  ;\n\n")
	b.WriteString("  const SearchResolvedFrom(this.wireValue);\n\n")
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString("  static SearchResolvedFrom fromWire(String? value) {\n")
	b.WriteString("    switch ((value ?? '').trim()) {\n")
	for _, item := range contract.ResolvedSources {
		b.WriteString(fmt.Sprintf("      case '%s':\n", item.ID))
		b.WriteString(fmt.Sprintf("        return SearchResolvedFrom.%s;\n", toDartValueName(item.ID)))
	}
	defaultSource := "remote"
	if len(contract.ResolvedSources) > 0 {
		defaultSource = toDartValueName(contract.ResolvedSources[0].ID)
	}
	b.WriteString("      default:\n")
	b.WriteString(fmt.Sprintf("        return SearchResolvedFrom.%s;\n", defaultSource))
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	b.WriteString("enum SearchConversationType {\n")
	for _, item := range contract.ConversationTypes {
		b.WriteString(fmt.Sprintf("  %s('%s'),\n", toDartValueName(item.ID), item.ID))
	}
	b.WriteString("  ;\n\n")
	b.WriteString("  const SearchConversationType(this.wireValue);\n\n")
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString("  static SearchConversationType? fromWire(String? value) {\n")
	b.WriteString("    switch ((value ?? '').trim()) {\n")
	for _, item := range contract.ConversationTypes {
		b.WriteString(fmt.Sprintf("      case '%s':\n", item.ID))
		b.WriteString(fmt.Sprintf("        return SearchConversationType.%s;\n", toDartValueName(item.ID)))
	}
	b.WriteString("      default:\n")
	b.WriteString("        return null;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	b.WriteString("enum SearchToolContentType {\n")
	for _, item := range contract.ContentTypeFilters {
		b.WriteString(fmt.Sprintf("  %s('%s'),\n", toDartValueName(item.ID), item.ID))
	}
	b.WriteString("  ;\n\n")
	b.WriteString("  const SearchToolContentType(this.wireValue);\n\n")
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString("  static SearchToolContentType? fromWire(String? value) {\n")
	b.WriteString("    switch ((value ?? '').trim()) {\n")
	for _, item := range contract.ContentTypeFilters {
		b.WriteString(fmt.Sprintf("      case '%s':\n", item.ID))
		b.WriteString(fmt.Sprintf("        return SearchToolContentType.%s;\n", toDartValueName(item.ID)))
	}
	b.WriteString("      default:\n")
	b.WriteString("        return null;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class SearchContractDefaults {\n")
	b.WriteString("  const SearchContractDefaults._();\n\n")
	b.WriteString(fmt.Sprintf("  static const int suggestLimit = %d;\n", contract.Defaults.SuggestLimit))
	b.WriteString(fmt.Sprintf("  static const int resultLimit = %d;\n", contract.Defaults.ResultLimit))
	b.WriteString(fmt.Sprintf("  static const int assistantLimit = %d;\n", contract.Defaults.AssistantLimit))
	b.WriteString("}\n\n")

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class SearchToolFieldNames {\n")
	b.WriteString("  const SearchToolFieldNames._();\n\n")
	for _, field := range allSearchToolFields {
		b.WriteString(fmt.Sprintf("  static const String %s = '%s';\n", toDartFieldName(field), escapeDartString(field)))
	}
	b.WriteString("}\n\n")

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class SearchToolContract {\n")
	b.WriteString("  const SearchToolContract._();\n\n")
	b.WriteString(fmt.Sprintf("  static const String name = '%s';\n", escapeDartString(contract.ToolContract.Name)))
	b.WriteString(fmt.Sprintf("  static const String description = '%s';\n", escapeDartString(contract.ToolContract.Description)))
	b.WriteString(fmt.Sprintf("  static const List<String> requiredFields = %s;\n", renderStringListLiteral(contract.ToolContract.RequiredFields)))
	b.WriteString(fmt.Sprintf("  static const List<String> optionalFields = %s;\n", renderStringListLiteral(contract.ToolContract.OptionalFields)))
	b.WriteString(fmt.Sprintf("  static const List<String> internalOptionalFields = %s;\n", renderStringListLiteral(contract.ToolContract.InternalOptionalFields)))
	b.WriteString(fmt.Sprintf("  static const List<String> conversationTypes = %s;\n", renderSearchNamedValuesLiteral(contract.ConversationTypes)))
	b.WriteString(fmt.Sprintf("  static const List<String> contentTypes = %s;\n", renderSearchNamedValuesLiteral(contract.ContentTypeFilters)))
	b.WriteString("  static const List<String> allFields = <String>[\n")
	b.WriteString("    ...requiredFields,\n")
	b.WriteString("    ...optionalFields,\n")
	b.WriteString("    ...internalOptionalFields,\n")
	b.WriteString("  ];\n")
	b.WriteString("}\n")
	return b.String()
}

func renderSearchRegistryDart(objects *searchObjectsFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from _shared/search_objects.yaml. DO NOT EDIT.\n\n")
	b.WriteString("import 'search_contract.g.dart';\n\n")
	b.WriteString("enum SearchObjectType {\n")
	for _, item := range objects.ObjectTypes {
		b.WriteString(fmt.Sprintf("  %s('%s'),\n", toDartValueName(item.ID), item.ID))
	}
	b.WriteString("  ;\n\n")
	b.WriteString("  const SearchObjectType(this.wireValue);\n\n")
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString("  static SearchObjectType? fromWire(String? value) {\n")
	b.WriteString("    switch ((value ?? '').trim()) {\n")
	for _, item := range objects.ObjectTypes {
		b.WriteString(fmt.Sprintf("      case '%s':\n", item.ID))
		b.WriteString(fmt.Sprintf("        return SearchObjectType.%s;\n", toDartValueName(item.ID)))
	}
	b.WriteString("      default:\n")
	b.WriteString("        return null;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	b.WriteString("class SearchObjectRegistryEntry {\n")
	b.WriteString("  const SearchObjectRegistryEntry({\n")
	b.WriteString("    required this.type,\n")
	b.WriteString("    required this.label,\n")
	b.WriteString("    required this.domain,\n")
	b.WriteString("    required this.executionStrategy,\n")
	b.WriteString("    required this.provider,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final SearchObjectType type;\n")
	b.WriteString("  final String label;\n")
	b.WriteString("  final String domain;\n")
	b.WriteString("  final SearchExecutionStrategy executionStrategy;\n")
	b.WriteString("  final String provider;\n")
	b.WriteString("}\n\n")

	b.WriteString("class SearchSectionRegistryEntry {\n")
	b.WriteString("  const SearchSectionRegistryEntry({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.title,\n")
	b.WriteString("    required this.defaultObjectTypes,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String title;\n")
	b.WriteString("  final List<SearchObjectType> defaultObjectTypes;\n")
	b.WriteString("}\n\n")

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class SearchRegistry {\n")
	b.WriteString("  const SearchRegistry._();\n\n")
	b.WriteString("  static const List<SearchObjectRegistryEntry> objectTypes = <SearchObjectRegistryEntry>[\n")
	for _, item := range objects.ObjectTypes {
		b.WriteString("    SearchObjectRegistryEntry(\n")
		b.WriteString(fmt.Sprintf("      type: SearchObjectType.%s,\n", toDartValueName(item.ID)))
		b.WriteString(fmt.Sprintf("      label: '%s',\n", escapeDartString(item.Label)))
		b.WriteString(fmt.Sprintf("      domain: '%s',\n", escapeDartString(item.Domain)))
		b.WriteString(fmt.Sprintf("      executionStrategy: SearchExecutionStrategy.%s,\n", toDartValueName(item.ExecutionStrategy)))
		b.WriteString(fmt.Sprintf("      provider: '%s',\n", escapeDartString(item.Provider)))
		b.WriteString("    ),\n")
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<SearchSectionRegistryEntry> sections = <SearchSectionRegistryEntry>[\n")
	for _, item := range objects.SectionKinds {
		b.WriteString("    SearchSectionRegistryEntry(\n")
		b.WriteString(fmt.Sprintf("      id: '%s',\n", escapeDartString(item.ID)))
		b.WriteString(fmt.Sprintf("      title: '%s',\n", escapeDartString(item.Title)))
		b.WriteString(fmt.Sprintf("      defaultObjectTypes: %s,\n", renderSearchObjectTypesLiteral(item.DefaultObjectTypes)))
		b.WriteString("    ),\n")
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static SearchObjectRegistryEntry? entryFor(SearchObjectType type) {\n")
	b.WriteString("    for (final entry in objectTypes) {\n")
	b.WriteString("      if (entry.type == type) {\n")
	b.WriteString("        return entry;\n")
	b.WriteString("      }\n")
	b.WriteString("    }\n")
	b.WriteString("    return null;\n")
	b.WriteString("  }\n\n")

	b.WriteString("  static SearchSectionRegistryEntry? sectionById(String id) {\n")
	b.WriteString("    for (final section in sections) {\n")
	b.WriteString("      if (section.id == id) {\n")
	b.WriteString("        return section;\n")
	b.WriteString("      }\n")
	b.WriteString("    }\n")
	b.WriteString("    return null;\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

// renderContentMetadataDart generates the legacy metadata constants file
// (renamed from post_runtime_metadata.g.dart → content_metadata.g.dart).
func renderContentMetadataDart(
	postDefaults map[string]string,
	feedDefaults map[string]string,
	contentTypeMapping map[string]string,
	feedCategoryToType map[string]string,
	appTabToCategory map[string]string,
	feedRoute routeDef,
	getPostRoute routeDef,
	recommendRoute routeDef,
	feedDefaultLimit int,
	writableFields []string,
	likeRoutes map[string]string,
) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class GeneratedPostRuntimeMetadata {\n")
	b.WriteString("  const GeneratedPostRuntimeMetadata._();\n\n")

	b.WriteString("  // Field defaults derived from post/fields.yaml constraints.\n")
	b.WriteString("  static const Map<String, dynamic> postFieldDefaults = <String, dynamic>{\n")
	writeSortedMap(&b, postDefaults)
	b.WriteString("  };\n\n")

	b.WriteString("  // Legacy feed projection defaults (use FeedItemDto for new code).\n")
	b.WriteString("  static const Map<String, dynamic> feedProjectionDefaults = <String, dynamic>{\n")
	writeSortedMap(&b, feedDefaults)
	b.WriteString("  };\n\n")

	b.WriteString("  static const Map<String, String> contentTypeToRenderType = <String, String>{\n")
	writeSortedStringMap(&b, contentTypeMapping)
	b.WriteString("  };\n\n")

	b.WriteString("  static const Map<String, String> feedCategoryToRequestType = <String, String>{\n")
	writeSortedStringMap(&b, feedCategoryToType)
	b.WriteString("  };\n\n")

	b.WriteString("  static const Map<String, String> appTabToFeedCategory = <String, String>{\n")
	writeSortedStringMap(&b, appTabToCategory)
	b.WriteString("  };\n\n")

	b.WriteString(fmt.Sprintf("  static const int feedDefaultLimit = %d;\n\n", feedDefaultLimit))
	b.WriteString(fmt.Sprintf("  static const String feedPath = '%s';\n", nonEmpty(feedRoute.Path, "/v1/content/feed")))
	b.WriteString(fmt.Sprintf("  static const String postDetailPathTemplate = '%s';\n", nonEmpty(getPostRoute.Path, "/v1/content/posts/{postId}")))
	b.WriteString(fmt.Sprintf("  static const String recommendPath = '%s';\n\n", nonEmpty(recommendRoute.Path, "/v1/content/recommend")))

	b.WriteString("  static const List<String> feedQueryParams = <String>[\n")
	for _, key := range feedRoute.QueryParams {
		b.WriteString(fmt.Sprintf("    '%s',\n", key))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<String> createWritableFields = <String>[\n")
	for _, f := range writableFields {
		b.WriteString(fmt.Sprintf("    '%s',\n", f))
	}
	b.WriteString("  ];\n\n")

	// Mutation route paths (like/save)
	if len(likeRoutes) > 0 {
		b.WriteString("  // Reaction mutation route paths (from post/service.yaml).\n")
		b.WriteString("  static const Map<String, String> reactionRoutePaths = <String, String>{\n")
		writeSortedStringMap(&b, likeRoutes)
		b.WriteString("  };\n")
	}

	b.WriteString("}\n")
	return b.String()
}

// renderStandaloneDtoDart generates a standalone DTO (no base class) from client_projection.
// Used for integration/location LocationPoiDto etc.
func renderStandaloneDtoDart(proj clientProjection, sourcePath string) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("// Code generated by tools/codegen_app_metadata from %s. DO NOT EDIT.\n", sourcePath))
	b.WriteString("// ignore_for_file: prefer_const_constructors, unnecessary_null_in_if_null_operators\n\n")

	className := proj.DartClass
	if className == "" {
		className = "Dto"
	}
	b.WriteString(fmt.Sprintf("class %s {\n", className))
	for _, f := range proj.Fields {
		dartType := normalizeDartType(f.DartType)
		if f.Nullable && !strings.HasSuffix(dartType, "?") {
			dartType += "?"
		}
		b.WriteString(fmt.Sprintf("  final %s %s;\n", dartType, f.Name))
	}
	b.WriteString("\n  const " + className + "({\n")
	for _, f := range proj.Fields {
		if f.Nullable {
			b.WriteString(fmt.Sprintf("    this.%s,\n", f.Name))
		} else {
			b.WriteString(fmt.Sprintf("    required this.%s,\n", f.Name))
		}
	}
	b.WriteString("  });\n\n")
	b.WriteString(fmt.Sprintf("  factory %s.fromMap(Map<String, dynamic> m) {\n", className))
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, f := range proj.Fields {
		b.WriteString(fmt.Sprintf("      %s: %s,\n", f.Name, buildAliasResolver(f)))
	}
	b.WriteString("    );\n  }\n\n")
	b.WriteString("  Map<String, dynamic> toMap() {\n    return <String, dynamic>{\n")
	for _, f := range proj.Fields {
		b.WriteString(fmt.Sprintf("      '%s': %s,\n", f.Name, f.Name))
	}
	b.WriteString("    };\n  }\n\n")

	b.WriteString(fmt.Sprintf("  %s copyWith({\n", className))
	for _, f := range proj.Fields {
		dartType := normalizeDartType(f.DartType)
		if !strings.HasSuffix(dartType, "?") {
			dartType += "?"
		}
		b.WriteString(fmt.Sprintf("    %s %s,\n", dartType, f.Name))
	}
	b.WriteString("  }) {\n")
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, f := range proj.Fields {
		b.WriteString(fmt.Sprintf("      %s: %s ?? this.%s,\n", f.Name, f.Name, f.Name))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n")

	if len(proj.ComputedGetters) > 0 {
		b.WriteString("\n")
		for _, g := range proj.ComputedGetters {
			returnType := strings.TrimSpace(g.DartReturnType)
			body := strings.TrimSpace(g.Body)
			if g.Description != "" {
				b.WriteString(fmt.Sprintf("  /// %s\n", g.Description))
			}
			b.WriteString(fmt.Sprintf("  %s get %s {\n", returnType, g.Name))
			for _, line := range strings.Split(body, "\n") {
				b.WriteString(fmt.Sprintf("    %s\n", strings.TrimSpace(line)))
			}
			b.WriteString("  }\n")
		}
	}

	b.WriteString("}\n\n")
	b.WriteString("DateTime? _parseDateTime(dynamic v) {\n")
	b.WriteString("  if (v == null) return null;\n")
	b.WriteString("  if (v is DateTime) return v;\n")
	b.WriteString("  if (v is String) return DateTime.tryParse(v);\n")
	b.WriteString("  return null;\n")
	b.WriteString("}\n\n")
	b.WriteString("List<String>? _parseStringList(dynamic v) {\n")
	b.WriteString("  if (v == null) return null;\n")
	b.WriteString("  if (v is List) return v.map((e) => e?.toString() ?? '').toList();\n")
	b.WriteString("  return null;\n")
	b.WriteString("}\n")
	return b.String()
}

// renderFeedItemDtoDart generates the strongly-typed FeedItemDto class
// from discovery_feed.yaml client_projection section.
func renderFeedItemDtoDart(proj clientProjection) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from content/post/projections/discovery_feed.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors, unnecessary_null_in_if_null_operators\n\n")

	className := proj.DartClass
	if className == "" {
		className = "FeedItemDto"
	}

	// Class declaration
	b.WriteString(fmt.Sprintf("class %s {\n", className))

	// Fields
	for _, f := range proj.Fields {
		dartType := normalizeDartType(f.DartType)
		if f.Nullable && !strings.HasSuffix(dartType, "?") {
			dartType += "?"
		}
		b.WriteString(fmt.Sprintf("  final %s %s;\n", dartType, f.Name))
	}
	b.WriteString("\n")

	// Constructor
	b.WriteString(fmt.Sprintf("  const %s({\n", className))
	for _, f := range proj.Fields {
		if f.Nullable {
			b.WriteString(fmt.Sprintf("    this.%s,\n", f.Name))
		} else {
			b.WriteString(fmt.Sprintf("    required this.%s,\n", f.Name))
		}
	}
	b.WriteString("  });\n\n")

	// fromMap factory with alias resolver
	b.WriteString(fmt.Sprintf("  factory %s.fromMap(Map<String, dynamic> m) {\n", className))
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, f := range proj.Fields {
		resolver := buildAliasResolver(f)
		b.WriteString(fmt.Sprintf("      %s: %s,\n", f.Name, resolver))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n\n")

	// toMap
	b.WriteString("  Map<String, dynamic> toMap() {\n")
	b.WriteString("    return <String, dynamic>{\n")
	for _, f := range proj.Fields {
		b.WriteString(fmt.Sprintf("      '%s': %s,\n", f.Name, f.Name))
	}
	b.WriteString("    };\n")
	b.WriteString("  }\n\n")

	// copyWith
	b.WriteString(fmt.Sprintf("  %s copyWith({\n", className))
	for _, f := range proj.Fields {
		dartType := normalizeDartType(f.DartType)
		if !strings.HasSuffix(dartType, "?") {
			dartType += "?"
		}
		b.WriteString(fmt.Sprintf("    %s %s,\n", dartType, f.Name))
	}
	b.WriteString("  }) {\n")
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, f := range proj.Fields {
		b.WriteString(fmt.Sprintf("      %s: %s ?? this.%s,\n", f.Name, f.Name, f.Name))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n")

	if len(proj.ComputedGetters) > 0 {
		b.WriteString("\n")
		for _, g := range proj.ComputedGetters {
			returnType := strings.TrimSpace(g.DartReturnType)
			body := strings.TrimSpace(g.Body)
			if g.Description != "" {
				b.WriteString(fmt.Sprintf("  /// %s\n", g.Description))
			}
			if shouldAnnotateOverrideForComputedGetter(proj.BaseClass, g.Name) {
				b.WriteString("  @override\n")
			}
			b.WriteString(fmt.Sprintf("  %s get %s {\n", returnType, g.Name))
			for _, line := range strings.Split(body, "\n") {
				b.WriteString(fmt.Sprintf("    %s\n", strings.TrimSpace(line)))
			}
			b.WriteString("  }\n")
		}
	}

	b.WriteString("}\n\n")

	// Helper functions used by fromMap
	b.WriteString("DateTime? _parseDateTime(dynamic v) {\n")
	b.WriteString("  if (v == null) return null;\n")
	b.WriteString("  if (v is DateTime) return v;\n")
	b.WriteString("  if (v is String) return DateTime.tryParse(v);\n")
	b.WriteString("  return null;\n")
	b.WriteString("}\n\n")

	b.WriteString("List<String>? _parseStringList(dynamic v) {\n")
	b.WriteString("  if (v == null) return null;\n")
	b.WriteString("  if (v is List) return v.map((e) => e?.toString() ?? '').toList();\n")
	b.WriteString("  return null;\n")
	b.WriteString("}\n")

	return b.String()
}

// postBaseDtoFields lists the getter names declared in PostBaseDto (the hand-written base class).
// Fields in this set will receive an @override annotation in generated typed DTOs.
var postBaseDtoFields = map[string]bool{
	"id":                  true,
	"type":                true,
	"identity":            true,
	"authorId":            true,
	"displayName":         true,
	"avatarUrl":           true,
	"authorBackgroundUrl": true,
	"assistantUsePolicy":  true,
	"likeCount":           true,
	"commentCount":        true,
	"favoriteCount":       true,
	"shareCount":          true,
	"createdAt":           true,
}

var postBaseDtoComputedGetters = map[string]bool{
	"displayFormat": true,
}

func shouldAnnotateOverrideForComputedGetter(baseClass, getterName string) bool {
	if strings.TrimSpace(baseClass) != "PostBaseDto" {
		return false
	}
	return postBaseDtoComputedGetters[strings.TrimSpace(getterName)]
}

// renderTypedPostDtoDart generates a typed DTO that extends a base class (e.g. PostBaseDto).
func renderTypedPostDtoDart(proj clientProjection, sourceFile string) string {
	var b strings.Builder
	className := proj.DartClass
	baseClass := proj.BaseClass

	b.WriteString(fmt.Sprintf("// Code generated by tools/codegen_app_metadata from content/post/projections/%s. DO NOT EDIT.\n", sourceFile))
	b.WriteString("// ignore_for_file: prefer_const_constructors, unnecessary_null_in_if_null_operators\n\n")
	if baseClass != "" {
		b.WriteString("import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';\n\n")
	}

	// Class declaration with base class
	b.WriteString(fmt.Sprintf("class %s extends %s {\n", className, baseClass))

	// Fields
	for _, f := range proj.Fields {
		dartType := normalizeDartType(f.DartType)
		if f.Nullable && !strings.HasSuffix(dartType, "?") {
			dartType += "?"
		}
		if postBaseDtoFields[f.Name] {
			b.WriteString(fmt.Sprintf("  @override final %s %s;\n", dartType, f.Name))
		} else {
			b.WriteString(fmt.Sprintf("  final %s %s;\n", dartType, f.Name))
		}
	}
	b.WriteString("\n")

	// Constructor
	b.WriteString(fmt.Sprintf("  const %s({\n", className))
	for _, f := range proj.Fields {
		if f.Nullable {
			b.WriteString(fmt.Sprintf("    this.%s,\n", f.Name))
		} else {
			b.WriteString(fmt.Sprintf("    required this.%s,\n", f.Name))
		}
	}
	b.WriteString("  });\n\n")

	// fromMap factory
	b.WriteString(fmt.Sprintf("  factory %s.fromMap(Map<String, dynamic> m) {\n", className))
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, f := range proj.Fields {
		resolver := buildAliasResolver(f)
		b.WriteString(fmt.Sprintf("      %s: %s,\n", f.Name, resolver))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n\n")

	// toMap override
	b.WriteString("  @override\n")
	b.WriteString("  Map<String, dynamic> toMap() {\n")
	b.WriteString("    return <String, dynamic>{\n")
	for _, f := range proj.Fields {
		b.WriteString(fmt.Sprintf("      '%s': %s,\n", f.Name, f.Name))
	}
	b.WriteString("    };\n")
	b.WriteString("  }\n\n")

	// copyWith
	b.WriteString(fmt.Sprintf("  %s copyWith({\n", className))
	for _, f := range proj.Fields {
		dartType := normalizeDartType(f.DartType)
		if !strings.HasSuffix(dartType, "?") {
			dartType += "?"
		}
		b.WriteString(fmt.Sprintf("    %s %s,\n", dartType, f.Name))
	}
	b.WriteString("  }) {\n")
	b.WriteString(fmt.Sprintf("    return %s(\n", className))
	for _, f := range proj.Fields {
		b.WriteString(fmt.Sprintf("      %s: %s ?? this.%s,\n", f.Name, f.Name, f.Name))
	}
	b.WriteString("    );\n")
	b.WriteString("  }\n")

	// Computed getters
	if len(proj.ComputedGetters) > 0 {
		b.WriteString("\n")
		for _, g := range proj.ComputedGetters {
			returnType := strings.TrimSpace(g.DartReturnType)
			body := strings.TrimSpace(g.Body)
			if g.Description != "" {
				b.WriteString(fmt.Sprintf("  /// %s\n", g.Description))
			}
			if shouldAnnotateOverrideForComputedGetter(baseClass, g.Name) {
				b.WriteString("  @override\n")
			}
			b.WriteString(fmt.Sprintf("  %s get %s {\n", returnType, g.Name))
			for _, line := range strings.Split(body, "\n") {
				b.WriteString(fmt.Sprintf("    %s\n", strings.TrimSpace(line)))
			}
			b.WriteString("  }\n")
		}
	}

	b.WriteString("}\n\n")

	// Helper functions used by fromMap (only if needed)
	needsDateTime := false
	needsStringList := false
	for _, f := range proj.Fields {
		dt := normalizeDartType(f.DartType)
		if dt == "DateTime" {
			needsDateTime = true
		}
		if dt == "List<String>" {
			needsStringList = true
		}
	}

	if needsDateTime {
		b.WriteString("DateTime? _parseDateTime(dynamic v) {\n")
		b.WriteString("  if (v == null) return null;\n")
		b.WriteString("  if (v is DateTime) return v;\n")
		b.WriteString("  if (v is String) return DateTime.tryParse(v);\n")
		b.WriteString("  return null;\n")
		b.WriteString("}\n\n")
	}
	if needsStringList {
		b.WriteString("List<String>? _parseStringList(dynamic v) {\n")
		b.WriteString("  if (v == null) return null;\n")
		b.WriteString("  if (v is List) return v.map((e) => e?.toString() ?? '').toList();\n")
		b.WriteString("  return null;\n")
		b.WriteString("}\n")
	}

	return b.String()
}

// buildAliasResolver generates the fromMap expression for a single field,
// trying each alias key in order until a non-null value is found.
func buildAliasResolver(f projectionFieldDef) string {
	dartType := normalizeDartType(f.DartType)
	defaultVal := f.Default
	if defaultVal == "" {
		if f.Nullable {
			defaultVal = "null"
		} else {
			defaultVal = defaultForType(dartType)
		}
	}

	allKeys := []string{f.Source}
	for _, a := range f.Aliases {
		if a != f.Source {
			allKeys = append(allKeys, a)
		}
	}
	// deduplicate
	seen := map[string]bool{}
	deduped := []string{}
	for _, k := range allKeys {
		if !seen[k] {
			seen[k] = true
			deduped = append(deduped, k)
		}
	}

	switch dartType {
	case "String":
		parts := make([]string, len(deduped))
		for i, k := range deduped {
			parts[i] = fmt.Sprintf("m['%s']?.toString()", k)
		}
		return strings.Join(parts, " ?? ") + fmt.Sprintf(" ?? %s", defaultVal)

	case "int":
		parts := make([]string, len(deduped))
		for i, k := range deduped {
			parts[i] = fmt.Sprintf("(m['%s'] as num?)?.toInt()", k)
		}
		return strings.Join(parts, " ?? ") + fmt.Sprintf(" ?? %s", defaultVal)

	case "double":
		parts := make([]string, len(deduped))
		for i, k := range deduped {
			parts[i] = fmt.Sprintf("(m['%s'] as num?)?.toDouble()", k)
		}
		return strings.Join(parts, " ?? ") + fmt.Sprintf(" ?? %s", defaultVal)

	case "bool":
		parts := make([]string, len(deduped))
		for i, k := range deduped {
			parts[i] = fmt.Sprintf("m['%s'] as bool?", k)
		}
		return strings.Join(parts, " ?? ") + fmt.Sprintf(" ?? %s", defaultVal)

	case "DateTime":
		parts := make([]string, len(deduped))
		for i, k := range deduped {
			parts[i] = fmt.Sprintf("_parseDateTime(m['%s'])", k)
		}
		return strings.Join(parts, " ?? ") + fmt.Sprintf(" ?? %s", defaultVal)

	case "List<String>":
		parts := make([]string, len(deduped))
		for i, k := range deduped {
			parts[i] = fmt.Sprintf("_parseStringList(m['%s'])", k)
		}
		return strings.Join(parts, " ?? ") + fmt.Sprintf(" ?? %s", defaultVal)

	default:
		// fallback: raw cast
		if len(deduped) == 0 {
			return defaultVal
		}
		return fmt.Sprintf("m['%s'] as %s? ?? %s", deduped[0], dartType, defaultVal)
	}
}

func normalizeDartType(t string) string {
	t = strings.TrimSpace(t)
	t = strings.TrimSuffix(t, "?")
	return t
}

func defaultForType(dartType string) string {
	switch dartType {
	case "String":
		return "''"
	case "int":
		return "0"
	case "double":
		return "0.0"
	case "bool":
		return "false"
	case "List<String>":
		return "<String>[]"
	case "DateTime":
		return "DateTime(0)"
	default:
		return "null"
	}
}

// ── helpers ───────────────────────────────────────────────────────────────────

func writeFile(path string, content string) {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		exitErr(err)
	}
	fmt.Printf("generated: %s\n", path)
}

func nonEmpty(v, fallback string) string {
	if strings.TrimSpace(v) == "" {
		return fallback
	}
	return v
}

func dartStringLiteral(v string) string {
	return fmt.Sprintf("%q", v)
}

func dartStringOrNull(v string) string {
	if strings.TrimSpace(v) == "" {
		return "null"
	}
	return dartStringLiteral(v)
}

func dartDoubleLiteral(v float64, fallback float64) string {
	if v <= 0 {
		v = fallback
	}
	return strconv.FormatFloat(v, 'f', -1, 64)
}

func writeSortedMap[T ~string](b *strings.Builder, m map[string]T) {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		b.WriteString(fmt.Sprintf("    '%s': %s,\n", k, m[k]))
	}
}

func writeSortedStringMap(b *strings.Builder, m map[string]string) {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		b.WriteString(fmt.Sprintf("    '%s': '%s',\n", k, m[k]))
	}
}

func extractPathParams(path string) []string {
	start := -1
	params := []string{}
	for i, r := range path {
		switch r {
		case '{':
			start = i + 1
		case '}':
			if start > 0 && start <= i {
				params = append(params, path[start:i])
			}
			start = -1
		}
	}
	return params
}

func collectRoutePrefixes(routes []routeDef) []string {
	seen := map[string]bool{}
	prefixes := []string{}
	for _, route := range routes {
		parts := strings.Split(strings.Trim(route.Path, "/"), "/")
		if len(parts) < 2 {
			continue
		}
		prefix := "/" + parts[0] + "/" + parts[1]
		if seen[prefix] {
			continue
		}
		seen[prefix] = true
		prefixes = append(prefixes, prefix)
	}
	sort.Strings(prefixes)
	return prefixes
}

func routeSegment(path string) string {
	trimmed := strings.Trim(path, "/")
	if trimmed == "" {
		return ""
	}
	parts := strings.Split(trimmed, "/")
	return parts[len(parts)-1]
}

func toDartExportedName(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == '_' || r == '-' || r == '/' || r == ' '
	})
	var b strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		lower := strings.ToLower(part)
		b.WriteString(strings.ToUpper(lower[:1]))
		if len(lower) > 1 {
			b.WriteString(lower[1:])
		}
	}
	return b.String()
}

func lowerCamel(value string) string {
	parts := splitCamelCase(value)
	if len(parts) == 0 {
		return value
	}
	var b strings.Builder
	for idx, part := range parts {
		lower := strings.ToLower(part)
		if idx == 0 {
			b.WriteString(lower)
			continue
		}
		b.WriteString(strings.ToUpper(lower[:1]))
		if len(lower) > 1 {
			b.WriteString(lower[1:])
		}
	}
	return b.String()
}

func toDartValueName(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == '_' || r == '-' || r == '/' || r == ' ' || r == '.'
	})
	if len(parts) == 0 {
		return "value"
	}
	var b strings.Builder
	for idx, part := range parts {
		if part == "" {
			continue
		}
		lower := strings.ToLower(part)
		if idx == 0 {
			b.WriteString(lower)
			continue
		}
		b.WriteString(strings.ToUpper(lower[:1]))
		if len(lower) > 1 {
			b.WriteString(lower[1:])
		}
	}
	name := b.String()
	if name == "" {
		return "value"
	}
	first := rune(name[0])
	if first >= '0' && first <= '9' {
		return "v" + name
	}
	return name
}

func toDartFieldName(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return "field"
	}
	var b strings.Builder
	upperNext := false
	wroteAny := false
	for _, r := range trimmed {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			if !wroteAny {
				b.WriteRune(unicode.ToLower(r))
				wroteAny = true
				upperNext = false
				continue
			}
			if upperNext {
				b.WriteRune(unicode.ToUpper(r))
				upperNext = false
				continue
			}
			b.WriteRune(r)
			continue
		}
		if wroteAny {
			upperNext = true
		}
	}
	name := b.String()
	if name == "" {
		return "field"
	}
	first := rune(name[0])
	if first >= '0' && first <= '9' {
		return "f" + name
	}
	return name
}

func splitCamelCase(value string) []string {
	if value == "" {
		return nil
	}
	var parts []string
	var current strings.Builder
	for idx, r := range value {
		if idx > 0 && r >= 'A' && r <= 'Z' && current.Len() > 0 {
			parts = append(parts, current.String())
			current.Reset()
		}
		current.WriteRune(r)
	}
	if current.Len() > 0 {
		parts = append(parts, current.String())
	}
	return parts
}

func resolvePageID(domain string, operation string) string {
	if opMap, ok := sharedRequestContext.DomainOperationPageIDs[domain]; ok {
		if pageID, ok := opMap[operation]; ok {
			return pageID
		}
	}
	parts := splitCamelCase(operation)
	if len(parts) == 0 {
		return domain + "." + strings.ToLower(operation)
	}
	lowered := make([]string, 0, len(parts)+1)
	lowered = append(lowered, domain)
	for _, part := range parts {
		lowered = append(lowered, strings.ToLower(part))
	}
	return strings.Join(lowered, ".")
}

func escapeDartString(value string) string {
	return strings.ReplaceAll(value, "'", "\\'")
}

func renderStringListLiteral(items []string) string {
	if len(items) == 0 {
		return "const <String>[]"
	}
	var b strings.Builder
	b.WriteString("<String>[")
	for idx, item := range items {
		if idx > 0 {
			b.WriteString(", ")
		}
		b.WriteString(fmt.Sprintf("'%s'", escapeDartString(item)))
	}
	b.WriteString("]")
	return b.String()
}

func renderSearchNamedValuesLiteral(items []searchNamedValueDef) string {
	if len(items) == 0 {
		return "const <String>[]"
	}
	values := make([]string, 0, len(items))
	for _, item := range items {
		if strings.TrimSpace(item.ID) == "" {
			continue
		}
		values = append(values, item.ID)
	}
	return renderStringListLiteral(values)
}

func mergeUniqueStringLists(lists ...[]string) []string {
	out := make([]string, 0)
	seen := make(map[string]struct{})
	for _, list := range lists {
		for _, item := range list {
			trimmed := strings.TrimSpace(item)
			if trimmed == "" {
				continue
			}
			if _, exists := seen[trimmed]; exists {
				continue
			}
			seen[trimmed] = struct{}{}
			out = append(out, trimmed)
		}
	}
	return out
}

func renderSearchObjectTypesLiteral(items []string) string {
	if len(items) == 0 {
		return "const <SearchObjectType>[]"
	}
	var b strings.Builder
	b.WriteString("<SearchObjectType>[")
	for idx, item := range items {
		if idx > 0 {
			b.WriteString(", ")
		}
		b.WriteString(fmt.Sprintf("SearchObjectType.%s", toDartValueName(item)))
	}
	b.WriteString("]")
	return b.String()
}

// ── new cross-cutting readers ─────────────────────────────────────────────────

func readErrors(path string) (*errorsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed errorsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readBehaviors(path string) (*behaviorsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed behaviorsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readPrivacy(path string) (*privacyFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed privacyFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readUIConfig(path string) (*uiConfigFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed uiConfigFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readRequestContext(path string) (*requestContextFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed requestContextFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readAppRoutes(path string) (*appRoutesFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed appRoutesFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readUISurfaces(path string) (*uiSurfacesFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed uiSurfacesFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readSearchContract(path string) (*searchContractFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed searchContractFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readSearchObjects(path string) (*searchObjectsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed searchObjectsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

// ── new cross-cutting renderers ───────────────────────────────────────────────

func renderContentErrorsDart(ef *errorsFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from content/post/errors.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: constant_identifier_names\n\n")

	// Enum values
	b.WriteString("enum ContentErrorCode {\n")
	for _, e := range ef.Errors {
		b.WriteString(fmt.Sprintf("  %s,\n", e.DartConst))
	}
	b.WriteString("  unknown;\n\n")

	// isRetryable getter
	b.WriteString("  bool get isRetryable {\n")
	b.WriteString("    switch (this) {\n")
	for _, e := range ef.Errors {
		if e.Retryable {
			b.WriteString(fmt.Sprintf("      case ContentErrorCode.%s:\n", e.DartConst))
		}
	}
	b.WriteString("        return true;\n")
	b.WriteString("      default:\n")
	b.WriteString("        return false;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n\n")

	// fromCode factory
	b.WriteString("  static ContentErrorCode fromCode(String code) {\n")
	b.WriteString("    switch (code) {\n")
	for _, e := range ef.Errors {
		b.WriteString(fmt.Sprintf("      case '%s':\n        return ContentErrorCode.%s;\n", e.Code, e.DartConst))
	}
	b.WriteString("      default:\n        return ContentErrorCode.unknown;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	// ContentErrorMessages
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class ContentErrorMessages {\n")
	b.WriteString("  const ContentErrorMessages._();\n\n")

	// zh messages
	b.WriteString("  static const Map<ContentErrorCode, String> zh = <ContentErrorCode, String>{\n")
	for _, e := range ef.Errors {
		if msg, ok := e.UserMessage["zh"]; ok {
			b.WriteString(fmt.Sprintf("    ContentErrorCode.%s: '%s',\n", e.DartConst, strings.ReplaceAll(msg, "'", "\\'")))
		}
	}
	b.WriteString("  };\n\n")

	// en messages
	b.WriteString("  static const Map<ContentErrorCode, String> en = <ContentErrorCode, String>{\n")
	for _, e := range ef.Errors {
		if msg, ok := e.UserMessage["en"]; ok {
			b.WriteString(fmt.Sprintf("    ContentErrorCode.%s: '%s',\n", e.DartConst, strings.ReplaceAll(msg, "'", "\\'")))
		}
	}
	b.WriteString("  };\n")
	b.WriteString("}\n")

	return b.String()
}

// renderIntegrationLocationErrorsDart 生成 IntegrationLocationErrorCode + IntegrationLocationErrorMessages
// code 与 enum 双向可转换，toDisplayMessage 使用 l10n_key 映射到 AppLocalizations
func renderIntegrationLocationErrorsDart(ef *errorsFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from integration/location/errors.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: constant_identifier_names\n\n")

	b.WriteString("import 'package:quwoquan_app/l10n/l10n.dart';\n\n")

	b.WriteString("enum IntegrationLocationErrorCode {\n")
	for _, e := range ef.Errors {
		b.WriteString(fmt.Sprintf("  %s,\n", e.DartConst))
	}
	b.WriteString("  unknown;\n\n")

	b.WriteString("  /// 枚举对应的云端错误码字符串，与 fromCode 互为逆变换\n")
	b.WriteString("  String get code {\n")
	b.WriteString("    switch (this) {\n")
	for _, e := range ef.Errors {
		b.WriteString(fmt.Sprintf("      case IntegrationLocationErrorCode.%s:\n        return '%s';\n", e.DartConst, e.Code))
	}
	b.WriteString("      case IntegrationLocationErrorCode.unknown:\n        return '';\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n\n")

	b.WriteString("  bool get isRetryable {\n")
	b.WriteString("    switch (this) {\n")
	for _, e := range ef.Errors {
		if e.Retryable {
			b.WriteString(fmt.Sprintf("      case IntegrationLocationErrorCode.%s:\n", e.DartConst))
		}
	}
	b.WriteString("        return true;\n")
	b.WriteString("      default:\n")
	b.WriteString("        return false;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n\n")

	b.WriteString("  /// 从云端 code 字符串解析为枚举\n")
	b.WriteString("  static IntegrationLocationErrorCode fromCode(String? code) {\n")
	b.WriteString("    switch (code) {\n")
	for _, e := range ef.Errors {
		b.WriteString(fmt.Sprintf("      case '%s':\n        return IntegrationLocationErrorCode.%s;\n", e.Code, e.DartConst))
	}
	b.WriteString("      default:\n        return IntegrationLocationErrorCode.unknown;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n\n")

	b.WriteString("  /// 映射到 AppLocalizations 展示文案（使用 errors.yaml 中 l10n_key）\n")
	b.WriteString("  String toDisplayMessage(AppLocalizations l10n) {\n")
	b.WriteString("    switch (this) {\n")
	l10nFallback := "locationLoadFailed"
	for _, e := range ef.Errors {
		key := e.L10nKey
		if key == "" {
			key = l10nFallback
		}
		b.WriteString(fmt.Sprintf("      case IntegrationLocationErrorCode.%s:\n        return l10n.%s;\n", e.DartConst, key))
	}
	b.WriteString("      case IntegrationLocationErrorCode.unknown:\n        return l10n.locationLoadFailed;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class IntegrationLocationErrorMessages {\n")
	b.WriteString("  const IntegrationLocationErrorMessages._();\n\n")
	b.WriteString("  static const Map<IntegrationLocationErrorCode, String> zh = <IntegrationLocationErrorCode, String>{\n")
	for _, e := range ef.Errors {
		if msg, ok := e.UserMessage["zh"]; ok {
			b.WriteString(fmt.Sprintf("    IntegrationLocationErrorCode.%s: '%s',\n", e.DartConst, strings.ReplaceAll(msg, "'", "\\'")))
		}
	}
	b.WriteString("  };\n\n")
	b.WriteString("  static const Map<IntegrationLocationErrorCode, String> en = <IntegrationLocationErrorCode, String>{\n")
	for _, e := range ef.Errors {
		if msg, ok := e.UserMessage["en"]; ok {
			b.WriteString(fmt.Sprintf("    IntegrationLocationErrorCode.%s: '%s',\n", e.DartConst, strings.ReplaceAll(msg, "'", "\\'")))
		}
	}
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}

// renderIntegrationLocationErrorsGo 从 errors.yaml 生成 integration-service errors.go
// Err* 哨兵 + AppErrorFrom*(debugMessage)，user_message 取 user_message.zh，code 与 message 均来自 metadata
func renderIntegrationLocationErrorsGo(ef *errorsFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from integration/location/errors.yaml. DO NOT EDIT.\n")
	b.WriteString("package generated\n\n")
	b.WriteString("import (\n")
	b.WriteString("\t\"context\"\n")
	b.WriteString("\t\"errors\"\n\n")
	b.WriteString("\trerrors \"quwoquan_service/runtime/errors\"\n")
	b.WriteString(")\n\n")
	b.WriteString("// Integration location error sentinels and helpers.\n")
	b.WriteString("// user_message from errors.yaml user_message.zh\n")
	b.WriteString("//\n//nolint:gochecknoglobals\n")
	b.WriteString("var (\n")
	for _, e := range ef.Errors {
		if e.GoConst == "" {
			continue
		}
		b.WriteString(fmt.Sprintf("\t%s = errors.New(%q)\n", e.GoConst, e.Code))
	}
	b.WriteString(")\n\n")
	for _, e := range ef.Errors {
		if e.GoConst == "" {
			continue
		}
		msgZh := e.UserMessage["zh"]
		if msgZh == "" {
			msgZh = e.UserMessage["en"]
		}
		if msgZh == "" {
			msgZh = "请稍后重试"
		}
		msgZh = strings.ReplaceAll(msgZh, "\\", "\\\\")
		msgZh = strings.ReplaceAll(msgZh, "\"", "\\\"")
		// AppErrorFrom + go_const[3:] e.g. ErrLocationUnavailable -> AppErrorFromLocationUnavailable
		funcName := "AppErrorFrom"
		if len(e.GoConst) > 3 && e.GoConst[:3] == "Err" {
			funcName += e.GoConst[3:]
		} else {
			funcName += e.GoConst
		}
		b.WriteString(fmt.Sprintf("// %s returns *AppError for %s (user_message from errors.yaml).\n", funcName, e.Code))
		b.WriteString(fmt.Sprintf("func %s(debugMessage string) *rerrors.AppError {\n", funcName))
		b.WriteString(fmt.Sprintf("\tcode, _ := rerrors.ParseCode(string(%s.Error()))\n", e.GoConst))
		b.WriteString(fmt.Sprintf("\treturn rerrors.NewAppError(code, %q, debugMessage, %v)\n", msgZh, e.Retryable))
		b.WriteString("}\n\n")
	}
	b.WriteString("// IsTimeout returns true if err is context.DeadlineExceeded or contains upstream timeout semantics.\n")
	b.WriteString("func IsTimeout(err error) bool {\n")
	b.WriteString("\treturn errors.Is(err, context.DeadlineExceeded)\n")
	b.WriteString("}\n")
	return b.String()
}

func renderContentBehaviorsDart(bf *behaviorsFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from content/post/behaviors.yaml. DO NOT EDIT.\n\n")

	// Collect batch events (those with dart_method and batch=true or batch=false but not dedicated_route)
	var trackedEvents []behaviorEventDef
	batchRoute := ""
	for _, ev := range bf.BehaviorEvents {
		if ev.DartMethod != "" && ev.DedicatedRoute == "" {
			trackedEvents = append(trackedEvents, ev)
			if ev.BatchRoute != "" && batchRoute == "" {
				// Extract path from "POST /v1/content/behaviors"
				parts := strings.SplitN(ev.BatchRoute, " ", 2)
				if len(parts) == 2 {
					batchRoute = parts[1]
				}
			}
		}
	}
	if batchRoute == "" {
		batchRoute = "/v1/content/behaviors"
	}

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class ContentBehaviorTracker {\n")
	b.WriteString("  const ContentBehaviorTracker._();\n\n")
	b.WriteString(fmt.Sprintf("  static const String _batchRoute = '%s';\n\n", batchRoute))
	b.WriteString("  /// Public read-only accessor for the batch route (used in contract tests).\n")
	b.WriteString("  static String get batchRoute => _batchRoute;\n\n")
	b.WriteString("  static final List<Map<String, dynamic>> _queue = <Map<String, dynamic>>[];\n")
	b.WriteString("  static const int _flushThreshold = 20;\n\n")
	b.WriteString("  // ignore: invalid_use_of_visible_for_testing_member\n")
	b.WriteString("  /// Returns a read-only snapshot of the pending event queue. For testing only.\n")
	b.WriteString("  static List<Map<String, dynamic>> get pendingQueue =>\n")
	b.WriteString("      List<Map<String, dynamic>>.unmodifiable(_queue);\n\n")
	b.WriteString("  /// Clears the pending queue. For testing only.\n")
	b.WriteString("  static void reset() => _queue.clear();\n\n")

	// Generate track methods - collect positional and named params separately.
	for _, ev := range trackedEvents {
		positional := []string{"String postId"}
		var named []string
		for _, pf := range ev.PayloadFields {
			if pf == "postId" {
				continue
			}
			switch pf {
			case "dwellMs":
				positional = append(positional, "int dwellMs")
			case "feedPosition":
				named = append(named, "int feedPosition = 0")
			case "contentType":
				named = append(named, "String contentType = ''")
			case "shareTarget":
				named = append(named, "String shareTarget = ''")
			}
		}
		sig := strings.Join(positional, ", ")
		if len(named) > 0 {
			sig += ", {" + strings.Join(named, ", ") + "}"
		}
		b.WriteString(fmt.Sprintf("  static void %s(%s) {\n", ev.DartMethod, sig))
		b.WriteString("    _enqueue(<String, dynamic>{\n")
		b.WriteString(fmt.Sprintf("      'type': '%s',\n", ev.Type))
		b.WriteString("      'postId': postId,\n")
		for _, pf := range ev.PayloadFields {
			if pf == "postId" {
				continue
			}
			b.WriteString(fmt.Sprintf("      '%s': %s,\n", pf, pf))
		}
		b.WriteString("    });\n")
		b.WriteString("  }\n\n")
	}

	b.WriteString("  static void _enqueue(Map<String, dynamic> event) {\n")
	b.WriteString("    _queue.add(event);\n")
	b.WriteString("    if (_queue.length >= _flushThreshold) {\n")
	b.WriteString("      flush();\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n\n")

	b.WriteString("  static Future<void> flush() async {\n")
	b.WriteString("    if (_queue.isEmpty) return;\n")
	b.WriteString("    final events = List<Map<String, dynamic>>.from(_queue);\n")
	b.WriteString("    _queue.clear();\n")
	b.WriteString("    // Route: $_batchRoute\n")
	b.WriteString("    // Caller injects HTTP client via BehaviorTrackerHttpClient.send(events);\n")
	b.WriteString("    await BehaviorTrackerHttpClient.send(_batchRoute, events);\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	// Abstract HTTP client interface for testability
	b.WriteString("abstract class BehaviorTrackerHttpClient {\n")
	b.WriteString("  static Future<void> Function(String route, List<Map<String, dynamic>> events) send =\n")
	b.WriteString("      _defaultSend;\n\n")
	b.WriteString("  static Future<void> _defaultSend(\n")
	b.WriteString("    String route,\n")
	b.WriteString("    List<Map<String, dynamic>> events,\n")
	b.WriteString("  ) async {\n")
	b.WriteString("    // Default no-op; override via BehaviorTrackerHttpClient.send = myImpl;\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")

	return b.String()
}

func renderContentPrivacyDart(pf *privacyFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from content/post/privacy.yaml. DO NOT EDIT.\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class ContentPrivacyPolicy {\n")
	b.WriteString("  const ContentPrivacyPolicy._();\n\n")

	b.WriteString("  /// Returns sanitized value for app logging. Returns null to drop field.\n")
	b.WriteString("  static dynamic sanitizeForLog(String fieldName, dynamic value) {\n")
	b.WriteString("    switch (fieldName) {\n")

	for _, policy := range pf.AppLogPolicy {
		b.WriteString(fmt.Sprintf("      case '%s':\n", policy.Field))
		switch policy.AppLog {
		case "drop":
			b.WriteString("        return null;\n")
		case "truncate":
			chars := policy.TruncateChars
			if chars <= 0 {
				chars = 200
			}
			b.WriteString(fmt.Sprintf("        if (value is String && value.length > %d) {\n", chars))
			b.WriteString(fmt.Sprintf("          return value.substring(0, %d);\n", chars))
			b.WriteString("        }\n")
			b.WriteString("        return value;\n")
		case "mask":
			switch policy.MaskStrategy {
			case "city_level_only":
				b.WriteString("        if (value is Map) return <String, dynamic>{'city': value['city']};\n")
				b.WriteString("        return null;\n")
			case "strip_detail":
				b.WriteString("        if (value is String) {\n")
				b.WriteString("          final parts = value.split(' ');\n")
				b.WriteString("          return parts.isNotEmpty ? parts.first : '';\n")
				b.WriteString("        }\n")
				b.WriteString("        return null;\n")
			default:
				b.WriteString("        return null;\n")
			}
		default:
			b.WriteString("        return value;\n")
		}
	}

	b.WriteString("      default:\n")
	b.WriteString("        return value;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")

	return b.String()
}

func renderContentUIConfigDart(uc *uiConfigFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from content/post/ui_config.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")

	b.WriteString("class DiscoveryTabConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String labelKey;\n")
	b.WriteString("  final String icon;\n")
	b.WriteString("  final String contentType;\n")
	b.WriteString("  final String layout;\n\n")
	b.WriteString("  const DiscoveryTabConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.labelKey,\n")
	b.WriteString("    required this.icon,\n")
	b.WriteString("    required this.contentType,\n")
	b.WriteString("    required this.layout,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class DiscoveryRailConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String labelKey;\n")
	b.WriteString("  final String identity;\n")
	b.WriteString("  final bool isDefault;\n\n")
	b.WriteString("  const DiscoveryRailConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.labelKey,\n")
	b.WriteString("    required this.identity,\n")
	b.WriteString("    required this.isDefault,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class IdentityFilterConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String labelKey;\n")
	b.WriteString("  final String? identity;\n\n")
	b.WriteString("  const IdentityFilterConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.labelKey,\n")
	b.WriteString("    required this.identity,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class WorkFormatFilterConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String labelKey;\n")
	b.WriteString("  final String? contentType;\n\n")
	b.WriteString("  const WorkFormatFilterConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.labelKey,\n")
	b.WriteString("    required this.contentType,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class ShareTemplateProfileConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String titleKey;\n")
	b.WriteString("  final String subtitleKey;\n")
	b.WriteString("  final String layout;\n")
	b.WriteString("  final String coverStrategy;\n")
	b.WriteString("  final bool includeAuthor;\n")
	b.WriteString("  final bool includeTimeContext;\n")
	b.WriteString("  final bool includeCircleContext;\n")
	b.WriteString("  final bool includeTags;\n\n")
	b.WriteString("  const ShareTemplateProfileConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.titleKey,\n")
	b.WriteString("    required this.subtitleKey,\n")
	b.WriteString("    required this.layout,\n")
	b.WriteString("    required this.coverStrategy,\n")
	b.WriteString("    required this.includeAuthor,\n")
	b.WriteString("    required this.includeTimeContext,\n")
	b.WriteString("    required this.includeCircleContext,\n")
	b.WriteString("    required this.includeTags,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class ArticleDistributionProfileConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String surface;\n")
	b.WriteString("  final String layout;\n")
	b.WriteString("  final String coverMode;\n")
	b.WriteString("  final int summaryLineLimit;\n\n")
	b.WriteString("  const ArticleDistributionProfileConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.surface,\n")
	b.WriteString("    required this.layout,\n")
	b.WriteString("    required this.coverMode,\n")
	b.WriteString("    required this.summaryLineLimit,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class ArticleReaderProfileConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String stageLayout;\n")
	b.WriteString("  final String pageIndicatorAnchor;\n")
	b.WriteString("  final String edgeTreatment;\n")
	b.WriteString("  final bool supportsPageCurl;\n\n")
	b.WriteString("  const ArticleReaderProfileConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.stageLayout,\n")
	b.WriteString("    required this.pageIndicatorAnchor,\n")
	b.WriteString("    required this.edgeTreatment,\n")
	b.WriteString("    required this.supportsPageCurl,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class ArticleTemplateConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String defaultFontPreset;\n")
	b.WriteString("  final String paperTexture;\n")
	b.WriteString("  final String decorationStyle;\n")
	b.WriteString("  final String chromeStyle;\n\n")
	b.WriteString("  const ArticleTemplateConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.defaultFontPreset,\n")
	b.WriteString("    required this.paperTexture,\n")
	b.WriteString("    required this.decorationStyle,\n")
	b.WriteString("    required this.chromeStyle,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class ArticleTemplateRecommendationConfig {\n")
	b.WriteString("  final String categoryId;\n")
	b.WriteString("  final List<String> recommendedArticleTemplates;\n\n")
	b.WriteString("  const ArticleTemplateRecommendationConfig({\n")
	b.WriteString("    required this.categoryId,\n")
	b.WriteString("    required this.recommendedArticleTemplates,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	tabs := append([]discoveryTabDef(nil), uc.DiscoveryTabs...)
	sort.Slice(tabs, func(i, j int) bool { return tabs[i].Order < tabs[j].Order })
	rails := append([]discoveryRailDef(nil), uc.DiscoveryRails...)
	sort.Slice(rails, func(i, j int) bool { return rails[i].Order < rails[j].Order })
	identityFilters := append([]identityFilterDef(nil), uc.CreationIdentityFilters...)
	sort.Slice(identityFilters, func(i, j int) bool { return identityFilters[i].Order < identityFilters[j].Order })
	workFormatFilters := append([]workFormatFilterDef(nil), uc.WorkFormatFilters...)
	sort.Slice(workFormatFilters, func(i, j int) bool { return workFormatFilters[i].Order < workFormatFilters[j].Order })
	shareProfiles := append([]shareTemplateProfileDef(nil), uc.ShareTemplateProfiles...)
	sort.Slice(shareProfiles, func(i, j int) bool { return shareProfiles[i].ID < shareProfiles[j].ID })
	articleDistributionProfiles := append([]articleDistributionProfileDef(nil), uc.ArticleDistributionProfiles...)
	sort.Slice(articleDistributionProfiles, func(i, j int) bool { return articleDistributionProfiles[i].ID < articleDistributionProfiles[j].ID })
	articleReaderProfiles := append([]articleReaderProfileDef(nil), uc.ArticleReaderProfiles...)
	sort.Slice(articleReaderProfiles, func(i, j int) bool { return articleReaderProfiles[i].ID < articleReaderProfiles[j].ID })
	articleTemplateConfigs := append([]articleTemplateConfigDef(nil), uc.ArticleTemplateConfigs...)
	sort.Slice(articleTemplateConfigs, func(i, j int) bool { return articleTemplateConfigs[i].ID < articleTemplateConfigs[j].ID })
	articleTemplateRecommendations := append([]articleTemplateRecommendationDef(nil), uc.ArticleTemplateRecommendations...)
	sort.Slice(articleTemplateRecommendations, func(i, j int) bool {
		return articleTemplateRecommendations[i].CategoryID < articleTemplateRecommendations[j].CategoryID
	})

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class ContentUIConfig {\n")
	b.WriteString("  const ContentUIConfig._();\n\n")

	b.WriteString("  static const List<DiscoveryTabConfig> discoveryTabs = <DiscoveryTabConfig>[\n")
	for _, tab := range tabs {
		b.WriteString(fmt.Sprintf("    DiscoveryTabConfig(id: %s, labelKey: %s, icon: %s, contentType: %s, layout: %s),\n",
			dartStringLiteral(tab.ID),
			dartStringLiteral(tab.LabelKey),
			dartStringLiteral(tab.Icon),
			dartStringLiteral(tab.ContentType),
			dartStringLiteral(tab.Layout)))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<DiscoveryRailConfig> discoveryRails = <DiscoveryRailConfig>[\n")
	for _, rail := range rails {
		b.WriteString(fmt.Sprintf("    DiscoveryRailConfig(id: %s, labelKey: %s, identity: %s, isDefault: %v),\n",
			dartStringLiteral(rail.ID),
			dartStringLiteral(rail.LabelKey),
			dartStringLiteral(rail.Identity),
			rail.Default))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<IdentityFilterConfig> creationIdentityFilters = <IdentityFilterConfig>[\n")
	for _, filter := range identityFilters {
		b.WriteString(fmt.Sprintf("    IdentityFilterConfig(id: %s, labelKey: %s, identity: %s),\n",
			dartStringLiteral(filter.ID),
			dartStringLiteral(filter.LabelKey),
			dartStringOrNull(filter.Identity)))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<WorkFormatFilterConfig> workFormatFilters = <WorkFormatFilterConfig>[\n")
	for _, filter := range workFormatFilters {
		b.WriteString(fmt.Sprintf("    WorkFormatFilterConfig(id: %s, labelKey: %s, contentType: %s),\n",
			dartStringLiteral(filter.ID),
			dartStringLiteral(filter.LabelKey),
			dartStringOrNull(filter.ContentType)))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<ShareTemplateProfileConfig> shareTemplateProfiles = <ShareTemplateProfileConfig>[\n")
	for _, profile := range shareProfiles {
		b.WriteString(fmt.Sprintf("    ShareTemplateProfileConfig(id: %s, titleKey: %s, subtitleKey: %s, layout: %s, coverStrategy: %s, includeAuthor: %v, includeTimeContext: %v, includeCircleContext: %v, includeTags: %v),\n",
			dartStringLiteral(profile.ID),
			dartStringLiteral(profile.TitleKey),
			dartStringLiteral(profile.SubtitleKey),
			dartStringLiteral(profile.Layout),
			dartStringLiteral(profile.CoverStrategy),
			profile.IncludeAuthor,
			profile.IncludeTimeContext,
			profile.IncludeCircleContext,
			profile.IncludeTags))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<ArticleDistributionProfileConfig> articleDistributionProfiles = <ArticleDistributionProfileConfig>[\n")
	for _, profile := range articleDistributionProfiles {
		b.WriteString(fmt.Sprintf("    ArticleDistributionProfileConfig(id: %s, surface: %s, layout: %s, coverMode: %s, summaryLineLimit: %d),\n",
			dartStringLiteral(profile.ID),
			dartStringLiteral(profile.Surface),
			dartStringLiteral(profile.Layout),
			dartStringLiteral(profile.CoverMode),
			profile.SummaryLineLimit))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<ArticleReaderProfileConfig> articleReaderProfiles = <ArticleReaderProfileConfig>[\n")
	for _, profile := range articleReaderProfiles {
		b.WriteString(fmt.Sprintf("    ArticleReaderProfileConfig(id: %s, stageLayout: %s, pageIndicatorAnchor: %s, edgeTreatment: %s, supportsPageCurl: %v),\n",
			dartStringLiteral(profile.ID),
			dartStringLiteral(profile.StageLayout),
			dartStringLiteral(profile.PageIndicatorAnchor),
			dartStringLiteral(profile.EdgeTreatment),
			profile.SupportsPageCurl))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<ArticleTemplateConfig> articleTemplateConfigs = <ArticleTemplateConfig>[\n")
	for _, config := range articleTemplateConfigs {
		b.WriteString(fmt.Sprintf("    ArticleTemplateConfig(id: %s, defaultFontPreset: %s, paperTexture: %s, decorationStyle: %s, chromeStyle: %s),\n",
			dartStringLiteral(config.ID),
			dartStringLiteral(config.DefaultFontPreset),
			dartStringLiteral(config.PaperTexture),
			dartStringLiteral(config.DecorationStyle),
			dartStringLiteral(config.ChromeStyle)))
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const List<ArticleTemplateRecommendationConfig> articleTemplateRecommendations = <ArticleTemplateRecommendationConfig>[\n")
	for _, recommendation := range articleTemplateRecommendations {
		b.WriteString(fmt.Sprintf("    ArticleTemplateRecommendationConfig(categoryId: %s, recommendedArticleTemplates: <String>[",
			dartStringLiteral(recommendation.CategoryID)))
		for i, templateID := range recommendation.RecommendedArticleTemplates {
			if i > 0 {
				b.WriteString(", ")
			}
			b.WriteString(dartStringLiteral(templateID))
		}
		b.WriteString("]),\n")
	}
	b.WriteString("  ];\n\n")

	b.WriteString("  static const Map<String, bool> featureFlags = <String, bool>{\n")
	flags := make([]featureFlagDef, len(uc.FeatureFlags))
	copy(flags, uc.FeatureFlags)
	sort.Slice(flags, func(i, j int) bool { return flags[i].Flag < flags[j].Flag })
	for _, ff := range flags {
		b.WriteString(fmt.Sprintf("    '%s': %v,\n", ff.Flag, ff.Default))
	}
	b.WriteString("  };\n\n")

	if len(uc.EmptyStates) > 0 {
		b.WriteString("  static const Map<String, Map<String, String>> emptyStates = <String, Map<String, String>>{\n")
		esKeys := make([]string, 0, len(uc.EmptyStates))
		for k := range uc.EmptyStates {
			esKeys = append(esKeys, k)
		}
		sort.Strings(esKeys)
		for _, k := range esKeys {
			es := uc.EmptyStates[k]
			b.WriteString(fmt.Sprintf("    '%s': <String, String>{\n", k))
			if es.TitleKey != "" {
				b.WriteString(fmt.Sprintf("      'titleKey': '%s',\n", es.TitleKey))
			}
			if es.SubtitleKey != "" {
				b.WriteString(fmt.Sprintf("      'subtitleKey': '%s',\n", es.SubtitleKey))
			}
			if es.CTALabelKey != "" {
				b.WriteString(fmt.Sprintf("      'ctaKey': '%s',\n", es.CTALabelKey))
			}
			b.WriteString("    },\n")
		}
		b.WriteString("  };\n")
	}

	b.WriteString("}\n")
	return b.String()
}

func renderUserProfileUIConfigDart(uc *uiConfigFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from user/user_profile/ui_config.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")

	b.WriteString("class UserProfileTabConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String labelKey;\n")
	b.WriteString("  final bool isDefault;\n\n")
	b.WriteString("  const UserProfileTabConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.labelKey,\n")
	b.WriteString("    required this.isDefault,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class UserProfileSubTabConfig {\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String labelKey;\n")
	b.WriteString("  final String? contentType;\n\n")
	b.WriteString("  const UserProfileSubTabConfig({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.labelKey,\n")
	b.WriteString("    required this.contentType,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class UserProfileHeaderLayoutConfig {\n")
	b.WriteString("  final double baseHeightRatio;\n")
	b.WriteString("  final double maxStretchHeightRatio;\n")
	b.WriteString("  final double avatarOverlapRatio;\n\n")
	b.WriteString("  const UserProfileHeaderLayoutConfig({\n")
	b.WriteString("    required this.baseHeightRatio,\n")
	b.WriteString("    required this.maxStretchHeightRatio,\n")
	b.WriteString("    required this.avatarOverlapRatio,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	b.WriteString("class UserProfileScrollMotionConfig {\n")
	b.WriteString("  final bool compactIdentityBar;\n")
	b.WriteString("  final bool primaryTabStickyBelowToolbar;\n")
	b.WriteString("  final bool secondaryTabInlineScroll;\n")
	b.WriteString("  final String reboundCurve;\n")
	b.WriteString("  final String collapseCurve;\n\n")
	b.WriteString("  const UserProfileScrollMotionConfig({\n")
	b.WriteString("    required this.compactIdentityBar,\n")
	b.WriteString("    required this.primaryTabStickyBelowToolbar,\n")
	b.WriteString("    required this.secondaryTabInlineScroll,\n")
	b.WriteString("    required this.reboundCurve,\n")
	b.WriteString("    required this.collapseCurve,\n")
	b.WriteString("  });\n")
	b.WriteString("}\n\n")

	profileTabs := append([]profileTabDef(nil), uc.ProfileTabs...)
	sort.Slice(profileTabs, func(i, j int) bool { return profileTabs[i].Order < profileTabs[j].Order })

	defaultTabID := "creations"
	for _, tab := range profileTabs {
		if tab.Default {
			defaultTabID = tab.ID
			break
		}
	}
	if len(profileTabs) > 0 && strings.TrimSpace(defaultTabID) == "" {
		defaultTabID = profileTabs[0].ID
	}

	sortSubTabs := func(tabs []profileSubTabDef) []profileSubTabDef {
		out := append([]profileSubTabDef(nil), tabs...)
		sort.Slice(out, func(i, j int) bool { return out[i].Order < out[j].Order })
		return out
	}

	findTab := func(id string) *profileTabDef {
		for i := range profileTabs {
			if profileTabs[i].ID == id {
				return &profileTabs[i]
			}
		}
		return nil
	}

	writeSubTabList := func(name string, tabs []profileSubTabDef) {
		b.WriteString(fmt.Sprintf("  static const List<UserProfileSubTabConfig> %s = <UserProfileSubTabConfig>[\n", name))
		for _, tab := range sortSubTabs(tabs) {
			b.WriteString(fmt.Sprintf("    UserProfileSubTabConfig(id: %s, labelKey: %s, contentType: %s),\n",
				dartStringLiteral(tab.ID),
				dartStringLiteral(tab.LabelKey),
				dartStringOrNull(tab.ContentType)))
		}
		b.WriteString("  ];\n\n")
	}

	writeModeFilterMap := func(name string, values map[string][]string) {
		keys := make([]string, 0, len(values))
		for key := range values {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		b.WriteString(fmt.Sprintf("  static const Map<String, List<String>> %s = <String, List<String>>{\n", name))
		for _, key := range keys {
			b.WriteString(fmt.Sprintf("    '%s': <String>[", key))
			for idx, value := range values[key] {
				if idx > 0 {
					b.WriteString(", ")
				}
				b.WriteString(dartStringLiteral(value))
			}
			b.WriteString("],\n")
		}
		b.WriteString("  };\n\n")
	}

	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class UserProfileUIConfig {\n")
	b.WriteString("  const UserProfileUIConfig._();\n\n")
	b.WriteString(fmt.Sprintf("  static const String defaultTabId = %s;\n\n", dartStringLiteral(defaultTabID)))
	b.WriteString(fmt.Sprintf("  static const UserProfileHeaderLayoutConfig headerLayout = UserProfileHeaderLayoutConfig(baseHeightRatio: %s, maxStretchHeightRatio: %s, avatarOverlapRatio: %s);\n\n",
		dartDoubleLiteral(uc.HeaderLayout.BaseHeightRatio, 0.25),
		dartDoubleLiteral(uc.HeaderLayout.MaxStretchHeightRatio, 0.333),
		dartDoubleLiteral(uc.HeaderLayout.AvatarOverlapRatio, 0.333)))
	reboundCurve := strings.TrimSpace(uc.ScrollMotion.ReboundCurve)
	if reboundCurve == "" {
		reboundCurve = "easeOutBack"
	}
	collapseCurve := strings.TrimSpace(uc.ScrollMotion.CollapseCurve)
	if collapseCurve == "" {
		collapseCurve = "easeOutCubic"
	}
	b.WriteString(fmt.Sprintf("  static const UserProfileScrollMotionConfig scrollMotion = UserProfileScrollMotionConfig(compactIdentityBar: %v, primaryTabStickyBelowToolbar: %v, secondaryTabInlineScroll: %v, reboundCurve: %s, collapseCurve: %s);\n\n",
		uc.ScrollMotion.CompactIdentityBar,
		uc.ScrollMotion.PrimaryTabStickyBelowToolbar,
		uc.ScrollMotion.SecondaryTabInlineScroll,
		dartStringLiteral(reboundCurve),
		dartStringLiteral(collapseCurve)))
	b.WriteString("  static const List<UserProfileTabConfig> profileTabs = <UserProfileTabConfig>[\n")
	for _, tab := range profileTabs {
		b.WriteString(fmt.Sprintf("    UserProfileTabConfig(id: %s, labelKey: %s, isDefault: %v),\n",
			dartStringLiteral(tab.ID),
			dartStringLiteral(tab.LabelKey),
			tab.Default))
	}
	b.WriteString("  ];\n\n")

	if creationTab := findTab("creations"); creationTab != nil {
		writeSubTabList("creationSubTabs", creationTab.SubTabs)
		writeModeFilterMap("creationVisibilityFiltersByMode", creationTab.VisibilityFilter)
	} else {
		writeSubTabList("creationSubTabs", nil)
		writeModeFilterMap("creationVisibilityFiltersByMode", map[string][]string{})
	}

	if interactionTab := findTab("interaction"); interactionTab != nil {
		writeSubTabList("interactionSubTabs", interactionTab.SubTabs)
		writeModeFilterMap("interactionDirectionFiltersByMode", interactionTab.DirectionFilter)
	} else {
		writeSubTabList("interactionSubTabs", nil)
		writeModeFilterMap("interactionDirectionFiltersByMode", map[string][]string{})
	}

	b.WriteString("}\n")
	return b.String()
}

// renderIntegrationLocationMetadataDart 生成 integration/location API 元数据常量。
// 路径与 response key 来自 contracts/metadata/integration/location/service.yaml，
// 禁止在业务/测试中硬编码。
func renderIntegrationLocationMetadataDart(svc *integrationLocationServiceFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from integration/location/service.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")
	b.WriteString("/// integration/location API 元数据，与 contracts/metadata 同步。\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class IntegrationLocationMetadata {\n")
	b.WriteString("  const IntegrationLocationMetadata._();\n\n")

	responseKey := strings.TrimSpace(svc.ResponseListKey)
	if responseKey == "" {
		responseKey = "items"
	}
	b.WriteString(fmt.Sprintf("  /// 列表响应根 key（与 integration-service handler 一致）\n"))
	b.WriteString(fmt.Sprintf("  static const String responseItemsKey = '%s';\n\n", responseKey))

	nearbyPath := ""
	searchPath := ""
	for _, r := range svc.APIRoutes {
		switch r.Operation {
		case "GetNearbyLocations":
			nearbyPath = r.Path
		case "SearchLocations":
			searchPath = r.Path
		}
	}
	if nearbyPath == "" {
		nearbyPath = "/v1/integration/location/nearby"
	}
	if searchPath == "" {
		searchPath = "/v1/integration/location/search"
	}
	b.WriteString("  /// API 路径（来自 api_routes）\n")
	b.WriteString(fmt.Sprintf("  static const String nearbyPath = '%s';\n", nearbyPath))
	b.WriteString(fmt.Sprintf("  static const String searchPath = '%s';\n", searchPath))

	b.WriteString("}\n")
	return b.String()
}

// renderIntegrationLocationMetadataGo 生成 integration-service Go 元数据常量。
// 路径、response key、LocationPoi 字段名全部来自 contracts/metadata。
func renderIntegrationLocationMetadataGo(svc *integrationLocationServiceFile, projFields []projectionFieldDef) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from integration/location metadata. DO NOT EDIT.\n")
	b.WriteString("package generated\n\n")
	b.WriteString("// LocationMetadata integration/location API 与 client_projection 元数据。\n")

	responseKey := strings.TrimSpace(svc.ResponseListKey)
	if responseKey == "" {
		responseKey = "items"
	}
	b.WriteString(fmt.Sprintf("const ResponseListKey = %q\n\n", responseKey))

	nearbyPath := ""
	searchPath := ""
	for _, r := range svc.APIRoutes {
		switch r.Operation {
		case "GetNearbyLocations":
			nearbyPath = r.Path
		case "SearchLocations":
			searchPath = r.Path
		}
	}
	if nearbyPath == "" {
		nearbyPath = "/v1/integration/location/nearby"
	}
	if searchPath == "" {
		searchPath = "/v1/integration/location/search"
	}
	b.WriteString("// API 路径（来自 api_routes）\n")
	b.WriteString(fmt.Sprintf("const NearbyPath = %q\n", nearbyPath))
	b.WriteString(fmt.Sprintf("const SearchPath = %q\n\n", searchPath))

	// 去重 query param 名称
	paramSet := make(map[string]struct{})
	for _, r := range svc.APIRoutes {
		for _, p := range r.QueryParams {
			paramSet[p] = struct{}{}
		}
	}
	b.WriteString("// Query 参数名（来自 api_routes query_params）\n")
	for _, r := range svc.APIRoutes {
		for _, p := range r.QueryParams {
			if _, ok := paramSet[p]; !ok {
				continue
			}
			delete(paramSet, p)
			goName := "QueryParam" + toGoExportedName(p)
			b.WriteString(fmt.Sprintf("const %s = %q\n", goName, p))
		}
	}
	// 补充 paramSet 剩余
	for p := range paramSet {
		goName := "QueryParam" + toGoExportedName(p)
		b.WriteString(fmt.Sprintf("const %s = %q\n", goName, p))
	}
	b.WriteString("\n")

	b.WriteString("// LocationPoi client_projection 字段 key（与 location_poi.yaml 一致）\n")
	for _, f := range projFields {
		key := f.Name
		if key == "" {
			continue
		}
		goName := "FieldKey" + toGoExportedName(key)
		b.WriteString(fmt.Sprintf("const %s = %q\n", goName, key))
	}
	return b.String()
}

func toGoExportedName(s string) string {
	if s == "" {
		return ""
	}
	return strings.ToUpper(s[:1]) + s[1:]
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_app_metadata error: %v\n", err)
	os.Exit(1)
}
