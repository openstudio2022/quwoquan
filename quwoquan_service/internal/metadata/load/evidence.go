package load

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	goast "go/ast"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

// readiness evidence 是派生结果，不是声明。它只从受版本控制的物理真相源反推：
// 云侧 `internal/<context>/<object>/<layer>/**`、云侧
// `tests/{local_contract,api_integration}/<context>/<object>/**`、端侧
// `lib/service/<service>/<context>/<object>/adapters/**`、
// `test/user_acceptance/service/<service>/<context>/<object>/**`、Ops
// `tests/acceptance/user_acceptance/<domain>/<context>/<object>/**` 以及
// `page_object_contract.yaml` 的 `object_ids`。metadata 作者不能写入任何 evidence
// 字段，`graph.Build` 只消费这里派生出的 packet。
//
// 层名与 kind 感知规则与 `quwoquan_ops/gate/object_path_map.py` 的 `CLOUD_LAYERS`、
// `REQUIRED_CLOUD_LAYERS_BY_KIND` 同源：层是 `quwoquan_service/AGENTS.md` 固定的
// `internal/<context>/<object>/<layer>` 组织轴，本文件不引入新层名。
//
// 红线：本文件派生的一律是**结构性证据**——「实现 seam 与验证入口的文件存在，且证据绑定
// 到这些文件的确切字节」。文件存在永远不等于用例通过；用例结果、四环境结果与 UAT 回执属
// **结果证据**，只能由 runner 在真实执行后附加（见 `contracts/metadata/DESIGN.md` 第 9
// 节）。因此这里的任何字段名、注释与输出都不得出现「已验证 / 已通过」语义，
// `testLayer*` 系列常量指的是测试入口目录，不是测试结论。
const (
	serviceTreeRoot = "quwoquan_service"
	appTreeRoot     = "quwoquan_app"
	opsTreeRoot     = "quwoquan_ops"
	appServiceRoot  = "service"
)

// 服务根的两个物理落点，与 object_path_map.py 的 SERVICE_ROOT_GLOBS 同源。
var serviceRootParents = []string{"services", "control-plane"}

// 云侧 DDD 层目录名。evidence 字段只映射到这四个真实层，不新增 layer 名。
const (
	cloudLayerDomain         = "domain"
	cloudLayerApplication    = "application"
	cloudLayerAdapters       = "adapters"
	cloudLayerInfrastructure = "infrastructure"
)

// 云侧对象测试层目录名，与 `quwoquan_service/AGENTS.md` 的
// `tests/<layer>/<context>/<object>/` 一致。
const (
	testLayerLocalContract  = "local_contract"
	testLayerAPIIntegration = "api_integration"
	testLayerUserAcceptance = "user_acceptance"
)

// 端侧对象化四层，与 object_path_map.py 的 canonical target shape 同源。
const (
	appLayerDomain       = "domain"
	appLayerApplication  = "application"
	appLayerAdapters     = "adapters"
	appLayerPresentation = "presentation"
)

var appLayers = []string{
	appLayerDomain,
	appLayerApplication,
	appLayerAdapters,
	appLayerPresentation,
}

// Ops runner 只证明可执行入口存在，不携带运行状态。目录不存在时保持空集；真实结果由
// readiness.ReadinessResultBundle 提供。
const (
	opsLayerEnvironmentAcceptance = "environment_acceptance"
	opsLayerRollback              = "rollback"
	opsLayerReplay                = "replay"
)

// 事务性事件发布 seam（下称 outbox 证据）是唯一没有专属层目录、也无法按文件位置归属的
// seam：实现常落在共享 store 或装配处。它的判定由归属（对象自己 `storage.yaml` 的
// `publication_role` 标注）与真实性（服务内对该存储的事务性写入）合成，见
// publication_evidence.go。这里不再按文件名或标识符里的 outbox 字样识别。

// 页面归属的唯一权威信号，与 object_path_map.py 的 PAGE_OBJECT_CONTRACT_PATH 同源。
var pageObjectContractPath = filepath.Join(
	serviceTreeRoot, "contracts", "metadata", "_shared", "page_object_contract.yaml",
)

