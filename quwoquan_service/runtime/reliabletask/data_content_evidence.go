package reliabletask

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

const dataContentObjectTransactionApplySchema = "quwoquan_data.object_transaction_apply"

var dataContentSensitivePathPattern = regexp.MustCompile(
	`(?i)(?:api[_-]?key|credential|secret|password|access[_-]?token|refresh[_-]?token|cookie|session)`,
)

type DataContentResultVerifier interface {
	VerifyDataContentResult(
		ctx context.Context,
		item DataContentWorkItem,
		result DataContentExecutionResult,
	) error
}

type DataContentResultVerifierFunc func(
	context.Context,
	DataContentWorkItem,
	DataContentExecutionResult,
) error

func (fn DataContentResultVerifierFunc) VerifyDataContentResult(
	ctx context.Context,
	item DataContentWorkItem,
	result DataContentExecutionResult,
) error {
	return fn(ctx, item, result)
}

// DataContentFilesystemEvidenceVerifier verifies the immutable Python object
// transaction apply report and the current canonical object before a publish
// task may be counted as canonically accepted in either lifecycle state.
type DataContentFilesystemEvidenceVerifier struct {
	PublishRoot  string
	EvidenceRoot string
}

type dataContentObjectTransactionApply struct {
	Schema              string `json:"schema"`
	Status              string `json:"status"`
	TransactionID       string `json:"transactionId"`
	ExecutionID         string `json:"executionId"`
	ObjectKind          string `json:"objectKind"`
	ObjectRef           string `json:"objectRef"`
	ObjectClosureDigest string `json:"objectClosureDigest"`
}

func (v DataContentFilesystemEvidenceVerifier) VerifyDataContentResult(
	ctx context.Context,
	item DataContentWorkItem,
	result DataContentExecutionResult,
) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if result.AcceptanceClass != DataContentAcceptanceCanonicalPool {
		return nil
	}
	publishRoot, err := existingDataContentRoot(v.PublishRoot, "publishRoot")
	if err != nil {
		return err
	}
	evidenceRoot, err := existingDataContentRoot(v.EvidenceRoot, "evidenceRoot")
	if err != nil {
		return err
	}
	applyPath, err := resolveDataContentRelativeFile(
		evidenceRoot,
		result.ResultEnvelopeRef,
		"resultEnvelopeRef",
	)
	if err != nil {
		return err
	}
	apply, err := readDataContentApplyReport(applyPath)
	if err != nil {
		return err
	}
	if apply.Schema != dataContentObjectTransactionApplySchema ||
		apply.Status != "applied" {
		return fmt.Errorf("reliabletask canonical result apply report is not applied")
	}
	if strings.TrimSpace(apply.TransactionID) != strings.TrimSpace(result.ObjectTransactionID) ||
		strings.TrimSpace(apply.ExecutionID) != item.ExecutionID {
		return fmt.Errorf("reliabletask canonical result apply report binding mismatch")
	}
	if !validDataContentSHA256(apply.ObjectClosureDigest) {
		return fmt.Errorf("reliabletask canonical result object closure digest is invalid")
	}
	canonicalRef := filepath.ToSlash(
		filepath.Join(strings.TrimSpace(apply.ObjectKind), strings.TrimSpace(apply.ObjectRef)),
	)
	if canonicalRef != strings.TrimSpace(result.CanonicalObjectRef) {
		return fmt.Errorf("reliabletask canonical result canonical object binding mismatch")
	}
	canonicalRoot, err := resolveDataContentRelativeDirectory(
		publishRoot,
		canonicalRef,
		"canonicalObjectRef",
	)
	if err != nil {
		return err
	}
	merkle, err := dataContentTreeMerkle(canonicalRoot)
	if err != nil {
		return err
	}
	if merkle != strings.TrimSpace(result.CanonicalObjectSHA256) {
		return fmt.Errorf("reliabletask canonical result canonical object digest mismatch")
	}
	return nil
}

const (
	dataContentExecutionSpecRef       = "0.plan/execution_spec.yaml"
	dataContentReviewAttestationRef   = "5.review/attestation.json"
	dataContentFinalizationReportRef  = "5.review/finalization_report.json"
	dataContentFinalizationReportPath = "5.review/finalization_report.json"
)

