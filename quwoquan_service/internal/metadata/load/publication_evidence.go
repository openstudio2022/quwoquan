package load

import (
	goast "go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

// 事务性事件发布 seam 的证据由两个互相独立的事实合成，缺一不可：
//
//  1. **归属**：对象在自己的 `storage.yaml` 里把某张存储标注成 `transactional_outbox` 或
//     `transactional_event_log`（判别位见 ast.ClassifyStoragePublicationRole）。
//  2. **真实性**：拥有服务的生产代码里，这张存储被绑定到某个存储实现包，且该包内存在一次
//     通过事务句柄执行的写入。
//
// 为什么必须合成而不能各用一半：
//
//   - 只看代码：证据的主语会变成**文件位置**而不是归属。`content.profile_interaction_activity_view`
//     是 projection，它的 `application/projectors.go` 只是 durable outbox 的**消费侧**
//     （它自己的 port 注释写着 "used only by durable outbox consumers"），按文件位置扫会把
//     「接触」当成「拥有」；`content.content_account_closure_workflow` 的账号关闭清理代码会
//     写 8 张兄弟对象的发件箱，按文件位置扫会让它凭别人的表拿到证据。
//   - 只看声明：声明不证明表存在、更不证明有人往里发布。「建了表、有了句柄、没人发布」正是
//     这条口径要拦的假实现形态。
//
// 粒度声明（不要退回临近性）：seam 判定落在**包**级，不在语句级。集合句柄常由构造参数注入
// （`NewMongoAggregateCommandStore(db, receipts, outbox)` 在 cmd 装配处传入集合名），写入通过
// 结构体字段发生，与字面量相隔数百行甚至跨文件，用插入语句临近性推断写入语义实测 90 张误判
// 53 张。包级 join 的代价是同一存储实现包内不区分具体哪张句柄被事务写入；这被归属侧的标注
// 限制在「对象自己声明为发布型的存储」上，所以不会把任意 collection 当成发件箱。

// storagePublication 是单个对象的存储归属声明派生结果。
type storagePublication struct {
	// seams 是被标注为发布 seam 的存储（发件箱与事务性事件表）。
	seams []string
	// outboxes 只含 `transactional_outbox`：它们要有投递实现，事务性事件表按定义没有
	// 具名消费者，不要求投递。
	outboxes []string
	// declared 是该对象声明过的全部存储名，用于反向识别「有事务写入但没有声明位」。
	declared    []string
	unannotated []string
}

// resolveStoragePublication 读取对象 `storage.yaml` 的每张存储声明与其 `publication_role`。
// 只解析 collections / tables / streams 三种存储块；其它键与本判定无关。
func resolveStoragePublication(
	serviceRoot string,
	context string,
	objectSegment string,
) (storagePublication, error) {
	path := filepath.Join(serviceRoot, "contracts", context, objectSegment, "storage.yaml")
	document, err := loadOptionalStorageDocument(path)
	if err != nil {
		return storagePublication{}, err
	}
	if document == nil {
		return storagePublication{}, nil
	}
	result := storagePublication{}
	for name, entry := range document.Collections {
		result.add(name, entry.PublicationRole)
	}
	for name, entry := range document.Tables {
		result.add(name, entry.PublicationRole)
	}
	for name, entry := range document.Streams {
		result.add(name, entry.PublicationRole)
	}
	sort.Strings(result.seams)
	sort.Strings(result.outboxes)
	sort.Strings(result.declared)
	sort.Strings(result.unannotated)
	return result, nil
}

func (result *storagePublication) add(name string, publicationRole string) {
	result.declared = append(result.declared, name)
	switch ast.ClassifyStoragePublicationRole(publicationRole) {
	case ast.StoragePublicationUnannotated:
		result.unannotated = append(result.unannotated, name)
	case ast.StoragePublicationTransactionalOutbox:
		result.seams = append(result.seams, name)
		result.outboxes = append(result.outboxes, name)
	case ast.StoragePublicationTransactionalEventLog:
		result.seams = append(result.seams, name)
	}
}

// publicationEvidence 是单个对象的发布 seam 派生结果。三个方向必须分开表达，因为它们的
// 修法完全不同：
//
//   - artifacts：存储名 → 事务性写入位置，成立的证据。
//   - delivery：存储名 → 投递实现位置（读取存储并推进进度）。
//   - unresolved：关系名在服务里被绑定过，但写入发生在解析器跟不动的地方（句柄由构造参数
//     注入、事务上下文由调用方传入）。这是**维度盲点**，不是缺口：把跟不动的地方报成缺口，
//     等于让人去补一份本来就存在的实现。
//
// 剩下的（既无写入证据、也无任何绑定）才是真缺口：声明了一张代码里不存在的表。
type publicationEvidence struct {
	artifacts          []ast.StorageEvidence
	delivery           []ast.StorageEvidence
	unresolved         []string
	unresolvedDelivery []string
}

func collectPublicationEvidence(
	repoRoot string,
	publication storagePublication,
	writeIndex *serviceWriteIndex,
) (publicationEvidence, error) {
	result := publicationEvidence{}
	if writeIndex == nil {
		return result, nil
	}
	for _, storage := range publication.seams {
		site, ok := writeIndex.resolveTransactionalWrite(storage)
		if !ok {
			if writeIndex.hasUnattributableWrite(storage) {
				result.unresolved = append(result.unresolved, storage)
			}
			continue
		}
		artifact, err := boundArtifact(repoRoot, site, storage)
		if err != nil {
			return publicationEvidence{}, err
		}
		result.artifacts = append(result.artifacts, artifact)
	}
	// 投递实现只对事务性发件箱有意义：事务性事件表按定义没有具名消费者。
	for _, storage := range publication.outboxes {
		site, ok := writeIndex.resolveDeliveryImplementation(storage)
		if !ok {
			if writeIndex.hasExternalBinding(storage) {
				result.unresolvedDelivery = append(result.unresolvedDelivery, storage)
			}
			continue
		}
		artifact, err := boundArtifact(repoRoot, site, storage)
		if err != nil {
			return publicationEvidence{}, err
		}
		result.delivery = append(result.delivery, artifact)
	}
	sortStorageArtifacts(result.artifacts)
	sortStorageArtifacts(result.delivery)
	sort.Strings(result.unresolved)
	sort.Strings(result.unresolvedDelivery)
	return result, nil
}

// undeclaredTransactionalWrites 是反方向的缺口：对象自己的实现树里存在事务性写入，但目标
// 关系名在**全仓任何对象**的 `storage.yaml` 里都没有声明位。
//
// 两个方向必须是两条独立维度，不能合成一条：
//   - 「声明了但没观测到事务性写入」的修法是补实现或撤声明；
//   - 「有事务性写入但没有声明位」的修法是补声明，且它意味着有一张表在契约外承重。
//
// 归属判定刻意用「全仓无人声明」而不是「本对象未声明」：清理型工作流会写兄弟对象的发件箱
// （`content.content_account_closure_workflow` 写 8 张），那些表由兄弟对象声明，不是缺口。
func undeclaredTransactionalWrites(
	objectRoot string,
	writeIndex *serviceWriteIndex,
	declaredAnywhere map[string]struct{},
) []string {
	if writeIndex == nil {
		return nil
	}
	prefix := objectRoot + string(filepath.Separator)
	found := map[string]struct{}{}
	for relation, sites := range writeIndex.transactionalWrites {
		if _, declared := declaredAnywhere[relation]; declared {
			continue
		}
		for _, site := range sites {
			if strings.HasPrefix(site.file, prefix) {
				found[relation] = struct{}{}
				break
			}
		}
	}
	relations := make([]string, 0, len(found))
	for relation := range found {
		relations = append(relations, relation)
	}
	sort.Strings(relations)
	return relations
}

// writeIndexHasPythonImplementation 表示该对象的实现树里有 Python 生产代码。受支持的
// PyMongo AST 形状会产生正常写入证据；只有仍未解析到事务写入时，这一事实才让 graph 把
// 缺口保留为 scanner blindspot，而不是误判实现不存在。
func writeIndexHasPythonImplementation(
	writeIndex *serviceWriteIndex,
	objectRoot string,
) bool {
	if writeIndex == nil {
		return false
	}
	prefix := objectRoot + string(filepath.Separator)
	for _, path := range writeIndex.pythonFiles {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}

func boundArtifact(
	repoRoot string,
	site transactionalWriteSite,
	storage string,
) (ast.StorageEvidence, error) {
	digest, err := fileDigest(site.file)
	if err != nil {
		return ast.StorageEvidence{}, err
	}
	return ast.StorageEvidence{
		Storage: storage,
		Artifact: ast.EvidenceArtifact{
			Path:   relativePath(repoRoot, site.file),
			SHA256: digest,
		},
	}, nil
}

func sortStorageArtifacts(artifacts []ast.StorageEvidence) {
	sort.Slice(artifacts, func(i, j int) bool {
		if artifacts[i].Storage != artifacts[j].Storage {
			return artifacts[i].Storage < artifacts[j].Storage
		}
		return artifacts[i].Artifact.Path < artifacts[j].Artifact.Path
	})
}

// serviceWriteIndexCache 让同一个服务只被扫描一次。
type serviceWriteIndexCache struct {
	byServiceRoot map[string]*serviceWriteIndex
}

func newServiceWriteIndexCache() *serviceWriteIndexCache {
	return &serviceWriteIndexCache{byServiceRoot: map[string]*serviceWriteIndex{}}
}

func (cache *serviceWriteIndexCache) forService(
	serviceRoot string,
) (*serviceWriteIndex, error) {
	if index, ok := cache.byServiceRoot[serviceRoot]; ok {
		return index, nil
	}
	index, err := buildServiceWriteIndex(serviceRoot)
	if err != nil {
		return nil, err
	}
	cache.byServiceRoot[serviceRoot] = index
	return index, nil
}

// 写入判定的粒度声明：关系名必须沿精确字段/形参绑定到实际写调用，函数是否事务性由函数
// 自持句柄、跨包 interface 的事务实参事实，或同包最多四跳的有限调用传播决定。
//
// 为什么不能退回包级 join：包级只能回答「这个包里有事务性写入，且这个包提到过这张表」，
// 回答不了「有人往这张表里写」。`content.post` 的 `post_import_task_outbox` 就是反例——
// 只有一个集合句柄、没有任何写调用，包级 join 会把它判成有发布实现。
//
// 为什么必须解析结构体字段绑定：Go 里集合句柄几乎总是在构造处绑定、在方法里使用
// （`outbox: db.Collection("content_outbox")` + `s.outbox.InsertOne(sessCtx, ...)`），
// 只认函数内局部绑定会让 45 个真实发件箱全部变成盲点。字段绑定是**按字段名逐个绑**的：
// 同一个包里写 `s.state` 不会给 `s.outbox` 记账，所以它不是临近性推断。
//
// 为什么需要有限调用：Mongo 的事务上下文是 `WithTransaction(ctx, func(txCtx ...))` 闭包
// 参数，会作为普通 `context.Context` 传进 helper/store，签名上看不出事务性。跨包 interface
// 保留精确事务实参事实；同包 helper 再按实参位置最多传播四跳，避免 ctx 无界污染全服务。
//
// 仍然跟不动的形态登记为维度盲点，不记缺口，见 unresolvedPublicationWrites。

// writeSite 是一次「事务性函数对某个关系名执行写入」的位置。
type writeSite struct {
	file     string
	function string
}

// serviceWriteIndex 是单个服务一次扫描出的发布写入索引。
type serviceWriteIndex struct {
	// transactionalWrites 是唯一的写入证据源：关系名 → 事务性写入位置。
	transactionalWrites map[string][]writeSite
	// relationBindings 记录关系名被绑定的包目录。它**不构成写入证据**，只用来把两种
	// 「没有证据」分开：跟不动（盲点）与根本不存在（缺口）。
	relationBindings map[string][]string
	// packagesWritingTransactionally 是存在事务性写入的包目录。
	packagesWritingTransactionally map[string]struct{}
	// deliveryReads 是「读取该关系」的位置，按包记账。
	deliveryReads map[string][]readSite
	// packagesAdvancingProgress 是包内存在写入（推进检查点 / 标记已投递）的包目录。
	packagesAdvancingProgress map[string]struct{}
	// deliveryRelayScopes 是同时执行 outbox read/claim、durable handoff 与 checkpoint/ack
	// 的 canonical object scope。它只证明实现存在，不证明生产 composition root 启用了它。
	deliveryRelayScopes map[string]struct{}
	// composedDeliveryRelayScopes 只含被本服务 cmd composition root 实际构造的对象 relay。
	// 只有 source relay 闭环与生产装配同时存在，才允许对象自己的 read+progress 成为投递证据。
	composedDeliveryRelayScopes map[string]struct{}
	// composedSharedScopes 只含被服务生产装配实际调用的 first-party platform package。
	composedSharedScopes map[string]struct{}
	// compositionDeliveries 是服务装配代码对受管共享投递器的精确、import-qualified 绑定。
	// 共享投递器内部用动态表名拼 SQL，单扫业务服务或共享包都无法把具体表名归回对象；
	// 因此必须在装配调用处把「canonical adapter + relation 实参」作为一条结构证据。
	compositionDeliveries map[string][]writeSite
	// externalBindings 是「关系名被当作实参传给本次扫描范围之外的函数」的位置。
	// `pgoutbox.NewDispatcher(pool, publisher, "product_ops_outbox")` 就是这一类：投递
	// 实现在 runtime 共享包里，且表名是参数化的，服务树内看不到任何读取语句。这类
	// 不可判定必须标成盲点，不能记成「没人投递」。
	externalBindings map[string][]string
	// pythonFiles 是服务内的 Python 生产文件，用于批量 Python AST 扫描及残余盲点归类。
	pythonFiles []string
}

// readSite 是一次读取位置，附带所在包，用于与检查点推进合并判定。
type readSite struct {
	writeSite
	packageDir string
}

// transactionalWriteSite 是某张存储的一次写入证据位置。
type transactionalWriteSite struct {
	file     string
	function string
}

func (index *serviceWriteIndex) resolveTransactionalWrite(
	relation string,
) (transactionalWriteSite, bool) {
	sites := index.transactionalWrites[relation]
	if len(sites) == 0 {
		return transactionalWriteSite{}, false
	}
	return transactionalWriteSite{file: sites[0].file, function: sites[0].function}, true
}

// hasExternalBinding 表示关系名被交给了扫描范围之外的实现。
func (index *serviceWriteIndex) hasExternalBinding(relation string) bool {
	return len(index.externalBindings[relation]) > 0
}

// hasUnattributableWrite 表示「有一个事务性存储包绑定了这张关系，但解析器归不到具体写入」。
//
// 只用「被绑定过」区分盲点与缺口会误判：`integration.external_interaction` 的
// `external_interaction_result_outbox` 在生产代码里只出现在账号关闭清理投影的
// `DeleteMany` 一侧，全服务没有任何追加，那是真缺口不是盲点。所以这里要求绑定它的包
// **自己有事务性写入**——判定器确实看见了一个在写的事务性存储，只是归不到这张关系上。
func (index *serviceWriteIndex) hasUnattributableWrite(relation string) bool {
	for _, dir := range index.relationBindings[relation] {
		if _, writes := index.packagesWritingTransactionally[dir]; writes {
			return true
		}
	}
	return false
}

// resolveDeliveryImplementation 判定是否存在「读取该关系并推进进度」的投递实现。
//
// 判据刻意不看文件名，也不看契约声明的索引：
//   - 文件名扫描（找 `*_relay.go`）已有漏判：投递实现常内联在 store 或 worker 里。
//   - 契约声明的索引不等于真实存在的索引。`content.report` 的契约声明了 `published_at`
//     列与 `idx_report_outbox_unpublished`，真实 DDL（report/infrastructure/persistence/
//     pg_store.go 建表七列）里既没有 `published_at` 也没有等价列，那个索引建不出来；实现
//     走的是 `outbox_sequence` + `report_outbox_sequence` 检查点。按声明判会把一个能投递
//     的实现判成不能投递。
//
// 判定单元是**包**而不是函数：真实实现里「拉取一批」与「推进检查点」几乎总是分成
// `ReadAfter` / `SaveCheckpoint` 两个方法（`content.post` 的 mongo_post_outbox.go 就是
// 这个形状），要求同一函数内既读又推进会把整类正确实现判成缺口。发件箱被读取本身就是
// 强信号：写发件箱的是聚合存储，读它的只有投递侧。
func (index *serviceWriteIndex) resolveDeliveryImplementation(
	relation string,
) (transactionalWriteSite, bool) {
	if sites := index.compositionDeliveries[relation]; len(sites) > 0 {
		return transactionalWriteSite{file: sites[0].file, function: sites[0].function}, true
	}
	ownerScopes := map[string]struct{}{}
	for _, write := range index.transactionalWrites[relation] {
		if scope := publicationImplementationScope(write.file); scope != "" {
			ownerScopes[scope] = struct{}{}
		}
	}
	for _, site := range index.deliveryReads[relation] {
		if _, advances := index.packagesAdvancingProgress[site.packageDir]; !advances {
			continue
		}
		scope := publicationImplementationScope(site.file)
		_, sameOwner := ownerScopes[scope]
		_, relayDefined := index.deliveryRelayScopes[scope]
		_, relayComposed := index.composedDeliveryRelayScopes[scope]
		_, sharedComposed := index.composedSharedScopes[scope]
		// 同 owner 的 claim/checkpoint 可能只是 processing 或尚未启用的 store 能力，不能
		// 单独冒充投递。对象路径必须同时存在 read→durable handoff→ack 闭环，并由 cmd
		// composition root 实际装配；受管 shared adapter 继续使用其 import-qualified 装配证据。
		objectRelayReady := sameOwner && relayDefined && relayComposed
		if scope == "" || (!objectRelayReady && !sharedComposed) {
			continue
		}
		return transactionalWriteSite{file: site.file, function: site.function}, true
	}
	return transactionalWriteSite{}, false
}

// publicationImplementationScope 从目录即领域树中提取实现 owner。业务实现的稳定形状是
// `services/<service>/internal/<context>/<object>/...`；实际装配后才扫描的 shared adapter
// 使用 `internal/platform/<package>/...`。只比较这条结构归属，不从文件名、注释或 token
// 猜测 publisher 身份。
func publicationImplementationScope(path string) string {
	clean := filepath.ToSlash(filepath.Clean(path))
	marker := "/internal/"
	position := strings.Index(clean, marker)
	if position < 0 {
		return ""
	}
	remainder := strings.TrimPrefix(clean[position+len(marker):], "/")
	segments := strings.Split(remainder, "/")
	if len(segments) < 3 || segments[0] == "" || segments[1] == "" {
		return ""
	}
	return clean[:position+len(marker)] + segments[0] + "/" + segments[1]
}

// functionRecord 是一次扫描里单个函数的语法事实，解析推迟到全服务事实齐备之后。
type functionRecord struct {
	file             string
	packageDir       string
	name             string
	parameters       []string
	transactionVars  []string
	calls            []functionCall
	holdsHandle      bool
	handleCallees    []string
	writtenFields    []string
	writtenLocals    []string
	writtenSQL       []string
	dynamicSQLWrites []methodRelationKey
	readFields       []string
	readLocals       []string
	readSQL          []string
	advancesProgres  bool
	deliveryRead     bool
	deliveryAdvance  bool
	deliveryHandoff  bool
}

// methodRelationKey identifies a receiver method that resolves a storage relation from
// constructor-bound state. The package and receiver type are part of the identity so an
// unrelated helper with the same method name cannot contribute evidence.
type methodRelationKey struct {
	packageDir   string
	receiverType string
	method       string
}

type receiverFieldKey struct {
	receiverType string
	field        string
}

// conditionalRelationResolver is the exact AST shape used by the shared control-plane store:
// a receiver-field switch whose case literals return relation-name literals.
type conditionalRelationResolver struct {
	field            receiverFieldKey
	relationsByValue map[string]map[string]struct{}
}

// functionCall 只保留有限跨函数传播所需的静态实参形状。它不保存源码 token，也不会从
// 注释、错误字符串或函数名猜关系；关系只能来自已解析的 collection/table 句柄绑定。
type functionCall struct {
	callee    string
	arguments []argumentReference
}

type argumentReference struct {
	identifier string
	field      string
	literal    string
}

type functionKey struct {
	packageDir string
	name       string
}

const maxPublicationCallDepth = 4

// packageBindings 是单个包目录内的字段绑定事实。
type packageBindings struct {
	// fieldRelations 是结构体字段 → 它绑定的关系名。
	fieldRelations map[string]map[string]struct{}
	// fieldConstructorParams 是「字段绑定到构造函数的第 N 个形参」，等全服务装配点扫完再
	// 用调用实参补齐。
	fieldConstructorParams map[string][]constructorParam
	// fieldValues stores scalar constructor state separately from storage relations. It is
	// used only to select a structurally declared receiver-method return; a scope token can
	// never become a storage relation by itself.
	fieldValues map[receiverFieldKey]map[string]struct{}
	// fieldValueConstructorParams records `&Store{scope: scope}` by receiver type, field and
	// constructor parameter position. The actual literal is supplied only by a real
	// production composition call.
	fieldValueConstructorParams map[receiverFieldKey][]scalarConstructorParam
	// localsByFunction 是函数内局部句柄绑定（`events := db.Collection("x")`）。
	localsByFunction map[string]map[string]string
	constants        map[string]string
}

type constructorParam struct {
	constructor string
	index       int
}

type constructorCallKey struct {
	packageDir string
	name       string
}

type scalarConstructorParam struct {
	constructor constructorCallKey
	index       int
}

func quwoquanServiceModuleRoot(serviceRoot string) string {
	current := filepath.Clean(serviceRoot)
	for {
		if filepath.Base(current) == serviceTreeRoot &&
			isDir(filepath.Join(current, "internal", "platform")) {
			return current
		}
		candidate := filepath.Join(filepath.Dir(current), serviceTreeRoot)
		if isDir(filepath.Join(candidate, "internal", "platform")) {
			return candidate
		}
		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}
	return filepath.Dir(filepath.Dir(serviceRoot))
}

func buildServiceWriteIndex(serviceRoot string) (*serviceWriteIndex, error) {
	index := &serviceWriteIndex{
		transactionalWrites:            map[string][]writeSite{},
		relationBindings:               map[string][]string{},
		packagesWritingTransactionally: map[string]struct{}{},
		externalBindings:               map[string][]string{},
		deliveryReads:                  map[string][]readSite{},
		packagesAdvancingProgress:      map[string]struct{}{},
		deliveryRelayScopes:            map[string]struct{}{},
		composedDeliveryRelayScopes:    map[string]struct{}{},
		composedSharedScopes:           map[string]struct{}{},
		compositionDeliveries:          map[string][]writeSite{},
	}
	scan := &serviceScan{
		bindings:                  map[string]*packageBindings{},
		constructorCallArgs:       map[string]map[int]map[string]struct{}{},
		constructorStringCallArgs: map[constructorCallKey]map[int]map[string]struct{}{},
		relationResolvers:         map[methodRelationKey][]conditionalRelationResolver{},
		txInvokedMethods:          map[string]struct{}{},
		declaredFunctions:         map[string]struct{}{},
		sharedPackageCalls:        map[string]struct{}{},
		serviceDir:                filepath.Base(serviceRoot),
	}
	for _, subtree := range []string{"internal", "cmd"} {
		root := filepath.Join(serviceRoot, subtree)
		err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				if os.IsNotExist(walkErr) {
					return nil
				}
				return walkErr
			}
			if entry.IsDir() {
				if isNonProductionDir(entry.Name()) {
					return filepath.SkipDir
				}
				return nil
			}
			if !isProductionSourceFile(path) {
				return nil
			}
			data, readErr := os.ReadFile(path)
			if readErr != nil {
				return readErr
			}
			switch strings.ToLower(filepath.Ext(path)) {
			case ".go":
				scan.indexGoFile(index, path, data)
			case ".py":
				index.pythonFiles = append(index.pythonFiles, path)
			}
			return nil
		})
		if err != nil && !os.IsNotExist(err) {
			return nil, err
		}
	}
	// 只扫描服务生产代码**真实调用**到的第一方共享 platform package。仅有 import、注释、
	// TODO 或错误字符串均不会进入 sharedPackageCalls；这让共享 adapter 仍是 composition-aware
	// 证据，而不是把整个 internal/platform 当成服务实现批量嫁接。
	moduleRoot := quwoquanServiceModuleRoot(serviceRoot)
	for importPath := range scan.sharedPackageCalls {
		if err := scan.indexSharedPlatformPackage(index, moduleRoot, importPath); err != nil {
			return nil, err
		}
	}
	if err := indexPythonPublicationFiles(index, index.pythonFiles); err != nil {
		return nil, err
	}
	scan.resolve(index)
	return index, nil
}

