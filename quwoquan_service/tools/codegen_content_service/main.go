package main

import (
	"bytes"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"text/template"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	var metadataDir string
	var outputRoot string
	var aggregate string
	var routeService string
	var check bool
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputRoot, "output-dir", "services/content-service/generated", "content-service generated root directory")
	flag.StringVar(&aggregate, "aggregate", "Post", "aggregate name to generate")
	flag.StringVar(
		&routeService,
		"route-service",
		"content-service",
		"service.name whose complete object route union is generated",
	)
	flag.BoolVar(&check, "check", false, "fail when generated outputs are stale")
	flag.Parse()
	originalOutputRoot := filepath.Clean(outputRoot)
	if check {
		temporaryRoot, err := os.MkdirTemp("", "content-service-codegen-check-")
		if err != nil {
			exitErr(err)
		}
		defer os.RemoveAll(temporaryRoot)
		outputRoot = temporaryRoot
	}

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	postOutputDir := filepath.Join(outputRoot, "content", "post")
	generator := contractcodegen.NewDomainGenerator(
		source,
		filepath.Clean(postOutputDir),
		contractcodegen.WithObjectFirstRoot(),
		contractcodegen.WithSliceEntityRefs(),
	)
	if err := generator.GenerateDomainModel(aggregate); err != nil {
		exitErr(fmt.Errorf("generate model %s: %w", aggregate, err))
	}
	if err := generator.GenerateDomainEvents(aggregate); err != nil {
		exitErr(fmt.Errorf("generate events %s: %w", aggregate, err))
	}
	routeGroups, err := loadServiceRoutes(source, routeService)
	if err != nil {
		exitErr(fmt.Errorf("load routes for service %s: %w", routeService, err))
	}
	if err := generateContracts(source, routeGroups, outputRoot); err != nil {
		exitErr(fmt.Errorf("generate contracts for service routes %s: %w", routeService, err))
	}
	if err := generatePostPublicationPolicy(source, postOutputDir); err != nil {
		exitErr(fmt.Errorf("generate Post publication policy: %w", err))
	}
	if err := generateOnboardingInterestCatalog(source, postOutputDir); err != nil {
		exitErr(fmt.Errorf("generate onboarding interest catalog: %w", err))
	}
	if err := generateContentMediaUploadPolicy(source, filepath.Join(outputRoot, "media", "media_upload_session")); err != nil {
		exitErr(fmt.Errorf("generate content media upload policy: %w", err))
	}
	if err := generateContentImageVariantPolicy(source, filepath.Join(outputRoot, "media", "media_asset")); err != nil {
		exitErr(fmt.Errorf("generate content image variant policy: %w", err))
	}
	if err := generateContentMediaOriginalAccessPolicy(source, filepath.Join(outputRoot, "media", "original_access_quota")); err != nil {
		exitErr(fmt.Errorf("generate content media original access policy: %w", err))
	}
	if err := generateHTTPScaffold(routeGroups, outputRoot); err != nil {
		exitErr(fmt.Errorf("generate http scaffold for service routes %s: %w", routeService, err))
	}
	if err := generateErrorConstants(source, outputRoot); err != nil {
		exitErr(fmt.Errorf("generate error constants for %s: %w", aggregate, err))
	}
	if check {
		if err := verifyGeneratedTree(outputRoot, originalOutputRoot); err != nil {
			exitErr(err)
		}
		fmt.Printf("verified content-service generated outputs at %s\n", originalOutputRoot)
		return
	}
	fmt.Printf(
		"generated content-service domain for aggregate=%s route-service=%s at %s\n",
		aggregate,
		routeService,
		outputRoot,
	)
}

func verifyGeneratedTree(actualRoot, expectedRoot string) error {
	return filepath.WalkDir(actualRoot, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		relativePath, err := filepath.Rel(actualRoot, path)
		if err != nil {
			return err
		}
		actual, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		expectedPath := filepath.Join(expectedRoot, relativePath)
		expected, err := os.ReadFile(expectedPath)
		if err != nil {
			return fmt.Errorf("read generated output %s: %w", expectedPath, err)
		}
		if !bytes.Equal(actual, expected) {
			return fmt.Errorf("generated content-service output is stale: %s", expectedPath)
		}
		return nil
	})
}

type contractData struct {
	PackageName string
	Aggregate   string
	Routes      []routeData
	ContentType []string
}

type routeData struct {
	ConstName string
	Method    string
	Path      string
	Operation string
}

type operationsYAML struct {
	APIRoutes []serviceRouteYAML `yaml:"api_routes"`
}