var dataContentExecutionIDCarrierPattern = regexp.MustCompile(
	`^20[0-9]{6}--[a-z][a-z0-9-]*-(homepage|article|image|video)-[a-z][a-z0-9-]*--[a-z0-9][a-z0-9-]*--(?:pilot|scale|full)-[0-9]{3,}$`,
)

type dataContentExecutionSpec struct {
	Provenance struct {
		CreatedAt string `yaml:"createdAt"`
	} `yaml:"provenance"`
}

type dataContentReviewAttestation struct {
	ExecutionID     string `json:"executionId"`
	ObjectRef       string `json:"objectRef"`
	Decision        string `json:"decision"`
	FinalizationRef string `json:"finalizationRef"`
}

type dataContentFinalizationReport struct {
	Schema          string `json:"schema"`
	ExecutionID     string `json:"executionId"`
	FinalRef        string `json:"finalRef"`
	FinalArticleRef string `json:"finalArticleRef"`
	FinalSHA256     string `json:"finalSha256"`
	VideoRef        string `json:"videoRef"`
	PosterRef       string `json:"posterRef"`
	SubtitlesRef    string `json:"subtitlesRef"`
}

type dataContentObjectManifest struct {
	ContentType string `json:"contentType"`
	Assets      []struct {
		FileName string `json:"fileName"`
		Kind     string `json:"kind"`
	} `json:"assets"`
}

// ResolveDataContentExecutionCreatedAt reads the immutable execution
// specification copied into the work package at creation. Fleet-local task
// timestamps are intentionally not accepted as an end-to-end start time.
func ResolveDataContentExecutionCreatedAt(
	evidenceRoot string,
	executionID string,
) (time.Time, error) {
	workPackage, err := dataContentWorkPackage(evidenceRoot, executionID)
	if err != nil {
		return time.Time{}, err
	}
	specPath, err := resolveDataContentRelativeFile(
		workPackage,
		dataContentExecutionSpecRef,
		"executionSpec",
	)
	if err != nil {
		return time.Time{}, err
	}
	payload, err := os.ReadFile(specPath)
	if err != nil {
		return time.Time{}, fmt.Errorf("read data content execution spec: %w", err)
	}
	var spec dataContentExecutionSpec
	if err := yaml.Unmarshal(payload, &spec); err != nil {
		return time.Time{}, fmt.Errorf("decode data content execution spec: %w", err)
	}
	createdAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(spec.Provenance.CreatedAt))
	if err != nil {
		return time.Time{}, fmt.Errorf(
			"reliabletask data evidence execution provenance.createdAt is invalid: %w",
			err,
		)
	}
	return createdAt.UTC(), nil
}

// CountFinalizedDataContentObjects observes how many finished objects the
// execution work package holds for the single carrier frozen by the fleet
// request. Homepage, article, image and video use their own final artifact
// signatures; a homepage page/manifest/entity triple cannot stand in for a
// post. It is a metric only; the commercial quota gate stays bound to
// ReliableTask results.
func CountFinalizedDataContentObjects(
	evidenceRoot string,
	executionID string,
	jobs []DataContentJob,
) (int, error) {
	root, err := existingDataContentRoot(evidenceRoot, "evidenceRoot")
	if err != nil {
		return 0, err
	}
	carrier, err := dataContentFleetCarrier(executionID, jobs)
	if err != nil {
		return 0, err
	}
	workPackage, err := resolveDataContentRelativePath(
		root,
		filepath.ToSlash(filepath.Join("data", "tasks", strings.TrimSpace(executionID))),
		"executionId",
	)
	if err != nil {
		return 0, err
	}
	workPackageInfo, err := os.Lstat(workPackage)
	if os.IsNotExist(err) {
		return 0, nil
	}
	if err != nil {
		return 0, fmt.Errorf("reliabletask data evidence work package: %w", err)
	}
	if !workPackageInfo.IsDir() || workPackageInfo.Mode()&os.ModeSymlink != 0 {
		return 0, fmt.Errorf("reliabletask data evidence work package must be a directory")
	}
	searchRoot := filepath.Join(workPackage, "posts", carrier)
	if carrier == "homepage" {
		searchRoot = filepath.Join(workPackage, "entities")
	}
	info, err := os.Lstat(searchRoot)
	if os.IsNotExist(err) {
		return 0, nil
	}
	if err != nil {
		return 0, fmt.Errorf("reliabletask data evidence carrier root: %w", err)
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return 0, fmt.Errorf("reliabletask data evidence carrier root must be a directory")
	}
	finalized := 0
	walkErr := filepath.WalkDir(
		searchRoot,
		func(path string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.Type()&os.ModeSymlink != 0 {
				if entry.IsDir() {
					return fs.SkipDir
				}
				return nil
			}
			if entry.IsDir() || entry.Name() != "attestation.json" {
				return nil
			}
			relative, err := filepath.Rel(searchRoot, path)
			if err != nil || !strings.HasSuffix(
				filepath.ToSlash(relative),
				dataContentReviewAttestationRef,
			) {
				return nil
			}
			objectRoot := filepath.Dir(filepath.Dir(path))
			ok, err := dataContentObjectFinalized(
				objectRoot,
				executionID,
				carrier,
			)
			if err != nil {
				return err
			}
			if ok {
				finalized++
			}
			return nil
		},
	)
	if walkErr != nil {
		return 0, walkErr
	}
	return finalized, nil
}

