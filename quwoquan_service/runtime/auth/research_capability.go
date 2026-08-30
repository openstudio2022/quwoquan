package auth

// RoleResearch 是研究态身份的 principal role（DEC-032）。user-service 登录与
// refresh 的 access token 签发单点在账号命中 research allowlist 时向 token
// roles 附加该值；operation guard 据此收敛能力面，判定与请求方是否自带任何
// 请求头无关，对 public 与 runtime 两种 operation 边界一致生效。
const RoleResearch = "research"

// ResearchAttestationHeader 只用于 readback 链路把请求精确绑定到已签发的
// research session（DEC-032）：content-service readback handler 与 isolation
// probe 消费它。它不再作为能力面判定依据；缺失该头不使任何请求脱离 role 收敛。
const ResearchAttestationHeader = "X-Research-Identity-Attestation"

// researchNamedOperationAllowlist 是 research 能力面的具名放行集。这些操作
// 维持 CommercialStatus=blocked 或属 command kind，不落入「ready 只读投影」
// 通则，必须显式列名；本表与通则一起构成 DEC-032 的研究能力闭集，归本包
// 单一持有。
var researchNamedOperationAllowlist = map[string]struct{}{
	"user.account_session.IssueWhitelistedResearchSession":          {},
	"user.account_session.GetResearchSessionAttestation":            {},
	"content.post.GetResearchReleaseReadback":                       {},
	"content.original_access_quota.ReserveOriginalImageAccessGrant": {},
	"content.original_access_quota.GetOriginalImageAccessAudit":     {},
}

func researchRoleAllowsNamedOperation(
	principal Principal,
	hasPrincipal bool,
	descriptor OperationSecurityDescriptor,
) bool {
	if !hasPrincipal || !containsGrant(principal.Roles, RoleResearch) {
		return false
	}
	_, allowed := researchNamedOperationAllowlist[descriptor.CanonicalOperationID]
	return allowed
}

// researchRoleDeniesOperation 收敛 research principal 的能力面（DEC-032）：
// 放行 ready 只读投影（feed、detail、对象主页、公开 profile 及同类 query）、
// 会话生命周期（session kind：登录、refresh、登出）与具名 research 操作；
// 写操作、站外分享、导出与其余操作一律 fail closed。ops/管理类 query 的
// role/scope 门槛仍由后续 principal 授权判定承担，本判定不重复表达。
func researchRoleDeniesOperation(
	principal Principal,
	hasPrincipal bool,
	descriptor OperationSecurityDescriptor,
) bool {
	if !hasPrincipal || !containsGrant(principal.Roles, RoleResearch) {
		return false
	}
	if researchRoleAllowsNamedOperation(principal, hasPrincipal, descriptor) {
		return false
	}
	switch descriptor.OperationKind {
	case "query":
		return descriptor.CommercialStatus != "ready"
	case "session":
		return false
	default:
		return true
	}
}
