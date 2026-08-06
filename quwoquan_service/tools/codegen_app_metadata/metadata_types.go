package main

import (
	"strings"

	"gopkg.in/yaml.v3"

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
	Name                string            `yaml:"name"`
	Source              string            `yaml:"source"`
	Type                string            `yaml:"type"`
	Constraints         []string          `yaml:"constraints"`
	APIExposure         string            `yaml:"api_exposure"`
	EnumRef             string            `yaml:"enum_ref"`
	ClientDartName      string            `yaml:"client_dart_name"`
	ClientDartType      string            `yaml:"client_dart_type"`
	ClientParameterType string            `yaml:"client_parameter_type"`
	ClientDefault       string            `yaml:"client_default"`
	ClientNormalization string            `yaml:"client_normalization"`
	ClientWire          string            `yaml:"client_wire"`
	ClientEnumMembers   map[string]string `yaml:"client_enum_members"`
	ClientWireName      string            `yaml:"client_wire_name"`
	ClientOmitEmpty     bool              `yaml:"client_omit_empty"`
	ClientSpreadBody    bool              `yaml:"client_spread_body"`
	ItemEntity          string            `yaml:"item_entity"`
	ObjectRef           string            `yaml:"object_ref"`
	MaxUTF8Bytes        int               `yaml:"max_utf8_bytes"`
}

type entityDef struct {
	Fields []fieldDef `yaml:"fields"`
}

type fieldsFile struct {
	Entity       string               `yaml:"entity"`
	Entities     map[string]entityDef `yaml:"entities"`
	Fields       []fieldDef           `yaml:"fields"`
	Types        map[string]entityDef `yaml:"types"`
	ValueObjects map[string]entityDef `yaml:"value_objects"`
	// Members 承载 `members:` 下的 owned_entity 声明。它与 `types:` 是同一种「聚合内
	// 嵌套结构」的两种写法，DTO 生成按名字查找，不关心声明落在哪个键下；漏读会让
	// 契约里明明存在的成员在生成期表现为"实体缺失"。
	Members map[string]entityDef `yaml:"members"`
}

// ── post/operations.yaml ─────────────────────────────────────────────────────────

type requestBindingDef struct {
	Name     string `yaml:"name"`
	Field    string `yaml:"field"`
	Required *bool  `yaml:"required"`
}

type requestBindingsDef struct {
	Path     []requestBindingDef `yaml:"path"`
	Query    []requestBindingDef `yaml:"query"`
	Header   []requestBindingDef `yaml:"header"`
	Injected []requestBindingDef `yaml:"injected"`
}

type routeDef struct {
	Method          string             `yaml:"method"`
	Path            string             `yaml:"path"`
	Operation       string             `yaml:"operation"`
	Description     string             `yaml:"description"`
	RequestBindings requestBindingsDef `yaml:"request_bindings"`
	ResponseFields  []string           `yaml:"response_fields"`
	RequestEntity   string             `yaml:"request_entity"`
	RequestBodyKind string             `yaml:"request_body_kind"`
	ResponseEntity  string             `yaml:"response_entity"`
	// 框架级响应契约（R-ID02）：response_body 指向 projection read_model。
	// response_body_kind ∈ object|page|ack|upgrade；ack 可以返回 typed receipt，
	// 也可以与 upgrade 一样使用 void/decodeEmptyResponse 表达无 JSON 响应体。
	ResponseBody     string `yaml:"response_body"`
	ResponseBodyKind string `yaml:"response_body_kind"`
}

func (r routeDef) queryBindingNames() []string {
	names := make([]string, 0, len(r.RequestBindings.Query))
	for _, binding := range r.RequestBindings.Query {
		if name := strings.TrimSpace(binding.Name); name != "" {
			names = append(names, name)
		}
	}
	return names
}

type serviceInfo struct {
	Name   string `yaml:"name"`
	Domain string `yaml:"domain"`
}

type serviceFile struct {
	Service   serviceInfo `yaml:"service"`
	APIRoutes []routeDef  `yaml:"api_routes"`
}

// ── {domain}/{entity}/projections/*.yaml ─────────────────────────────────────

type projectionFieldDef struct {
	Name        string `yaml:"name"`
	WireName    string `yaml:"wire_name"`
	DartType    string `yaml:"dart_type"`
	WireType    string `yaml:"type"`
	EnumRef     string `yaml:"enum_ref"`
	Nullable    bool   `yaml:"nullable"`
	Source      string `yaml:"source"`
	Default     string `yaml:"default"`
	Description string `yaml:"description"`
	// When dart_type is List<SomeDto>, set to SomeDto; fromMap uses SomeDto.fromMap per element.
	ListElementDartClass string `yaml:"list_element_dart_class"`
	// When dart_type is a class with SomeDto.fromMap(Map<String,dynamic>) and wire is a JSON object.
	MapFromStringKeyClass string `yaml:"map_from_string_key_class"`
	// The following two properties are derived by generators when a projection
	// reuses an enum owned by a generated domain operation contract. They are
	// intentionally unavailable to YAML so contracts cannot restate the Dart
	// codec ABI as a second truth source.
	DartEnumDecoderWithPath bool   `yaml:"-"`
	DartEnumWireGetter      string `yaml:"-"`
}