// serviceScan 承载解析阶段的中间事实。
type serviceScan struct {
	functions                 []functionRecord
	bindings                  map[string]*packageBindings
	constructorCallArgs       map[string]map[int]map[string]struct{}
	constructorStringCallArgs map[constructorCallKey]map[int]map[string]struct{}
	relationResolvers         map[methodRelationKey][]conditionalRelationResolver
	txInvokedMethods          map[string]struct{}
	declaredFunctions         map[string]struct{}
	externalCandidates        []externalCandidate
	sharedPackageCalls        map[string]struct{}
	serviceDir                string
}

type externalCandidate struct {
	relation string
	callee   string
	file     string
	// external 为 true 表示被调方来自本服务之外的包，无需再按函数名回查。函数名回查会
	// 误判：`pgoutbox.NewDispatcher` 与本服务自己的 `NewDispatcher` 同名但不是同一个函数。
	external bool
}

func (scan *serviceScan) packageBindings(dir string) *packageBindings {
	bindings := scan.bindings[dir]
	if bindings == nil {
		bindings = &packageBindings{
			fieldRelations:              map[string]map[string]struct{}{},
			fieldConstructorParams:      map[string][]constructorParam{},
			fieldValues:                 map[receiverFieldKey]map[string]struct{}{},
			fieldValueConstructorParams: map[receiverFieldKey][]scalarConstructorParam{},
			localsByFunction:            map[string]map[string]string{},
			constants:                   map[string]string{},
		}
		scan.bindings[dir] = bindings
	}
	return bindings
}

