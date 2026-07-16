package main

import (
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
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
	Name           string   `yaml:"name"`
	Type           string   `yaml:"type"`
	Constraints    []string `yaml:"constraints"`
	EnumRef        string   `yaml:"enum_ref"`
	ClientDartName string   `yaml:"client_dart_name"`
	JsonKeys       []string `yaml:"json_keys"`
	ClientDefault  string   `yaml:"client_default"`
	ItemEntity     string   `yaml:"item_entity"`
}

type entityDef struct {
	Fields []fieldDef `yaml:"fields"`
}

type fieldsFile struct {
	Entities map[string]entityDef `yaml:"entities"`
}

// ── post/service.yaml ─────────────────────────────────────────────────────────

type routeSecurity struct {
	AuthMode        string   `yaml:"auth_mode"`
	Principal       string   `yaml:"principal"`
	Permissions     []string `yaml:"permissions"`
	TokenTransport  string   `yaml:"token_transport"`
	AnonymousPolicy string   `yaml:"anonymous_policy"`
	Visibility      string   `yaml:"visibility"`
}

type routeDef struct {
	Method          string   `yaml:"method"`
	Path            string   `yaml:"path"`
	Operation       string   `yaml:"operation"`
	Description     string   `yaml:"description"`
	QueryParams     []string `yaml:"query_params"`
	WritableFields  []string `yaml:"writable_fields"`
	RequestFields   []string `yaml:"request_fields"`
	ResponseFields  []string `yaml:"response_fields"`
	RequestEntity   string   `yaml:"request_entity"`
	RequestBodyKind string   `yaml:"request_body_kind"`
	ResponseEntity  string   `yaml:"response_entity"`
	// 框架级响应契约（R-ID02）：response_body 指向 projection read_model，
	// response_body_kind ∈ object|page|ack（ack 无读模型，仅状态确认）。
	ResponseBody     string        `yaml:"response_body"`
	ResponseBodyKind string        `yaml:"response_body_kind"`
	Security         routeSecurity `yaml:"security"`
	// Back-compat: 旧写法 auth: required / auth_required: bool。统一收敛到 security.auth_mode。
	Auth         string `yaml:"auth"`
	AuthRequired *bool  `yaml:"auth_required"`
}

// resolveAuthMode 返回 public | optional | required 三态。
// 优先 security.auth_mode；其次兼容旧 auth/auth_required；缺失声明默认 required，
// 公开/可选 operation 必须由 metadata 显式授权，禁止 fail-open。
func (r routeDef) resolveAuthMode() string {
	mode := strings.ToLower(strings.TrimSpace(r.Security.AuthMode))
	switch mode {
	case "public", "optional", "required":
		return mode
	}
	if strings.EqualFold(strings.TrimSpace(r.Auth), "required") {
		return "required"
	}
	if strings.EqualFold(strings.TrimSpace(r.Auth), "optional") {
		return "optional"
	}
	if r.AuthRequired != nil {
		if *r.AuthRequired {
			return "required"
		}
		return "public"
	}
	return "required"
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
	Name                   string   `yaml:"name"`
	DartType               string   `yaml:"dart_type"`
	WireType               string   `yaml:"type"`
	Nullable               bool     `yaml:"nullable"`
	Source                 string   `yaml:"source"`
	Aliases                []string `yaml:"aliases"`
	Default                string   `yaml:"default"`
	Description            string   `yaml:"description"`
	SkipEmptyStringAliases bool     `yaml:"skip_empty_string_aliases"`
	// When dart_type is List<SomeDto>, set to SomeDto; fromMap uses SomeDto.fromMap per element.
	ListElementDartClass string `yaml:"list_element_dart_class"`
	// When dart_type is a class with SomeDto.fromMap(Map<String,dynamic>) and wire is a JSON object.
	MapFromStringKeyClass string `yaml:"map_from_string_key_class"`
}

type computedGetterDef struct {
	Name           string `yaml:"name"`
	DartReturnType string `yaml:"dart_return_type"`
	Nullable       bool   `yaml:"nullable"`
	Description    string `yaml:"description"`
	Body           string `yaml:"body"`
}

