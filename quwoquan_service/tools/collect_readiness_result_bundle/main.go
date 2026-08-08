package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"time"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
	readinesstrust "quwoquan_service/internal/metadata/readiness/trust"
)

const (
	maxGraphInputBytes    = 128 << 20
	maxTrustInputBytes    = 4 << 20
	maxReceiptInputBytes  = 1 << 20
	maxEvidenceInputBytes = 64 << 20
)

type options struct {
	graphPath     string
	metadataDir   string
	runnerKeyring string
	receiptRoot   string
	evidenceRoot  string
}

type fatalResult struct {
	Error string `json:"error"`
}

type incompleteResult struct {
	Complete     bool `json:"complete"`
	MissingSlots int  `json:"missingSlots"`
}

type collectionState struct {
	complete     bool
	missingSlots int
	nonPassed    bool
}

type resolverFactory func(
	receiptRoot string,
	evidenceRoot string,
	runnerKeyring []byte,
	schemas *readiness.WireSchemas,
) (readiness.ReceiptResolver, error)

type receiptFile struct {
	relative string
	bytes    []byte
	digest   string
	info     os.FileInfo
}

type receiptTreeSnapshot struct {
	rootInfo    os.FileInfo
	directories map[string]os.FileInfo
	files       map[string]receiptFile
	candidates  []receiptFile
	fingerprint string
}

type evidenceFile struct {
	digest string
	info   os.FileInfo
}

type stableFile struct {
	bytes []byte
	info  os.FileInfo
}

type evidenceSnapshot struct {
	rootInfo os.FileInfo
	shaInfo  os.FileInfo
	files    map[string]evidenceFile
}

type authoredSlot struct {
	objectID         string
	specRef          string
	caseID           string
	producer         ast.ReadinessProducer
	layer            ast.ReadinessLayer
	target           ast.ReadinessCaseTarget
	runnerSourcePath string
	execution        ast.ReadinessExecutionRequirement
}

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stdout, productionResolver))
}

// run returns 0 only when every graph-authored execution slot has exactly one
// trusted passed receipt. A trustworthy partial/non-passed bundle returns 1 so
// evaluate_readiness remains the sole policy authority. Malformed input,
// untrusted receipts and identity drift return 2.
func run(
	ctx context.Context,
	args []string,
	stdout io.Writer,
	newResolver resolverFactory,
) int {
	bundle, state, err := collect(ctx, args, newResolver)
	if err != nil {
		_ = writeJSON(stdout, fatalResult{Error: err.Error()})
		return 2
	}
	if len(bundle.Results) == 0 {
		_ = writeJSON(stdout, incompleteResult{
			Complete: false, MissingSlots: state.missingSlots,
		})
		return 1
	}
	if err := writeJSON(stdout, bundle); err != nil {
		return 2
	}
	if !state.complete || state.nonPassed {
		return 1
	}
	return 0
}