func (field *projectionFieldDef) UnmarshalYAML(node *yaml.Node) error {
	if node.Kind == yaml.ScalarNode {
		field.Name = strings.TrimSpace(node.Value)
		return nil
	}
	type rawProjectionFieldDef projectionFieldDef
	return node.Decode((*rawProjectionFieldDef)(field))
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
	ReadModel                      string               `yaml:"read_model"`
	ClientProjection               clientProjection     `yaml:"client_projection"`
	Fields                         []projectionFieldDef `yaml:"fields"`
	clientProjectionFieldsDeclared bool
}

// projectionBinding 只承载 operation response_body 解析所需的投影身份和端侧类型绑定。
// 这条链路不读取 projection.fields，避免简写字段列表影响强类型绑定索引。
type projectionBinding struct {
	ReadModel        string           `yaml:"read_model"`
	ClientProjection clientProjection `yaml:"client_projection"`
}

// ── errors.yaml ───────────────────────────────────────────────────────────────

type errorDef = contractcodegen.ErrorDefinition
type errorsFile = contractcodegen.ErrorsFile

// ── ui_config.yaml ────────────────────────────────────────────────────────────

type discoveryTabDef struct {
	ID          string `yaml:"id"`
	LabelKey    string `yaml:"label_key"`
	Icon        string `yaml:"icon"`
	ContentType string `yaml:"content_type"`
	Layout      string `yaml:"layout"`
	Order       int    `yaml:"order"`
}

// homeChannelDef：首页频道运营可配置项（端 meta 默认 + /config/app 远程覆盖）。
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
	FeedRequestTypeByCategory      map[string]string                  `yaml:"feed_request_type_by_category"`
	HomeChannels                   []homeChannelDef                   `yaml:"home_channels"`
	DiscoveryTabs                  []discoveryTabDef                  `yaml:"discovery_tabs"`
	DiscoveryRails                 []discoveryRailDef                 `yaml:"discovery_rails"`
	CreationIdentityFilters        []identityFilterDef                `yaml:"creation_identity_filters"`
	WorkFormatFilters              []workFormatFilterDef              `yaml:"work_format_filters"`
	OnboardingInterestCatalog      onboardingInterestCatalogDef       `yaml:"onboarding_interest_catalog"`
	HeaderLayout                   profileHeaderLayoutDef             `yaml:"header_layout"`
	ScrollMotion                   profileScrollMotionDef             `yaml:"scroll_motion"`
	CareerInterestCatalog          careerInterestCatalogDef           `yaml:"career_interest_catalog"`
	ProfileTabs                    []profileTabDef                    `yaml:"profile_tabs"`
	HomepageTabs                   []homepageTabDef                   `yaml:"homepage_tabs"`
	HomepageSubTabs                []homepageSubTabDef                `yaml:"homepage_sub_tabs"`
	HomepageWishlistTypes          []string                           `yaml:"homepage_wishlist_types"`
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

type onboardingInterestCatalogDef struct {
	MinSelectionCount int                              `yaml:"min_selection_count"`
	MaxSelectionCount int                              `yaml:"max_selection_count"`
	Dimensions        []onboardingInterestDimensionDef `yaml:"dimensions"`
}

type onboardingInterestDimensionDef struct {
	ID            string `yaml:"id"`
	TagRef        string `yaml:"tag_ref"`
	DisplayLabel  string `yaml:"display_label"`
	MinSelections int    `yaml:"min_selections"`
	MaxSelections int    `yaml:"max_selections"`
	Order         int    `yaml:"order"`
}

// ── _shared/request_context.yaml ──────────────────────────────────────────────

type requestContextFile struct {
	DomainOperationPageIDs map[string]map[string]string `yaml:"domain_operation_page_ids"`
}

var sharedRequestContext requestContextFile

type appRouteDef struct {
	ID          string   `yaml:"id"`
	Path        string   `yaml:"path"`
	QueryParams []string `yaml:"query_params"`
}

