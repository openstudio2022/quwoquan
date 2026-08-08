package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
	"quwoquan_service/internal/metadata/validate"
)

type reviewObjectProfile string

const (
	reviewObjectProfileModel          reviewObjectProfile = "model"
	reviewObjectProfileContract       reviewObjectProfile = "contract"
	reviewObjectProfileImplementation reviewObjectProfile = "implementation"
	reviewObjectProfileCommercial     reviewObjectProfile = "commercial"
)

// reviewObjectResult 是稳定的对象审查回执。它刻意不包含时间、主机、路径或注册表快照；
// 审查结论只能由本次编译出的 ContractGraph 与显式 profile 派生。
type reviewObjectResult struct {
	ObjectID                string                `json:"objectId"`
	CheckID                 string                `json:"checkId"`
	Profile                 reviewObjectProfile   `json:"profile"`
	ContractGraphSourceHash string                `json:"contractGraphSourceHash"`
	Status                  string                `json:"status"`
	Stage                   string                `json:"stage"`
	EvidenceSummary         reviewEvidenceSummary `json:"evidenceSummary"`
	Missing                 []string              `json:"missing"`
}

// reviewEvidenceSideSummary 只暴露可审计的结构数量，不能把物理路径或 artifact
// identity 复制到对象回执中。
type reviewEvidenceSideSummary struct {
	EntryCount int `json:"entryCount"`
}

// reviewEvidenceSummary 来自一个且仅一个 ObjectReadinessEvidence。不存在或重复
// packet 时整份摘要归零，以免从不可信 packet 拼出貌似完整的证据。
type reviewEvidenceSummary struct {
	Service         reviewEvidenceSideSummary `json:"service"`
	App             reviewEvidenceSideSummary `json:"app"`
	Ops             reviewEvidenceSideSummary `json:"ops"`
	PageParticipant bool                      `json:"pageParticipant"`
	PageOwned       bool                      `json:"pageOwned"`
}

// reviewObjectBundle 是 --all 的稳定批量回执。Objects 的顺序始终由 canonical
// objectId 决定，不能依赖 loader 的遍历顺序或调用方提供的注册表顺序。
type reviewObjectBundle struct {
	Profile                 reviewObjectProfile  `json:"profile"`
	ContractGraphSourceHash string               `json:"contractGraphSourceHash"`
	Objects                 []reviewObjectResult `json:"objects"`
}

func runReviewObject(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("review-object", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	metadataDir := flags.String("metadata-dir", "contracts/metadata", "metadata root")
	repoRoot := registerRepoRoot(flags)
	objectID := flags.String("object", "", "exact canonical object ID")
	all := flags.Bool("all", false, "review every object in current ContractGraph")
	profileValue := flags.String("profile", string(reviewObjectProfileModel), "model, contract, implementation or commercial")
	format := flags.String("format", "json", "JSON output format")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("review-object accepts no positional arguments")
	}
	if strings.TrimSpace(*format) != "json" {
		return fmt.Errorf("unsupported review-object format %q: expected json", *format)
	}
	profile, err := parseReviewObjectProfile(*profileValue)
	if err != nil {
		return err
	}
	requestedObjectID := strings.TrimSpace(*objectID)
	if *all && requestedObjectID != "" {
		return errors.New("--all and --object are mutually exclusive")
	}
	if !*all && requestedObjectID == "" {
		return errors.New("exactly one of --object or --all is required")
	}

	// 任一全图校验错误都意味着对象级切片不可信。这里不做「只看目标对象」的降级，
	// 让全局 ownership、引用与 schema 漂移按 fail-closed 语义阻断审查。
	contractGraph, err := compileAndValidate(
		*metadataDir,
		*repoRoot,
		validationProfileForReview(profile),
	)
	if err != nil {
		return err
	}
	var payload any
	if *all {
		bundle, reviewErr := reviewCompiledObjects(contractGraph, profile)
		if reviewErr != nil {
			return reviewErr
		}
		payload = bundle
	} else {
		result, reviewErr := reviewCompiledObject(contractGraph, requestedObjectID, profile)
		if reviewErr != nil {
			return reviewErr
		}
		payload = result
	}
	return emitReviewObjectPayload(stdout, payload)
}