func collect(
	ctx context.Context,
	args []string,
	newResolver resolverFactory,
) (readiness.ReadinessResultBundle, collectionState, error) {
	configuration, err := parseOptions(args)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	graphBytes, err := readiness.ReadStableRegularFile(
		configuration.graphPath, maxGraphInputBytes,
	)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			fmt.Errorf("read current ContractGraph: %w", err)
	}
	current, err := decodeGraph(graphBytes)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	sourceHash, err := readiness.ContractGraphSourceHash(current)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			fmt.Errorf("derive ContractGraph source hash: %w", err)
	}
	slots, err := projectAuthoredSlots(current)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	if len(slots) == 0 {
		return readiness.ReadinessResultBundle{}, collectionState{},
			errors.New("current ContractGraph has no readiness execution slots")
	}
	schemas, err := readiness.LoadWireSchemas(configuration.metadataDir)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			fmt.Errorf("load readiness wire schemas: %w", err)
	}
	keyringBytes, err := readiness.ReadStableRegularFile(
		configuration.runnerKeyring, maxTrustInputBytes,
	)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			fmt.Errorf("read runner keyring: %w", err)
	}
	receiptsBefore, err := scanReceiptTree(configuration.receiptRoot)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	evidenceBefore, err := snapshotBoundEvidence(
		configuration.evidenceRoot, receiptsBefore.candidates, schemas,
	)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	resolver, err := newResolver(
		configuration.receiptRoot, configuration.evidenceRoot, keyringBytes, schemas,
	)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			fmt.Errorf("initialize signed receipt trust: %w", err)
	}
	bundle, state, err := collectSnapshot(
		ctx, slots, sourceHash, schemas, receiptsBefore, resolver,
	)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	receiptsAfter, err := scanReceiptTree(configuration.receiptRoot)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	if !sameReceiptTree(receiptsBefore, receiptsAfter) {
		return readiness.ReadinessResultBundle{}, collectionState{},
			errors.New("receipt tree changed while collecting bundle")
	}
	evidenceAfter, err := snapshotBoundEvidence(
		configuration.evidenceRoot, receiptsAfter.candidates, schemas,
	)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{}, err
	}
	if !sameEvidenceSnapshot(evidenceBefore, evidenceAfter) {
		return readiness.ReadinessResultBundle{}, collectionState{},
			errors.New("bound evidence changed while collecting bundle")
	}
	currentGraphBytes, err := readiness.ReadStableRegularFile(
		configuration.graphPath, maxGraphInputBytes,
	)
	if err != nil || !bytes.Equal(graphBytes, currentGraphBytes) {
		return readiness.ReadinessResultBundle{}, collectionState{},
			errors.New("current ContractGraph changed while collecting bundle")
	}
	currentKeyringBytes, err := readiness.ReadStableRegularFile(
		configuration.runnerKeyring, maxTrustInputBytes,
	)
	if err != nil || !bytes.Equal(keyringBytes, currentKeyringBytes) {
		return readiness.ReadinessResultBundle{}, collectionState{},
			errors.New("runner keyring changed while collecting bundle")
	}
	return bundle, state, nil
}

func collectSnapshot(
	ctx context.Context,
	slots []authoredSlot,
	sourceHash string,
	schemas *readiness.WireSchemas,
	snapshot receiptTreeSnapshot,
	resolver readiness.ReceiptResolver,
) (readiness.ReadinessResultBundle, collectionState, error) {
	if resolver == nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			errors.New("signed receipt resolver is required")
	}
	expected := make(map[string]authoredSlot, len(slots))
	for _, slot := range slots {
		key := authoredSlotKey(slot)
		if _, duplicate := expected[key]; duplicate {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("duplicate graph-authored execution slot %q", slot.caseID)
		}
		expected[key] = slot
	}
	results := make([]readiness.ReadinessCaseResult, 0, len(snapshot.candidates))
	seen := map[string]string{}
	var generatedAt time.Time
	nonPassed := false
	for _, candidate := range snapshot.candidates {
		receipt, exactBytes, err := schemas.DecodeReceipt(bytes.NewReader(candidate.bytes))
		if err != nil {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("decode receipt %q: %w", candidate.relative, err)
		}
		if !bytes.Equal(exactBytes, candidate.bytes) {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("receipt %q changed while decoding", candidate.relative)
		}
		if receipt.Binding.ContractGraphSourceHash != sourceHash {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("receipt %q ContractGraph source identity drifted", candidate.relative)
		}
		key := receiptBindingSlotKey(receipt.Binding)
		if _, known := expected[key]; !known {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("receipt %q does not match a graph-authored execution slot", candidate.relative)
		}
		if previous, duplicate := seen[key]; duplicate {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("receipts %q and %q duplicate one execution slot", previous, candidate.relative)
		}
		result := resultFromReceipt(receipt.Binding, candidate)
		resolved, err := resolver.Resolve(ctx, result)
		if err != nil {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("verify signed receipt %q: %w", candidate.relative, err)
		}
		if !resolved.Trusted || !bytes.Equal(resolved.Bytes, candidate.bytes) ||
			!reflect.DeepEqual(resolved.Binding, receipt.Binding) {
			return readiness.ReadinessResultBundle{}, collectionState{},
				fmt.Errorf("signed receipt %q trust result drifted", candidate.relative)
		}
		seen[key] = candidate.relative
		results = append(results, result)
		if result.CompletedAt.After(generatedAt) {
			generatedAt = result.CompletedAt
		}
		if result.Status != readiness.StatusPassed {
			nonPassed = true
		}
	}
	sort.Slice(results, func(i, j int) bool {
		return resultSlotKey(results[i]) < resultSlotKey(results[j])
	})
	state := collectionState{
		complete:     len(seen) == len(expected),
		missingSlots: len(expected) - len(seen),
		nonPassed:    nonPassed,
	}
	bundle := readiness.ReadinessResultBundle{
		GeneratedAt: generatedAt,
		Results:     results,
	}
	if len(results) == 0 {
		return bundle, state, nil
	}
	bundleBytes, err := json.Marshal(bundle)
	if err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			fmt.Errorf("marshal readiness result bundle: %w", err)
	}
	if _, err := schemas.DecodeBundle(bytes.NewReader(bundleBytes)); err != nil {
		return readiness.ReadinessResultBundle{}, collectionState{},
			fmt.Errorf("validate readiness result bundle: %w", err)
	}
	return bundle, state, nil
}

