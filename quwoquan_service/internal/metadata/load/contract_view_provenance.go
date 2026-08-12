package load

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	contractViewProvenanceFilename = ".contract-view-provenance"
	contractViewProvenanceFormat   = "contract-view-provenance"
)

type contractViewProvenanceSource struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type contractViewProvenanceFile struct {
	Path        string   `json:"path"`
	SHA256      string   `json:"sha256"`
	SourcePaths []string `json:"sourcePaths"`
}

type contractViewProvenanceDocument struct {
	Format     string                         `json:"format"`
	ViewDigest string                         `json:"viewDigest"`
	Sources    []contractViewProvenanceSource `json:"sources"`
	Files      []contractViewProvenanceFile   `json:"files"`
}

// contractViewProvenance binds immutable bytes in a disposable compiler view
// back to their physical, repository-owned sources. It deliberately does not
// require current source bytes to remain equal after the snapshot is built:
// later source writes must not change an already-running compiler/test input.
type contractViewProvenance struct {
	metadataDir    string
	repositoryRoot string
	filesByPath    map[string]contractViewProvenanceFile
}

func loadContractViewProvenance(metadataDir string) (*contractViewProvenance, error) {
	manifestPath := filepath.Join(metadataDir, contractViewProvenanceFilename)
	payload, err := os.ReadFile(manifestPath)
	if os.IsNotExist(err) {
		if _, rootErr := repositoryRootForContractView(metadataDir); rootErr == nil {
			return nil, fmt.Errorf(
				"contract view below .qwq_output is missing %s",
				contractViewProvenanceFilename,
			)
		}
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read contract view provenance: %w", err)
	}

	var document contractViewProvenanceDocument
	decoder := json.NewDecoder(bufio.NewReader(strings.NewReader(string(payload))))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&document); err != nil {
		return nil, fmt.Errorf("decode contract view provenance: %w", err)
	}
	if err := ensureJSONEOF(decoder); err != nil {
		return nil, fmt.Errorf("decode contract view provenance: %w", err)
	}
	if document.Format != contractViewProvenanceFormat {
		return nil, fmt.Errorf(
			"contract view provenance format=%q, want %q",
			document.Format,
			contractViewProvenanceFormat,
		)
	}
	if !canonicalSHA256(document.ViewDigest) {
		return nil, fmt.Errorf("contract view provenance has invalid viewDigest")
	}

	repositoryRoot, err := repositoryRootForContractView(metadataDir)
	if err != nil {
		return nil, err
	}
	sourceDigests := make(map[string]string, len(document.Sources))
	previousPath := ""
	for _, source := range document.Sources {
		if err := validateRepositoryRelativePath(source.Path); err != nil {
			return nil, fmt.Errorf("contract view provenance source %q: %w", source.Path, err)
		}
		if source.Path <= previousPath {
			return nil, fmt.Errorf("contract view provenance sources must be unique and sorted")
		}
		previousPath = source.Path
		if !canonicalSHA256(source.SHA256) {
			return nil, fmt.Errorf("contract view provenance source %q has invalid sha256", source.Path)
		}
		absolute := filepath.Join(repositoryRoot, filepath.FromSlash(source.Path))
		if err := validatePhysicalProvenanceSource(repositoryRoot, absolute); err != nil {
			return nil, fmt.Errorf("contract view provenance source %q: %w", source.Path, err)
		}
		sourceDigests[source.Path] = source.SHA256
	}
	if len(sourceDigests) == 0 {
		return nil, fmt.Errorf("contract view provenance sources are empty")
	}

	filesByPath := make(map[string]contractViewProvenanceFile, len(document.Files))
	previousPath = ""
	viewDigest := sha256.New()
	for _, file := range document.Files {
		if err := validateRepositoryRelativePath(file.Path); err != nil {
			return nil, fmt.Errorf("contract view provenance file %q: %w", file.Path, err)
		}
		if file.Path <= previousPath {
			return nil, fmt.Errorf("contract view provenance files must be unique and sorted")
		}
		previousPath = file.Path
		if !canonicalSHA256(file.SHA256) {
			return nil, fmt.Errorf("contract view provenance file %q has invalid sha256", file.Path)
		}
		if len(file.SourcePaths) == 0 || !sort.StringsAreSorted(file.SourcePaths) {
			return nil, fmt.Errorf("contract view provenance file %q sourcePaths must be non-empty and sorted", file.Path)
		}
		for index, sourcePath := range file.SourcePaths {
			if index > 0 && sourcePath == file.SourcePaths[index-1] {
				return nil, fmt.Errorf("contract view provenance file %q has duplicate sourcePath %q", file.Path, sourcePath)
			}
			if _, ok := sourceDigests[sourcePath]; !ok {
				return nil, fmt.Errorf("contract view provenance file %q references unknown source %q", file.Path, sourcePath)
			}
		}

		absolute := filepath.Join(metadataDir, filepath.FromSlash(file.Path))
		info, err := os.Lstat(absolute)
		if err != nil {
			return nil, fmt.Errorf("contract view file %q is unavailable: %w", file.Path, err)
		}
		if !info.Mode().IsRegular() {
			return nil, fmt.Errorf("contract view file %q must be a byte snapshot, not a symlink or directory", file.Path)
		}
		payload, err := os.ReadFile(absolute)
		if err != nil {
			return nil, fmt.Errorf("read contract view file %q: %w", file.Path, err)
		}
		digest := sha256.Sum256(payload)
		if hex.EncodeToString(digest[:]) != file.SHA256 {
			return nil, fmt.Errorf("contract view file %q drifted from its byte snapshot", file.Path)
		}
		_, _ = viewDigest.Write([]byte(file.Path))
		_, _ = viewDigest.Write([]byte{0})
		_, _ = viewDigest.Write([]byte(file.SHA256))
		_, _ = viewDigest.Write([]byte{'\n'})
		filesByPath[file.Path] = file
	}
	if len(filesByPath) == 0 {
		return nil, fmt.Errorf("contract view provenance files are empty")
	}
	if hex.EncodeToString(viewDigest.Sum(nil)) != document.ViewDigest {
		return nil, fmt.Errorf("contract view provenance viewDigest does not match file inventory")
	}

	actual, err := contractViewFileInventory(metadataDir)
	if err != nil {
		return nil, err
	}
	expected := make([]string, 0, len(filesByPath))
	for path := range filesByPath {
		expected = append(expected, path)
	}
	sort.Strings(expected)
	if !equalStrings(actual, expected) {
		return nil, fmt.Errorf(
			"contract view file inventory differs from provenance: actual=%v expected=%v",
			actual,
			expected,
		)
	}

	return &contractViewProvenance{
		metadataDir:    filepath.Clean(metadataDir),
		repositoryRoot: repositoryRoot,
		filesByPath:    filesByPath,
	}, nil
}