// emitReviewObjectPayload preserves the machine-readable review receipt even
// when the requested profile is blocked, then returns a stable error so the
// CLI process cannot accidentally treat a BLOCK receipt as a successful gate.
// Serialization or write failures take precedence because callers did not
// receive a complete receipt in those cases.
func emitReviewObjectPayload(stdout io.Writer, payload any) error {
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal review-object result: %w", err)
	}
	if _, err := stdout.Write(append(data, '\n')); err != nil {
		return err
	}

	switch result := payload.(type) {
	case reviewObjectResult:
		if result.Status == "BLOCK" {
			return fmt.Errorf(
				"review-object %s blocked for %s",
				result.Profile,
				result.ObjectID,
			)
		}
	case reviewObjectBundle:
		blocked := 0
		for _, object := range result.Objects {
			if object.Status == "BLOCK" {
				blocked++
			}
		}
		if blocked > 0 {
			return fmt.Errorf(
				"review-object %s blocked for %d object(s)",
				result.Profile,
				blocked,
			)
		}
	default:
		return fmt.Errorf("unsupported review-object payload %T", payload)
	}
	return nil
}

func parseReviewObjectProfile(value string) (reviewObjectProfile, error) {
	profile := reviewObjectProfile(strings.TrimSpace(value))
	switch profile {
	case reviewObjectProfileModel,
		reviewObjectProfileContract,
		reviewObjectProfileImplementation,
		reviewObjectProfileCommercial:
		return profile, nil
	default:
		return "", fmt.Errorf(
			"unsupported review-object profile %q: expected model, contract, implementation or commercial",
			value,
		)
	}
}

func validationProfileForReview(profile reviewObjectProfile) validate.Profile {
	if profile == reviewObjectProfileCommercial {
		return validate.ProfileCommercial
	}
	return validate.ProfileBaseline
}

func reviewCompiledObject(
	contractGraph *graph.ContractGraph,
	objectID string,
	profile reviewObjectProfile,
) (reviewObjectResult, error) {
	if contractGraph == nil {
		return reviewObjectResult{}, errors.New("current ContractGraph is required")
	}
	index, err := indexReviewGraph(contractGraph)
	if err != nil {
		return reviewObjectResult{}, err
	}
	objectReadiness, exists := index.readinessByObject[objectID]
	if !exists {
		return reviewObjectResult{}, fmt.Errorf("object %q is not present in current ContractGraph", objectID)
	}
	sourceHash, err := readiness.ContractGraphSourceHash(contractGraph)
	if err != nil {
		return reviewObjectResult{}, fmt.Errorf("derive ContractGraph source hash: %w", err)
	}
	evidenceSummary, evidenceCount := reviewEvidenceSummaryForObject(contractGraph, objectID)
	return reviewReadiness(objectReadiness, profile, sourceHash, evidenceSummary, evidenceCount), nil
}

func reviewCompiledObjects(
	contractGraph *graph.ContractGraph,
	profile reviewObjectProfile,
) (reviewObjectBundle, error) {
	if contractGraph == nil {
		return reviewObjectBundle{}, errors.New("current ContractGraph is required")
	}
	index, err := indexReviewGraph(contractGraph)
	if err != nil {
		return reviewObjectBundle{}, err
	}
	sourceHash, err := readiness.ContractGraphSourceHash(contractGraph)
	if err != nil {
		return reviewObjectBundle{}, fmt.Errorf("derive ContractGraph source hash: %w", err)
	}
	objects := make([]reviewObjectResult, 0, len(index.objectIDs))
	for _, objectID := range index.objectIDs {
		objectReadiness := index.readinessByObject[objectID]
		evidenceSummary, evidenceCount := reviewEvidenceSummaryForObject(
			contractGraph,
			objectID,
		)
		objects = append(objects, reviewReadiness(
			objectReadiness,
			profile,
			sourceHash,
			evidenceSummary,
			evidenceCount,
		))
	}
	return reviewObjectBundle{
		Profile:                 profile,
		ContractGraphSourceHash: sourceHash,
		Objects:                 objects,
	}, nil
}

type reviewGraphIndex struct {
	objectIDs         []string
	readinessByObject map[string]graph.ObjectReadiness
}

func indexReviewGraph(contractGraph *graph.ContractGraph) (reviewGraphIndex, error) {
	objectIDs := make([]string, 0, len(contractGraph.Objects))
	objectCounts := make(map[string]int, len(contractGraph.Objects))
	for _, object := range contractGraph.Objects {
		objectID := strings.TrimSpace(object.ID)
		if objectID == "" {
			return reviewGraphIndex{}, errors.New("ContractGraph contains an object without objectId")
		}
		objectCounts[objectID]++
		if objectCounts[objectID] > 1 {
			return reviewGraphIndex{}, fmt.Errorf("ContractGraph contains duplicate object %q", objectID)
		}
		objectIDs = append(objectIDs, objectID)
	}
	readinessByObject := make(map[string]graph.ObjectReadiness, len(contractGraph.ObjectReadiness))
	for _, objectReadiness := range contractGraph.ObjectReadiness {
		objectID := strings.TrimSpace(objectReadiness.ObjectID)
		if objectID == "" {
			return reviewGraphIndex{}, errors.New("ContractGraph contains object readiness without objectId")
		}
		if _, duplicate := readinessByObject[objectID]; duplicate {
			return reviewGraphIndex{}, fmt.Errorf("ContractGraph contains duplicate readiness for object %q", objectID)
		}
		readinessByObject[objectID] = objectReadiness
	}
	for _, objectID := range objectIDs {
		if _, exists := readinessByObject[objectID]; !exists {
			return reviewGraphIndex{}, fmt.Errorf("ContractGraph object %q has no readiness result", objectID)
		}
	}
	for objectID := range readinessByObject {
		if objectCounts[objectID] == 0 {
			return reviewGraphIndex{}, fmt.Errorf("ContractGraph readiness references unknown object %q", objectID)
		}
	}
	sort.Strings(objectIDs)
	return reviewGraphIndex{
		objectIDs:         objectIDs,
		readinessByObject: readinessByObject,
	}, nil
}