func productionResolver(
	receiptRoot string,
	evidenceRoot string,
	keyring []byte,
	schemas *readiness.WireSchemas,
) (readiness.ReceiptResolver, error) {
	return readinesstrust.NewSignedReceiptResolver(
		receiptRoot, evidenceRoot, keyring, schemas,
	)
}

func parseOptions(args []string) (options, error) {
	flags := flag.NewFlagSet("collect-readiness-result-bundle", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var result options
	flags.StringVar(&result.graphPath, "graph", "", "current ContractGraph JSON")
	flags.StringVar(&result.metadataDir, "metadata-dir", "", "canonical metadata directory")
	flags.StringVar(&result.runnerKeyring, "runner-keyring", "", "trusted runner public-key keyring")
	flags.StringVar(&result.receiptRoot, "receipt-root", "", "contained signed receipt root")
	flags.StringVar(&result.evidenceRoot, "evidence-root", "", "content-addressed evidence root")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, errors.New("positional arguments are forbidden")
	}
	for name, value := range map[string]string{
		"--graph": result.graphPath, "--metadata-dir": result.metadataDir,
		"--runner-keyring": result.runnerKeyring, "--receipt-root": result.receiptRoot,
		"--evidence-root": result.evidenceRoot,
	} {
		if strings.TrimSpace(value) == "" {
			return options{}, fmt.Errorf("%s is required", name)
		}
	}
	return result, nil
}