// 拥有 `domain` 层的 kind，镜像 object_path_map.py 的
// REQUIRED_CLOUD_LAYERS_BY_KIND：projection 与 external_reference 不声明 domain 层，
// 它们的对象行为落在 application（projector / 出向 port 编排）。
var kindsWithDomainLayer = map[ast.ObjectKind]struct{}{
	ast.ObjectKindAggregateRoot:  {},
	ast.ObjectKindAppendOnlyFact: {},
	ast.ObjectKindProcessManager: {},
	ast.ObjectKindRuntimeSession: {},
}

var cloudSourceSuffixes = map[string]struct{}{".go": {}, ".py": {}}

var appSourceSuffixes = map[string]struct{}{".dart": {}}

var testSourceSuffixes = map[string]struct{}{".go": {}, ".py": {}, ".dart": {}}

// production 扫描要排除的路径段：测试替身与 fixture 不是实现证据（对齐
// `.cursor/rules/08-mock-data-isolation.mdc`）。
var nonProductionSegments = map[string]struct{}{
	"testsupport":   {},
	"test_fixtures": {},
}

// deriveReadinessEvidence 为每个 catalog 对象派生至多一个 evidence packet。
// packet 数与对象数一一对应，因此 `readiness.evidence.duplicate` 在派生模式下
// 结构上不可能发生；对象没有云侧实现根时不产生 packet，让
// `graph.deriveObjectReadiness` 如实记 `readiness.evidence`。
func deriveReadinessEvidence(catalog *ast.Catalog, repoRoot string, errs *[]error) {
	serviceRoots, err := resolveServiceRootsByDomain(repoRoot)
	if err != nil {
		*errs = append(*errs, err)
		return
	}
	pageClaims, err := resolvePageClaims(repoRoot, catalog.Objects, serviceRoots)
	if err != nil {
		*errs = append(*errs, err)
		return
	}
	operationIDs := map[string][]string{}
	for _, operation := range catalog.Operations {
		operationIDs[operation.ObjectID] = append(
			operationIDs[operation.ObjectID],
			operation.ID,
		)
	}
	for _, entrypoint := range catalog.RuntimeEntrypoints {
		operationIDs[entrypoint.ObjectID] = append(
			operationIDs[entrypoint.ObjectID],
			entrypoint.ID,
		)
	}
	// 发布写入索引按服务扫描一次即可复用：同一服务的所有对象共享同一份索引。
	writeIndexes := newServiceWriteIndexCache()
	// 反向缺口（有事务性写入但没有声明位）要回答「全仓有没有人声明这张表」，所以声明位
	// 必须先收齐再判定，不能边遍历边判。
	declaredAnywhere := map[string]struct{}{}
	objectPublications := map[string]storagePublication{}
	for _, object := range catalog.Objects {
		context, objectSegment, ok := objectPathSegments(object)
		if !ok {
			continue
		}
		serviceRoot, _, resolveErr := resolveObjectImplementationRoot(
			repoRoot,
			serviceRoots[object.Domain],
			object.Domain,
			context,
			objectSegment,
		)
		if resolveErr != nil || serviceRoot == "" {
			continue
		}
		publication, publicationErr := resolveStoragePublication(
			serviceRoot, context, objectSegment,
		)
		if publicationErr != nil {
			*errs = append(*errs, publicationErr)
			continue
		}
		objectPublications[object.ID] = publication
		for _, name := range publication.declared {
			declaredAnywhere[name] = struct{}{}
		}
	}
	for _, object := range catalog.Objects {
		context, objectSegment, ok := objectPathSegments(object)
		if !ok {
			continue
		}
		serviceRoot, objectRoot, resolveErr := resolveObjectImplementationRoot(
			repoRoot,
			serviceRoots[object.Domain],
			object.Domain,
			context,
			objectSegment,
		)
		if resolveErr != nil {
			*errs = append(*errs, resolveErr)
			continue
		}
		if objectRoot == "" {
			continue
		}
		writeIndex, indexErr := writeIndexes.forService(serviceRoot)
		if indexErr != nil {
			*errs = append(*errs, indexErr)
			continue
		}
		evidence, evidenceErr := deriveObjectEvidence(
			repoRoot,
			object,
			serviceRoot,
			objectRoot,
			context,
			objectSegment,
			operationIDs[object.ID],
			pageClaims[object.ID],
			writeIndex,
			objectPublications[object.ID],
			declaredAnywhere,
		)
		if evidenceErr != nil {
			*errs = append(*errs, evidenceErr)
			continue
		}
		catalog.ReadinessEvidence = append(catalog.ReadinessEvidence, evidence)
	}
}