type serviceRouteYAML struct {
	Method            string              `yaml:"method"`
	Path              string              `yaml:"path"`
	Operation         string              `yaml:"operation"`
	RequestEntity     string              `yaml:"request_entity"`
	RequestBodyKind   string              `yaml:"request_body_kind"`
	RequestBindings   requestBindingsYAML `yaml:"request_bindings"`
	Pagination        paginationYAML      `yaml:"pagination"`
	RequestBodyFields []string            `yaml:"-"`
}

type paginationYAML struct {
	DefaultItems int `yaml:"default_items"`
	MaximumItems int `yaml:"maximum_items"`
}

type requestBindingsYAML struct {
	Path     []requestBindingYAML `yaml:"path"`
	Query    []requestBindingYAML `yaml:"query"`
	Header   []requestBindingYAML `yaml:"header"`
	Injected []requestBindingYAML `yaml:"injected"`
}

type requestBindingYAML struct {
	Name  string `yaml:"name"`
	Field string `yaml:"field"`
}

type serviceRequestFieldYAML struct {
	Name           string `yaml:"name"`
	ClientWireName string `yaml:"client_wire_name"`
}

type serviceRequestEntityYAML struct {
	Fields []serviceRequestFieldYAML `yaml:"fields"`
}

type serviceFieldsYAML struct {
	Entity       string                              `yaml:"entity"`
	Fields       []serviceRequestFieldYAML           `yaml:"fields"`
	Entities     map[string]serviceRequestEntityYAML `yaml:"entities"`
	Types        map[string]serviceRequestEntityYAML `yaml:"types"`
	ValueObjects map[string]serviceRequestEntityYAML `yaml:"value_objects"`
	Members      map[string]serviceRequestEntityYAML `yaml:"members"`
}

type objectRouteGroup struct {
	Context    string
	Object     string
	SourcePath string
	Routes     []serviceRouteYAML
}

func generateContracts(
	source *contractcodegen.Source,
	groups []objectRouteGroup,
	outputRoot string,
) error {
	for _, group := range groups {
		if len(group.Routes) == 0 {
			continue
		}
		routes := make([]routeData, 0, len(group.Routes))
		for _, r := range group.Routes {
			if strings.TrimSpace(r.Path) == "" || strings.TrimSpace(r.Method) == "" {
				continue
			}
			routes = append(routes, routeData{
				ConstName: "Route" + toPascal(r.Operation),
				Method:    strings.ToUpper(r.Method),
				Path:      r.Path,
				Operation: r.Operation,
			})
		}
		sort.Slice(routes, func(i, j int) bool { return routes[i].ConstName < routes[j].ConstName })
		var contentTypes []string
		if group.Context == "content" && group.Object == "post" {
			var shared struct {
				Enums map[string][]string `yaml:"enums"`
			}
			if err := source.Decode("_shared/types.yaml", &shared); err != nil {
				return err
			}
			contentTypes = shared.Enums["ContentType"]
		}
		data := contractData{
			PackageName: "generated",
			Aggregate:   group.Object,
			Routes:      routes,
			ContentType: contentTypes,
		}
		const tmpl = `// Code generated by tools/codegen_content_service from {{.SourcePath}}. DO NOT EDIT.
package {{.PackageName}}

const (
{{- range .Routes }}
	{{ .ConstName }}Method = "{{ .Method }}"
	{{ .ConstName }}Path = "{{ .Path }}"
{{- end }}
)

var AllowedContentTypes = map[string]struct{}{
{{- range .ContentType }}
	"{{ . }}": {},
{{- end }}
}
`
		t, err := template.New("contracts").Parse(tmpl)
		if err != nil {
			return err
		}
		dataWithSource := struct {
			contractData
			SourcePath string
		}{contractData: data, SourcePath: group.SourcePath}
		var buf bytes.Buffer
		if err := t.Execute(&buf, dataWithSource); err != nil {
			return err
		}
		out := buf.Bytes()
		if formatted, err := format.Source(out); err == nil {
			out = formatted
		}
		targetDir := filepath.Join(outputRoot, group.Context, group.Object)
		if err := os.MkdirAll(targetDir, 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(targetDir, "contracts.go"), out, 0o644); err != nil {
			return err
		}
	}
	return nil
}

func toPascal(s string) string {
	if strings.TrimSpace(s) == "" {
		return ""
	}
	parts := strings.FieldsFunc(s, func(r rune) bool {
		return r == '_' || r == '-' || r == ' '
	})
	var b strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		b.WriteString(strings.ToUpper(part[:1]))
		if len(part) > 1 {
			b.WriteString(part[1:])
		}
	}
	return b.String()
}

type routeBindingData struct {
	Method            string
	Path              string
	Operation         string
	QueryBindingNames []string
	RequestBodyFields []string
}

