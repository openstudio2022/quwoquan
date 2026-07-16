package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/validate"
)

var (
	activeMetadataSource *contractcodegen.Source
	activeMetadataRoot   string
	activeContractLock   appContractLock
	activeContractSHA256 string
)

type appExposedOperation struct {
	ActorRequirement     string               `json:"actorRequirement"`
	AuthMode             string               `json:"authMode"`
	CanonicalOperationID string               `json:"canonicalOperationId"`
	ClientContract       *appClientContract   `json:"clientContract"`
	Commercial           appCommercialBinding `json:"commercial"`
	Domain               string               `json:"domain"`
	ErrorCodes           []string             `json:"errorCodes"`
	Facet                string               `json:"facet"`
	FacadeMethod         string               `json:"facadeMethod"`
	AggregateOwner       string               `json:"aggregateOwner"`
	MutationTarget       string               `json:"mutationTarget"`
	InvariantTarget      string               `json:"invariantTarget"`
	Kind                 string               `json:"kind"`
	LocalOperationID     string               `json:"localOperationId"`
	Method               string               `json:"method"`
	ObjectID             string               `json:"objectId"`
	OwnershipPolicy      string               `json:"ownershipPolicy"`
	PathTemplate         string               `json:"pathTemplate"`
	Permissions          []string             `json:"permissions"`
	Principal            string               `json:"principal"`
	Privacy              appPrivacyPolicy     `json:"privacy"`
	Reliability          appReliabilityPolicy `json:"reliability"`
	RequestEntity        string               `json:"requestEntity"`
	RequestBodyKind      string               `json:"requestBodyKind"`
	ResponseBody         string               `json:"responseBody"`
	ResponseBodyKind     string               `json:"responseBodyKind"`
	ResponseEntity       string               `json:"responseEntity"`
	Scopes               []string             `json:"scopes"`
	SLO                  appSLOPolicy         `json:"slo"`
	SourcePath           string               `json:"sourcePath"`
	SurfaceIDs           []string             `json:"surfaceIds"`
	Telemetry            appTelemetryPolicy   `json:"telemetry"`
}

type appClientContract struct {
	DartImport      string            `json:"dartImport"`
	PathBindings    map[string]string `json:"pathBindings"`
	QueryBindings   map[string]string `json:"queryBindings"`
	RequestEncoder  string            `json:"requestEncoder"`
	RequestType     string            `json:"requestType"`
	ResponseDecoder string            `json:"responseDecoder"`
	ResponseType    string            `json:"responseType"`
}

type appCommercialBinding struct {
	BlockReason string `json:"blockReason"`
	Status      string `json:"status"`
}

type appReliabilityPolicy struct {
	Cancellation        string `json:"cancellation"`
	Idempotency         string `json:"idempotency"`
	MaxAttempts         int    `json:"maxAttempts"`
	RetryMode           string `json:"retryMode"`
	TimeoutMilliseconds int    `json:"timeoutMilliseconds"`
}

type appPrivacyPolicy struct {
	LogPolicy              string `json:"logPolicy"`
	RequestClassification  string `json:"requestClassification"`
	ResponseClassification string `json:"responseClassification"`
}

type appTelemetryPolicy struct {
	Attributes []string `json:"attributes"`
	Metric     string   `json:"metric"`
	Trace      bool     `json:"trace"`
}

type appSLOPolicy struct {
	AvailabilityPercent    float64 `json:"availabilityPercent"`
	LatencyP95Milliseconds int     `json:"latencyP95Milliseconds"`
}

type appContractLock struct {
	Generator            string                `json:"generator"`
	AppExposedOperations []appExposedOperation `json:"appExposedOperations"`
	ContractGraph        struct {
		Path   string `json:"path"`
		SHA256 string `json:"sha256"`
	} `json:"contractGraph"`
}

func initializeContractGraph(metadataDir string) error {
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		return fmt.Errorf("compile ContractGraph: %w", err)
	}
	activeMetadataSource = source
	activeMetadataRoot = filepath.Clean(metadataDir)
	return nil
}