func isNonProductionDir(name string) bool {
	if name == "tests" || name == "test" {
		return true
	}
	_, nonProduction := nonProductionSegments[name]
	return nonProduction
}

func isProductionSourceFile(path string) bool {
	if strings.HasSuffix(path, "_test.go") {
		return false
	}
	_, ok := cloudSourceSuffixes[strings.ToLower(filepath.Ext(path))]
	return ok
}

func (scan *serviceScan) indexGoFile(index *serviceWriteIndex, path string, data []byte) {
	fileSet := token.NewFileSet()
	file, err := parser.ParseFile(fileSet, path, data, parser.SkipObjectResolution)
	if err != nil {
		return
	}
	dir := filepath.Dir(path)
	bindings := scan.packageBindings(dir)
	imports := importPathsByName(file)
	// 文件级 const/var 字符串是同一份静态事实：`const outboxCollection = "gathering_outbox"`
	// 必须能解析回字面量，否则 Go 里最常见的一种表名写法整类漏判。
	goast.Inspect(file, func(node goast.Node) bool {
		spec, ok := node.(*goast.ValueSpec)
		if !ok {
			return true
		}
		for position, value := range spec.Values {
			literal, isLiteral := value.(*goast.BasicLit)
			if !isLiteral || literal.Kind != token.STRING || position >= len(spec.Names) {
				continue
			}
			bindings.constants[spec.Names[position].Name] = trimStringLiteral(literal.Value)
		}
		return true
	})
	index.indexRelationBindings(dir, file, bindings.constants)
	scan.indexExternalCandidates(path, file, bindings.constants)
	scan.indexCompositionCalls(index, path, file, bindings.constants)
	for _, declaration := range file.Decls {
		function, ok := declaration.(*goast.FuncDecl)
		if !ok || function.Body == nil {
			continue
		}
		scan.indexFunction(path, dir, bindings, imports, function)
	}
}

