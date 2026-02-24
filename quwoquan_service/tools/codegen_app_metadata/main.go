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
	fields, err := readFields(filepath.Join(metadataDir, "post", "fields.yaml"))
	if err != nil {
		exitErr(err)
	}
	service, err := readService(filepath.Join(metadataDir, "post", "service.yaml"))
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

	out := renderGeneratedDart(
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
	)
	outPath := filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "post_runtime_metadata.g.dart")
	if err := os.MkdirAll(filepath.Dir(outPath), 0755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(outPath, []byte(out), 0644); err != nil {
		exitErr(err)
	}
	fmt.Printf("generated: %s\n", outPath)
}

func readShared(path string) (*sharedTypes, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed sharedTypes
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return nil, err
	}
	return &parsed, nil
}

func readFields(path string) (*fieldsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed fieldsFile
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return nil, err
	}
	return &parsed, nil
}

func readService(path string) (*serviceFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed serviceFile
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return nil, err
	}
	return &parsed, nil
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
	return map[string]string{
		"likes":            get("likeCount", "0"),
		"likesCount":       get("likeCount", "0"),
		"comments":         get("commentCount", "0"),
		"commentsCount":    get("commentCount", "0"),
		"bookmarks":        get("favoriteCount", "0"),
		"savesCount":       get("favoriteCount", "0"),
		"shares":           get("shareCount", "0"),
		"visibility":       get("visibility", "'public'"),
		"tags":             get("tags", "<String>[]"),
		"images":           "<String>[]",
		"videoUrl":         get("videoUrl", "''"),
		"coverUrl":         get("coverUrl", "''"),
		"thumbnailUrl":     get("coverUrl", "''"),
		"isLocalGenerated": "true",
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

func renderGeneratedDart(
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
) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata. DO NOT EDIT.\n")
	b.WriteString("class GeneratedPostRuntimeMetadata {\n")
	b.WriteString("  const GeneratedPostRuntimeMetadata._();\n\n")

	b.WriteString("  static const Map<String, dynamic> postFieldDefaults = <String, dynamic>{\n")
	writeSortedMap(&b, postDefaults)
	b.WriteString("  };\n\n")

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
	b.WriteString("  ];\n")
	b.WriteString("}\n")
	return b.String()
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

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_app_metadata error: %v\n", err)
	os.Exit(1)
}
