package load

import (
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"
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
	document, err := storagecontract.LoadOptional(path)
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
// 回答不了「有人往这张表里写」。只有集合句柄、没有任何写调用的关系会被包级 join
// 误判为有发布实现。
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