// app_routes.yaml 只描述端内导航，不承载 HTTP request_bindings，
// 因此 query 绑定名就是 query_params 本身。
func (r appRouteDef) queryBindingNames() []string {
	return r.QueryParams
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

// ── _shared/app_pages.yaml + ops/product_ops/event_record/event_catalog.yaml ────────────

type appPageDef struct {
	PageName          string `yaml:"page_name"`
	RouteID           string `yaml:"route_id"`
	InternalID        string `yaml:"internal_id"`
	Location          string `yaml:"location"`
	CollectPageAccess bool   `yaml:"collect_page_access"`
}

type appPagesFile struct {
	Pages            []appPageDef `yaml:"pages"`
	InternalPages    []appPageDef `yaml:"internal_pages"`
	FallbackContexts []string     `yaml:"fallback_contexts"`
}

type telemetryExtensionDef struct {
	Type          string   `yaml:"type"`
	Enum          []string `yaml:"enum"`
	Minimum       *int     `yaml:"minimum"`
	Maximum       *int     `yaml:"maximum"`
	MaxLength     int      `yaml:"max_length"`
	MaxItems      int      `yaml:"max_items"`
	ItemMaxLength int      `yaml:"item_max_length"`
	Sensitive     bool     `yaml:"sensitive"`
}

type telemetryEventDef struct {
	EventType          string   `yaml:"event_type"`
	LogType            string   `yaml:"log_type"`
	RequiredExtensions []string `yaml:"required_extensions"`
	OptionalExtensions []string `yaml:"optional_extensions"`
	NormalSampleRate   float64  `yaml:"normal_sample_rate"`
	SlowThresholdMS    int      `yaml:"slow_threshold_ms"`
	InternalPriority   string   `yaml:"internal_priority"`
}

type telemetryEventCatalogFile struct {
	LogTypes          []string                         `yaml:"log_types"`
	NetworkClasses    []string                         `yaml:"network_classes"`
	CommonFields      []string                         `yaml:"common_fields"`
	ContextExtensions []string                         `yaml:"context_extensions"`
	ExtensionFields   map[string]telemetryExtensionDef `yaml:"extension_fields"`
	Events            []telemetryEventDef              `yaml:"events"`
}

type contentPublicationPolicyFile struct {
	Schema               string                            `yaml:"schema"`
	TextLimits           contentPublicationTextLimitsDef   `yaml:"text_limits"`
	FormatRecommendation contentPublicationFormatPolicyDef `yaml:"format_recommendation"`
	RateLimit            contentPublicationRateLimitDef    `yaml:"rate_limit"`
	Safety               contentPublicationSafetyPolicyDef `yaml:"safety"`
}

type contentPublicationTextLimitsDef struct {
	TitleMaxRunes            int `yaml:"title_max_runes"`
	MicroBodyMaxRunes        int `yaml:"micro_body_max_runes"`
	ArticleMarkdownMaxRunes  int `yaml:"article_markdown_max_runes"`
	SummaryMaxRunes          int `yaml:"summary_max_runes"`
	SemanticMentionsMaxItems int `yaml:"semantic_mentions_max_items"`
}

type contentPublicationFormatPolicyDef struct {
	ArticleBodyMinRunes      int  `yaml:"article_body_min_runes"`
	ArticleParagraphMinCount int  `yaml:"article_paragraph_min_count"`
	ArticleWhenTitlePresent  bool `yaml:"article_when_title_present"`
	ArticleWhenMediaPresent  bool `yaml:"article_when_media_present"`
	UserConfirmationRequired bool `yaml:"user_confirmation_required"`
}

type contentPublicationRateLimitDef struct {
	PersonaWindowSeconds   int    `yaml:"persona_window_seconds"`
	PersonaMaxPublications int    `yaml:"persona_max_publications"`
	DependencyFailure      string `yaml:"dependency_failure"`
}

type contentPublicationSafetyPolicyDef struct {
	Required             bool     `yaml:"required"`
	DependencyFailure    string   `yaml:"dependency_failure"`
	Decisions            []string `yaml:"decisions"`
	UnavailableAction    string   `yaml:"unavailable_action"`
	RejectErrorCode      string   `yaml:"reject_error_code"`
	UnavailableErrorCode string   `yaml:"unavailable_error_code"`
}

type contentMediaUploadPolicyFile struct {
	Schema            string                               `yaml:"schema"`
	StreamingRequired bool                                 `yaml:"streaming_required"`
	MediaTypes        map[string]contentMediaUploadTypeDef `yaml:"media_types"`
	Errors            contentMediaUploadErrorDef           `yaml:"errors"`
}

type contentMediaUploadTypeDef struct {
	MaxFileSizeBytes    int      `yaml:"max_file_size_bytes"`
	AllowedContentTypes []string `yaml:"allowed_content_types"`
}

type contentMediaUploadErrorDef struct {
	FileTooLarge    string `yaml:"file_too_large"`
	UnsupportedType string `yaml:"unsupported_type"`
}

type contentImageVariantPolicyFile struct {
	Schema                  string                                   `yaml:"schema"`
	DerivativePolicyVersion int                                      `yaml:"derivative_policy_version"`
	Profiles                map[string]contentImageVariantProfileDef `yaml:"profiles"`
}

type contentImageVariantProfileDef struct {
	Width      int    `yaml:"width"`
	Format     string `yaml:"format"`
	Quality    int    `yaml:"quality"`
	Scene      string `yaml:"scene"`
	Processing string `yaml:"processing"`
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
