package load

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

func deriveReadinessEvidence(catalog *ast.Catalog, repoRoot string, errs *[]error) {
	collector, err := loadEvidenceCollector(repoRoot)
	if err != nil {
		*errs = append(*errs, err)
		return
	}
	collector.deriveReadinessEvidence(catalog, repoRoot, errs)
}

type evidenceManifestSource struct {
	Path      string `yaml:"path"`
	Root      string `yaml:"root"`
	Generator string `yaml:"generator"`
}

// evidenceCollector 复用 code-health 的生成来源登记；只有生成头与所有已登记
// manifest 输出摘要一致的文件才是派生产物。目录名、后缀和 source-only 登记不授予豁免。
// manifest 只作输入分类，不把其 graph 摘要反向写入 readinessEvidence。
type evidenceCollector map[string][]string

func loadEvidenceCollector(repoRoot string) (evidenceCollector, error) {
	result := evidenceCollector{}
	policy, err := optionalEvidenceBytes(filepath.Join(repoRoot, "quwoquan_ops/policies/code_health_policy.yaml"))
	if err != nil {
		return nil, err
	}
	var config struct {
		Classification struct {
			Manifests []evidenceManifestSource `yaml:"generated_manifests"`
		} `yaml:"classification"`
	}
	if err := yaml.Unmarshal(policy, &config); err != nil {
		return nil, err
	}
	for _, source := range config.Classification.Manifests {
		if err := result.readManifest(repoRoot, source); err != nil {
			return nil, err
		}
	}
	return result, nil
}

func (collector evidenceCollector) readManifest(repoRoot string, source evidenceManifestSource) error {
	if !safeEvidenceRelativePath(source.Path) || (source.Root != "" && !safeEvidenceRelativePath(source.Root)) {
		return nil
	}
	body, err := optionalEvidenceBytes(filepath.Join(repoRoot, source.Path))
	if err != nil {
		return err
	}
	var manifest struct {
		Generator string `json:"generator"`
		Outputs   []struct {
			Path   string `json:"path"`
			SHA256 string `json:"sha256"`
		} `json:"outputs"`
	}
	if json.Unmarshal(body, &manifest) != nil || source.Generator == "" || manifest.Generator != source.Generator {
		return nil
	}
	for _, output := range manifest.Outputs {
		if !safeEvidenceRelativePath(output.Path) {
			continue
		}
		path := filepath.ToSlash(filepath.Join(source.Root, output.Path))
		collector[path] = append(collector[path], strings.TrimPrefix(output.SHA256, "sha256:"))
	}
	return nil
}

// collectArtifacts 扫描匹配后缀的真实输入并绑定摘要；缺失目录表达为无证据。
func (collector evidenceCollector) collectArtifacts(
	repoRoot string,
	dir string,
	suffixes map[string]struct{},
	productionOnly bool,
) ([]ast.EvidenceArtifact, error) {
	info, err := os.Stat(dir)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	if !info.IsDir() {
		return nil, nil
	}
	var artifacts []ast.EvidenceArtifact
	walkErr := filepath.WalkDir(dir, func(current string, entry fs.DirEntry, walkErr error) error {
		if errors.Is(walkErr, fs.ErrNotExist) {
			return nil
		}
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			_, excluded := nonProductionSegments[entry.Name()]
			if productionOnly && excluded {
				return filepath.SkipDir
			}
			return nil
		}
		if _, ok := suffixes[strings.ToLower(filepath.Ext(entry.Name()))]; !ok {
			return nil
		}
		if productionOnly && isTestSourceName(entry.Name()) {
			return nil
		}
		artifact, err := collector.inputArtifact(repoRoot, current)
		if err != nil {
			return err
		}
		if artifact != nil {
			artifacts = append(artifacts, *artifact)
		}
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	sortEvidenceArtifacts(artifacts)
	return artifacts, nil
}

func (collector evidenceCollector) inputArtifact(repoRoot, current string) (*ast.EvidenceArtifact, error) {
	body, err := optionalEvidenceBytes(current)
	if err != nil || body == nil {
		return nil, err
	}
	sum := sha256.Sum256(body)
	digest := hex.EncodeToString(sum[:])
	path := relativePath(repoRoot, current)
	if collector.isGenerated(path, body, digest) {
		return nil, nil
	}
	return &ast.EvidenceArtifact{Path: path, SHA256: digest}, nil
}

func optionalEvidenceBytes(path string) ([]byte, error) {
	body, err := os.ReadFile(path)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	return body, err
}

func safeEvidenceRelativePath(path string) bool {
	if path == "" || filepath.IsAbs(path) {
		return false
	}
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if part == ".." {
			return false
		}
	}
	return true
}

func (collector evidenceCollector) isGenerated(path string, body []byte, digest string) bool {
	declarations := collector[path]
	if len(declarations) == 0 {
		return false
	}
	for _, declared := range declarations {
		if declared != digest {
			return false
		}
	}
	// 沿用 App emitter 的 generated + DO NOT EDIT header 约定，并限制在首行注释，
	// 避免测试字符串、普通代码注释提到生成器时被误判。
	header := strings.ToLower(strings.SplitN(string(body), "\n", 2)[0])
	return (strings.HasPrefix(header, "// ") || strings.HasPrefix(header, "# ")) &&
		strings.Contains(header, "generated") && strings.Contains(header, "do not edit")
}