func dataContentWorkPackage(evidenceRoot string, executionID string) (string, error) {
	root, err := existingDataContentRoot(evidenceRoot, "evidenceRoot")
	if err != nil {
		return "", err
	}
	execution := strings.TrimSpace(executionID)
	if execution == "" {
		return "", fmt.Errorf("reliabletask data evidence requires executionId")
	}
	workPackage, err := resolveDataContentRelativeDirectory(
		root,
		filepath.ToSlash(filepath.Join("data", "tasks", execution)),
		"executionId",
	)
	if err != nil {
		return "", err
	}
	return workPackage, nil
}

func dataContentFleetCarrier(executionID string, jobs []DataContentJob) (string, error) {
	matches := dataContentExecutionIDCarrierPattern.FindStringSubmatch(
		strings.TrimSpace(executionID),
	)
	if len(matches) != 2 {
		return "", fmt.Errorf("reliabletask data evidence executionId carrier is invalid")
	}
	if len(jobs) == 0 {
		return "", fmt.Errorf("reliabletask data evidence requires frozen jobs")
	}
	carrier := matches[1]
	for _, job := range jobs {
		if strings.TrimSpace(job.ExecutionID) != strings.TrimSpace(executionID) ||
			strings.TrimSpace(job.Carrier) != carrier {
			return "", fmt.Errorf(
				"reliabletask data evidence fleet carrier binding mismatch",
			)
		}
	}
	return carrier, nil
}

func dataContentObjectFinalized(
	directory string,
	executionID string,
	carrier string,
) (bool, error) {
	attestation, err := readDataContentJSON[dataContentReviewAttestation](
		filepath.Join(directory, dataContentReviewAttestationRef),
	)
	if err != nil {
		return false, nil
	}
	if strings.TrimSpace(attestation.ExecutionID) != strings.TrimSpace(executionID) ||
		strings.TrimSpace(attestation.ObjectRef) == "" ||
		attestation.Decision != "approved" ||
		attestation.FinalizationRef != dataContentFinalizationReportPath {
		return false, nil
	}
	manifest, err := readDataContentJSON[dataContentObjectManifest](
		filepath.Join(directory, "manifest.json"),
	)
	if err != nil {
		return false, nil
	}
	finalization, err := readDataContentJSON[dataContentFinalizationReport](
		filepath.Join(directory, dataContentFinalizationReportRef),
	)
	if err != nil {
		return false, nil
	}
	switch carrier {
	case "homepage":
		if !dataContentRegularFiles(directory, "_entity.json", "manifest.json", "page.md") {
			return false, nil
		}
		return dataContentTextFinalized(
			directory,
			executionID,
			finalization,
			"page.md",
		), nil
	case "article":
		if manifest.ContentType != "article" ||
			!dataContentRegularFiles(directory, "manifest.json", "article.md") {
			return false, nil
		}
		return dataContentTextFinalized(
			directory,
			executionID,
			finalization,
			"article.md",
		), nil
	case "image":
		if manifest.ContentType != "image" {
			return false, nil
		}
		return dataContentImageFinalized(directory, manifest), nil
	case "video":
		if manifest.ContentType != "video" ||
			finalization.Schema != "quwoquan_data.video_finalization_report" {
			return false, nil
		}
		return dataContentVideoFinalized(directory, manifest, finalization), nil
	default:
		return false, fmt.Errorf("unsupported data content carrier %q", carrier)
	}
}