func deriveObjectEvidence(
	repoRoot string,
	object ast.Object,
	serviceRoot string,
	objectRoot string,
	context string,
	objectSegment string,
	operationIDs []string,
	pages pageClaim,
	writeIndex *serviceWriteIndex,
	publication storagePublication,
	declaredAnywhere map[string]struct{},
) (ast.ObjectReadinessEvidence, error) {
	production, err := collectCloudProduction(repoRoot, objectRoot)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	publicationEvidence, err := collectPublicationEvidence(repoRoot, publication, writeIndex)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	behaviorLayer := cloudLayerApplication
	if _, ok := kindsWithDomainLayer[object.Kind]; ok {
		behaviorLayer = cloudLayerDomain
	}
	appProduction, err := collectAppProduction(
		repoRoot, appServiceSegment(serviceRoot), context, objectSegment,
	)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	evidence := ast.ObjectReadinessEvidence{
		ObjectID:     object.ID,
		OperationIDs: sortedCopy(operationIDs),
		Service: ast.ServiceStructureEvidence{
			Domain:    production.layers[behaviorLayer],
			Store:     production.layers[cloudLayerInfrastructure],
			Outbox:    publicationEvidence.artifacts,
			Reader:    production.layers[cloudLayerApplication],
			Transport: production.layers[cloudLayerAdapters],
		},
		App: ast.AppStructureEvidence{
			Domain:          appProduction[appLayerDomain],
			Application:     appProduction[appLayerApplication],
			Adapters:        appProduction[appLayerAdapters],
			Presentation:    pages.artifacts,
			PageParticipant: pages.participant,
			PageOwned:       pages.owned,
		},
		PublicationDelivery:           publicationEvidence.delivery,
		PublicationStores:             publication.seams,
		DeliveryStores:                publication.outboxes,
		UnannotatedStores:             publication.unannotated,
		UnresolvedPublicationWrites:   publicationEvidence.unresolved,
		UnresolvedPublicationDelivery: publicationEvidence.unresolvedDelivery,
		UndeclaredStorageWrites: undeclaredTransactionalWrites(
			objectRoot, writeIndex, declaredAnywhere,
		),
		PythonImplementation: writeIndexHasPythonImplementation(writeIndex, objectRoot),
		SourcePath:           relativePath(repoRoot, objectRoot),
	}
	evidence.Service.LocalContract, err = collectArtifacts(
		repoRoot,
		filepath.Join(serviceRoot, "tests", testLayerLocalContract, context, objectSegment),
		testSourceSuffixes,
		false,
	)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	evidence.Service.APIIntegration, err = collectArtifacts(
		repoRoot,
		filepath.Join(serviceRoot, "tests", testLayerAPIIntegration, context, objectSegment),
		testSourceSuffixes,
		false,
	)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	evidence.App.LocalContract, err = collectArtifacts(
		repoRoot,
		filepath.Join(
			repoRoot, appTreeRoot, "test", testLayerLocalContract,
			appServiceRoot, appServiceSegment(serviceRoot), context, objectSegment,
		),
		testSourceSuffixes,
		false,
	)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	evidence.App.APIIntegration, err = collectArtifacts(
		repoRoot,
		filepath.Join(
			repoRoot, appTreeRoot, "test", testLayerAPIIntegration,
			appServiceRoot, appServiceSegment(serviceRoot), context, objectSegment,
		),
		testSourceSuffixes,
		false,
	)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	evidence.App.UserAcceptance, err = collectArtifacts(
		repoRoot,
		filepath.Join(
			repoRoot, appTreeRoot, "test", testLayerUserAcceptance,
			appServiceRoot, appServiceSegment(serviceRoot), context, objectSegment,
		),
		testSourceSuffixes,
		false,
	)
	if err != nil {
		return ast.ObjectReadinessEvidence{}, err
	}
	for _, target := range []struct {
		layer string
		set   *[]ast.EvidenceArtifact
	}{
		{layer: opsLayerEnvironmentAcceptance, set: &evidence.Ops.EnvironmentAcceptance},
		{layer: opsLayerRollback, set: &evidence.Ops.RollbackRunner},
		{layer: opsLayerReplay, set: &evidence.Ops.ReplayRunner},
	} {
		*target.set, err = collectArtifacts(
			repoRoot,
			filepath.Join(
				repoRoot, opsTreeRoot, "tests", "acceptance", target.layer,
				object.Domain, context, objectSegment,
			),
			testSourceSuffixes,
			false,
		)
		if err != nil {
			return ast.ObjectReadinessEvidence{}, err
		}
	}
	normalizeEvidence(&evidence)
	return evidence, nil
}