type clientProjection struct {
	DartClass        string               `yaml:"dart_class"`
	BaseClass        string               `yaml:"base_class"`
	OutputPath       string               `yaml:"output_path"`
	ExternalDartPath string               `yaml:"external_dart_path"`
	Strict           bool                 `yaml:"strict"`
	DartImports      []string             `yaml:"dart_imports"`
	Fields           []projectionFieldDef `yaml:"fields"`
	ComputedGetters  []computedGetterDef  `yaml:"computed_getters"`
}

type projectionFile struct {
	ReadModel        string               `yaml:"read_model"`
	ClientProjection clientProjection     `yaml:"client_projection"`
	Fields           []projectionFieldDef `yaml:"fields"`
}

// projectionBinding 只承载 operation response_body 解析所需的投影身份和端侧类型绑定。
// 这条链路不读取 projection.fields，避免简写字段列表影响强类型绑定索引。
type projectionBinding struct {
	ReadModel        string           `yaml:"read_model"`
	ClientProjection clientProjection `yaml:"client_projection"`
}

// ── errors.yaml ───────────────────────────────────────────────────────────────

type errorRecoveryDef = contractcodegen.ErrorRecovery
type errorDef = contractcodegen.ErrorDefinition
type errorsFile = contractcodegen.ErrorsFile

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

// homeChannelDef：首页频道运营可配置项（端 meta 默认 + /v1/config/app 远程覆盖）。
type homeChannelDef struct {
	ID                       string            `yaml:"id"`
	LabelKey                 string            `yaml:"label_key"`
	Template                 string            `yaml:"template"`
	LayoutTemplate           string            `yaml:"layout_template"`
	PhoneColumns             int               `yaml:"phone_columns"`
	SupportsFullSpanModules  bool              `yaml:"supports_full_span_modules"`
	IntersectionModulePolicy string            `yaml:"intersection_module_policy"`
	ContentCardPolicy        string            `yaml:"content_card_policy"`
	FeedQuery                map[string]string `yaml:"feed_query"`
	MoodCopyKey              string            `yaml:"mood_copy_key"`
	Order                    int               `yaml:"order"`
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
	ID           string `yaml:"id"`
	LabelKey     string `yaml:"label_key"`
	ContentType  string `yaml:"content_type"`
	LifeCategory string `yaml:"life_category"`
	Order        int    `yaml:"order"`
	Default      bool   `yaml:"default"`
	// Modes 限制二级 Tab 仅在指定主页模式（mine/other）可见；空表示全模式可见。
	Modes []string `yaml:"modes"`
}