func dataContentTextFinalized(
	directory string,
	executionID string,
	finalization dataContentFinalizationReport,
	expectedRef string,
) bool {
	finalRef := strings.TrimSpace(finalization.FinalRef)
	if finalRef == "" {
		finalRef = strings.TrimSpace(finalization.FinalArticleRef)
	}
	if finalRef != expectedRef ||
		(finalization.ExecutionID != "" &&
			strings.TrimSpace(finalization.ExecutionID) != strings.TrimSpace(executionID)) {
		return false
	}
	digest, err := dataContentFileSHA256(filepath.Join(directory, expectedRef))
	if err != nil {
		return false
	}
	return strings.TrimSpace(finalization.FinalSHA256) ==
		"sha256:"+hex.EncodeToString(digest[:])
}

func dataContentImageFinalized(
	directory string,
	manifest dataContentObjectManifest,
) bool {
	for _, asset := range manifest.Assets {
		ref := strings.TrimSpace(asset.FileName)
		extension := strings.ToLower(filepath.Ext(ref))
		if ref == "" || !dataContentImageExtension(extension) {
			continue
		}
		if dataContentReferencedFilesExist(directory, ref) {
			return true
		}
	}
	return false
}

func dataContentImageExtension(extension string) bool {
	switch extension {
	case ".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp":
		return true
	default:
		return false
	}
}

func dataContentVideoFinalized(
	directory string,
	manifest dataContentObjectManifest,
	finalization dataContentFinalizationReport,
) bool {
	videoRef := strings.TrimSpace(finalization.VideoRef)
	posterRef := strings.TrimSpace(finalization.PosterRef)
	subtitlesRef := strings.TrimSpace(finalization.SubtitlesRef)
	if strings.ToLower(filepath.Ext(videoRef)) != ".mp4" ||
		!dataContentImageExtension(strings.ToLower(filepath.Ext(posterRef))) ||
		strings.ToLower(filepath.Ext(subtitlesRef)) != ".vtt" {
		return false
	}
	manifestBindsVideo := false
	for _, asset := range manifest.Assets {
		if strings.TrimSpace(asset.FileName) == videoRef &&
			(strings.TrimSpace(asset.Kind) == "" || strings.TrimSpace(asset.Kind) == "video") {
			manifestBindsVideo = true
			break
		}
	}
	return manifestBindsVideo && dataContentReferencedFilesExist(
		directory,
		videoRef,
		posterRef,
		subtitlesRef,
	)
}

func dataContentReferencedFilesExist(directory string, refs ...string) bool {
	for _, ref := range refs {
		if _, err := resolveDataContentRelativeFile(directory, ref, "finalArtifactRef"); err != nil {
			return false
		}
	}
	return len(refs) > 0
}

func dataContentRegularFiles(directory string, refs ...string) bool {
	for _, ref := range refs {
		info, err := os.Lstat(filepath.Join(directory, filepath.FromSlash(ref)))
		if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
			return false
		}
	}
	return true
}

func readDataContentJSON[T any](path string) (T, error) {
	var result T
	info, err := os.Lstat(path)
	if err != nil {
		return result, err
	}
	if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
		return result, fmt.Errorf("data content evidence JSON must be a regular file")
	}
	payload, err := os.ReadFile(path)
	if err != nil {
		return result, err
	}
	if err := json.Unmarshal(payload, &result); err != nil {
		return result, err
	}
	return result, nil
}