const (
	firstPartyPlatformImportPrefix = "quwoquan_service/internal/platform/"
	postgresOutboxImportPath       = "quwoquan_service/internal/platform/pgoutbox"
)

// indexCompositionCalls 只认真实 AST call 与解析后的 import identity：
//
//   - 被实际调用的第一方 shared platform package 才进入后续扫描；
//   - cmd composition root 对本服务对象 relay constructor 的调用，绑定到该对象 scope；
//   - `pgoutbox.NewDispatcher(..., relation)` 是 canonical PostgreSQL outbox 投递装配，
//     具体 relation 只存在于调用点，因此在此绑定为 delivery evidence。
//
// 同名本地函数、其它 import 的 NewDispatcher、注释与字符串都不会命中。
func (scan *serviceScan) indexCompositionCalls(
	index *serviceWriteIndex,
	path string,
	file *goast.File,
	constants map[string]string,
) {
	imports := importPathsByName(file)
	for _, declaration := range file.Decls {
		function, ok := declaration.(*goast.FuncDecl)
		if !ok || function.Body == nil {
			continue
		}
		goast.Inspect(function.Body, func(node goast.Node) bool {
			call, isCall := node.(*goast.CallExpr)
			if !isCall {
				return true
			}
			selector, isSelector := call.Fun.(*goast.SelectorExpr)
			if !isSelector {
				return true
			}
			qualifier, isIdentifier := selector.X.(*goast.Ident)
			if !isIdentifier {
				return true
			}
			importPath, imported := imports[qualifier.Name]
			if !imported {
				return true
			}
			if strings.HasPrefix(importPath, firstPartyPlatformImportPrefix) {
				scan.sharedPackageCalls[importPath] = struct{}{}
			}
			if scope := composedObjectRelayScope(path, importPath, selector.Sel.Name); scope != "" {
				index.composedDeliveryRelayScopes[scope] = struct{}{}
			}
			if importPath != postgresOutboxImportPath || selector.Sel.Name != "NewDispatcher" {
				return true
			}
			for _, argument := range call.Args {
				relation, resolved := stringArgument(argument, constants)
				if !resolved || !relationNamePattern.MatchString(relation) {
					continue
				}
				index.compositionDeliveries[relation] = appendSite(
					index.compositionDeliveries[relation],
					writeSite{file: path, function: function.Name.Name},
				)
			}
			return true
		})
	}
}

// composedObjectRelayScope 将 cmd 里的 import-qualified relay constructor 解析回同一服务
// 的 canonical object scope。只接受 `New*Relay*` 的真实调用和本服务 private internal import；
// 字符串、注释、兄弟服务私有包以及 internal 内部自构造都不能形成生产装配证据。
func composedObjectRelayScope(path string, importPath string, constructor string) string {
	if !strings.HasPrefix(constructor, "New") || !strings.Contains(constructor, "Relay") {
		return ""
	}
	cleanPath := filepath.ToSlash(filepath.Clean(path))
	marker := "/cmd/"
	position := strings.Index(cleanPath, marker)
	if position < 0 {
		return ""
	}
	serviceRoot := cleanPath[:position]
	rootParent := filepath.Base(filepath.Dir(filepath.FromSlash(serviceRoot)))
	if rootParent != "services" && rootParent != "control-plane" {
		return ""
	}
	importMarker := "/internal/"
	importPosition := strings.Index(importPath, importMarker)
	if importPosition < 0 {
		return ""
	}
	wantImportRoot := "quwoquan_service/" + rootParent + "/" + filepath.Base(filepath.FromSlash(serviceRoot))
	if importPath[:importPosition] != wantImportRoot {
		return ""
	}
	implementationPath := filepath.Join(
		filepath.FromSlash(serviceRoot),
		filepath.FromSlash(strings.TrimPrefix(importPath[importPosition:], "/")),
		"package.go",
	)
	return publicationImplementationScope(implementationPath)
}

// indexSharedPlatformPackage 将真实 composition call 指向的单个第一方 package 纳入与服务
// 相同的 AST 索引。路径由 import identity 推导并强制留在 moduleRoot/internal/platform 下；
// 不递归吞并未被装配的兄弟 package。
func (scan *serviceScan) indexSharedPlatformPackage(
	index *serviceWriteIndex,
	moduleRoot string,
	importPath string,
) error {
	if !strings.HasPrefix(importPath, firstPartyPlatformImportPrefix) {
		return nil
	}
	relative := strings.TrimPrefix(importPath, "quwoquan_service/")
	packageDir := filepath.Clean(filepath.Join(moduleRoot, filepath.FromSlash(relative)))
	platformRoot := filepath.Clean(filepath.Join(moduleRoot, "internal", "platform"))
	if packageDir == platformRoot || !strings.HasPrefix(
		packageDir, platformRoot+string(filepath.Separator),
	) {
		return nil
	}
	if scope := publicationImplementationScope(filepath.Join(packageDir, "package.go")); scope != "" {
		index.composedSharedScopes[scope] = struct{}{}
	}
	entries, err := os.ReadDir(packageDir)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			continue
		}
		path := filepath.Join(packageDir, entry.Name())
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		scan.indexGoFile(index, path, data)
	}
	return nil
}

// indexRelationBindings 记录关系名的绑定位置，用途只有一个：区分「跟不动」与「不存在」。
func (index *serviceWriteIndex) indexRelationBindings(
	dir string,
	file *goast.File,
	constants map[string]string,
) {
	record := func(relation string) {
		for _, existing := range index.relationBindings[relation] {
			if existing == dir {
				return
			}
		}
		index.relationBindings[relation] = append(index.relationBindings[relation], dir)
	}
	for _, value := range constants {
		if relationNamePattern.MatchString(value) {
			record(value)
			continue
		}
		for _, relation := range sqlRelations(value) {
			record(relation)
		}
	}
	goast.Inspect(file, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		bindingCall := storageHandleBindingCalls[callTargetName(call)] ||
			isConstructorName(callTargetName(call))
		for _, argument := range call.Args {
			value, resolved := stringArgument(argument, constants)
			if !resolved {
				continue
			}
			if bindingCall && relationNamePattern.MatchString(value) {
				record(value)
				continue
			}
			for _, relation := range sqlRelations(value) {
				record(relation)
			}
		}
		return true
	})
}

// indexExternalCandidates 记录「关系名被当实参传给某个函数」这条边，等全服务函数名收齐后
// 再判断被调方是否在扫描范围内。
func (scan *serviceScan) indexExternalCandidates(
	path string,
	file *goast.File,
	constants map[string]string,
) {
	imports := importPathsByName(file)
	goast.Inspect(file, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		callee := callTargetName(call)
		if callee == "" || storageHandleBindingCalls[callee] {
			return true
		}
		external := scan.callTargetsOutsideService(call, imports)
		for _, argument := range call.Args {
			value, resolved := stringArgument(argument, constants)
			if !resolved || !relationNamePattern.MatchString(value) {
				continue
			}
			scan.externalCandidates = append(scan.externalCandidates, externalCandidate{
				relation: value, callee: callee, file: path, external: external,
			})
		}
		return true
	})
}

// callTargetsOutsideService 判断 `pkg.Fn(...)` 的 pkg 是否来自本服务之外的导入路径。
func (scan *serviceScan) callTargetsOutsideService(
	call *goast.CallExpr,
	imports map[string]string,
) bool {
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok {
		return false
	}
	qualifier, isIdent := selector.X.(*goast.Ident)
	if !isIdent {
		return false
	}
	path, imported := imports[qualifier.Name]
	if !imported {
		return false
	}
	return !strings.Contains(path, "/"+scan.serviceDir+"/")
}

func importPathsByName(file *goast.File) map[string]string {
	paths := map[string]string{}
	for _, entry := range file.Imports {
		if entry.Path == nil {
			continue
		}
		path := trimStringLiteral(entry.Path.Value)
		name := path
		if index := strings.LastIndex(path, "/"); index >= 0 {
			name = path[index+1:]
		}
		if entry.Name != nil {
			name = entry.Name.Name
		}
		paths[name] = path
	}
	return paths
}

// indexFunction 抽出单个函数的写入/读取目标与事务性来源，目标解析推迟到 resolve。
func (scan *serviceScan) indexFunction(
	path string,
	dir string,
	bindings *packageBindings,
	imports map[string]string,
	function *goast.FuncDecl,
) {
	handles := map[string]struct{}{}
	collectTransactionHandles(function.Type, handles)
	locals := map[string]string{}
	// 字段绑定在**所有**函数里收集：投递侧常把句柄放进函数内的匿名结构体切片
	// （`{name: "TripMembership", collection: db.Collection("trip_membership_outbox")}`），
	// 只认构造函数会漏掉整类投递实现。形参位置绑定仍只对构造函数有效，因为只有构造调用
	// 点会传入集合名。
	paramIndex := map[string]int{}
	if isConstructorName(function.Name.Name) {
		paramIndex = parameterIndexes(function.Type)
	}
	goast.Inspect(function.Body, func(node goast.Node) bool {
		switch typed := node.(type) {
		case *goast.FuncLit:
			collectTransactionHandles(typed.Type, handles)
		case *goast.AssignStmt:
			collectTransactionAssignments(typed, handles)
			collectLocalRelationBindings(typed, locals, bindings.constants)
			scan.collectFieldAssignments(typed, bindings, paramIndex, function.Name.Name)
		case *goast.CompositeLit:
			scan.collectFieldComposites(typed, bindings, paramIndex, function.Name.Name)
			scan.collectConstructorValueComposite(
				dir, typed, bindings, paramIndex, function.Name.Name,
			)
		case *goast.CallExpr:
			collectTransactionClosureHandles(typed, handles)
			scan.collectConstructorCallArgs(typed, dir, imports, bindings.constants)
		}
		return true
	})
	record := functionRecord{
		file:            path,
		packageDir:      dir,
		name:            function.Name.Name,
		parameters:      parameterNames(function.Type),
		transactionVars: sortedSetKeys(handles),
		holdsHandle:     functionUsesTransactionHandle(function.Body, handles),
		dynamicSQLWrites: collectDynamicTransactionalSQLWrites(
			dir, function, handles, bindings.constants, imports,
		),
	}
	scan.collectConditionalRelationResolvers(dir, function, bindings.constants)
	collectAccessTargets(function.Body, handles, &record, bindings.constants)
	bindings.localsByFunction[function.Name.Name] = locals
	scan.declaredFunctions[function.Name.Name] = struct{}{}
	scan.functions = append(scan.functions, record)
	for _, callee := range record.handleCallees {
		scan.txInvokedMethods[callee] = struct{}{}
	}
}