// cloudProduction 是对象云侧 production 文件按层的一次性分桶结果。
type cloudProduction struct {
	layers map[string][]ast.EvidenceArtifact
}

func collectCloudProduction(repoRoot, objectRoot string) (cloudProduction, error) {
	result := cloudProduction{layers: map[string][]ast.EvidenceArtifact{}}
	entries, err := os.ReadDir(objectRoot)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return result, nil
		}
		return cloudProduction{}, err
	}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		switch entry.Name() {
		case cloudLayerDomain,
			cloudLayerApplication,
			cloudLayerAdapters,
			cloudLayerInfrastructure:
		default:
			continue
		}
		artifacts, collectErr := collectArtifacts(
			repoRoot,
			filepath.Join(objectRoot, entry.Name()),
			cloudSourceSuffixes,
			true,
		)
		if collectErr != nil {
			return cloudProduction{}, collectErr
		}
		result.layers[entry.Name()] = artifacts
	}
	return result, nil
}

// collectAppProduction scans only the canonical object-shaped App root. Legacy
// paths are intentionally not inferred here: migration aliases would turn the
// evidence loader into a second ownership registry. Presentation is populated
// from page_object_contract physical ownership instead of this directory scan.
func collectAppProduction(
	repoRoot string,
	service string,
	context string,
	objectSegment string,
) (map[string][]ast.EvidenceArtifact, error) {
	result := map[string][]ast.EvidenceArtifact{}
	objectRoot := filepath.Join(
		repoRoot, appTreeRoot, "lib", appServiceRoot, service, context, objectSegment,
	)
	for _, layer := range appLayers {
		if layer == appLayerPresentation {
			// A file merely living under presentation does not prove that this
			// object physically owns a page. Page ownership is derived below from
			// the canonical page source path.
			result[layer] = []ast.EvidenceArtifact{}
			continue
		}
		artifacts, err := collectArtifacts(
			repoRoot,
			filepath.Join(objectRoot, layer),
			appSourceSuffixes,
			true,
		)
		if err != nil {
			return nil, err
		}
		result[layer] = artifacts
	}
	return result, nil
}