func existingDataContentRoot(value string, label string) (string, error) {
	root := strings.TrimSpace(value)
	if root == "" {
		return "", fmt.Errorf("reliabletask data evidence verifier requires %s", label)
	}
	absolute, err := filepath.Abs(root)
	if err != nil {
		return "", fmt.Errorf("reliabletask data evidence %s: %w", label, err)
	}
	info, err := os.Stat(absolute)
	if err != nil {
		return "", fmt.Errorf("reliabletask data evidence %s: %w", label, err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("reliabletask data evidence %s must be a directory", label)
	}
	return absolute, nil
}

func resolveDataContentRelativePath(root string, value string, label string) (string, error) {
	ref := strings.TrimSpace(value)
	if ref == "" || filepath.IsAbs(ref) {
		return "", fmt.Errorf("reliabletask data evidence %s must be relative", label)
	}
	clean := filepath.Clean(filepath.FromSlash(ref))
	if clean == "." || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("reliabletask data evidence %s escapes its root", label)
	}
	target := filepath.Join(root, clean)
	relative, err := filepath.Rel(root, target)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("reliabletask data evidence %s escapes its root", label)
	}
	return target, nil
}

func resolveDataContentRelativeFile(root string, value string, label string) (string, error) {
	target, err := resolveDataContentRelativePath(root, value, label)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(target)
	if err != nil {
		return "", fmt.Errorf("reliabletask data evidence %s: %w", label, err)
	}
	if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
		return "", fmt.Errorf("reliabletask data evidence %s must be a regular file", label)
	}
	return target, nil
}

func resolveDataContentRelativeDirectory(root string, value string, label string) (string, error) {
	target, err := resolveDataContentRelativePath(root, value, label)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(target)
	if err != nil {
		return "", fmt.Errorf("reliabletask data evidence %s: %w", label, err)
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return "", fmt.Errorf("reliabletask data evidence %s must be a directory", label)
	}
	return target, nil
}

func readDataContentApplyReport(path string) (dataContentObjectTransactionApply, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return dataContentObjectTransactionApply{}, err
	}
	var report dataContentObjectTransactionApply
	if err := json.Unmarshal(data, &report); err != nil {
		return dataContentObjectTransactionApply{}, fmt.Errorf(
			"reliabletask commercial result apply report is invalid: %w",
			err,
		)
	}
	return report, nil
}

type dataContentTreeLeaf struct {
	path string
	hash [32]byte
}

func dataContentTreeMerkle(root string) (string, error) {
	leaves := make([]dataContentTreeLeaf, 0)
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("reliabletask canonical object cannot contain symlink: %s", path)
		}
		if entry.IsDir() {
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("reliabletask canonical object contains non-regular file: %s", path)
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if dataContentSensitivePathPattern.MatchString(relative) {
			sum := sha256.Sum256([]byte(relative))
			relative = "redacted/" + hex.EncodeToString(sum[:])
		}
		blobHash, err := dataContentFileSHA256(path)
		if err != nil {
			return err
		}
		leafInput := "blob\x00" + relative + "\x00sha256:" +
			hex.EncodeToString(blobHash[:]) + "\x00" + strconv.FormatInt(info.Size(), 10)
		leaves = append(leaves, dataContentTreeLeaf{
			path: relative,
			hash: sha256.Sum256([]byte(leafInput)),
		})
		return nil
	})
	if err != nil {
		return "", err
	}
	sort.Slice(leaves, func(i, j int) bool {
		return leaves[i].path < leaves[j].path
	})
	if len(leaves) == 0 {
		empty := sha256.Sum256(nil)
		return "sha256:" + hex.EncodeToString(empty[:]), nil
	}
	level := make([][32]byte, 0, len(leaves))
	for _, leaf := range leaves {
		level = append(level, leaf.hash)
	}
	for len(level) > 1 {
		if len(level)%2 != 0 {
			level = append(level, level[len(level)-1])
		}
		next := make([][32]byte, 0, len(level)/2)
		for index := 0; index < len(level); index += 2 {
			input := make([]byte, 0, len("node\x00")+64)
			input = append(input, []byte("node\x00")...)
			input = append(input, level[index][:]...)
			input = append(input, level[index+1][:]...)
			next = append(next, sha256.Sum256(input))
		}
		level = next
	}
	return "sha256:" + hex.EncodeToString(level[0][:]), nil
}

func dataContentFileSHA256(path string) ([32]byte, error) {
	handle, err := os.Open(path)
	if err != nil {
		return [32]byte{}, err
	}
	defer handle.Close()
	digest := sha256.New()
	if _, err := io.Copy(digest, handle); err != nil {
		return [32]byte{}, err
	}
	var result [32]byte
	copy(result[:], digest.Sum(nil))
	return result, nil
}