func decodeGraph(data []byte) (*graph.ContractGraph, error) {
	if err := readiness.RejectDuplicateJSONKeys(data); err != nil {
		return nil, fmt.Errorf("decode current ContractGraph: %w", err)
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var current graph.ContractGraph
	if err := decoder.Decode(&current); err != nil {
		return nil, fmt.Errorf("decode current ContractGraph: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return nil, errors.New("decode current ContractGraph: trailing JSON document")
		}
		return nil, fmt.Errorf("decode current ContractGraph trailing content: %w", err)
	}
	return &current, nil
}

func projectAuthoredSlots(current *graph.ContractGraph) ([]authoredSlot, error) {
	caseIdentities := map[string]struct{}{}
	slotIdentities := map[string]struct{}{}
	result := make([]authoredSlot, 0)
	for _, contract := range current.ReadinessCases {
		if err := validateCaseIdentity(contract); err != nil {
			return nil, err
		}
		caseKey := caseIdentityKey(contract)
		if _, duplicate := caseIdentities[caseKey]; duplicate {
			return nil, fmt.Errorf("duplicate readiness case identity %q", contract.CaseID)
		}
		caseIdentities[caseKey] = struct{}{}
		for _, execution := range contract.Executions {
			if err := validateExecutionIdentity(contract.CaseID, execution); err != nil {
				return nil, err
			}
			slot := authoredSlot{
				objectID: contract.ObjectID, specRef: contract.SpecRef,
				caseID: contract.CaseID, producer: contract.Producer,
				layer: contract.Layer, target: contract.Target,
				runnerSourcePath: contract.RunnerSourcePath, execution: execution,
			}
			key := authoredSlotKey(slot)
			if _, duplicate := slotIdentities[key]; duplicate {
				return nil, fmt.Errorf("duplicate execution requirement for readiness case %q", contract.CaseID)
			}
			slotIdentities[key] = struct{}{}
			result = append(result, slot)
		}
	}
	sort.Slice(result, func(i, j int) bool {
		return authoredSlotKey(result[i]) < authoredSlotKey(result[j])
	})
	return result, nil
}

func validateCaseIdentity(contract ast.ReadinessCaseContract) error {
	values := []string{
		contract.ObjectID, contract.SpecRef, contract.CaseID,
		string(contract.Producer), string(contract.Layer),
		string(contract.Target.Kind), contract.Target.ID,
		contract.RunnerSourcePath, contract.SourcePath,
	}
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("readiness case %q has an incomplete identity", contract.CaseID)
		}
	}
	if len(contract.Executions) == 0 {
		return fmt.Errorf("readiness case %q has no execution requirements", contract.CaseID)
	}
	return nil
}

func validateExecutionIdentity(
	caseID string,
	execution ast.ReadinessExecutionRequirement,
) error {
	for _, value := range []string{
		execution.Environment, execution.Platform, execution.DeviceClass,
		execution.Provider, string(execution.DigestBinding),
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("readiness case %q has an incomplete execution requirement", caseID)
		}
	}
	return nil
}

func caseIdentityKey(contract ast.ReadinessCaseContract) string {
	return strings.Join([]string{
		contract.ObjectID, contract.SpecRef, contract.CaseID,
		string(contract.Producer), string(contract.Layer),
		string(contract.Target.Kind), contract.Target.ID,
	}, "\x00")
}

func authoredSlotKey(slot authoredSlot) string {
	return strings.Join([]string{
		slot.objectID, slot.specRef, slot.caseID,
		string(slot.producer), string(slot.layer),
		string(slot.target.Kind), slot.target.ID, slot.runnerSourcePath,
		slot.execution.Environment, slot.execution.Platform,
		slot.execution.DeviceClass, slot.execution.Provider,
	}, "\x00")
}

func receiptBindingSlotKey(binding readiness.ReceiptBinding) string {
	return strings.Join([]string{
		binding.ObjectID, binding.SpecRef, binding.CaseID,
		string(binding.Producer), string(binding.Layer),
		string(binding.Target.Kind), binding.Target.ID, binding.RunnerSourcePath,
		binding.Environment, binding.Platform, binding.DeviceClass, binding.Provider,
	}, "\x00")
}

func resultSlotKey(result readiness.ReadinessCaseResult) string {
	return strings.Join([]string{
		result.ObjectID, result.SpecRef, result.CaseID,
		string(result.Producer), string(result.Layer),
		string(result.Target.Kind), result.Target.ID,
		result.Environment, result.Platform, result.DeviceClass, result.Provider,
	}, "\x00")
}

