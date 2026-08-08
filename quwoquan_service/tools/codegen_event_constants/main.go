// Command codegen_event_constants orchestrates every canonical object-local Go
// event package and the single Python event wire surface from one ContractGraph.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/codegen/eventconstants"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/metadata/validate"
)

const (
	generatorIdentity = "tools/codegen_event_constants"
	manifestVersion   = 1
)

type stringList []string

func (values *stringList) String() string { return strings.Join(*values, ",") }

func (values *stringList) Set(value string) error {
	value = strings.TrimSpace(value)
	if value == "" {
		return fmt.Errorf("excluded object must not be empty")
	}
	*values = append(*values, value)
	return nil
}

func main() {
	metadataDir := flag.String(
		"metadata-dir",
		"contracts/metadata",
		"canonical metadata root or service-contract-view",
	)
	serviceRoot := flag.String(
		"service-root",
		".",
		"quwoquan_service root containing services/ and generated/",
	)
	pythonOutput := flag.String(
		"python-output",
		"services/recommendation-service/generated/event_constants.py",
		"single generated Python event-constant surface",
	)
	manifestOutput := flag.String(
		"manifest-output",
		"generated/event_constants_manifest.json",
		"generated output ownership manifest",
	)
	checkPlan := flag.Bool(
		"check-plan",
		false,
		"compile and print the ownership plan without writing generated outputs",
	)
	var excludedObjects stringList
	flag.Var(
		&excludedObjects,
		"exclude-object",
		"read-only --check-plan exclusion for a temporarily frozen object; repeatable",
	)
	flag.Parse()

	if err := run(
		*metadataDir,
		*serviceRoot,
		*pythonOutput,
		*manifestOutput,
		excludedObjects,
		*checkPlan,
	); err != nil {
		fmt.Fprintf(os.Stderr, "codegen_event_constants: %v\n", err)
		os.Exit(1)
	}
}

type storageDocument struct {
	Codegen *storageCodegen `yaml:"codegen"`
}

type storageCodegen struct {
	Enabled    bool   `yaml:"enabled"`
	Package    string `yaml:"package"`
	DomainPath string `yaml:"domain_path"`
}

type goOutputPlan struct {
	Object       ast.Object
	Path         string
	Package      string
	Emitter      string
	StorageOwned bool
	Definitions  []eventconstants.Definition
}

type generationPlan struct {
	GoOutputs       []goOutputPlan
	PythonEvents    []eventconstants.Definition
	ExcludedObjects []excludedObject
	SourceDigest    string
}

type excludedObject struct {
	ObjectID  string   `json:"objectId"`
	EventRefs []string `json:"eventRefs"`
}

type manifestOutput struct {
	Path     string `json:"path"`
	Language string `json:"language"`
	Owner    string `json:"owner"`
	Emitter  string `json:"emitter"`
	SHA256   string `json:"sha256"`
	Bytes    int    `json:"bytes"`
}

type ownershipManifest struct {
	SchemaVersion   int              `json:"schemaVersion"`
	Generator       string           `json:"generator"`
	SourceDigest    string           `json:"sourceDigest"`
	ExcludedObjects []excludedObject `json:"excludedObjects"`
	Outputs         []manifestOutput `json:"outputs"`
}

func run(
	metadataDir,
	serviceRoot,
	pythonOutput,
	manifestOutput string,
	excludedObjects []string,
	checkPlan bool,
) error {
	if len(excludedObjects) > 0 && !checkPlan {
		return errors.New(
			"--exclude-object is permitted only with --check-plan; " +
				"generation must cover every canonical event owner",
		)
	}
	serviceRoot = filepath.Clean(serviceRoot)
	contractGraph, err := loadEventContractGraph(
		metadataDir,
		validate.ProfileBaseline,
		excludedObjects,
	)
	if err != nil {
		return fmt.Errorf("compile event ContractGraph: %w", err)
	}
	plan, err := buildGenerationPlan(contractGraph, serviceRoot, excludedObjects)
	if err != nil {
		return err
	}
	if checkPlan {
		return printGenerationPlan(
			plan,
			serviceRoot,
			pythonOutput,
			manifestOutput,
		)
	}
	source := contractcodegen.NewSourceFromGraph(metadataDir, contractGraph)
	return writeGeneration(
		source,
		plan,
		serviceRoot,
		pythonOutput,
		manifestOutput,
	)
}