type profileTabDef struct {
	ID               string              `yaml:"id"`
	LabelKey         string              `yaml:"label_key"`
	Order            int                 `yaml:"order"`
	Default          bool                `yaml:"default"`
	SubTabs          []profileSubTabDef  `yaml:"sub_tabs"`
	VisibilityFilter map[string][]string `yaml:"visibility_filter"`
	DirectionFilter  map[string][]string `yaml:"direction_filter"`
	// Modes 限制一级 Tab 仅在指定主页模式可见（mine/other）；空表示全模式可见。
	// 隐私门控真相源：足迹=浏览历史仅本人可见，必须声明 modes: [mine]。
	Modes []string `yaml:"modes"`
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
	ID                 string `yaml:"id"`
	TitleKey           string `yaml:"title_key"`
	SubtitleKey        string `yaml:"subtitle_key"`
	Layout             string `yaml:"layout"`
	CoverStrategy      string `yaml:"cover_strategy"`
	IncludeAuthor      bool   `yaml:"include_author"`
	IncludeTimeContext bool   `yaml:"include_time_context"`
	IncludeTags        bool   `yaml:"include_tags"`
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

type articlePaperThemeOptionDef struct {
	ID       string `yaml:"id"`
	LabelKey string `yaml:"label_key"`
}

type articlePaperThemeDef struct {
	ID            string `yaml:"id"`
	Stage         string `yaml:"stage"`
	Paper         string `yaml:"paper"`
	Text          string `yaml:"text"`
	SecondaryText string `yaml:"secondary_text"`
}

type articleDarkPaperThemesDef struct {
	DefaultTheme          string                       `yaml:"default_theme"`
	ReadingSettingOptions []articlePaperThemeOptionDef `yaml:"reading_setting_options"`
	VerticalDefaults      map[string]string            `yaml:"vertical_defaults"`
	Themes                []articlePaperThemeDef       `yaml:"themes"`
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
	HomeChannels                   []homeChannelDef                   `yaml:"home_channels"`
	DiscoveryTabs                  []discoveryTabDef                  `yaml:"discovery_tabs"`
	DiscoveryRails                 []discoveryRailDef                 `yaml:"discovery_rails"`
	CreationIdentityFilters        []identityFilterDef                `yaml:"creation_identity_filters"`
	WorkFormatFilters              []workFormatFilterDef              `yaml:"work_format_filters"`
	HeaderLayout                   profileHeaderLayoutDef             `yaml:"header_layout"`
	ScrollMotion                   profileScrollMotionDef             `yaml:"scroll_motion"`
	CareerInterestCatalog          careerInterestCatalogDef           `yaml:"career_interest_catalog"`
	ProfileTabs                    []profileTabDef                    `yaml:"profile_tabs"`
	HomepageTabs                   []homepageTabDef                   `yaml:"homepage_tabs"`
	HomepageSubTabs                []homepageSubTabDef                `yaml:"homepage_sub_tabs"`
	CircleTabs                     []circleTabDef                     `yaml:"circle_tabs"`
	CircleSections                 []circleSectionDef                 `yaml:"circle_sections"`
	ShareTemplateProfiles          []shareTemplateProfileDef          `yaml:"share_template_profiles"`
	ArticleDistributionProfiles    []articleDistributionProfileDef    `yaml:"article_distribution_profiles"`
	ArticleReaderProfiles          []articleReaderProfileDef          `yaml:"article_reader_profiles"`
	ArticleTemplateConfigs         []articleTemplateConfigDef         `yaml:"article_template_configs"`
	ArticleTemplateRecommendations []articleTemplateRecommendationDef `yaml:"article_template_recommendations"`
	ArticleDarkPaperThemes         articleDarkPaperThemesDef          `yaml:"article_dark_paper_themes"`
	FeatureFlags                   []featureFlagDef                   `yaml:"feature_flags"`
	EmptyStates                    map[string]emptyStateDef           `yaml:"empty_states"`
}

type careerInterestCatalogDef struct {
	OccupationRootRef         string                      `yaml:"occupation_root_ref"`
	InterestRootRef           string                      `yaml:"interest_root_ref"`
	MaxInterestCount          int                         `yaml:"max_interest_count"`
	DefaultInterestCategoryID string                      `yaml:"default_interest_category_id"`
	OccupationCategories      []careerInterestCategoryDef `yaml:"occupation_categories"`
	InterestCategories        []careerInterestCategoryDef `yaml:"interest_categories"`
}

type careerInterestCategoryDef struct {
	ID       string `yaml:"id"`
	TagRef   string `yaml:"tag_ref"`
	LabelKey string `yaml:"label_key"`
	Order    int    `yaml:"order"`
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
	Name                   string   `yaml:"name"`
	Description            string   `yaml:"description"`
	RequiredFields         []string `yaml:"required_fields"`
	OptionalFields         []string `yaml:"optional_fields"`
	InternalOptionalFields []string `yaml:"internal_optional_fields"`
}

type retrieveContractDef struct {
	Name            string   `yaml:"name"`
	Description     string   `yaml:"description"`
	MatchConditions []string `yaml:"match_conditions"`
	FilterFields    []string `yaml:"filter_fields"`
	PageFields      []string `yaml:"page_fields"`
	ResponseFields  []string `yaml:"response_fields"`
	HitFields       []string `yaml:"hit_fields"`
	ForbiddenFields []string `yaml:"forbidden_fields"`
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
	RetrieveContract    retrieveContractDef       `yaml:"retrieve_contract"`
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

type aiTargetDef struct {
	ID          string `yaml:"id"`
	Label       string `yaml:"label"`
	ObjectType  string `yaml:"object_type"`
	ContentType string `yaml:"content_type"`
	Description string `yaml:"description"`
}

type searchObjectsFile struct {
	Version      int                    `yaml:"version"`
	ObjectTypes  []searchObjectTypeDef  `yaml:"object_types"`
	AITargets    []aiTargetDef          `yaml:"ai_targets"`
	SectionKinds []searchSectionKindDef `yaml:"section_kinds"`
}

// ── main ──────────────────────────────────────────────────────────────────────