type httpScaffoldData struct {
	Routes                   []routeBindingData
	DispatchOperations       []string
	BodyOperations           []string
	BodyFieldsByOperation    map[string][]string
	GetFeedRouteFound        bool
	GetFeedQueryBindingNames []string
	GetFeedLimitInQuery      bool
	GetFeedDefaultItems      int
	GetFeedMaximumItems      int
}

func generateHTTPScaffold(
	groups []objectRouteGroup,
	outputRoot string,
) error {
	for _, group := range groups {
		if len(group.Routes) == 0 {
			continue
		}
		if err := generateObjectHTTPScaffold(
			group.Routes,
			filepath.Join(outputRoot, group.Context, group.Object),
			group.SourcePath,
		); err != nil {
			return fmt.Errorf("generate %s/%s routes: %w", group.Context, group.Object, err)
		}
	}
	return nil
}

func generateObjectHTTPScaffold(
	serviceRoutes []serviceRouteYAML,
	outputDir string,
	sourcePath string,
) error {
	data := httpScaffoldData{
		Routes:                make([]routeBindingData, 0, len(serviceRoutes)),
		BodyFieldsByOperation: map[string][]string{},
	}
	for _, r := range serviceRoutes {
		if strings.TrimSpace(r.Method) == "" || strings.TrimSpace(r.Path) == "" || strings.TrimSpace(r.Operation) == "" {
			continue
		}
		qp := make([]string, 0, len(r.RequestBindings.Query))
		seenQP := map[string]struct{}{}
		for _, binding := range r.RequestBindings.Query {
			k := strings.TrimSpace(binding.Name)
			if k == "" {
				continue
			}
			if _, ok := seenQP[k]; ok {
				continue
			}
			seenQP[k] = struct{}{}
			qp = append(qp, k)
		}
		bodyFields := make([]string, 0, len(r.RequestBodyFields))
		seenBodyFields := map[string]struct{}{}
		for _, field := range r.RequestBodyFields {
			f := strings.TrimSpace(field)
			if f == "" {
				continue
			}
			if _, ok := seenBodyFields[f]; ok {
				continue
			}
			seenBodyFields[f] = struct{}{}
			bodyFields = append(bodyFields, f)
		}
		data.Routes = append(data.Routes, routeBindingData{
			Method:            strings.ToUpper(r.Method),
			Path:              r.Path,
			Operation:         r.Operation,
			QueryBindingNames: qp,
			RequestBodyFields: bodyFields,
		})
		if strings.TrimSpace(r.RequestBodyKind) == "object" {
			data.BodyFieldsByOperation[r.Operation] = bodyFields
		}
		if r.Operation == "GetFeed" {
			data.GetFeedRouteFound = true
			data.GetFeedQueryBindingNames = qp
			data.GetFeedDefaultItems = r.Pagination.DefaultItems
			data.GetFeedMaximumItems = r.Pagination.MaximumItems
			for _, key := range qp {
				if key == "limit" {
					data.GetFeedLimitInQuery = true
					break
				}
			}
			if !data.GetFeedLimitInQuery {
				return fmt.Errorf("GetFeed must bind the limit query parameter")
			}
			if data.GetFeedDefaultItems <= 0 || data.GetFeedMaximumItems <= 0 ||
				data.GetFeedDefaultItems > data.GetFeedMaximumItems {
				return fmt.Errorf("GetFeed must declare a valid pagination budget")
			}
		}
	}
	dispatchSet := map[string]struct{}{}
	for _, route := range data.Routes {
		dispatchSet[route.Operation] = struct{}{}
	}
	for op := range dispatchSet {
		data.DispatchOperations = append(data.DispatchOperations, op)
	}
	sort.Strings(data.DispatchOperations)
	for op := range data.BodyFieldsByOperation {
		data.BodyOperations = append(data.BodyOperations, op)
	}
	sort.Strings(data.BodyOperations)
	sort.Slice(data.Routes, func(i, j int) bool {
		if data.Routes[i].Path == data.Routes[j].Path {
			return data.Routes[i].Method < data.Routes[j].Method
		}
		return data.Routes[i].Path < data.Routes[j].Path
	})
	const tmpl = `// Code generated by tools/codegen_content_service. DO NOT EDIT.
package http

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

func RegisterGeneratedRoutes(mux *http.ServeMux, h *ContentHandler) {
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		op, ok := resolveGeneratedOperation(r)
		if !ok {
			rterr.WriteHTTPError(
				w,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
					"接口不存在或已下线",
					"generated content route not found",
				),
				rterr.HTTPWriteOptionsFromRequest(r),
			)
			return
		}
		dispatchGeneratedOperation(h, op, w, r)
	})
}

func dispatchGeneratedOperation(h *ContentHandler, operation string, w http.ResponseWriter, r *http.Request) {
	switch operation {
{{- range .DispatchOperations }}
	case "{{ . }}":
		{{- if eq . "GetFeed" }}
		h.handleGetFeed(w, r)
		{{- else if eq . "GetPost" }}
		h.handleGetPost(w, r)
		{{- else if eq . "ListUserPosts" }}
		h.handleListUserPosts(w, r)
		{{- else if eq . "SubmitPostPublication" }}
		h.handleSubmitPostPublication(w, r)
		{{- else if eq . "CreateReport" }}
		h.handleCreateReport(w, r)
		{{- else if eq . "ListReports" }}
		h.handleListReports(w, r)
		{{- else if eq . "ListMyReports" }}
		h.handleListMyReports(w, r)
		{{- else if eq . "GetReport" }}
		h.handleGetReport(w, r)
		{{- else if eq . "BeginReportReview" }}
		h.handleBeginReportReview(w, r)
		{{- else if eq . "DismissReport" }}
		h.handleDismissReport(w, r)
		{{- else if eq . "ResolveReport" }}
		h.handleResolveReport(w, r)
		{{- else if eq . "UpdatePostSettings" }}
		h.handleUpdatePostSettings(w, r)
		{{- else if eq . "PromotePostToWork" }}
		h.handlePromotePostToWork(w, r)
		{{- else if eq . "DeletePost" }}
		h.handleDeletePost(w, r)
		{{- else if eq . "ReportBehaviors" }}
		h.handleReportBehaviors(w, r)
		{{- else if eq . "CreateComment" }}
		h.handleCreateComment(w, r, strings.TrimSpace(r.PathValue("postId")))
		{{- else if eq . "DeleteComment" }}
		h.handleDeleteComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
		)
		{{- else if eq . "HideComment" }}
		h.handleHideComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("commentId")),
		)
		{{- else if eq . "RestoreComment" }}
		h.handleRestoreComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("commentId")),
		)
		{{- else if eq . "PinComment" }}
		h.handleSetCommentPinned(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
			true,
		)
		{{- else if eq . "UnpinComment" }}
		h.handleSetCommentPinned(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
			false,
		)
		{{- else if eq . "BindMediaAssetsToComment" }}
		h.handleBindMediaAssetsToComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("commentId")),
		)
		{{- else if eq . "ListComments" }}
		h.handleListComments(w, r, strings.TrimSpace(r.PathValue("postId")))
		{{- else if eq . "ListCommentReplies" }}
		h.handleListCommentReplies(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
		)
		{{- else if eq . "ListCommentsByAuthor" }}
		h.handleListCommentsByAuthor(w, r)
		{{- else if eq . "ListCommentsForPostAuthor" }}
		h.handleListCommentsForPostAuthor(w, r)
		{{- else if eq . "ReactToComment" }}
		h.handleReactToComment(w, r, strings.TrimSpace(r.PathValue("commentId")))
		{{- else if eq . "GetMyIntersectionSummary" }}
		h.handleGetMyIntersectionSummary(w, r)
		{{- else if eq . "ListMyIntersections" }}
		h.handleListMyIntersections(w, r)
		{{- else if eq . "MarkIntersectionsVisited" }}
		h.handleMarkIntersectionsVisited(w, r)
		{{- else if eq . "GetObjectIntersections" }}
		h.handleGetObjectIntersections(w, r)
		{{- else if eq . "GetAuthorImpact" }}
		h.handleGetAuthorImpact(w, r)
		{{- else if eq . "ListAuthorImpactEvidence" }}
		h.handleListAuthorImpactEvidence(w, r)
		{{- else if eq . "GetAppConfig" }}
		h.handleGetAppConfig(w, r)
		{{- else if eq . "ListProfileInteractionActivitiesReceived" }}
		h.handleListProfileInteractionActivitiesReceived(w, r)
		{{- else if eq . "ListProfileInteractionActivitiesSent" }}
		h.handleListProfileInteractionActivitiesSent(w, r)
		{{- else if eq . "AppendProfileInteractionReadFact" }}
		h.handleAppendProfileInteractionReadFact(w, r)
		{{- else if eq . "InitMediaUpload" }}
		h.handleInitMediaUpload(w, r)
		{{- else if eq . "CompleteMediaUpload" }}
		h.handleCompleteMediaUpload(w, r)
		{{- else if eq . "AbortMediaUpload" }}
		h.handleAbortMediaUpload(w, r)
		{{- else if eq . "GetMediaAsset" }}
		h.handleGetMediaAsset(w, r)
		{{- else if eq . "GetMediaAssetReference" }}
		h.handleGetMediaAssetReference(w, r)
		{{- else if eq . "GetMediaAssetDeliveryReference" }}
		h.handleGetMediaAssetDeliveryReference(w, r)
		{{- else if eq . "GetMediaUploadSession" }}
		h.handleGetMediaUploadSession(w, r)
		{{- else if eq . "GetOwnedMediaAsset" }}
		h.handleGetOwnedMediaAsset(w, r)
		{{- else if eq . "DiscardMediaAsset" }}
		h.handleDiscardMediaAsset(w, r)
		{{- else if eq . "RecordMediaProcessingResult" }}
		h.handleRecordMediaProcessingResult(w, r)
		{{- else if eq . "UpdateMediaAssetAccessPolicy" }}
		h.handleUpdateMediaAssetAccessPolicy(w, r)
		{{- else if eq . "ReserveOriginalImageAccessGrant" }}
		h.handleReserveOriginalImageAccessGrant(w, r)
		{{- else if eq . "SelectAutoVideoCover" }}
		h.handleSelectAutoVideoCover(w, r)
		{{- else if eq . "SelectManualVideoCover" }}
		h.handleSelectManualVideoCover(w, r)
		{{- else if eq . "AppendOutboundShareFact" }}
		h.handleAppendOutboundShareFact(w, r)
		{{- else if eq . "LikePost" }}
		h.handleLikePost(w, r, strings.TrimSpace(r.PathValue("postId")))
		{{- else if eq . "UnlikePost" }}
		h.handleUnlikePost(w, r, strings.TrimSpace(r.PathValue("postId")))
		{{- else if eq . "GetContentReactionState" }}
		h.handleGetReactionState(w, r, strings.TrimSpace(r.PathValue("postId")))
		{{- else if eq . "GetCounters" }}
		h.handleGetCounters(w, r, strings.TrimSpace(r.PathValue("postId")))
		{{- else if eq . "GetMyFootprint" }}
		h.handleGetMyFootprint(w, r)
		{{- else if eq . "GetEntityWishlistState" }}
		h.handleGetEntityWishlistState(w, r)
		{{- else if eq . "GenerateArticleSummary" }}
		h.handleGenerateArticleSummary(w, r)
		{{- else if eq . "GetHelperRead" }}
		h.handleGetHelperRead(w, r)
		{{- else if eq . "StageFilterCatalogRelease" }}
		h.handleStageFilterCatalogRelease(w, r)
		{{- else if eq . "ActivateFilterCatalogRelease" }}
		h.handleActivateFilterCatalogRelease(w, r)
		{{- else if eq . "RollbackFilterCatalogRelease" }}
		h.handleRollbackFilterCatalogRelease(w, r)
		{{- else if eq . "GetActiveFilterCatalog" }}
		h.handleGetActiveFilterCatalog(w, r)
		{{- else if eq . "StartMediaImageReprocessRun" }}
		h.handleStartMediaImageReprocessRun(w, r)
		{{- else if eq . "PauseMediaImageReprocessRun" }}
		h.handlePauseMediaImageReprocessRun(w, r)
		{{- else if eq . "ResumeMediaImageReprocessRun" }}
		h.handleResumeMediaImageReprocessRun(w, r)
		{{- else if eq . "RollbackMediaImageReprocessRun" }}
		h.handleRollbackMediaImageReprocessRun(w, r)
		{{- else if eq . "GetMediaImageReprocessRun" }}
		h.handleGetMediaImageReprocessRun(w, r)
		{{- else if eq . "OpenPostModerationCase" }}
		h.handleOpenPostModerationCase(w, r)
		{{- else if eq . "ReviewPostModerationCase" }}
		h.handleReviewPostModerationCase(w, r)
		{{- else if eq . "DecidePostModeration" }}
		h.handleDecidePostModeration(w, r)
		{{- else if eq . "SupersedePostModerationCase" }}
		h.handleSupersedePostModerationCase(w, r)
		{{- else if eq . "GetCurrentPostModerationCase" }}
		h.handleGetCurrentPostModerationCase(w, r)
		{{- else if eq . "GetPostPublicationEligibility" }}
		h.handleGetPostPublicationEligibility(w, r)
		{{- else }}
		h.handleNotImplemented(w, r, operation)
		{{- end }}
{{- end }}
	default:
		h.handleNotImplemented(w, r, operation)
	}
}

var generatedRouteTable = []generatedRouteDef{
{{- range .Routes }}
	{method: "{{ .Method }}", pathTemplate: "{{ .Path }}", operation: "{{ .Operation }}"},
{{- end }}
}

type generatedRouteDef struct {
	method       string
	pathTemplate string
	operation    string
}

func resolveGeneratedOperation(r *http.Request) (string, bool) {
	m := strings.ToUpper(strings.TrimSpace(r.Method))
	bestScore := -1
	bestOperation := ""
	var bestValues map[string]string
	for _, route := range generatedRouteTable {
		if route.method != m {
			continue
		}
		pathValues, matched := generatedPathValues(route.pathTemplate, r.URL.Path)
		if !matched {
			continue
		}
		score := generatedPathSpecificity(route.pathTemplate)
		if score == bestScore && bestOperation != "" && bestOperation != route.operation {
			return "", false
		}
		if score > bestScore {
			bestScore = score
			bestOperation = route.operation
			bestValues = pathValues
		}
	}
	if bestOperation == "" {
		return "", false
	}
	for name, value := range bestValues {
		r.SetPathValue(name, value)
	}
	return bestOperation, true
}

func generatedPathSpecificity(templatePath string) int {
	score := 0
	inParameter := false
	for _, char := range templatePath {
		switch char {
		case '{':
			inParameter = true
		case '}':
			inParameter = false
		default:
			if !inParameter {
				score++
			}
		}
	}
	return score
}

func generatedPathValues(templatePath, requestPath string) (map[string]string, bool) {
	tParts := generatedSplitPath(templatePath)
	rParts := generatedSplitPath(requestPath)
	if len(tParts) != len(rParts) {
		return nil, false
	}
	values := make(map[string]string)
	for i := range tParts {
		name, value, matched := generatedSegmentValue(tParts[i], rParts[i])
		if !matched {
			return nil, false
		}
		if name != "" {
			values[name] = value
		}
	}
	return values, true
}

func generatedSegmentValue(templateSegment, requestSegment string) (string, string, bool) {
	paramStart := strings.Index(templateSegment, "{")
	if paramStart < 0 {
		return "", "", templateSegment == requestSegment
	}
	paramEndOffset := strings.Index(templateSegment[paramStart:], "}")
	if paramEndOffset < 0 {
		return "", "", false
	}
	paramEnd := paramStart + paramEndOffset
	name := strings.TrimSpace(templateSegment[paramStart+1 : paramEnd])
	if name == "" {
		return "", "", false
	}
	prefix := templateSegment[:paramStart]
	suffix := templateSegment[paramEnd+1:]
	if !strings.HasPrefix(requestSegment, prefix) || !strings.HasSuffix(requestSegment, suffix) {
		return "", "", false
	}
	value := strings.TrimSuffix(strings.TrimPrefix(requestSegment, prefix), suffix)
	return name, value, value != ""
}

func generatedSplitPath(raw string) []string {
	trimmed := strings.Trim(strings.TrimSpace(raw), "/")
	if trimmed == "" {
		return []string{}
	}
	return strings.Split(trimmed, "/")
}

{{- if .GetFeedRouteFound }}
type GeneratedGetFeedParams struct {
{{- range .GetFeedQueryBindingNames }}
{{- if ne . "limit" }}
	{{ generatedGoField . }} string
{{- end }}
{{- end }}
	Limit int
}

const (
	GeneratedGetFeedDefaultItems = {{ .GetFeedDefaultItems }}
	GeneratedGetFeedMaximumItems = {{ .GetFeedMaximumItems }}
)

func BindGeneratedGetFeedParams(r *http.Request) (GeneratedGetFeedParams, error) {
	out := GeneratedGetFeedParams{Limit: GeneratedGetFeedDefaultItems}
	q := r.URL.Query()
{{- range .GetFeedQueryBindingNames }}
{{- if ne . "limit" }}
	out.{{ generatedGoField . }} = strings.TrimSpace(q.Get("{{ . }}"))
{{- end }}
{{- end }}
	rawLimit := strings.TrimSpace(q.Get("limit"))
	if rawLimit != "" {
		parsed, err := strconv.Atoi(rawLimit)
		if err != nil {
			return GeneratedGetFeedParams{}, fmt.Errorf("limit must be an integer")
		}
		out.Limit = parsed
	}
	if out.Limit <= 0 || out.Limit > GeneratedGetFeedMaximumItems {
		return GeneratedGetFeedParams{}, fmt.Errorf(
			"limit must be between 1 and %d",
			GeneratedGetFeedMaximumItems,
		)
	}
	return out, nil
}
{{- end }}

var generatedRequestBodyFieldSetByOperation = map[string]map[string]struct{}{
{{- range .BodyOperations }}
	"{{ . }}": {
		{{- range index $.BodyFieldsByOperation . }}
		"{{ . }}": {},
		{{- end }}
	},
{{- end }}
}

func BindGeneratedRequestBodyFromRequest(r *http.Request, operation string) (map[string]any, error) {
	allowed, ok := generatedRequestBodyFieldSetByOperation[operation]
	if !ok {
		return nil, nil
	}
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		return nil, fmt.Errorf("read request body: %w", err)
	}
	if len(strings.TrimSpace(string(raw))) == 0 {
		return map[string]any{}, nil
	}
	var input map[string]any
	if err := json.Unmarshal(raw, &input); err != nil {
		return nil, fmt.Errorf("decode request body: %w", err)
	}
	sanitized := make(map[string]any, len(input))
	for key, value := range input {
		if _, allowedKey := allowed[key]; !allowedKey {
			return nil, fmt.Errorf("field %q is not part of request body for operation %s", key, operation)
		}
		sanitized[key] = value
	}
	return sanitized, nil
}
`
	t, err := template.New("http_scaffold").Funcs(template.FuncMap{
		"generatedGoField": func(s string) string { return toPascal(s) },
	}).Parse(tmpl)
	if err != nil {
		return err
	}
	var buf bytes.Buffer
	if err := t.Execute(&buf, data); err != nil {
		return err
	}
	out := buf.Bytes()
	if formatted, err := format.Source(out); err == nil {
		out = formatted
	}
	marker := []byte("var generatedRouteTable = []generatedRouteDef{")
	markerIndex := bytes.Index(out, marker)
	if markerIndex < 0 {
		return fmt.Errorf("generated route table marker not found")
	}
	strconvImport := ""
	if data.GetFeedRouteFound {
		strconvImport = "\t\"strconv\"\n"
	}
	generatedHeader := fmt.Sprintf(`// Code generated by tools/codegen_content_service from %s. DO NOT EDIT.
package transport

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
%s
	"strings"
)

`, sourcePath, strconvImport)
	generated := append([]byte(generatedHeader), out[markerIndex:]...)
	generated = bytes.Replace(generated, []byte("func resolveGeneratedOperation("), []byte("func ResolveOperation("), 1)
	if formatted, err := format.Source(generated); err == nil {
		generated = formatted
	}
	targetDir := filepath.Join(outputDir, "transport")
	if err := os.MkdirAll(targetDir, 0o755); err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(targetDir, "routes.g.go"), generated, 0o644)
}