func printGenerationPlan(
	plan generationPlan,
	serviceRoot,
	pythonOutput,
	manifestOutput string,
) error {
	encoded, err := renderGenerationPlan(
		plan,
		serviceRoot,
		pythonOutput,
		manifestOutput,
	)
	if err != nil {
		return err
	}
	fmt.Println(string(encoded))
	return nil
}

func renderGenerationPlan(
	plan generationPlan,
	serviceRoot,
	pythonOutput,
	manifestOutput string,
) ([]byte, error) {
	type plannedOutput struct {
		Path    string `json:"path"`
		Owner   string `json:"owner"`
		Emitter string `json:"emitter"`
	}
	outputs := make([]plannedOutput, 0, len(plan.GoOutputs)+1)
	for _, output := range plan.GoOutputs {
		relative, err := ownedRelativePath(serviceRoot, output.Path)
		if err != nil {
			return nil, err
		}
		outputs = append(outputs, plannedOutput{
			Path: relative, Owner: output.Object.ID, Emitter: output.Emitter,
		})
	}
	pythonPath, err := ownedOutputPath(serviceRoot, pythonOutput)
	if err != nil {
		return nil, err
	}
	pythonRelative, err := ownedRelativePath(serviceRoot, pythonPath)
	if err != nil {
		return nil, err
	}
	outputs = append(outputs, plannedOutput{
		Path: pythonRelative, Owner: "cross-service.event-wire-identity",
		Emitter: generatorIdentity,
	})
	manifestPath, err := ownedOutputPath(serviceRoot, manifestOutput)
	if err != nil {
		return nil, err
	}
	manifestRelative, err := ownedRelativePath(serviceRoot, manifestPath)
	if err != nil {
		return nil, err
	}
	encoded, err := json.MarshalIndent(struct {
		Generator       string           `json:"generator"`
		SourceDigest    string           `json:"sourceDigest"`
		GoObjects       int              `json:"goObjects"`
		PythonEvents    int              `json:"pythonEvents"`
		ExcludedObjects []excludedObject `json:"excludedObjects"`
		Manifest        string           `json:"manifest"`
		Outputs         []plannedOutput  `json:"outputs"`
	}{
		Generator: generatorIdentity, SourceDigest: plan.SourceDigest,
		GoObjects: len(plan.GoOutputs), PythonEvents: len(plan.PythonEvents),
		ExcludedObjects: plan.ExcludedObjects, Manifest: manifestRelative,
		Outputs: outputs,
	}, "", "  ")
	if err != nil {
		return nil, err
	}
	return encoded, nil
}

func loadEventContractGraph(
	metadataDir string,
	profile validate.Profile,
	excludedObjects []string,
) (*graph.ContractGraph, error) {
	catalog, err := load.Load(metadataDir)
	if err != nil {
		return nil, err
	}
	contractGraph := graph.Build(catalog)
	excluded := stringSet(excludedObjects)
	sourceOwners := eventSourceOwners(contractGraph)
	var blocking []validate.Issue
	for _, issue := range validate.Run(contractGraph, profile) {
		owner := sourceOwners[path.Clean(issue.SourcePath)]
		if issue.Code == "CONTRACT.EVENT.MISSING_WIRE_EVENT_TYPE" &&
			owner != "" && contains(excluded, owner) {
			continue
		}
		blocking = append(blocking, issue)
	}
	if len(blocking) > 0 {
		first := blocking[0]
		return nil, fmt.Errorf(
			"metadata validation failed with %d issue(s); first=%s %s: %s",
			len(blocking),
			first.Code,
			first.SourcePath,
			first.Message,
		)
	}
	return contractGraph, nil
}