func resultFromReceipt(
	binding readiness.ReceiptBinding,
	file receiptFile,
) readiness.ReadinessCaseResult {
	return readiness.ReadinessCaseResult{
		ObjectID: binding.ObjectID, SpecRef: binding.SpecRef,
		CaseID: binding.CaseID, Producer: binding.Producer,
		Layer: binding.Layer, Status: binding.Status, Target: binding.Target,
		CommitSHA:               binding.CommitSHA,
		ContractGraphSourceHash: binding.ContractGraphSourceHash,
		DeploymentTarget:        binding.DeploymentTarget, BaselineID: binding.BaselineID,
		PackageDigest:           binding.PackageDigest,
		ConfigurationDigest:     binding.ConfigurationDigest,
		CandidateManifestSHA256: binding.CandidateManifestSHA256,
		CandidateDigest:         binding.CandidateDigest, ReleaseDigest: binding.ReleaseDigest,
		Environment: binding.Environment, Platform: binding.Platform,
		DeviceClass: binding.DeviceClass, Provider: binding.Provider,
		StartedAt: binding.StartedAt, CompletedAt: binding.CompletedAt,
		RunnerIdentity: binding.RunnerIdentity,
		ArtifactSHA256: file.digest, ArtifactPath: file.relative,
	}
}

func scanReceiptTree(root string) (receiptTreeSnapshot, error) {
	if strings.TrimSpace(root) == "" {
		return receiptTreeSnapshot{}, errors.New("receipt root is required")
	}
	absRoot, err := filepath.Abs(root)
	if err != nil {
		return receiptTreeSnapshot{}, fmt.Errorf("resolve receipt root: %w", err)
	}
	rootInfo, err := os.Lstat(absRoot)
	if err != nil || rootInfo.Mode()&os.ModeSymlink != 0 || !rootInfo.IsDir() {
		return receiptTreeSnapshot{}, errors.New("receipt root must be a stable directory")
	}
	result := receiptTreeSnapshot{
		rootInfo: rootInfo, directories: map[string]os.FileInfo{},
		files: map[string]receiptFile{},
	}
	err = filepath.WalkDir(absRoot, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == absRoot {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("receipt tree contains symlink %q", path)
		}
		if entry.IsDir() {
			info, err := os.Lstat(path)
			if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
				return fmt.Errorf("receipt tree contains unstable directory %q", path)
			}
			relative, err := filepath.Rel(absRoot, path)
			if err != nil {
				return err
			}
			result.directories[filepath.ToSlash(relative)] = info
			return nil
		}
		info, err := entry.Info()
		if err != nil || !info.Mode().IsRegular() {
			return fmt.Errorf("receipt tree contains non-regular file %q", path)
		}
		relative, err := filepath.Rel(absRoot, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if !strings.HasSuffix(relative, ".json") {
			return fmt.Errorf("receipt tree contains non-JSON file %q", relative)
		}
		stable, err := readContainedStableFile(absRoot, relative, maxReceiptInputBytes)
		if err != nil {
			return fmt.Errorf("read receipt tree file %q: %w", relative, err)
		}
		digest := sha256.Sum256(stable.bytes)
		file := receiptFile{
			relative: relative, bytes: stable.bytes, digest: hex.EncodeToString(digest[:]),
			info: stable.info,
		}
		result.files[relative] = file
		if !strings.HasSuffix(relative, ".sig.json") {
			result.candidates = append(result.candidates, file)
		}
		return nil
	})
	if err != nil {
		return receiptTreeSnapshot{}, fmt.Errorf("scan receipt tree: %w", err)
	}
	currentRoot, err := os.Lstat(absRoot)
	if err != nil || currentRoot.Mode()&os.ModeSymlink != 0 || !currentRoot.IsDir() ||
		!os.SameFile(rootInfo, currentRoot) {
		return receiptTreeSnapshot{}, errors.New("receipt root changed while scanning")
	}
	sort.Slice(result.candidates, func(i, j int) bool {
		return result.candidates[i].relative < result.candidates[j].relative
	})
	for _, candidate := range result.candidates {
		if _, present := result.files[candidate.relative+".sig.json"]; !present {
			return receiptTreeSnapshot{}, fmt.Errorf("receipt %q is unsigned", candidate.relative)
		}
	}
	for relative := range result.files {
		if strings.HasSuffix(relative, ".sig.json") {
			receiptPath := strings.TrimSuffix(relative, ".sig.json")
			if _, present := result.files[receiptPath]; !present {
				return receiptTreeSnapshot{}, fmt.Errorf("signature %q has no receipt", relative)
			}
		}
	}
	paths := make([]string, 0, len(result.files))
	for path := range result.files {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	hash := sha256.New()
	for _, path := range paths {
		_, _ = hash.Write([]byte(path))
		_, _ = hash.Write([]byte{0})
		_, _ = hash.Write([]byte(result.files[path].digest))
		_, _ = hash.Write([]byte{'\n'})
	}
	result.fingerprint = hex.EncodeToString(hash.Sum(nil))
	return result, nil
}