func findObjectDir(
	source *contractcodegen.Source,
	aggregateName string,
) (string, error) {
	for _, object := range source.Graph().Objects {
		if object.Name == aggregateName {
			return path.Dir(object.SourcePath), nil
		}
	}
	return "", fmt.Errorf("business object %q not found", aggregateName)
}

func deriveRequestBodyFields(
	route serviceRouteYAML,
	objectName string,
	fields serviceFieldsYAML,
) ([]string, error) {
	if strings.TrimSpace(route.RequestBodyKind) != "object" {
		return nil, nil
	}
	requestEntity := strings.TrimSpace(route.RequestEntity)
	if requestEntity == "" {
		return nil, fmt.Errorf(
			"operation %s request_body_kind=object requires request_entity",
			route.Operation,
		)
	}
	entity, err := findServiceRequestEntity(fields, objectName, requestEntity)
	if err != nil {
		return nil, fmt.Errorf("operation %s: %w", route.Operation, err)
	}

	boundFields := make(map[string]string)
	for _, group := range []struct {
		name   string
		values []requestBindingYAML
	}{
		{name: "path", values: route.RequestBindings.Path},
		{name: "query", values: route.RequestBindings.Query},
		{name: "header", values: route.RequestBindings.Header},
		{name: "injected", values: route.RequestBindings.Injected},
	} {
		for _, binding := range group.values {
			field := strings.TrimSpace(binding.Field)
			if field == "" {
				return nil, fmt.Errorf(
					"operation %s request_bindings.%s has an empty field",
					route.Operation,
					group.name,
				)
			}
			if previous, exists := boundFields[field]; exists {
				return nil, fmt.Errorf(
					"operation %s request field %s is bound to both %s and %s",
					route.Operation,
					field,
					previous,
					group.name,
				)
			}
			boundFields[field] = group.name
		}
	}

	bodyFields := make([]string, 0, len(entity.Fields))
	seenNames := make(map[string]struct{}, len(entity.Fields))
	seenWireNames := make(map[string]struct{}, len(entity.Fields))
	for _, field := range entity.Fields {
		name := strings.TrimSpace(field.Name)
		if name == "" {
			return nil, fmt.Errorf(
				"request_entity %s has an empty field",
				requestEntity,
			)
		}
		if _, exists := seenNames[name]; exists {
			return nil, fmt.Errorf(
				"request_entity %s repeats field %s",
				requestEntity,
				name,
			)
		}
		seenNames[name] = struct{}{}
		if _, bound := boundFields[name]; bound {
			continue
		}
		wireName := strings.TrimSpace(field.ClientWireName)
		if wireName == "" {
			wireName = name
		}
		if _, exists := seenWireNames[wireName]; exists {
			return nil, fmt.Errorf(
				"request_entity %s maps multiple body fields to wire name %s",
				requestEntity,
				wireName,
			)
		}
		seenWireNames[wireName] = struct{}{}
		bodyFields = append(bodyFields, wireName)
	}
	if len(bodyFields) == 0 {
		return nil, fmt.Errorf(
			"operation %s request_body_kind=object has no body fields after canonical bindings",
			route.Operation,
		)
	}
	return bodyFields, nil
}

