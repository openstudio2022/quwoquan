package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

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
	QueryParams    []string `yaml:"query_params"`
	WritableFields []string `yaml:"writable_fields"`
}

type serviceFile struct {
	APIRoutes []routeDef `yaml:"api_routes"`
}

// ── _projections/*.yaml ───────────────────────────────────────────────────────

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
	ReadModel         string           `yaml:"read_model"`
	ClientProjection  clientProjection `yaml:"client_projection"`
}

// ── errors.yaml ───────────────────────────────────────────────────────────────

type errorDef struct {
	Code               string            `yaml:"code"`
	Kind               string            `yaml:"kind"`
	Reason             string            `yaml:"reason"`
	HTTPStatus         int               `yaml:"http_status"`
	Retryable          bool              `yaml:"retryable"`
	RetryAfterSeconds  int               `yaml:"retry_after_seconds"`
	DartConst          string            `yaml:"dart_const"`
	GoConst            string            `yaml:"go_const"`
	UserMessage        map[string]string `yaml:"user_message"`
}

type errorsFile struct {
	Domain string     `yaml:"domain"`
	Errors []errorDef `yaml:"errors"`
}

// ── behaviors.yaml ─────────────────────────────────────────────────────────────

type behaviorEventDef struct {
	Type          string   `yaml:"type"`
	Description   string   `yaml:"description"`
	Trigger       string   `yaml:"trigger"`
	Batch         bool     `yaml:"batch"`
	BatchRoute    string   `yaml:"batch_route"`
	DartMethod    string   `yaml:"dart_method"`
	DedicatedRoute string  `yaml:"dedicated_route"`
	PayloadFields []string `yaml:"payload_fields"`
	MLSignal      string   `yaml:"ml_signal"`
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
	ID             string  `yaml:"id"`
	LabelKey       string  `yaml:"label_key"`
	Icon           string  `yaml:"icon"`
	ContentType    string  `yaml:"content_type"`
	Layout         string  `yaml:"layout"`
	Order          int     `yaml:"order"`
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
	DiscoveryTabs []discoveryTabDef        `yaml:"discovery_tabs"`
	FeatureFlags  []featureFlagDef         `yaml:"feature_flags"`
	EmptyStates   map[string]emptyStateDef `yaml:"empty_states"`
}

// ── main ──────────────────────────────────────────────────────────────────────

func main() {
	var metadataDir string
	var appDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&appDir, "app-dir", "../quwoquan_app", "app root directory")
	flag.Parse()

	shared, err := readShared(filepath.Join(metadataDir, "_shared", "types.yaml"))
	if err != nil {
		exitErr(err)
	}
	// Support both legacy (post/) and domain-centric (content/post/) locations.
	postDir := filepath.Join(metadataDir, "post")
	if _, statErr := os.Stat(postDir); os.IsNotExist(statErr) {
		postDir = filepath.Join(metadataDir, "content", "post")
	}
	fields, err := readFields(filepath.Join(postDir, "fields.yaml"))
	if err != nil {
		exitErr(err)
	}
	service, err := readService(filepath.Join(postDir, "service.yaml"))
	if err != nil {
		exitErr(err)
	}
	// discovery_feed projection: try legacy _projections/ first, then post/projections/
	feedProjPath := filepath.Join(metadataDir, "_projections", "discovery_feed.yaml")
	if _, statErr := os.Stat(feedProjPath); os.IsNotExist(statErr) {
		feedProjPath = filepath.Join(postDir, "projections", "discovery_feed.yaml")
	}
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

	// 2. 生成 feed_item_dto.g.dart（FeedItemDto 强类型 DTO）
	if len(projection.ClientProjection.Fields) > 0 {
		dtoOut := renderFeedItemDtoDart(projection.ClientProjection)
		dtoRelPath := projection.ClientProjection.OutputPath
		if dtoRelPath == "" {
			dtoRelPath = "cloud/runtime/generated/content/feed_item_dto.g.dart"
		}
		dtoPath := filepath.Join(appDir, "lib", dtoRelPath)
		writeFile(dtoPath, dtoOut)
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

	// 3. 生成带 base_class 的 typed post DTOs（photo/video/article/moment）
	// 优先扫描 content/post/projections/（新规范），回退到 post/projections/，再回退到 _projections/
	projDirNew := filepath.Join(postDir, "projections")
	projDirLegacy := filepath.Join(metadataDir, "_projections")

	projDir := projDirNew
	if _, statErr := os.Stat(projDirNew); os.IsNotExist(statErr) {
		projDir = projDirLegacy
	}

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

func readProjection(path string) (*projectionFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed projectionFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

// ── builders ──────────────────────────────────────────────────────────────────

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

// ── renderers ─────────────────────────────────────────────────────────────────

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

// renderFeedItemDtoDart generates the strongly-typed FeedItemDto class
// from discovery_feed.yaml client_projection section.
func renderFeedItemDtoDart(proj clientProjection) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from _projections/discovery_feed.yaml. DO NOT EDIT.\n")
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
	"authorId":            true,
	"displayName":         true,
	"avatarUrl":           true,
	"authorBackgroundUrl": true,
	"likeCount":           true,
	"commentCount":        true,
	"favoriteCount":       true,
	"shareCount":          true,
	"createdAt":           true,
}

// renderTypedPostDtoDart generates a typed DTO that extends a base class (e.g. PostBaseDto).
func renderTypedPostDtoDart(proj clientProjection, sourceFile string) string {
	var b strings.Builder
	className := proj.DartClass
	baseClass := proj.BaseClass

	b.WriteString(fmt.Sprintf("// Code generated by tools/codegen_app_metadata from _projections/%s. DO NOT EDIT.\n", sourceFile))
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

	// DiscoveryTabConfig class
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

	// Sort tabs by order
	tabs := uc.DiscoveryTabs
	sort.Slice(tabs, func(i, j int) bool { return tabs[i].Order < tabs[j].Order })

	// ContentUIConfig class
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("class ContentUIConfig {\n")
	b.WriteString("  const ContentUIConfig._();\n\n")

	// discoveryTabs
	b.WriteString("  static const List<DiscoveryTabConfig> discoveryTabs = <DiscoveryTabConfig>[\n")
	for _, tab := range tabs {
		b.WriteString(fmt.Sprintf("    DiscoveryTabConfig(id: '%s', labelKey: '%s', icon: '%s', contentType: '%s', layout: '%s'),\n",
			tab.ID, tab.LabelKey, tab.Icon, tab.ContentType, tab.Layout))
	}
	b.WriteString("  ];\n\n")

	// featureFlags
	b.WriteString("  static const Map<String, bool> featureFlags = <String, bool>{\n")
	// Sort by flag name for determinism
	flags := make([]featureFlagDef, len(uc.FeatureFlags))
	copy(flags, uc.FeatureFlags)
	sort.Slice(flags, func(i, j int) bool { return flags[i].Flag < flags[j].Flag })
	for _, ff := range flags {
		b.WriteString(fmt.Sprintf("    '%s': %v,\n", ff.Flag, ff.Default))
	}
	b.WriteString("  };\n\n")

	// emptyStates
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

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_app_metadata error: %v\n", err)
	os.Exit(1)
}