func (provenance *contractViewProvenance) canonicalSourceFor(viewPath string) (string, error) {
	if provenance == nil {
		return "", fmt.Errorf("contract view provenance is unavailable")
	}
	relative := relativePath(provenance.metadataDir, viewPath)
	file, ok := provenance.filesByPath[relative]
	if !ok {
		return "", fmt.Errorf("contract view provenance has no entry for %q", relative)
	}
	if len(file.SourcePaths) != 1 {
		return "", fmt.Errorf(
			"contract view file %q has %d canonical sources; object-local ownership requires exactly one",
			relative,
			len(file.SourcePaths),
		)
	}
	return file.SourcePaths[0], nil
}

func repositoryRootForContractView(metadataDir string) (string, error) {
	absolute, err := filepath.Abs(metadataDir)
	if err != nil {
		return "", fmt.Errorf("resolve contract view root: %w", err)
	}
	current := filepath.Clean(absolute)
	for {
		if filepath.Base(current) == ".qwq_output" {
			root := filepath.Dir(current)
			if root == current {
				break
			}
			return root, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}
	return "", fmt.Errorf("contract view provenance is not below repository .qwq_output")
}

func validatePhysicalProvenanceSource(repositoryRoot, source string) error {
	resolvedRoot, err := filepath.EvalSymlinks(repositoryRoot)
	if err != nil {
		return fmt.Errorf("resolve repository root: %w", err)
	}
	resolvedSource, err := filepath.EvalSymlinks(source)
	if err != nil {
		return fmt.Errorf("resolve canonical source: %w", err)
	}
	relative, err := filepath.Rel(resolvedRoot, resolvedSource)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return fmt.Errorf("canonical source resolves outside repository root")
	}
	info, err := os.Lstat(source)
	if err != nil {
		return fmt.Errorf("inspect canonical source: %w", err)
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("canonical source must be a regular file, not a symlink or directory")
	}
	return nil
}

func contractViewFileInventory(metadataDir string) ([]string, error) {
	var result []string
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("contract view contains a live symlink: %s", path)
		}
		if entry.Name() == contractViewProvenanceFilename {
			return nil
		}
		result = append(result, relativePath(metadataDir, path))
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("inspect contract view inventory: %w", err)
	}
	sort.Strings(result)
	return result, nil
}

func validateRepositoryRelativePath(path string) error {
	if path == "" || strings.Contains(path, "\\") || filepath.IsAbs(path) {
		return fmt.Errorf("path must be repository-relative and use forward slashes")
	}
	normalized := filepath.ToSlash(filepath.Clean(filepath.FromSlash(path)))
	if normalized != path || normalized == "." || normalized == ".." || strings.HasPrefix(normalized, "../") {
		return fmt.Errorf("path is not canonical")
	}
	return nil
}

func canonicalSHA256(value string) bool {
	if len(value) != sha256.Size*2 || strings.ToLower(value) != value {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

func ensureJSONEOF(decoder *json.Decoder) error {
	var trailing any
	if err := decoder.Decode(&trailing); err == io.EOF {
		return nil
	} else if err != nil {
		return err
	}
	return fmt.Errorf("unexpected trailing JSON value")
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