func sameReceiptTree(left, right receiptTreeSnapshot) bool {
	if left.rootInfo == nil || right.rootInfo == nil ||
		!os.SameFile(left.rootInfo, right.rootInfo) ||
		left.fingerprint != right.fingerprint ||
		len(left.directories) != len(right.directories) || len(left.files) != len(right.files) {
		return false
	}
	for path, leftInfo := range left.directories {
		rightInfo, exists := right.directories[path]
		if !exists || !os.SameFile(leftInfo, rightInfo) {
			return false
		}
	}
	for path, leftFile := range left.files {
		rightFile, exists := right.files[path]
		if !exists || leftFile.info == nil || rightFile.info == nil ||
			!os.SameFile(leftFile.info, rightFile.info) || leftFile.digest != rightFile.digest {
			return false
		}
	}
	return true
}

func snapshotBoundEvidence(
	root string,
	receipts []receiptFile,
	schemas *readiness.WireSchemas,
) (evidenceSnapshot, error) {
	if schemas == nil {
		return evidenceSnapshot{}, errors.New("readiness wire schema authority is required")
	}
	absRoot, err := filepath.Abs(root)
	if err != nil {
		return evidenceSnapshot{}, fmt.Errorf("resolve evidence root: %w", err)
	}
	rootInfo, err := stableDirectoryInfo(absRoot)
	if err != nil {
		return evidenceSnapshot{}, fmt.Errorf("inspect evidence root: %w", err)
	}
	shaRoot := filepath.Join(absRoot, "sha256")
	shaInfo, err := stableDirectoryInfo(shaRoot)
	if err != nil {
		return evidenceSnapshot{}, fmt.Errorf("inspect content-addressed evidence directory: %w", err)
	}
	result := evidenceSnapshot{
		rootInfo: rootInfo,
		shaInfo:  shaInfo,
		files:    make(map[string]evidenceFile),
	}
	for _, candidate := range receipts {
		receipt, exactBytes, err := schemas.DecodeReceipt(bytes.NewReader(candidate.bytes))
		if err != nil {
			return evidenceSnapshot{}, fmt.Errorf("decode receipt %q for evidence binding: %w", candidate.relative, err)
		}
		if !bytes.Equal(exactBytes, candidate.bytes) {
			return evidenceSnapshot{}, fmt.Errorf("receipt %q changed while binding evidence", candidate.relative)
		}
		if _, exists := result.files[receipt.EvidenceSHA256]; exists {
			continue
		}
		file, err := readContainedStableFile(
			absRoot, filepath.ToSlash(filepath.Join("sha256", receipt.EvidenceSHA256)),
			maxEvidenceInputBytes,
		)
		if err != nil {
			return evidenceSnapshot{}, fmt.Errorf("read bound evidence %q: %w", receipt.EvidenceSHA256, err)
		}
		digest := sha256.Sum256(file.bytes)
		actual := hex.EncodeToString(digest[:])
		if actual != receipt.EvidenceSHA256 {
			return evidenceSnapshot{}, fmt.Errorf("bound evidence %q digest mismatch", receipt.EvidenceSHA256)
		}
		result.files[receipt.EvidenceSHA256] = evidenceFile{digest: actual, info: file.info}
	}
	currentRoot, err := stableDirectoryInfo(absRoot)
	if err != nil || !os.SameFile(rootInfo, currentRoot) {
		return evidenceSnapshot{}, errors.New("evidence root changed while scanning")
	}
	currentSHA, err := stableDirectoryInfo(shaRoot)
	if err != nil || !os.SameFile(shaInfo, currentSHA) {
		return evidenceSnapshot{}, errors.New("content-addressed evidence directory changed while scanning")
	}
	return result, nil
}