func findServiceRequestEntity(
	fields serviceFieldsYAML,
	objectName string,
	requestEntity string,
) (serviceRequestEntityYAML, error) {
	var matches []serviceRequestEntityYAML
	for _, catalog := range []map[string]serviceRequestEntityYAML{
		fields.Entities,
		fields.Types,
		fields.ValueObjects,
		fields.Members,
	} {
		if entity, exists := catalog[requestEntity]; exists {
			matches = append(matches, entity)
		}
	}
	if strings.TrimSpace(fields.Entity) == requestEntity ||
		(strings.TrimSpace(fields.Entity) == "" && toPascal(objectName) == requestEntity) {
		matches = append(matches, serviceRequestEntityYAML{Fields: fields.Fields})
	}
	if len(matches) == 0 {
		return serviceRequestEntityYAML{}, fmt.Errorf(
			"request_entity %s is absent from fields.yaml",
			requestEntity,
		)
	}
	if len(matches) > 1 {
		return serviceRequestEntityYAML{}, fmt.Errorf(
			"request_entity %s is declared more than once in fields.yaml",
			requestEntity,
		)
	}
	return matches[0], nil
}

func loadServiceRoutes(
	source *contractcodegen.Source,
	serviceName string,
) ([]objectRouteGroup, error) {
	groups := make([]objectRouteGroup, 0)
	byMethodPath := map[string]string{}
	byOperation := map[string]string{}
	serviceName = strings.TrimSpace(serviceName)
	if serviceName == "" {
		return nil, fmt.Errorf("route service name is required")
	}
	domainPrefix := strings.TrimSuffix(serviceName, "-service") + "/"
	for _, operationsPath := range source.Paths(domainPrefix, "operations.yaml") {
		parts := strings.Split(operationsPath, "/")
		if len(parts) != 4 || parts[0]+"/" != domainPrefix || parts[3] != "operations.yaml" {
			return nil, fmt.Errorf("unexpected content operations path %q", operationsPath)
		}
		var operations operationsYAML
		if err := source.Decode(operationsPath, &operations); err != nil {
			return nil, err
		}
		fieldsPath := path.Join(path.Dir(operationsPath), "fields.yaml")
		var fields serviceFieldsYAML
		if source.Has(fieldsPath) {
			if err := source.Decode(fieldsPath, &fields); err != nil {
				return nil, err
			}
		}
		group := objectRouteGroup{
			Context:    parts[1],
			Object:     parts[2],
			SourcePath: operationsPath,
			Routes:     make([]serviceRouteYAML, 0, len(operations.APIRoutes)),
		}
		for _, route := range operations.APIRoutes {
			method := strings.ToUpper(strings.TrimSpace(route.Method))
			routePath := strings.TrimSpace(route.Path)
			operation := strings.TrimSpace(route.Operation)
			if method == "" || routePath == "" || operation == "" {
				continue
			}
			key := method + " " + routePath
			if existing, exists := byMethodPath[key]; exists {
				if existing != operation {
					return nil, fmt.Errorf(
						"route %s is claimed by both %s and %s",
						key,
						existing,
						operation,
					)
				}
				continue
			}
			byMethodPath[key] = operation
			if existing, exists := byOperation[operation]; exists && existing != key {
				return nil, fmt.Errorf(
					"operation %s is bound to both %s and %s",
					operation,
					existing,
					key,
				)
			}
			byOperation[operation] = key
			route.Method = method
			route.Path = routePath
			route.Operation = operation
			requestBodyFields, err := deriveRequestBodyFields(
				route,
				group.Object,
				fields,
			)
			if err != nil {
				return nil, fmt.Errorf("%s: %w", operationsPath, err)
			}
			route.RequestBodyFields = requestBodyFields
			group.Routes = append(group.Routes, route)
		}
		groups = append(groups, group)
	}
	sort.Slice(groups, func(i, j int) bool {
		left := groups[i].Context + "/" + groups[i].Object
		right := groups[j].Context + "/" + groups[j].Object
		return left < right
	})
	return groups, nil
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_content_service error: %v\n", err)
	os.Exit(1)
}