func initializeContractGraphBundle(
	metadataDir string,
	graphPath string,
	lockPath string,
) error {
	graphBytes, err := os.ReadFile(graphPath)
	if err != nil {
		return fmt.Errorf("read fixed ContractGraph bundle: %w", err)
	}
	lockBytes, err := os.ReadFile(lockPath)
	if err != nil {
		return fmt.Errorf("read App ContractGraph lock: %w", err)
	}
	for label, payload := range map[string][]byte{
		"ContractGraph":          graphBytes,
		"App ContractGraph lock": lockBytes,
	} {
		var envelope map[string]json.RawMessage
		if err := json.Unmarshal(payload, &envelope); err != nil {
			return fmt.Errorf("decode %s envelope: %w", label, err)
		}
		for _, retiredField := range []string{"version", "schemaVersion", "registryRevision"} {
			if _, exists := envelope[retiredField]; exists {
				return fmt.Errorf("%s contains retired field %q", label, retiredField)
			}
		}
	}
	var lock appContractLock
	if err := json.Unmarshal(lockBytes, &lock); err != nil {
		return fmt.Errorf("decode App ContractGraph lock: %w", err)
	}
	sum := sha256.Sum256(graphBytes)
	actualSHA := hex.EncodeToString(sum[:])
	if lock.Generator != "app-cloud-handoff" {
		return fmt.Errorf("unexpected App ContractGraph handoff: %q", lock.Generator)
	}
	if lock.ContractGraph.SHA256 != actualSHA {
		return fmt.Errorf(
			"fixed ContractGraph hash mismatch: lock=%s actual=%s",
			lock.ContractGraph.SHA256,
			actualSHA,
		)
	}
	var contractGraph graph.ContractGraph
	if err := json.Unmarshal(graphBytes, &contractGraph); err != nil {
		return fmt.Errorf("decode fixed ContractGraph bundle: %w", err)
	}
	if issues := validate.Run(&contractGraph, validate.ProfileBaseline); len(issues) > 0 {
		return fmt.Errorf(
			"fixed ContractGraph baseline validation failed: %s: %s",
			issues[0].Code,
			issues[0].Message,
		)
	}
	activeMetadataSource = contractcodegen.NewSourceFromGraph(
		metadataDir,
		&contractGraph,
	)
	activeMetadataRoot = filepath.Clean(metadataDir)
	activeContractLock = lock
	activeContractSHA256 = actualSHA
	return nil
}

func metadataDocumentPath(path string) (string, error) {
	if activeMetadataSource == nil {
		return "", fmt.Errorf("ContractGraph is not initialized")
	}
	return activeMetadataSource.RelativePath(path)
}

func decodeMetadataDocument(path string, target any) error {
	relative, err := metadataDocumentPath(path)
	if err != nil {
		return err
	}
	if !activeMetadataSource.Has(relative) {
		return &os.PathError{Op: "read", Path: path, Err: os.ErrNotExist}
	}
	return activeMetadataSource.Decode(relative, target)
}

func readMetadataDocument(path string) ([]byte, error) {
	relative, err := metadataDocumentPath(path)
	if err != nil {
		return nil, err
	}
	if !activeMetadataSource.Has(relative) {
		return nil, &os.PathError{Op: "read", Path: path, Err: os.ErrNotExist}
	}
	return activeMetadataSource.Content(relative)
}

func hasMetadataDocument(path string) bool {
	relative, err := metadataDocumentPath(path)
	return err == nil && activeMetadataSource.Has(relative)
}

func metadataDocumentPaths(prefix, suffix string) []string {
	if activeMetadataSource == nil {
		return nil
	}
	var paths []string
	for _, relative := range activeMetadataSource.Paths(prefix, suffix) {
		paths = append(
			paths,
			filepath.Join(activeMetadataRoot, filepath.FromSlash(relative)),
		)
	}
	return paths
}