func parameterNames(signature *goast.FuncType) []string {
	if signature == nil || signature.Params == nil {
		return nil
	}
	names := []string{}
	for _, field := range signature.Params.List {
		if len(field.Names) == 0 {
			names = append(names, "")
			continue
		}
		for _, name := range field.Names {
			names = append(names, name.Name)
		}
	}
	return names
}

func sortedSetKeys(values map[string]struct{}) []string {
	keys := make([]string, 0, len(values))
	for value := range values {
		keys = append(keys, value)
	}
	sort.Strings(keys)
	return keys
}

func parameterIndexes(signature *goast.FuncType) map[string]int {
	indexes := map[string]int{}
	if signature == nil || signature.Params == nil {
		return indexes
	}
	position := 0
	for _, field := range signature.Params.List {
		if len(field.Names) == 0 {
			position++
			continue
		}
		for _, name := range field.Names {
			indexes[name.Name] = position
			position++
		}
	}
	return indexes
}

// collectFieldComposites 解析 `&Store{outbox: db.Collection("content_outbox")}` 形态。
func (scan *serviceScan) collectFieldComposites(
	literal *goast.CompositeLit,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	for _, element := range literal.Elts {
		pair, ok := element.(*goast.KeyValueExpr)
		if !ok {
			continue
		}
		key, isIdent := pair.Key.(*goast.Ident)
		if !isIdent {
			continue
		}
		bindFieldValue(key.Name, pair.Value, bindings, paramIndex, constructor)
	}
}

// collectConstructorValueComposite records only direct scalar constructor propagation:
// `func NewStore(..., scope string) *Store { return &Store{scope: scope} }`.
// It deliberately does not treat that scalar as a relation. A relation is selected later only
// when a receiver method contains an exact field-switch/case-return mapping.
func (scan *serviceScan) collectConstructorValueComposite(
	dir string,
	literal *goast.CompositeLit,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	if !isConstructorName(constructor) || len(paramIndex) == 0 {
		return
	}
	receiverType := namedTypeExpression(literal.Type)
	if receiverType == "" {
		return
	}
	for _, element := range literal.Elts {
		pair, ok := element.(*goast.KeyValueExpr)
		if !ok {
			continue
		}
		field, fieldOK := pair.Key.(*goast.Ident)
		value, valueOK := pair.Value.(*goast.Ident)
		if !fieldOK || !valueOK {
			continue
		}
		position, bound := paramIndex[value.Name]
		if !bound {
			continue
		}
		key := receiverFieldKey{receiverType: receiverType, field: field.Name}
		bindings.fieldValueConstructorParams[key] = append(
			bindings.fieldValueConstructorParams[key],
			scalarConstructorParam{
				constructor: constructorCallKey{packageDir: dir, name: constructor},
				index:       position,
			},
		)
	}
}

func namedTypeExpression(expression goast.Expr) string {
	switch typed := expression.(type) {
	case *goast.Ident:
		return typed.Name
	case *goast.StarExpr:
		return namedTypeExpression(typed.X)
	case *goast.IndexExpr:
		return namedTypeExpression(typed.X)
	case *goast.IndexListExpr:
		return namedTypeExpression(typed.X)
	}
	return ""
}

// collectFieldAssignments 解析 `store.outbox = db.Collection(collectionName)` 形态。
func (scan *serviceScan) collectFieldAssignments(
	statement *goast.AssignStmt,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	for position, target := range statement.Lhs {
		selector, ok := target.(*goast.SelectorExpr)
		if !ok || position >= len(statement.Rhs) {
			continue
		}
		bindFieldValue(
			selector.Sel.Name, statement.Rhs[position], bindings, paramIndex, constructor,
		)
	}
}

func bindFieldValue(
	field string,
	value goast.Expr,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	call, ok := value.(*goast.CallExpr)
	if !ok || !storageHandleBindingCalls[callTargetName(call)] {
		return
	}
	for _, argument := range call.Args {
		if literal, resolved := stringArgument(argument, bindings.constants); resolved {
			if relationNamePattern.MatchString(literal) {
				addFieldRelation(bindings, field, literal)
			}
			continue
		}
		identifier, isIdent := argument.(*goast.Ident)
		if !isIdent {
			continue
		}
		// 集合名由构造形参注入：等全服务装配点扫完，再用实参补齐这条边。
		if index, known := paramIndex[identifier.Name]; known {
			bindings.fieldConstructorParams[field] = append(
				bindings.fieldConstructorParams[field],
				constructorParam{constructor: constructor, index: index},
			)
		}
	}
}

func addFieldRelation(bindings *packageBindings, field string, relation string) {
	relations := bindings.fieldRelations[field]
	if relations == nil {
		relations = map[string]struct{}{}
		bindings.fieldRelations[field] = relations
	}
	relations[relation] = struct{}{}
}

func addFieldValue(bindings *packageBindings, field receiverFieldKey, value string) {
	values := bindings.fieldValues[field]
	if values == nil {
		values = map[string]struct{}{}
		bindings.fieldValues[field] = values
	}
	values[value] = struct{}{}
}

// collectConstructorCallArgs 记录装配点传给构造函数的关系名字面量，按实参位置登记。位置
// 匹配保证 `NewStore(db, "conversations", "conversations_outbox", "..._sequences")` 里
// 三个名字各归各的字段，不会互相串味。
func (scan *serviceScan) collectConstructorCallArgs(
	call *goast.CallExpr,
	dir string,
	imports map[string]string,
	constants map[string]string,
) {
	name := callTargetName(call)
	if !isConstructorName(name) {
		return
	}
	scalarKey, hasScalarIdentity := constructorCallIdentity(call, dir, imports)
	for position, argument := range call.Args {
		value, resolved := stringArgument(argument, constants)
		if !resolved {
			continue
		}
		if hasScalarIdentity {
			stringByIndex := scan.constructorStringCallArgs[scalarKey]
			if stringByIndex == nil {
				stringByIndex = map[int]map[string]struct{}{}
				scan.constructorStringCallArgs[scalarKey] = stringByIndex
			}
			if stringByIndex[position] == nil {
				stringByIndex[position] = map[string]struct{}{}
			}
			stringByIndex[position][value] = struct{}{}
		}
		if !relationNamePattern.MatchString(value) {
			continue
		}
		byIndex := scan.constructorCallArgs[name]
		if byIndex == nil {
			byIndex = map[int]map[string]struct{}{}
			scan.constructorCallArgs[name] = byIndex
		}
		if byIndex[position] == nil {
			byIndex[position] = map[string]struct{}{}
		}
		byIndex[position][value] = struct{}{}
	}
}

// constructorCallIdentity resolves only local calls or import-qualified first-party calls.
// This prevents an unrelated package's same-named constructor from supplying the scope for a
// shared store scanned in the same service composition.
func constructorCallIdentity(
	call *goast.CallExpr,
	dir string,
	imports map[string]string,
) (constructorCallKey, bool) {
	switch target := call.Fun.(type) {
	case *goast.Ident:
		return constructorCallKey{packageDir: dir, name: target.Name}, true
	case *goast.SelectorExpr:
		qualifier, ok := target.X.(*goast.Ident)
		if !ok {
			return constructorCallKey{}, false
		}
		importPath, imported := imports[qualifier.Name]
		if !imported || !strings.HasPrefix(importPath, "quwoquan_service/") {
			return constructorCallKey{}, false
		}
		packageDir, resolved := firstPartyPackageDir(dir, importPath)
		if !resolved {
			return constructorCallKey{}, false
		}
		return constructorCallKey{packageDir: packageDir, name: target.Sel.Name}, true
	}
	return constructorCallKey{}, false
}

func firstPartyPackageDir(currentDir string, importPath string) (string, bool) {
	current := filepath.ToSlash(filepath.Clean(currentDir))
	const moduleMarker = "/quwoquan_service/"
	position := strings.Index(current, moduleMarker)
	if position < 0 {
		return "", false
	}
	moduleRoot := current[:position] + "/quwoquan_service"
	relative := strings.TrimPrefix(importPath, "quwoquan_service/")
	if relative == importPath || relative == "" {
		return "", false
	}
	return filepath.Clean(filepath.FromSlash(moduleRoot + "/" + relative)), true
}

