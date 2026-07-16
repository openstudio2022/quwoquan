package openapi

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type DriftKind string

const (
	DriftMissing DriftKind = "missing"
	DriftStale   DriftKind = "stale"
	DriftOrphan  DriftKind = "orphan"
)

// Drift 表示磁盘 OpenAPI artifact 与 ContractGraph 期望快照之间的差异。
type Drift struct {
	Kind         DriftKind
	RelativePath string
}

// CompareDirectory 直接读取磁盘 artifact，与生成期望逐字节比较并发现孤儿文件。
func CompareDirectory(metadataDir string, snapshots []Snapshot) ([]Drift, error) {
	expected, err := indexSnapshots(snapshots)
	if err != nil {
		return nil, err
	}
	var drifts []Drift
	for relativePath, snapshot := range expected {
		target, err := snapshotPath(metadataDir, relativePath)
		if err != nil {
			return nil, err
		}
		actual, err := os.ReadFile(target)
		if errors.Is(err, os.ErrNotExist) {
			drifts = append(drifts, Drift{
				Kind:         DriftMissing,
				RelativePath: relativePath,
			})
			continue
		}
		if err != nil {
			return nil, fmt.Errorf("read OpenAPI snapshot %s: %w", target, err)
		}
		if !bytes.Equal(actual, snapshot.Content) {
			drifts = append(drifts, Drift{
				Kind:         DriftStale,
				RelativePath: relativePath,
			})
		}
	}

	actualPaths, err := discoverSnapshotPaths(metadataDir)
	if err != nil {
		return nil, err
	}
	for _, relativePath := range actualPaths {
		if _, exists := expected[relativePath]; exists {
			continue
		}
		drifts = append(drifts, Drift{
			Kind:         DriftOrphan,
			RelativePath: relativePath,
		})
	}
	sortDrifts(drifts)
	return drifts, nil
}

// WriteDirectory 先在目标目录内完成全部临时文件写入，再逐文件原子 rename。
// 不读取或合并旧快照内容；写完后删除 ContractGraph 中已不存在的孤儿快照。
func WriteDirectory(metadataDir string, snapshots []Snapshot) error {
	expected, err := indexSnapshots(snapshots)
	if err != nil {
		return err
	}
	relativePaths := make([]string, 0, len(expected))
	for relativePath := range expected {
		relativePaths = append(relativePaths, relativePath)
	}
	sort.Strings(relativePaths)

	staged := make([]stagedSnapshot, 0, len(relativePaths))
	cleanup := func() {
		for _, current := range staged {
			if current.temporaryPath != "" {
				_ = os.Remove(current.temporaryPath)
			}
		}
	}
	for _, relativePath := range relativePaths {
		target, err := snapshotPath(metadataDir, relativePath)
		if err != nil {
			cleanup()
			return err
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			cleanup()
			return fmt.Errorf("create OpenAPI snapshot directory: %w", err)
		}
		temporary, err := os.CreateTemp(
			filepath.Dir(target),
			".openapi.yaml.tmp-*",
		)
		if err != nil {
			cleanup()
			return fmt.Errorf("stage OpenAPI snapshot %s: %w", target, err)
		}
		current := stagedSnapshot{
			targetPath:    target,
			temporaryPath: temporary.Name(),
		}
		staged = append(staged, current)
		if err := temporary.Chmod(0o644); err != nil {
			_ = temporary.Close()
			cleanup()
			return fmt.Errorf("chmod staged OpenAPI snapshot %s: %w", target, err)
		}
		if _, err := temporary.Write(expected[relativePath].Content); err != nil {
			_ = temporary.Close()
			cleanup()
			return fmt.Errorf("write staged OpenAPI snapshot %s: %w", target, err)
		}
		if err := temporary.Sync(); err != nil {
			_ = temporary.Close()
			cleanup()
			return fmt.Errorf("sync staged OpenAPI snapshot %s: %w", target, err)
		}
		if err := temporary.Close(); err != nil {
			cleanup()
			return fmt.Errorf("close staged OpenAPI snapshot %s: %w", target, err)
		}
	}

	for index := range staged {
		current := &staged[index]
		if err := os.Rename(current.temporaryPath, current.targetPath); err != nil {
			cleanup()
			return fmt.Errorf(
				"atomically replace OpenAPI snapshot %s: %w",
				current.targetPath,
				err,
			)
		}
		current.temporaryPath = ""
	}

	actualPaths, err := discoverSnapshotPaths(metadataDir)
	if err != nil {
		return err
	}
	for _, relativePath := range actualPaths {
		if _, exists := expected[relativePath]; exists {
			continue
		}
		target, err := snapshotPath(metadataDir, relativePath)
		if err != nil {
			return err
		}
		if err := os.Remove(target); err != nil {
			return fmt.Errorf("remove orphan OpenAPI snapshot %s: %w", target, err)
		}
	}
	return nil
}