func eventSourceOwners(contractGraph *graph.ContractGraph) map[string]string {
	owners := map[string]string{}
	for _, packet := range contractGraph.Governance.Objects {
		for _, event := range packet.Events {
			owners[path.Clean(event.SourcePath)] = packet.ObjectID
		}
	}
	return owners
}

func buildGenerationPlan(
	contractGraph *graph.ContractGraph,
	serviceRoot string,
	excludedObjects []string,
) (generationPlan, error) {
	excluded := stringSet(excludedObjects)
	objects := make(map[string]ast.Object, len(contractGraph.Objects))
	for _, object := range contractGraph.Objects {
		objects[object.ID] = object
	}
	domainServices, err := discoverDomainServices(serviceRoot)
	if err != nil {
		return generationPlan{}, err
	}

	var plan generationPlan
	wireOwners := map[string]string{}
	seenExcluded := map[string]struct{}{}
	for _, packet := range contractGraph.Governance.Objects {
		hasOutbox := false
		for _, event := range packet.Events {
			if event.DeliverySemantics == eventconstants.TransactionalOutbox {
				hasOutbox = true
				break
			}
		}
		if !hasOutbox {
			continue
		}
		object, exists := objects[packet.ObjectID]
		if !exists {
			return generationPlan{}, fmt.Errorf(
				"event packet %q has no canonical object",
				packet.ObjectID,
			)
		}
		if contains(excluded, packet.ObjectID) {
			excludedItem, excludeErr := validateExcludedObject(packet)
			if excludeErr != nil {
				return generationPlan{}, excludeErr
			}
			plan.ExcludedObjects = append(plan.ExcludedObjects, excludedItem)
			seenExcluded[packet.ObjectID] = struct{}{}
			continue
		}

		definitions, err := eventconstants.DefinitionsForObject(
			contractGraph,
			packet.ObjectID,
		)
		if err != nil {
			return generationPlan{}, err
		}
		for _, event := range definitions {
			if event.DeliverySemantics != eventconstants.TransactionalOutbox {
				continue
			}
			ref := event.ObjectID + "." + event.Name
			if previous, duplicate := wireOwners[event.WireValue]; duplicate {
				return generationPlan{}, fmt.Errorf(
					"wire_event_type %q is shared by %q and %q",
					event.WireValue,
					previous,
					ref,
				)
			}
			wireOwners[event.WireValue] = ref
			plan.PythonEvents = append(plan.PythonEvents, event)
		}

		output, err := deriveGoOutputPlan(
			contractGraph,
			serviceRoot,
			domainServices,
			object,
			definitions,
		)
		if err != nil {
			return generationPlan{}, err
		}
		plan.GoOutputs = append(plan.GoOutputs, output)
	}
	for objectID := range excluded {
		if _, found := seenExcluded[objectID]; !found {
			return generationPlan{}, fmt.Errorf(
				"excluded object %q is not an outbox object with missing wire identities",
				objectID,
			)
		}
	}
	sort.Slice(plan.GoOutputs, func(i, j int) bool {
		return plan.GoOutputs[i].Object.ID < plan.GoOutputs[j].Object.ID
	})
	sort.Slice(plan.PythonEvents, func(i, j int) bool {
		left := plan.PythonEvents[i].ObjectID + "." + plan.PythonEvents[i].Name
		right := plan.PythonEvents[j].ObjectID + "." + plan.PythonEvents[j].Name
		return left < right
	})
	sort.Slice(plan.ExcludedObjects, func(i, j int) bool {
		return plan.ExcludedObjects[i].ObjectID < plan.ExcludedObjects[j].ObjectID
	})
	plan.SourceDigest, err = generationSourceDigest(plan)
	if err != nil {
		return generationPlan{}, err
	}
	return plan, nil
}