func methodReceiver(function *goast.FuncDecl) (string, string, bool) {
	if function == nil || function.Recv == nil || len(function.Recv.List) != 1 {
		return "", "", false
	}
	field := function.Recv.List[0]
	if len(field.Names) != 1 {
		return "", "", false
	}
	typeName := namedTypeExpression(field.Type)
	if typeName == "" || field.Names[0].Name == "_" {
		return "", "", false
	}
	return field.Names[0].Name, typeName, true
}

func functionReturnsString(function *goast.FuncDecl) bool {
	if function == nil || function.Type == nil || function.Type.Results == nil ||
		len(function.Type.Results.List) != 1 {
		return false
	}
	result, ok := function.Type.Results.List[0].Type.(*goast.Ident)
	return ok && result.Name == "string"
}

// collectConditionalRelationResolvers recognizes only a receiver-field switch with literal
// cases and literal relation returns. It does not infer from method names, comments, default
// branches or string proximity. The configured field value must later arrive through a real
// constructor call before any relation can be selected.
func (scan *serviceScan) collectConditionalRelationResolvers(
	dir string,
	function *goast.FuncDecl,
	constants map[string]string,
) {
	receiverName, receiverType, ok := methodReceiver(function)
	if !ok || !functionReturnsString(function) {
		return
	}
	key := methodRelationKey{
		packageDir: dir, receiverType: receiverType, method: function.Name.Name,
	}
	for _, statement := range function.Body.List {
		switchStatement, isSwitch := statement.(*goast.SwitchStmt)
		if !isSwitch || switchStatement.Tag == nil {
			continue
		}
		selector, isSelector := switchStatement.Tag.(*goast.SelectorExpr)
		if !isSelector {
			continue
		}
		receiver, isReceiver := selector.X.(*goast.Ident)
		if !isReceiver || receiver.Name != receiverName {
			continue
		}
		resolver := conditionalRelationResolver{
			field:            receiverFieldKey{receiverType: receiverType, field: selector.Sel.Name},
			relationsByValue: map[string]map[string]struct{}{},
		}
		for _, clauseStatement := range switchStatement.Body.List {
			clause, isClause := clauseStatement.(*goast.CaseClause)
			if !isClause || len(clause.List) == 0 {
				// A default branch is intentionally unusable: it is not tied to an exact
				// production composition value.
				continue
			}
			relation, returned := singleReturnedRelation(clause.Body, constants)
			if !returned {
				continue
			}
			for _, caseExpression := range clause.List {
				value, resolved := stringArgument(caseExpression, constants)
				if !resolved {
					continue
				}
				if resolver.relationsByValue[value] == nil {
					resolver.relationsByValue[value] = map[string]struct{}{}
				}
				resolver.relationsByValue[value][relation] = struct{}{}
			}
		}
		if len(resolver.relationsByValue) != 0 {
			scan.relationResolvers[key] = append(scan.relationResolvers[key], resolver)
		}
	}
}

func singleReturnedRelation(
	statements []goast.Stmt,
	constants map[string]string,
) (string, bool) {
	if len(statements) != 1 {
		return "", false
	}
	result, ok := statements[0].(*goast.ReturnStmt)
	if !ok || len(result.Results) != 1 {
		return "", false
	}
	relation, resolved := stringArgument(result.Results[0], constants)
	if !resolved || !relationNamePattern.MatchString(relation) {
		return "", false
	}
	return relation, true
}

// collectDynamicTransactionalSQLWrites follows one bounded, explicit local flow:
//
//	relation := receiver.literalSwitchResolver()
//	query := fmt.Sprintf("INSERT INTO %s (...) ...", relation)
//	tx.Exec(ctx, query, ...)
//
// The fmt import identity, SQL relation placeholder, receiver identity and transaction handle
// are all required. A similar-looking log string, SELECT, pool.Exec or uncomposed resolver does
// not become publication evidence.
func collectDynamicTransactionalSQLWrites(
	dir string,
	function *goast.FuncDecl,
	handles map[string]struct{},
	constants map[string]string,
	imports map[string]string,
) []methodRelationKey {
	receiverName, receiverType, hasReceiver := methodReceiver(function)
	if !hasReceiver {
		return nil
	}
	relationLocals := map[string]methodRelationKey{}
	queryLocals := map[string]methodRelationKey{}
	writes := []methodRelationKey{}
	goast.Inspect(function.Body, func(node goast.Node) bool {
		switch typed := node.(type) {
		case *goast.AssignStmt:
			for _, target := range typed.Lhs {
				if identifier, ok := target.(*goast.Ident); ok {
					delete(relationLocals, identifier.Name)
					delete(queryLocals, identifier.Name)
				}
			}
			if len(typed.Lhs) != len(typed.Rhs) {
				return true
			}
			for position, expression := range typed.Rhs {
				target, isIdentifier := typed.Lhs[position].(*goast.Ident)
				if !isIdentifier || target.Name == "_" {
					continue
				}
				if key, ok := receiverRelationMethodCall(
					dir, receiverName, receiverType, expression,
				); ok {
					relationLocals[target.Name] = key
					continue
				}
				if key, ok := formattedSQLRelationCall(
					expression, relationLocals, constants, imports,
				); ok {
					queryLocals[target.Name] = key
				}
			}
		case *goast.CallExpr:
			if !writeMethodNames[callTargetName(typed)] {
				return true
			}
			selector, isSelector := typed.Fun.(*goast.SelectorExpr)
			if !isSelector {
				return true
			}
			tx, isTransaction := selector.X.(*goast.Ident)
			if !isTransaction {
				return true
			}
			if _, allowed := handles[tx.Name]; !allowed {
				return true
			}
			for _, argument := range typed.Args {
				query, isIdentifier := argument.(*goast.Ident)
				if !isIdentifier {
					continue
				}
				if key, bound := queryLocals[query.Name]; bound {
					writes = appendUniqueMethodRelationKey(writes, key)
				}
			}
		}
		return true
	})
	return writes
}

func receiverRelationMethodCall(
	dir string,
	receiverName string,
	receiverType string,
	expression goast.Expr,
) (methodRelationKey, bool) {
	call, ok := expression.(*goast.CallExpr)
	if !ok || len(call.Args) != 0 {
		return methodRelationKey{}, false
	}
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok {
		return methodRelationKey{}, false
	}
	receiver, ok := selector.X.(*goast.Ident)
	if !ok || receiver.Name != receiverName {
		return methodRelationKey{}, false
	}
	return methodRelationKey{
		packageDir: dir, receiverType: receiverType, method: selector.Sel.Name,
	}, true
}

func formattedSQLRelationCall(
	expression goast.Expr,
	relationLocals map[string]methodRelationKey,
	constants map[string]string,
	imports map[string]string,
) (methodRelationKey, bool) {
	call, ok := expression.(*goast.CallExpr)
	if !ok || len(call.Args) != 2 {
		return methodRelationKey{}, false
	}
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok || selector.Sel.Name != "Sprintf" {
		return methodRelationKey{}, false
	}
	qualifier, ok := selector.X.(*goast.Ident)
	if !ok || imports[qualifier.Name] != "fmt" {
		return methodRelationKey{}, false
	}
	format, resolved := stringArgument(call.Args[0], constants)
	if !resolved || strings.Count(format, "%s") != 1 ||
		!sqlWriteRelationPlaceholderPattern.MatchString(format) {
		return methodRelationKey{}, false
	}
	relation, ok := call.Args[1].(*goast.Ident)
	if !ok {
		return methodRelationKey{}, false
	}
	key, bound := relationLocals[relation.Name]
	return key, bound
}

func appendUniqueMethodRelationKey(
	keys []methodRelationKey,
	key methodRelationKey,
) []methodRelationKey {
	for _, existing := range keys {
		if existing == key {
			return keys
		}
	}
	return append(keys, key)
}

// collectTransactionClosureHandles 把 `session.WithTransaction(ctx, func(txCtx ...))` 的闭包
// 形参识别成事务句柄。Mongo 的事务上下文就是这个闭包参数，签名类型上看不出来。
func collectTransactionClosureHandles(call *goast.CallExpr, handles map[string]struct{}) {
	name := callTargetName(call)
	if !transactionOpenerNames[name] && !transactionScopeCallNames[name] {
		return
	}
	for _, argument := range call.Args {
		literal, ok := argument.(*goast.FuncLit)
		if !ok || literal.Type == nil || literal.Type.Params == nil {
			continue
		}
		for _, field := range literal.Type.Params.List {
			for _, parameterName := range field.Names {
				if parameterName.Name != "_" {
					handles[parameterName.Name] = struct{}{}
				}
			}
		}
	}
}