// collectArtifacts 扫描 dir 下所有匹配后缀的文件并绑定内容摘要。目录缺失不是错误：
// 端侧对象化搬迁进行中，缺失必须表达为「无证据」，由 readiness missing 如实暴露，
// 不能中断 Load。
func collectArtifacts(
	repoRoot string,
	dir string,
	suffixes map[string]struct{},
	productionOnly bool,
) ([]ast.EvidenceArtifact, error) {
	info, err := os.Stat(dir)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil, nil
		}
		return nil, err
	}
	if !info.IsDir() {
		return nil, nil
	}
	var artifacts []ast.EvidenceArtifact
	walkErr := filepath.WalkDir(dir, func(
		current string,
		entry fs.DirEntry,
		walkErr error,
	) error {
		if walkErr != nil {
			if errors.Is(walkErr, fs.ErrNotExist) {
				return nil
			}
			return walkErr
		}
		if entry.IsDir() {
			if productionOnly {
				if _, excluded := nonProductionSegments[entry.Name()]; excluded {
					return filepath.SkipDir
				}
			}
			return nil
		}
		if _, ok := suffixes[strings.ToLower(filepath.Ext(entry.Name()))]; !ok {
			return nil
		}
		if productionOnly && isTestSourceName(entry.Name()) {
			return nil
		}
		digest, digestErr := fileDigest(current)
		if digestErr != nil {
			if errors.Is(digestErr, fs.ErrNotExist) {
				return nil
			}
			return digestErr
		}
		artifacts = append(artifacts, ast.EvidenceArtifact{
			Path:   relativePath(repoRoot, current),
			SHA256: digest,
		})
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	sortEvidenceArtifacts(artifacts)
	return artifacts, nil
}

// collectTransactionHandles 收集签名里声明为事务类型的形参名。类型是语法事实，不需要类型
// 检查：`tx pgx.Tx`、`tx *sql.Tx`、`sessionContext mongo.SessionContext` 都能直接读出。
func collectTransactionHandles(
	signature *goast.FuncType,
	handles map[string]struct{},
) {
	if signature == nil || signature.Params == nil {
		return
	}
	for _, field := range signature.Params.List {
		if !typeExpressionIsTransaction(field.Type) {
			continue
		}
		for _, name := range field.Names {
			handles[name.Name] = struct{}{}
		}
	}
}

func typeExpressionIsTransaction(expression goast.Expr) bool {
	switch typed := expression.(type) {
	case *goast.StarExpr:
		return typeExpressionIsTransaction(typed.X)
	case *goast.SelectorExpr:
		return transactionTypeNames[typed.Sel.Name]
	case *goast.Ident:
		return transactionTypeNames[typed.Name]
	}
	return false
}

// collectTransactionAssignments 收集 `tx, err := pool.BeginTx(...)` 这类由事务开启调用绑定
// 的变量名。
func collectTransactionAssignments(
	statement *goast.AssignStmt,
	handles map[string]struct{},
) {
	opensTransaction := false
	for _, value := range statement.Rhs {
		call, ok := value.(*goast.CallExpr)
		if !ok {
			continue
		}
		if callTargetName(call) != "" && transactionOpenerNames[callTargetName(call)] {
			opensTransaction = true
		}
	}
	if !opensTransaction {
		return
	}
	for _, target := range statement.Lhs {
		if identifier, ok := target.(*goast.Ident); ok && identifier.Name != "_" {
			handles[identifier.Name] = struct{}{}
		}
	}
}

// functionUsesTransactionHandle 要求 journal 写入所在的函数真的把事务句柄用了出去：句柄既
// 可能是调用的接收者（`tx.Exec(...)`），也可能作为实参传给下一层（`appendEvent(ctx, tx, ...)`、
// mongo 的 `collection.InsertOne(sessionContext, ...)`）。
func functionUsesTransactionHandle(
	body *goast.BlockStmt,
	handles map[string]struct{},
) bool {
	if len(handles) == 0 {
		return false
	}
	used := false
	goast.Inspect(body, func(node goast.Node) bool {
		if used {
			return false
		}
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		if selector, isSelector := call.Fun.(*goast.SelectorExpr); isSelector {
			if receiver, isIdent := selector.X.(*goast.Ident); isIdent {
				if _, isHandle := handles[receiver.Name]; isHandle {
					used = true
					return false
				}
			}
		}
		for _, argument := range call.Args {
			identifier, isIdent := argument.(*goast.Ident)
			if !isIdent {
				continue
			}
			if _, isHandle := handles[identifier.Name]; isHandle {
				used = true
				return false
			}
		}
		return true
	})
	return used
}

func callTargetName(call *goast.CallExpr) string {
	switch typed := call.Fun.(type) {
	case *goast.SelectorExpr:
		return typed.Sel.Name
	case *goast.Ident:
		return typed.Name
	}
	return ""
}

// 事务句柄类型与事务开启调用：语法层面可直接读出的事务边界信号。
var (
	transactionTypeNames = map[string]bool{
		"Tx":             true,
		"Txn":            true,
		"Transaction":    true,
		"SessionContext": true,
	}
	transactionOpenerNames = map[string]bool{
		"Begin":             true,
		"BeginTx":           true,
		"BeginTransaction":  true,
		"StartTransaction":  true,
		"WithTransaction":   true,
		"StartSession":      true,
		"BeginTxWithOption": true,
	}
)

// splitPythonCodeAndStrings 把 Python 源码切成「去掉注释与字符串的代码文本」与「字符串
// 字面量列表」两部分，让标识符判定与字面量判定各用各的依据。
func splitPythonCodeAndStrings(source string) (string, []string) {
	var builder strings.Builder
	var literals []string
	var literal strings.Builder
	var stringDelimiter string
	for index := 0; index < len(source); {
		if stringDelimiter != "" {
			if source[index] == '\\' && len(stringDelimiter) == 1 {
				index += 2
				continue
			}
			if strings.HasPrefix(source[index:], stringDelimiter) {
				index += len(stringDelimiter)
				stringDelimiter = ""
				literals = append(literals, literal.String())
				literal.Reset()
				continue
			}
			literal.WriteByte(source[index])
			if source[index] == '\n' {
				builder.WriteByte('\n')
			}
			index++
			continue
		}
		switch {
		case strings.HasPrefix(source[index:], `"""`),
			strings.HasPrefix(source[index:], "'''"):
			stringDelimiter = source[index : index+3]
			index += 3
		case source[index] == '"', source[index] == '\'':
			stringDelimiter = source[index : index+1]
			index++
		case source[index] == '#':
			for index < len(source) && source[index] != '\n' {
				index++
			}
		default:
			builder.WriteByte(source[index])
			index++
		}
	}
	if literal.Len() > 0 {
		literals = append(literals, literal.String())
	}
	return builder.String(), literals
}

func isTestSourceName(name string) bool {
	return strings.HasSuffix(name, "_test.go") || strings.HasPrefix(name, "test_")
}

func fileDigest(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}

// resolveServiceRootsByDomain 从每个服务自己的 `contracts/domain.yaml` 派生
// domain → 服务根。一个 domain 可以由多个服务根承载（`ops` 同时属于
// product-ops-service 与 control-plane/platform-ops），因此返回切片。
func resolveServiceRootsByDomain(repoRoot string) (map[string][]string, error) {
	result := map[string][]string{}
	for _, parent := range serviceRootParents {
		parentDir := filepath.Join(repoRoot, serviceTreeRoot, parent)
		entries, err := os.ReadDir(parentDir)
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) {
				continue
			}
			return nil, err
		}
		for _, entry := range entries {
			if !entry.IsDir() {
				continue
			}
			serviceRoot := filepath.Join(parentDir, entry.Name())
			domainPath := filepath.Join(serviceRoot, "contracts", "domain.yaml")
			data, readErr := os.ReadFile(domainPath)
			if readErr != nil {
				if errors.Is(readErr, fs.ErrNotExist) {
					continue
				}
				return nil, readErr
			}
			var document struct {
				Domain string `yaml:"domain"`
			}
			if err := yaml.Unmarshal(data, &document); err != nil {
				return nil, fmt.Errorf("%s: %w", domainPath, err)
			}
			if domain := strings.TrimSpace(document.Domain); domain != "" {
				result[domain] = append(result[domain], serviceRoot)
			}
		}
	}
	for domain := range result {
		sort.Strings(result[domain])
	}
	return result, nil
}