func validateExcludedObject(packet ast.ObjectGovernance) (excludedObject, error) {
	result := excludedObject{ObjectID: packet.ObjectID}
	missing := 0
	for _, event := range packet.Events {
		if event.DeliverySemantics != eventconstants.TransactionalOutbox {
			continue
		}
		if strings.TrimSpace(event.WireEventType) != "" {
			return excludedObject{}, fmt.Errorf(
				"excluded object %q already authors wire_event_type for %q; remove the exclusion",
				packet.ObjectID,
				event.Name,
			)
		}
		missing++
		result.EventRefs = append(
			result.EventRefs,
			packet.ObjectID+"."+strings.TrimSpace(event.Name),
		)
	}
	if missing == 0 {
		return excludedObject{}, fmt.Errorf(
			"excluded object %q has no missing outbox wire identity",
			packet.ObjectID,
		)
	}
	sort.Strings(result.EventRefs)
	return result, nil
}

func deriveGoOutputPlan(
	contractGraph *graph.ContractGraph,
	serviceRoot string,
	domainServices map[string]string,
	object ast.Object,
	definitions []eventconstants.Definition,
) (goOutputPlan, error) {
	objectDir := path.Dir(object.SourcePath)
	parts := strings.Split(objectDir, "/")
	if len(parts) != 3 || parts[0] != object.Domain {
		return goOutputPlan{}, fmt.Errorf(
			"object %q source path %q is not <domain>/<context>/<object>/object.yaml",
			object.ID,
			object.SourcePath,
		)
	}
	service, exists := domainServices[object.Domain]
	if !exists {
		return goOutputPlan{}, fmt.Errorf(
			"object %q domain %q has no service contracts owner",
			object.ID,
			object.Domain,
		)
	}
	base := filepath.Join(
		serviceRoot,
		"services",
		service,
		"generated",
		parts[1],
		parts[2],
	)
	result := goOutputPlan{
		Object:      object,
		Path:        filepath.Join(base, "contract", "event", "events.go"),
		Package:     "event",
		Emitter:     "internal/metadata/codegen.DomainGenerator",
		Definitions: definitions,
	}
	storagePath := path.Join(objectDir, "storage.yaml")
	if !contractGraph.HasDocument(storagePath) {
		return result, nil
	}
	var storage storageDocument
	if err := contractGraph.DecodeDocumentYAML(storagePath, &storage); err != nil {
		return goOutputPlan{}, fmt.Errorf("decode %s: %w", storagePath, err)
	}
	if storage.Codegen == nil || !storage.Codegen.Enabled {
		return result, nil
	}
	packageName := strings.TrimSpace(storage.Codegen.Package)
	if packageName == "" {
		packageName = strings.ReplaceAll(parts[1], "-", "_")
	}
	domainPath := strings.TrimSpace(storage.Codegen.DomainPath)
	if domainPath == "" {
		domainPath = packageName
	}
	result.Path = filepath.Join(
		base,
		"contract",
		filepath.FromSlash(domainPath),
		"event",
		"events.g.go",
	)
	result.Package = packageName
	result.Emitter = "tools/codegen_storage"
	result.StorageOwned = true
	return result, nil
}

func discoverDomainServices(serviceRoot string) (map[string]string, error) {
	paths, err := filepath.Glob(filepath.Join(
		serviceRoot,
		"services",
		"*-service",
		"contracts",
		"domain.yaml",
	))
	if err != nil {
		return nil, err
	}
	result := map[string]string{}
	for _, domainPath := range paths {
		raw, err := os.ReadFile(domainPath)
		if err != nil {
			return nil, err
		}
		var document struct {
			Domain string `yaml:"domain"`
		}
		if err := yaml.Unmarshal(raw, &document); err != nil {
			return nil, fmt.Errorf("decode %s: %w", domainPath, err)
		}
		domain := strings.TrimSpace(document.Domain)
		service := filepath.Base(filepath.Dir(filepath.Dir(domainPath)))
		if domain == "" {
			return nil, fmt.Errorf("%s missing domain", domainPath)
		}
		if previous, duplicate := result[domain]; duplicate {
			return nil, fmt.Errorf(
				"domain %q is owned by both %q and %q",
				domain,
				previous,
				service,
			)
		}
		result[domain] = service
	}
	return result, nil
}