func reviewReadiness(
	readiness graph.ObjectReadiness,
	profile reviewObjectProfile,
	sourceHash string,
	evidenceSummary reviewEvidenceSummary,
	evidenceCount int,
) reviewObjectResult {
	missing := append([]string(nil), readiness.Missing...)
	passed := false
	switch profile {
	case reviewObjectProfileModel:
		passed = readiness.Modeled
	case reviewObjectProfileContract:
		passed = readiness.ContractReady
	case reviewObjectProfileImplementation:
		passed = readiness.Implemented
	case reviewObjectProfileCommercial:
		// ContractGraph 不承载动态环境历史；即使静态字段意外为 true，也绝不能把
		// 未经 trust boundary 验证的 bundle 解释成商业准出。
		missing = append(missing, "commercial.result_bundle")
	}
	if profile == reviewObjectProfileImplementation || profile == reviewObjectProfileCommercial {
		switch evidenceCount {
		case 0:
			missing = append(missing, "readiness.evidence")
			passed = false
		case 1:
			// 唯一 evidence packet 才能参与 implementation/commercial 的结构审查。
		default:
			missing = append(missing, "readiness.evidence.duplicate")
			passed = false
		}
	}
	return reviewObjectResult{
		ObjectID:                readiness.ObjectID,
		CheckID:                 checkIDForReviewProfile(profile),
		Profile:                 profile,
		ContractGraphSourceHash: sourceHash,
		Status:                  reviewStatus(passed),
		Stage:                   readiness.Stage,
		EvidenceSummary:         evidenceSummary,
		Missing:                 uniqueSortedStrings(missing),
	}
}

func checkIDForReviewProfile(profile reviewObjectProfile) string {
	return "object." + string(profile)
}

func reviewEvidenceSummaryForObject(
	contractGraph *graph.ContractGraph,
	objectID string,
) (reviewEvidenceSummary, int) {
	if contractGraph == nil {
		return reviewEvidenceSummary{}, 0
	}
	var evidenceIndex = -1
	evidenceCount := 0
	for index, evidence := range contractGraph.ReadinessEvidence {
		if evidence.ObjectID != objectID {
			continue
		}
		evidenceIndex = index
		evidenceCount++
	}
	if evidenceCount != 1 {
		return reviewEvidenceSummary{}, evidenceCount
	}
	evidence := contractGraph.ReadinessEvidence[evidenceIndex]
	return reviewEvidenceSummary{
		Service: reviewEvidenceSideSummary{EntryCount: len(evidence.Service.Domain) +
			len(evidence.Service.Store) + len(evidence.Service.Outbox) +
			len(evidence.Service.Reader) + len(evidence.Service.Transport) +
			len(evidence.Service.LocalContract) + len(evidence.Service.APIIntegration)},
		App: reviewEvidenceSideSummary{EntryCount: len(evidence.App.Domain) +
			len(evidence.App.Application) + len(evidence.App.Adapters) +
			len(evidence.App.Presentation) + len(evidence.App.LocalContract) +
			len(evidence.App.APIIntegration) + len(evidence.App.UserAcceptance)},
		Ops: reviewEvidenceSideSummary{EntryCount: len(evidence.Ops.EnvironmentAcceptance) +
			len(evidence.Ops.RollbackRunner) + len(evidence.Ops.ReplayRunner)},
		PageParticipant: evidence.App.PageParticipant,
		PageOwned:       evidence.App.PageOwned,
	}, evidenceCount
}

func reviewStatus(passed bool) string {
	if passed {
		return "PASS"
	}
	return "BLOCK"
}

func uniqueSortedStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			seen[trimmed] = struct{}{}
		}
	}
	result := make([]string, 0, len(seen))
	for value := range seen {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}