// FormatDrifts 生成稳定、可直接用于 CLI/Gate 的漂移报告。
func FormatDrifts(drifts []Drift) string {
	if len(drifts) == 0 {
		return ""
	}
	sorted := append([]Drift(nil), drifts...)
	sortDrifts(sorted)
	var message strings.Builder
	message.WriteString("OpenAPI snapshots differ from ContractGraph:")
	for _, drift := range sorted {
		fmt.Fprintf(
			&message,
			"\n- %s: %s",
			drift.Kind,
			drift.RelativePath,
		)
	}
	return message.String()
}

type stagedSnapshot struct {
	targetPath    string
	temporaryPath string
}

func indexSnapshots(snapshots []Snapshot) (map[string]Snapshot, error) {
	result := make(map[string]Snapshot, len(snapshots))
	for _, snapshot := range snapshots {
		relativePath := filepath.ToSlash(filepath.Clean(snapshot.RelativePath))
		if relativePath == "." || relativePath == "" {
			return nil, fmt.Errorf("OpenAPI snapshot has no relative path")
		}
		if previous, exists := result[relativePath]; exists {
			return nil, fmt.Errorf(
				"duplicate OpenAPI snapshot path %s for %s and %s",
				relativePath,
				previous.Domain,
				snapshot.Domain,
			)
		}
		snapshot.RelativePath = relativePath
		result[relativePath] = snapshot
	}
	return result, nil
}

func discoverSnapshotPaths(metadataDir string) ([]string, error) {
	entries, err := os.ReadDir(metadataDir)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read metadata directory %s: %w", metadataDir, err)
	}
	var result []string
	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}
		relativePath := filepath.ToSlash(
			filepath.Join(entry.Name(), "openapi.yaml"),
		)
		target, err := snapshotPath(metadataDir, relativePath)
		if err != nil {
			return nil, err
		}
		if _, err := os.Stat(target); err == nil {
			result = append(result, relativePath)
		} else if !errors.Is(err, os.ErrNotExist) {
			return nil, fmt.Errorf("stat OpenAPI snapshot %s: %w", target, err)
		}
	}
	sort.Strings(result)
	return result, nil
}

func snapshotPath(metadataDir string, relativePath string) (string, error) {
	root, err := filepath.Abs(filepath.Clean(metadataDir))
	if err != nil {
		return "", fmt.Errorf("resolve metadata directory: %w", err)
	}
	target, err := filepath.Abs(
		filepath.Join(root, filepath.FromSlash(relativePath)),
	)
	if err != nil {
		return "", fmt.Errorf("resolve OpenAPI snapshot path: %w", err)
	}
	relative, err := filepath.Rel(root, target)
	if err != nil {
		return "", fmt.Errorf("relativize OpenAPI snapshot path: %w", err)
	}
	if relative == ".." ||
		strings.HasPrefix(relative, ".."+string(filepath.Separator)) ||
		filepath.IsAbs(relative) {
		return "", fmt.Errorf(
			"OpenAPI snapshot path %q escapes metadata directory",
			relativePath,
		)
	}
	return target, nil
}

func sortDrifts(drifts []Drift) {
	sort.Slice(drifts, func(left, right int) bool {
		if drifts[left].RelativePath != drifts[right].RelativePath {
			return drifts[left].RelativePath < drifts[right].RelativePath
		}
		return drifts[left].Kind < drifts[right].Kind
	})
}