// collectAccessTargets 抽出函数体内的写入目标、读取目标、是否推进进度，以及「以事务句柄
// 调用了哪些方法」。目标可能是字段、局部句柄或 SQL 关系位，解析统一推迟到 resolve。
func collectAccessTargets(
	body *goast.BlockStmt,
	handles map[string]struct{},
	record *functionRecord,
	constants map[string]string,
) {
	goast.Inspect(body, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		name := callTargetName(call)
		if name != "" {
			arguments := make([]argumentReference, 0, len(call.Args))
			for _, argument := range call.Args {
				arguments = append(
					arguments,
					argumentReferenceForExpression(argument, constants),
				)
			}
			record.calls = append(record.calls, functionCall{
				callee: name, arguments: arguments,
			})
			record.deliveryRead = record.deliveryRead || isDeliveryReadCall(name)
			record.deliveryAdvance = record.deliveryAdvance || isDeliveryAdvanceCall(name)
			record.deliveryHandoff = record.deliveryHandoff || isDeliveryHandoffCall(name)
		}
		if callPassesHandle(call, handles) && name != "" {
			record.handleCallees = append(record.handleCallees, name)
		}
		// 领取型原子操作（`FindOneAndUpdate` 等）同时是读与推进：投递侧的「认领一条」
		// 就是这一个调用，拆成读或写任一侧都会漏判。
		isWrite := writeMethodNames[name] || claimMethodNames[name]
		isRead := readMethodNames[name] || claimMethodNames[name]
		if !isWrite && !isRead {
			return true
		}
		if selector, isSelector := call.Fun.(*goast.SelectorExpr); isSelector {
			switch receiver := selector.X.(type) {
			case *goast.SelectorExpr:
				// `s.outbox.InsertOne(...)`：接收者是结构体字段。
				if isWrite {
					record.writtenFields = append(record.writtenFields, receiver.Sel.Name)
					record.advancesProgres = true
				}
				if isRead {
					record.readFields = append(record.readFields, receiver.Sel.Name)
				}
			case *goast.Ident:
				if isWrite {
					record.writtenLocals = append(record.writtenLocals, receiver.Name)
					record.advancesProgres = true
				}
				if isRead {
					record.readLocals = append(record.readLocals, receiver.Name)
				}
			case *goast.CallExpr:
				if storageHandleBindingCalls[callTargetName(receiver)] {
					if relation, resolved := handleBindingRelation(receiver, constants); resolved {
						if isWrite {
							record.writtenSQL = append(record.writtenSQL, relation)
							record.advancesProgres = true
						}
						if isRead {
							record.readSQL = append(record.readSQL, relation)
						}
					}
				}
			}
		}
		for _, argument := range call.Args {
			statement, resolved := stringArgument(argument, constants)
			if !resolved {
				continue
			}
			for _, relation := range sqlWriteRelations(statement) {
				record.writtenSQL = append(record.writtenSQL, relation)
				record.advancesProgres = true
			}
			for _, relation := range sqlReadRelations(statement) {
				record.readSQL = append(record.readSQL, relation)
			}
		}
		return true
	})
}

// 三类调用必须在同一个 relay/drain 函数中形成闭环。这里匹配的是 AST selector call 的
// canonical operation identity，不扫描原始 token；注释、TODO、错误字符串和同名文件均
// 不可能命中。名称集合覆盖仓内现有 OutboxReader / lease / checkpoint port 形状。
func isDeliveryReadCall(name string) bool {
	return name == "ReadAfter" ||
		(strings.HasPrefix(name, "Read") && strings.Contains(name, "Outbox")) ||
		strings.HasPrefix(name, "ClaimPending") ||
		strings.HasPrefix(name, "LeaseNext")
}

func isDeliveryAdvanceCall(name string) bool {
	return (strings.HasPrefix(name, "Save") && strings.Contains(name, "Checkpoint")) ||
		(strings.HasPrefix(name, "Mark") &&
			(strings.Contains(name, "Published") || strings.Contains(name, "Dispatched"))) ||
		strings.HasPrefix(name, "Acknowledge")
}

func isDeliveryHandoffCall(name string) bool {
	return strings.HasPrefix(name, "Publish") || name == "AppendDurable"
}

func argumentReferenceForExpression(
	expression goast.Expr,
	constants map[string]string,
) argumentReference {
	switch typed := expression.(type) {
	case *goast.Ident:
		if value, ok := constants[typed.Name]; ok && relationNamePattern.MatchString(value) {
			return argumentReference{literal: value}
		}
		return argumentReference{identifier: typed.Name}
	case *goast.SelectorExpr:
		return argumentReference{field: typed.Sel.Name}
	case *goast.BasicLit:
		value, ok := stringArgument(typed, constants)
		if ok && relationNamePattern.MatchString(value) {
			return argumentReference{literal: value}
		}
	}
	return argumentReference{}
}

func callPassesHandle(call *goast.CallExpr, handles map[string]struct{}) bool {
	for _, argument := range call.Args {
		identifier, ok := argument.(*goast.Ident)
		if !ok {
			continue
		}
		if _, isHandle := handles[identifier.Name]; isHandle {
			return true
		}
	}
	return false
}

type propagatedCallFacts struct {
	transactionVars    map[int]map[string]struct{}
	transactional      map[int]bool
	parameterRelations map[int]map[string]map[string]struct{}
}

// propagateCallFacts 只沿同包、已声明函数和精确实参位置传播，且最多四跳。该上界覆盖现仓
// `WithTransaction -> appendOutbox -> appendOutboxEvent -> InsertOne`，同时阻止 context 或
// collection 一旦进入通用 helper 就无界污染全服务。
func (scan *serviceScan) propagateCallFacts() propagatedCallFacts {
	facts := propagatedCallFacts{
		transactionVars:    map[int]map[string]struct{}{},
		transactional:      map[int]bool{},
		parameterRelations: map[int]map[string]map[string]struct{}{},
	}
	recordsByKey := map[functionKey][]int{}
	for index, record := range scan.functions {
		key := functionKey{packageDir: record.packageDir, name: record.name}
		recordsByKey[key] = append(recordsByKey[key], index)
		facts.transactionVars[index] = map[string]struct{}{}
		for _, name := range record.transactionVars {
			facts.transactionVars[index][name] = struct{}{}
		}
		// 保留既有「事务句柄作为实参调用同名方法」的跨包接口事实；它覆盖 application
		// 通过 interface 调用 persistence method 的形状。后续 helper 传播仍只沿同包已声明
		// 调用图进行，避免把同名函数无限扩散到整个服务。
		_, invokedWithTransaction := scan.txInvokedMethods[record.name]
		facts.transactional[index] = record.holdsHandle || invokedWithTransaction
		facts.parameterRelations[index] = map[string]map[string]struct{}{}
	}

	for depth := 0; depth < maxPublicationCallDepth; depth++ {
		changed := false
		for callerIndex, caller := range scan.functions {
			bindings := scan.bindings[caller.packageDir]
			if bindings == nil {
				continue
			}
			locals := bindings.localsByFunction[caller.name]
			for _, call := range caller.calls {
				targets := recordsByKey[functionKey{
					packageDir: caller.packageDir,
					name:       call.callee,
				}]
				for _, targetIndex := range targets {
					target := scan.functions[targetIndex]
					for position, reference := range call.arguments {
						if position >= len(target.parameters) || target.parameters[position] == "" {
							continue
						}
						parameter := target.parameters[position]
						if reference.identifier != "" {
							if _, tainted := facts.transactionVars[callerIndex][reference.identifier]; tainted {
								if addSetValue(facts.transactionVars[targetIndex], parameter) {
									changed = true
								}
								facts.transactional[targetIndex] = true
							}
						}
						relations := resolveArgumentRelations(
							reference,
							bindings,
							locals,
							facts.parameterRelations[callerIndex],
						)
						if len(relations) == 0 {
							continue
						}
						if facts.parameterRelations[targetIndex][parameter] == nil {
							facts.parameterRelations[targetIndex][parameter] = map[string]struct{}{}
						}
						for relation := range relations {
							if addSetValue(
								facts.parameterRelations[targetIndex][parameter], relation,
							) {
								changed = true
							}
						}
					}
				}
			}
		}
		if !changed {
			break
		}
	}
	return facts
}

func addSetValue(values map[string]struct{}, value string) bool {
	if value == "" {
		return false
	}
	if _, exists := values[value]; exists {
		return false
	}
	values[value] = struct{}{}
	return true
}

func resolveArgumentRelations(
	reference argumentReference,
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
) map[string]struct{} {
	result := map[string]struct{}{}
	if reference.literal != "" {
		result[reference.literal] = struct{}{}
	}
	if reference.field != "" {
		for relation := range bindings.fieldRelations[reference.field] {
			result[relation] = struct{}{}
		}
	}
	if reference.identifier != "" {
		if relation, ok := locals[reference.identifier]; ok {
			result[relation] = struct{}{}
		}
		for relation := range parameters[reference.identifier] {
			result[relation] = struct{}{}
		}
	}
	return result
}

