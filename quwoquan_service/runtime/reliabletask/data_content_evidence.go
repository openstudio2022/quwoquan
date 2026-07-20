package reliabletask

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
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
// task may be counted as commercially accepted.
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
	if result.AcceptanceClass != DataContentAcceptanceCommercialCanonical {
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
		return fmt.Errorf("reliabletask commercial result apply report is not applied")
	}
	if strings.TrimSpace(apply.TransactionID) != strings.TrimSpace(result.ObjectTransactionID) ||
		strings.TrimSpace(apply.ExecutionID) != item.ExecutionID {
		return fmt.Errorf("reliabletask commercial result apply report binding mismatch")
	}
	if !validDataContentSHA256(apply.ObjectClosureDigest) {
		return fmt.Errorf("reliabletask commercial result object closure digest is invalid")
	}
	canonicalRef := filepath.ToSlash(
		filepath.Join(strings.TrimSpace(apply.ObjectKind), strings.TrimSpace(apply.ObjectRef)),
	)
	if canonicalRef != strings.TrimSpace(result.CanonicalObjectRef) {
		return fmt.Errorf("reliabletask commercial result canonical object binding mismatch")
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
		return fmt.Errorf("reliabletask commercial result canonical object digest mismatch")
	}
	return nil
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