func writeGeneration(
	source *contractcodegen.Source,
	plan generationPlan,
	serviceRoot,
	pythonOutput,
	manifestOutputPath string,
) error {
	serviceRoot = filepath.Clean(serviceRoot)
	pythonPath, err := ownedOutputPath(serviceRoot, pythonOutput)
	if err != nil {
		return err
	}
	manifestPath, err := ownedOutputPath(serviceRoot, manifestOutputPath)
	if err != nil {
		return err
	}
	outputs := make([]manifestOutput, 0, len(plan.GoOutputs)+1)
	desired := map[string]struct{}{}
	for _, output := range plan.GoOutputs {
		if output.StorageOwned {
			generated, renderErr := eventconstants.RenderGo(
				eventconstants.GoRenderOptions{
					Generator:     "codegen_storage",
					Package:       output.Package,
					AggregateRoot: output.Object.Name,
				},
				output.Definitions,
			)
			if renderErr != nil {
				return fmt.Errorf("render %s: %w", output.Object.ID, renderErr)
			}
			if err := writeGeneratedFile(output.Path, generated); err != nil {
				return err
			}
		} else {
			objectRoot := filepath.Dir(filepath.Dir(filepath.Dir(output.Path)))
			generator := contractcodegen.NewDomainGenerator(
				source,
				objectRoot,
				contractcodegen.WithObjectFirstRoot(),
			)
			if err := generator.GenerateObjectEvents(output.Object.ID); err != nil {
				return fmt.Errorf("generate %s: %w", output.Object.ID, err)
			}
		}
		generated, err := os.ReadFile(output.Path)
		if err != nil {
			return fmt.Errorf("read generated %s: %w", output.Path, err)
		}
		relative, err := ownedRelativePath(serviceRoot, output.Path)
		if err != nil {
			return err
		}
		desired[relative] = struct{}{}
		outputs = append(outputs, describeOutput(
			relative,
			"go",
			output.Object.ID,
			output.Emitter,
			generated,
		))
	}
	python, err := eventconstants.RenderPython(plan.PythonEvents)
	if err != nil {
		return err
	}
	if err := writeGeneratedFile(pythonPath, python); err != nil {
		return err
	}
	pythonRelative, err := ownedRelativePath(serviceRoot, pythonPath)
	if err != nil {
		return err
	}
	desired[pythonRelative] = struct{}{}
	outputs = append(outputs, describeOutput(
		pythonRelative,
		"python",
		"cross-service.event-wire-identity",
		generatorIdentity,
		python,
	))
	sort.Slice(outputs, func(i, j int) bool { return outputs[i].Path < outputs[j].Path })
	manifest := ownershipManifest{
		SchemaVersion:   manifestVersion,
		Generator:       generatorIdentity,
		SourceDigest:    plan.SourceDigest,
		ExcludedObjects: plan.ExcludedObjects,
		Outputs:         outputs,
	}
	if err := retireStaleOwnedOutputs(serviceRoot, manifestPath, desired); err != nil {
		return err
	}
	encoded, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return err
	}
	encoded = append(encoded, '\n')
	return writeGeneratedFile(manifestPath, encoded)
}

func describeOutput(path, language, owner, emitter string, content []byte) manifestOutput {
	sum := sha256.Sum256(content)
	return manifestOutput{
		Path:     path,
		Language: language,
		Owner:    owner,
		Emitter:  emitter,
		SHA256:   hex.EncodeToString(sum[:]),
		Bytes:    len(content),
	}
}