func stableDirectoryInfo(path string) (os.FileInfo, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return nil, errors.New("path must be a stable directory")
	}
	return info, nil
}

func readContainedStableFile(root, relative string, limit int64) (stableFile, error) {
	if root == "" || relative == "" || limit <= 0 || filepath.IsAbs(relative) {
		return stableFile{}, errors.New("contained file root, relative path and positive limit are required")
	}
	parts := strings.Split(filepath.ToSlash(relative), "/")
	current := root
	inspected := make([]struct {
		path string
		info os.FileInfo
	}, 0, len(parts)+1)
	rootInfo, err := stableDirectoryInfo(root)
	if err != nil {
		return stableFile{}, err
	}
	inspected = append(inspected, struct {
		path string
		info os.FileInfo
	}{path: root, info: rootInfo})
	for index, part := range parts {
		if part == "" || part == "." || part == ".." {
			return stableFile{}, errors.New("contained file path is invalid")
		}
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if err != nil {
			return stableFile{}, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return stableFile{}, fmt.Errorf("contained file path contains symlink at %q", strings.Join(parts[:index+1], "/"))
		}
		if index < len(parts)-1 && !info.IsDir() {
			return stableFile{}, errors.New("contained file path component is not a directory")
		}
		if index == len(parts)-1 && (!info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > limit) {
			return stableFile{}, errors.New("contained file must be a bounded non-empty regular file")
		}
		inspected = append(inspected, struct {
			path string
			info os.FileInfo
		}{path: current, info: info})
	}
	file, err := os.Open(current)
	if err != nil {
		return stableFile{}, err
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil || !opened.Mode().IsRegular() || opened.Size() <= 0 || opened.Size() > limit ||
		!os.SameFile(inspected[len(inspected)-1].info, opened) {
		return stableFile{}, errors.New("contained file changed while opening")
	}
	for _, item := range inspected {
		currentInfo, err := os.Lstat(item.path)
		if err != nil || currentInfo.Mode()&os.ModeSymlink != 0 || !os.SameFile(item.info, currentInfo) {
			return stableFile{}, errors.New("contained file path changed while opening")
		}
	}
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil {
		return stableFile{}, err
	}
	if len(data) == 0 || int64(len(data)) > limit {
		return stableFile{}, errors.New("contained file size is invalid")
	}
	after, err := os.Lstat(current)
	if err != nil || after.Mode()&os.ModeSymlink != 0 || !os.SameFile(opened, after) ||
		after.Size() != opened.Size() || after.ModTime() != opened.ModTime() {
		return stableFile{}, errors.New("contained file changed while reading")
	}
	return stableFile{bytes: data, info: after}, nil
}

func sameEvidenceSnapshot(left, right evidenceSnapshot) bool {
	if left.rootInfo == nil || right.rootInfo == nil || left.shaInfo == nil || right.shaInfo == nil ||
		!os.SameFile(left.rootInfo, right.rootInfo) || !os.SameFile(left.shaInfo, right.shaInfo) ||
		len(left.files) != len(right.files) {
		return false
	}
	for digest, leftFile := range left.files {
		rightFile, exists := right.files[digest]
		if !exists || leftFile.info == nil || rightFile.info == nil ||
			!os.SameFile(leftFile.info, rightFile.info) || leftFile.digest != rightFile.digest {
			return false
		}
	}
	return true
}

func writeJSON(writer io.Writer, value any) error {
	encoder := json.NewEncoder(writer)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}