// resolveObjectImplementationRoot 反推对象的云侧实现根。canonical 形态是
// `internal/<context>/<object>`；`internal/<domain>/<context>/<object>` 只是
// control-plane/platform-ops 的历史多余前缀，仅在 canonical 缺失时回退，与
// object_path_map.py 的处理一致。
func resolveObjectImplementationRoot(
	repoRoot string,
	serviceRoots []string,
	domain string,
	context string,
	objectSegment string,
) (string, string, error) {
	var owners []string
	var canonicalService, canonicalRoot string
	for _, serviceRoot := range serviceRoots {
		candidate := filepath.Join(serviceRoot, "internal", context, objectSegment)
		if isDir(candidate) {
			owners = append(owners, relativePath(repoRoot, candidate))
			if canonicalRoot == "" {
				canonicalService, canonicalRoot = serviceRoot, candidate
			}
		}
	}
	if len(owners) > 1 {
		return "", "", fmt.Errorf(
			"%s.%s: object implementation root must have a single owner, found %s",
			domain,
			objectSegment,
			strings.Join(owners, ", "),
		)
	}
	if canonicalRoot != "" {
		return canonicalService, canonicalRoot, nil
	}
	for _, serviceRoot := range serviceRoots {
		candidate := filepath.Join(
			serviceRoot, "internal", domain, context, objectSegment,
		)
		if isDir(candidate) {
			return serviceRoot, candidate, nil
		}
	}
	return "", "", nil
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func appServiceSegment(serviceRoot string) string {
	return strings.ReplaceAll(filepath.Base(serviceRoot), "-", "_")
}

func resolveAppServiceForContext(
	serviceRootsByDomain map[string][]string,
	domain string,
	context string,
) (string, error) {
	var owners []string
	for _, serviceRoot := range serviceRootsByDomain[domain] {
		if isDir(filepath.Join(serviceRoot, "contracts", context)) {
			owners = append(owners, serviceRoot)
		}
	}
	if len(owners) != 1 {
		relativeOwners := make([]string, 0, len(owners))
		for _, owner := range owners {
			relativeOwners = append(relativeOwners, filepath.ToSlash(owner))
		}
		sort.Strings(relativeOwners)
		return "", fmt.Errorf(
			"%s.%s: context must have exactly one service owner, found %d (%s)",
			domain,
			context,
			len(owners),
			strings.Join(relativeOwners, ", "),
		)
	}
	return appServiceSegment(owners[0]), nil
}

// objectPathSegments 从 `<domain>/<context>/<object>/object.yaml` 反推 context 与
// object 目录名；它们与云侧 `internal/<context>/<object>` 同名。
func objectPathSegments(object ast.Object) (string, string, bool) {
	segments := strings.Split(object.SourcePath, "/")
	if len(segments) != 4 {
		return "", "", false
	}
	return segments[1], segments[2], true
}

// pageObjectContractDocument 只读页面 → object_ids 的权威声明。
type pageObjectContractDocument struct {
	SourcePathRoot string `yaml:"source_path_root"`
	Pages          []struct {
		SourcePath string   `yaml:"source_path"`
		ObjectIDs  []string `yaml:"object_ids"`
	} `yaml:"pages"`
}

// pageClaim separates participation from physical ownership. object_ids makes
// an object a participant; only a canonical
// lib/service/<service>/<context>/<object>/presentation source path makes it the owner.
// A multi-object page therefore requires one presentation root, not one per
// participant.
type pageClaim struct {
	participant bool
	owned       bool
	artifacts   []ast.EvidenceArtifact
}

// resolvePageClaims derives participant identity from object_ids and physical
// owner identity from canonical source_path. Missing page bytes preserve the
// ownership requirement while leaving presentation evidence empty.
func resolvePageClaims(
	repoRoot string,
	objects []ast.Object,
	serviceRootsByDomain map[string][]string,
) (map[string]pageClaim, error) {
	contractPath := filepath.Join(repoRoot, pageObjectContractPath)
	data, err := os.ReadFile(contractPath)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return map[string]pageClaim{}, nil
		}
		return nil, err
	}
	var document pageObjectContractDocument
	if err := yaml.Unmarshal(data, &document); err != nil {
		return nil, fmt.Errorf("%s: %w", contractPath, err)
	}
	sourceRoot := strings.TrimSpace(document.SourcePathRoot)
	if sourceRoot == "" {
		sourceRoot = appTreeRoot
	}
	ownersByPrefix := map[string]string{}
	for _, object := range objects {
		context, objectSegment, ok := objectPathSegments(object)
		if !ok {
			continue
		}
		service, serviceErr := resolveAppServiceForContext(
			serviceRootsByDomain, object.Domain, context,
		)
		if serviceErr != nil {
			return nil, serviceErr
		}
		prefix := filepath.ToSlash(filepath.Join(
			"lib", appServiceRoot, service, context, objectSegment, appLayerPresentation,
		)) + "/"
		ownersByPrefix[prefix] = object.ID
	}
	result := map[string]pageClaim{}
	for _, page := range document.Pages {
		sourcePath := strings.TrimSpace(page.SourcePath)
		if sourcePath == "" {
			continue
		}
		absolute := filepath.Join(repoRoot, sourceRoot, sourcePath)
		var artifact *ast.EvidenceArtifact
		digest, digestErr := fileDigest(absolute)
		switch {
		case digestErr == nil:
			artifact = &ast.EvidenceArtifact{
				Path:   relativePath(repoRoot, absolute),
				SHA256: digest,
			}
		case errors.Is(digestErr, fs.ErrNotExist):
			// 认领仍然成立，只是页面文件不在磁盘上。
		default:
			return nil, digestErr
		}
		for _, objectID := range page.ObjectIDs {
			objectID = strings.TrimSpace(objectID)
			if objectID == "" {
				continue
			}
			claim := result[objectID]
			claim.participant = true
			result[objectID] = claim
		}
		normalizedSourcePath := filepath.ToSlash(sourcePath)
		for prefix, ownerID := range ownersByPrefix {
			if !strings.HasPrefix(normalizedSourcePath, prefix) {
				continue
			}
			claim := result[ownerID]
			claim.owned = true
			if artifact != nil {
				claim.artifacts = append(claim.artifacts, *artifact)
			}
			result[ownerID] = claim
			break
		}
	}
	for objectID := range result {
		sortEvidenceArtifacts(result[objectID].artifacts)
	}
	return result, nil
}