func generationSourceDigest(plan generationPlan) (string, error) {
	type sourceEvent struct {
		ObjectID          string `json:"objectId"`
		Name              string `json:"name"`
		DeliverySemantics string `json:"deliverySemantics"`
		WireValue         string `json:"wireValue"`
		ClientWSType      string `json:"clientWsType,omitempty"`
	}
	var events []sourceEvent
	for _, output := range plan.GoOutputs {
		for _, event := range output.Definitions {
			events = append(events, sourceEvent{
				ObjectID:          event.ObjectID,
				Name:              event.Name,
				DeliverySemantics: event.DeliverySemantics,
				WireValue:         event.WireValue,
				ClientWSType:      event.ClientWSType,
			})
		}
	}
	sort.Slice(events, func(i, j int) bool {
		left := events[i].ObjectID + "." + events[i].Name
		right := events[j].ObjectID + "." + events[j].Name
		return left < right
	})
	payload, err := json.Marshal(struct {
		Events   []sourceEvent    `json:"events"`
		Excluded []excludedObject `json:"excluded"`
	}{Events: events, Excluded: plan.ExcludedObjects})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func retireStaleOwnedOutputs(
	serviceRoot,
	manifestPath string,
	desired map[string]struct{},
) error {
	raw, err := os.ReadFile(manifestPath)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	var previous ownershipManifest
	if err := json.Unmarshal(raw, &previous); err != nil {
		return fmt.Errorf("decode prior event constants manifest: %w", err)
	}
	if previous.SchemaVersion != manifestVersion {
		return fmt.Errorf(
			"event constants manifest schemaVersion is %d, want %d",
			previous.SchemaVersion,
			manifestVersion,
		)
	}
	if previous.Generator != generatorIdentity {
		return fmt.Errorf(
			"event constants manifest is owned by %q, not %q",
			previous.Generator,
			generatorIdentity,
		)
	}
	if len(previous.ExcludedObjects) != 0 {
		return errors.New(
			"event constants manifest contains excluded objects; " +
				"formal generation must cover every canonical event owner",
		)
	}
	seenPaths := map[string]struct{}{}
	for _, output := range previous.Outputs {
		if _, duplicate := seenPaths[output.Path]; duplicate {
			return fmt.Errorf(
				"event constants manifest repeats output %q",
				output.Path,
			)
		}
		seenPaths[output.Path] = struct{}{}
		if _, keep := desired[output.Path]; keep {
			continue
		}
		path, err := ownedOutputPath(serviceRoot, output.Path)
		if err != nil {
			return err
		}
		content, err := os.ReadFile(path)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return err
		}
		digest := sha256.Sum256(content)
		if len(content) != output.Bytes ||
			hex.EncodeToString(digest[:]) != output.SHA256 {
			return fmt.Errorf(
				"refuse to remove output %s drifted from prior manifest",
				path,
			)
		}
		if !bytesOwnedByEmitter(content) {
			return fmt.Errorf("refuse to remove non-generated output %s", path)
		}
		if err := os.Remove(path); err != nil {
			return err
		}
	}
	return nil
}

func bytesOwnedByEmitter(content []byte) bool {
	header := string(content)
	if newline := strings.IndexByte(header, '\n'); newline >= 0 {
		header = header[:newline]
	}
	return strings.Contains(header, "Code generated by") &&
		(strings.Contains(header, "codegen_event_constants") ||
			strings.Contains(header, "codegen_storage") ||
			strings.Contains(header, "internal/metadata/codegen"))
}

func writeGeneratedFile(path string, content []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, content, 0o644)
}

func ownedOutputPath(root, output string) (string, error) {
	if !filepath.IsAbs(output) {
		output = filepath.Join(root, output)
	}
	if _, err := ownedRelativePath(root, output); err != nil {
		return "", err
	}
	return filepath.Clean(output), nil
}

func ownedRelativePath(root, output string) (string, error) {
	absoluteRoot, err := filepath.Abs(root)
	if err != nil {
		return "", err
	}
	absoluteOutput, err := filepath.Abs(output)
	if err != nil {
		return "", err
	}
	relative, err := filepath.Rel(absoluteRoot, absoluteOutput)
	if err != nil || relative == ".." ||
		strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("generated output %q is outside service root %q", output, root)
	}
	return filepath.ToSlash(relative), nil
}

func stringSet(values []string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			result[value] = struct{}{}
		}
	}
	return result
}

func contains(values map[string]struct{}, value string) bool {
	_, exists := values[value]
	return exists
}