// resolve 把推迟的目标解析成关系名，并合成事务性判定。
func (scan *serviceScan) resolve(index *serviceWriteIndex) {
	// 构造形参注入的集合名：按「构造函数名 + 实参位置」补齐，位置匹配保证
	// `NewStore(db, "conversations", "conversations_outbox", "..._sequences")` 里三个名字
	// 各归各的字段，不会互相串味。
	for _, bindings := range scan.bindings {
		for field, params := range bindings.fieldConstructorParams {
			for _, param := range params {
				for relation := range scan.constructorCallArgs[param.constructor][param.index] {
					addFieldRelation(bindings, field, relation)
				}
			}
		}
		for field, params := range bindings.fieldValueConstructorParams {
			for _, param := range params {
				for value := range scan.constructorStringCallArgs[param.constructor][param.index] {
					addFieldValue(bindings, field, value)
				}
			}
		}
	}
	callFacts := scan.propagateCallFacts()
	for _, candidate := range scan.externalCandidates {
		if _, declared := scan.declaredFunctions[candidate.callee]; declared && !candidate.external {
			continue
		}
		index.externalBindings[candidate.relation] = append(
			index.externalBindings[candidate.relation], candidate.file,
		)
	}
	for recordIndex, record := range scan.functions {
		bindings := scan.bindings[record.packageDir]
		if bindings == nil {
			continue
		}
		if record.deliveryRead && record.deliveryAdvance && record.deliveryHandoff {
			if scope := publicationImplementationScope(record.file); scope != "" {
				index.deliveryRelayScopes[scope] = struct{}{}
			}
		}
		transactional := record.holdsHandle || callFacts.transactional[recordIndex]
		site := writeSite{file: record.file, function: record.name}
		locals := bindings.localsByFunction[record.name]
		if transactional {
			if len(record.writtenFields)+len(record.writtenLocals)+len(record.writtenSQL)+
				len(record.dynamicSQLWrites) > 0 {
				index.packagesWritingTransactionally[record.packageDir] = struct{}{}
			}
			dynamicWrites := scan.resolveDynamicSQLWrites(record.dynamicSQLWrites, bindings)
			for _, relation := range record.resolvedWrites(
				bindings, locals, callFacts.parameterRelations[recordIndex], dynamicWrites,
			) {
				index.transactionalWrites[relation] = appendSite(
					index.transactionalWrites[relation], site,
				)
			}
		}
		// 投递实现不要求事务：relay 通常在事务外拉取，再单独提交检查点。
		if record.advancesProgres {
			index.packagesAdvancingProgress[record.packageDir] = struct{}{}
		}
		for _, relation := range record.resolvedReads(
			bindings, locals, callFacts.parameterRelations[recordIndex],
		) {
			index.deliveryReads[relation] = appendReadSite(
				index.deliveryReads[relation],
				readSite{writeSite: site, packageDir: record.packageDir},
			)
		}
	}
}

func (scan *serviceScan) resolveDynamicSQLWrites(
	keys []methodRelationKey,
	bindings *packageBindings,
) []string {
	found := map[string]struct{}{}
	for _, key := range keys {
		for _, resolver := range scan.relationResolvers[key] {
			for value := range bindings.fieldValues[resolver.field] {
				for relation := range resolver.relationsByValue[value] {
					found[relation] = struct{}{}
				}
			}
		}
	}
	relations := make([]string, 0, len(found))
	for relation := range found {
		relations = append(relations, relation)
	}
	sort.Strings(relations)
	return relations
}

func (record functionRecord) resolvedWrites(
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
	dynamic []string,
) []string {
	return resolveTargets(
		record.writtenFields, record.writtenLocals, append(record.writtenSQL, dynamic...),
		bindings, locals, parameters,
	)
}

func (record functionRecord) resolvedReads(
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
) []string {
	return resolveTargets(
		record.readFields, record.readLocals, record.readSQL,
		bindings, locals, parameters,
	)
}

func resolveTargets(
	fields []string,
	localNames []string,
	direct []string,
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
) []string {
	found := map[string]struct{}{}
	for _, field := range fields {
		for relation := range bindings.fieldRelations[field] {
			found[relation] = struct{}{}
		}
	}
	for _, name := range localNames {
		if relation, ok := locals[name]; ok {
			found[relation] = struct{}{}
		}
		for relation := range parameters[name] {
			found[relation] = struct{}{}
		}
	}
	for _, relation := range direct {
		found[relation] = struct{}{}
	}
	relations := make([]string, 0, len(found))
	for relation := range found {
		relations = append(relations, relation)
	}
	sort.Strings(relations)
	return relations
}

func appendReadSite(sites []readSite, site readSite) []readSite {
	for _, existing := range sites {
		if existing == site {
			return sites
		}
	}
	return append(sites, site)
}

func appendSite(sites []writeSite, site writeSite) []writeSite {
	for _, existing := range sites {
		if existing == site {
			return sites
		}
	}
	return append(sites, site)
}

func appendUniqueString(values []string, value string) []string {
	for _, existing := range values {
		if existing == value {
			return values
		}
	}
	return append(values, value)
}

// collectLocalRelationBindings 解析函数体内的局部句柄绑定：`events := db.Collection("x")`。
func collectLocalRelationBindings(
	statement *goast.AssignStmt,
	locals map[string]string,
	constants map[string]string,
) {
	for position, value := range statement.Rhs {
		call, ok := value.(*goast.CallExpr)
		if !ok || !storageHandleBindingCalls[callTargetName(call)] {
			continue
		}
		relation, resolved := handleBindingRelation(call, constants)
		if !resolved || position >= len(statement.Lhs) {
			continue
		}
		if identifier, isIdent := statement.Lhs[position].(*goast.Ident); isIdent {
			locals[identifier.Name] = relation
		}
	}
}

func handleBindingRelation(
	call *goast.CallExpr,
	constants map[string]string,
) (string, bool) {
	for _, argument := range call.Args {
		value, ok := stringArgument(argument, constants)
		if !ok {
			continue
		}
		if relationNamePattern.MatchString(value) {
			return value, true
		}
	}
	return "", false
}

// stringArgument 把实参解析成字符串：字面量直接取，标识符回查包内 const/var。
func stringArgument(expression goast.Expr, constants map[string]string) (string, bool) {
	switch typed := expression.(type) {
	case *goast.BasicLit:
		if typed.Kind != token.STRING {
			return "", false
		}
		return trimStringLiteral(typed.Value), true
	case *goast.Ident:
		value, ok := constants[typed.Name]
		return value, ok
	}
	return "", false
}

// sqlWriteRelations 抽 SQL 写语句关系位的裸标识符。Postgres 不带引号，所以按词边界匹配、
// 不要求引号——`INSERT INTO credential_bindings_outbox(` 这种紧跟左括号的形态也必须命中。
func sqlWriteRelations(statement string) []string {
	return matchRelations(sqlWritePattern, statement)
}

func sqlReadRelations(statement string) []string {
	return matchRelations(sqlReadPattern, statement)
}

func sqlRelations(statement string) []string {
	return append(sqlWriteRelations(statement), sqlReadRelations(statement)...)
}

func matchRelations(pattern *regexp.Regexp, statement string) []string {
	var relations []string
	for _, match := range pattern.FindAllStringSubmatch(statement, -1) {
		relation := strings.Trim(strings.ToLower(match[1]), `"`)
		if !relationNamePattern.MatchString(relation) {
			continue
		}
		// `ON CONFLICT ... DO UPDATE SET col = ...` 的 `SET` 会落在 UPDATE 的关系位上，
		// `DELETE FROM ... USING ...` 同理。SQL 关键字不是关系名。
		if sqlKeywords[relation] {
			continue
		}
		relations = append(relations, relation)
	}
	return relations
}

func isConstructorName(name string) bool {
	return strings.HasPrefix(name, "New") || strings.HasPrefix(name, "Open")
}

func trimStringLiteral(literal string) string {
	return strings.Trim(literal, "`\"'")
}

var (
	// relationNamePattern 是「整体就是一个关系名」的形状：小写标识符 token，允许 schema
	// 前缀与连字符。散文与 SQL 片段不会整体匹配到它。
	relationNamePattern = regexp.MustCompile(`^[a-z][a-z0-9_]*(?:[.$-][a-z0-9_]+)*$`)
	sqlWritePattern     = regexp.MustCompile(
		`(?is)\b(?:insert\s+into|update|delete\s+from|` +
			`create\s+table(?:\s+if\s+not\s+exists)?)\s+("?[a-z][a-z0-9_.$-]*"?)`,
	)
	sqlReadPattern = regexp.MustCompile(
		`(?is)\bfrom\s+("?[a-z][a-z0-9_.$-]*"?)`,
	)
	// Dynamic SQL is accepted only when fmt.Sprintf places its sole `%s` directly in a
	// write-statement relation slot. Other formatting, diagnostics and SELECTs are ignored.
	sqlWriteRelationPlaceholderPattern = regexp.MustCompile(
		`(?is)\b(?:insert\s+into|update|delete\s+from|` +
			`create\s+table(?:\s+if\s+not\s+exists)?)\s+%s(?:\s|\(|"|$)`,
	)
	sqlKeywords = map[string]bool{
		"set": true, "of": true, "only": true, "select": true, "where": true,
		"values": true, "returning": true, "using": true, "as": true, "on": true,
	}
	// storageHandleBindingCalls 是把集合/表名字面量绑定成存储句柄的调用。
	storageHandleBindingCalls = map[string]bool{
		"Collection":     true,
		"Table":          true,
		"GetCollection":  true,
		"WithCollection": true,
	}
	writeMethodNames = map[string]bool{
		"InsertOne":   true,
		"InsertMany":  true,
		"BulkWrite":   true,
		"ReplaceOne":  true,
		"UpdateOne":   true,
		"UpdateMany":  true,
		"Exec":        true,
		"ExecContext": true,
	}
	// transactionScopeCallNames 是「把事务范围交给闭包」的调用：闭包形参就是事务上下文。
	// Mongo 与领域事务端口都走这个形状（`s.transactions.RunInTransaction(ctx, func(txCtx
	// context.Context) error {...})`），签名类型上完全看不出事务性。
	transactionScopeCallNames = map[string]bool{
		"WithTransaction":      true,
		"UseSession":           true,
		"RunInTransaction":     true,
		"RunTransaction":       true,
		"InTransaction":        true,
		"ExecuteInTransaction": true,
		"WithTx":               true,
		"RunInTx":              true,
	}
	claimMethodNames = map[string]bool{
		"FindOneAndUpdate":  true,
		"FindOneAndDelete":  true,
		"FindOneAndReplace": true,
	}
	readMethodNames = map[string]bool{
		"Find":      true,
		"FindOne":   true,
		"Query":     true,
		"QueryRow":  true,
		"Aggregate": true,
	}
)