// normalizeEvidence 排序每类证据，并把「无证据」统一表达成空列表。JSON 里 `null` 会被
// ContractGraph schema 拒收（`{"type": "array"}`），而无证据是派生期的正常结果，必须能
// 完整落进图里由 objectReadiness.missing 如实暴露。
func normalizeEvidence(evidence *ast.ObjectReadinessEvidence) {
	for _, artifacts := range []*[]ast.EvidenceArtifact{
		&evidence.Service.Domain,
		&evidence.Service.Store,
		&evidence.Service.Reader,
		&evidence.Service.Transport,
		&evidence.Service.LocalContract,
		&evidence.Service.APIIntegration,
		&evidence.App.Domain,
		&evidence.App.Application,
		&evidence.App.Adapters,
		&evidence.App.Presentation,
		&evidence.App.LocalContract,
		&evidence.App.APIIntegration,
		&evidence.App.UserAcceptance,
		&evidence.Ops.EnvironmentAcceptance,
		&evidence.Ops.RollbackRunner,
		&evidence.Ops.ReplayRunner,
	} {
		if *artifacts == nil {
			*artifacts = []ast.EvidenceArtifact{}
			continue
		}
		sortEvidenceArtifacts(*artifacts)
	}
	if evidence.OperationIDs == nil {
		evidence.OperationIDs = []string{}
	}
	if evidence.Service.Outbox == nil {
		evidence.Service.Outbox = []ast.StorageEvidence{}
	} else {
		sortStorageArtifacts(evidence.Service.Outbox)
	}
	if evidence.PublicationDelivery == nil {
		evidence.PublicationDelivery = []ast.StorageEvidence{}
	} else {
		sortStorageArtifacts(evidence.PublicationDelivery)
	}
}

func sortEvidenceArtifacts(values []ast.EvidenceArtifact) {
	sort.Slice(values, func(i, j int) bool { return values[i].Path < values[j].Path })
}

func sortedCopy(values []string) []string {
	result := append([]string{}, values...)
	sort.Strings(result)
	return result
}
