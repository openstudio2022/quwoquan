// Code generated from runtime_observability.yaml and object-local privacy.yaml. DO NOT EDIT.

package runtimeobservability

const ObservabilitySchema = "observability.slim"

type CatalogSignalMetadata struct {
	Owner              string
	Producers          []string
	LogKind            string
	DefaultSeverity    string
	Environments       []string
	AttributeAllowlist []string
	CorrelationKeys    []string
	Backend            string
	RetentionDays      int
	Sampling           string
	Alert              string
	Runbook            string
	PIIClassification  string
}

var CatalogLogKinds = map[string]struct{}{
	"deploy":    {},
	"runtime":   {},
	"access":    {},
	"event":     {},
	"exception": {},
	"audit":     {},
}

var CatalogSeverityLevels = map[string]struct{}{
	"DEBUG": {},
	"INFO":  {},
	"WARN":  {},
	"ERROR": {},
}

var CatalogSignals = map[string]struct{}{
	"app.access.http":           {},
	"app.exception.flutter":     {},
	"app.exception.platform":    {},
	"app.performance.anr":       {},
	"app.performance.frame":     {},
	"app.performance.media":     {},
	"app.runtime.lifecycle":     {},
	"data.exception.stage":      {},
	"data.runtime.stage":        {},
	"ops.audit.control":         {},
	"ops.deploy.stackctl":       {},
	"ops.exception.runtime":     {},
	"ops.runtime.process":       {},
	"portal.exception.browser":  {},
	"service.access.http":       {},
	"service.audit.control":     {},
	"service.exception.runtime": {},
	"service.runtime.process":   {},
}

var CatalogForbiddenFields = map[string]struct{}{
	"schemaVersion":   {},
	"eventVersion":    {},
	"contractVersion": {},
	"protocolVersion": {},
	"releaseVersion":  {},
	"releaseId":       {},
	"dataReleaseId":   {},
}

var CatalogFailureCodes = map[string]string{
	"app_native_previous_crash": "APP.RUNTIME.native_previous_crash",
	"app_uncaught_flutter":      "APP.RUNTIME.uncaught_exception",
	"app_uncaught_platform":     "APP.RUNTIME.uncaught_platform_exception",
	"data_stage_failure":        "DATA.RUNTIME.stage_failed",
	"portal_uncaught_browser":   "PORTAL.RUNTIME.uncaught_browser_exception",
	"service_log_encoding":      "SERVICE.RUNTIME.log_encoding_failed",
}

var CatalogForbiddenAttributeKeys = map[string]struct{}{
	"authorization":   {},
	"password":        {},
	"passwd":          {},
	"secret":          {},
	"token":           {},
	"apiKey":          {},
	"credential":      {},
	"cookie":          {},
	"phone":           {},
	"email":           {},
	"ssid":            {},
	"ip":              {},
	"preciseLocation": {},
	"sessionId":       {},
}

var CatalogHighCardinalityMetricKeys = map[string]struct{}{
	"userId":    {},
	"sessionId": {},
	"requestId": {},
	"traceId":   {},
	"rawPath":   {},
}

func init() {
	registerCatalogFieldPrivacyPolicies([]CatalogFieldPrivacyPolicy{
		{ObjectID: "content.post", Field: "_id", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: []string{"never_expose"}},
		{ObjectID: "content.post", Field: "articleAssetManifest", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "articleFontPreset", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "articleMarkdown", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "articleMarkdownDigest", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "articleRenderProfile", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "articleTemplate", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "assistantUsePolicy", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "authorAvatarUrlSnapshot", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "authorDisplayNameSnapshot", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "authorId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: []string{"all"}},
		{ObjectID: "content.post", Field: "authorQualitySignals", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "body", Classification: "PUBLIC", Action: "truncate", MaskStrategy: "", TruncateChars: 200, Explicit: true, Visibility: nil},
		{ObjectID: "content.post", Field: "captureDisclosure", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "captureFeatureRefs", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "commentCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "contentDigest", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "contentIdentity", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "contentType", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "contentVertical", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "coverFrameTimeMs", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "coverStrategy", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "coverUrl", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "createdAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "creatorArchetype", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "creatorDisclosure", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "creatorProfileId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "creatorProfileVersion", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "deletedAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "deviceInfo", Classification: "PII", Action: "mask", MaskStrategy: "strip_detail", TruncateChars: 0, Explicit: true, Visibility: nil},
		{ObjectID: "content.post", Field: "durationMs", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "embedding", Classification: "SENSITIVE", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: true, Visibility: []string{"never_expose"}},
		{ObjectID: "content.post", Field: "entityMentions", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "entityRefs", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "experienceClaimMode", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "gatheringRef", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "geoTagRef", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "height", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "helperReadSummary", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "illustrationAssetId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "lastActiveAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "likeCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "localDraftId", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "location", Classification: "PII", Action: "mask", MaskStrategy: "city_level_only", TruncateChars: 0, Explicit: true, Visibility: []string{"app", "content-service-internal"}},
		{ObjectID: "content.post", Field: "locationName", Classification: "PII", Action: "mask", MaskStrategy: "strip_detail", TruncateChars: 0, Explicit: true, Visibility: nil},
		{ObjectID: "content.post", Field: "markdownDialect", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "mediaAssetIds", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "mediaItems", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "mediaUrls", Classification: "PUBLIC", Action: "count_only", MaskStrategy: "", TruncateChars: 0, Explicit: true, Visibility: nil},
		{ObjectID: "content.post", Field: "moderationStatus", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: []string{"first_party_service_internal", "platform-ops"}},
		{ObjectID: "content.post", Field: "personaContextVersion", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "pinnedCommentId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "primaryHomepageId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "primaryHomepageSnapshot", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "primaryHomepageType", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "publishIntentId", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "publishLocation", Classification: "PII", Action: "mask", MaskStrategy: "city_level_only", TruncateChars: 0, Explicit: true, Visibility: nil},
		{ObjectID: "content.post", Field: "publishedAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "semanticMentions", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "shareCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "sourceAttribution", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "sourcePostId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "sourceTaskId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "sourceType", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "status", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "summary", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "tagRefs", Classification: "PUBLIC", Action: "allow", MaskStrategy: "", TruncateChars: 0, Explicit: true, Visibility: nil},
		{ObjectID: "content.post", Field: "thumbnailUrl", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "title", Classification: "PUBLIC", Action: "truncate", MaskStrategy: "", TruncateChars: 100, Explicit: true, Visibility: nil},
		{ObjectID: "content.post", Field: "updatedAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "version", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "videoUrl", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "viewCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "visibility", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "visitedAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "content.post", Field: "width", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "accountState", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "anonymousRetentionPolicy", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "authEpoch", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "avatarAssetId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "avatarUrl", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "avatarVersion", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "backgroundAssetId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "backgroundUrl", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "bio", Classification: "PUBLIC", Action: "drop_if_gt_100chars", MaskStrategy: "", TruncateChars: 0, Explicit: true, Visibility: nil},
		{ObjectID: "user.user_account", Field: "birthDate", Classification: "PII", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: true, Visibility: []string{"self", "user-service-internal"}},
		{ObjectID: "user.user_account", Field: "circleCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "createdAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "followerCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "followingCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "gender", Classification: "PII", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: []string{"platform-ops", "self"}},
		{ObjectID: "user.user_account", Field: "identityOrigin", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "identityTags", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "interestTags", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "likeCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "logicalShard", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "nickname", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "nicknameCustomized", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "ownerDisplayName", Classification: "PII", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "personaCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "phone", Classification: "PII", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: true, Visibility: []string{"user-service-internal"}},
		{ObjectID: "user.user_account", Field: "postCount", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "profileVersion", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "region", Classification: "PII", Action: "mask", MaskStrategy: "city_level_only", TruncateChars: 0, Explicit: true, Visibility: nil},
		{ObjectID: "user.user_account", Field: "regionTagRef", Classification: "PII", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "suspendedAt", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "suspensionCaseRef", Classification: "INTERNAL", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "updatedAt", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
		{ObjectID: "user.user_account", Field: "userId", Classification: "PUBLIC", Action: "drop", MaskStrategy: "", TruncateChars: 0, Explicit: false, Visibility: nil},
	})
}

const CatalogMaxBatchItems = 50

const CatalogMaxCanonicalBodyBytes = 131072

const CatalogMaxMessageBytes = 2048

const CatalogMaxAttributes = 24

const CatalogMaxAttributesBytes = 4096

const CatalogMaxAttributeKeyLength = 64

const CatalogMaxAttributeValueLength = 512

const CatalogRawRetentionDays = 3

const CatalogAppBufferCapacity = 200

const CatalogAppDeadLetterCapacity = 100

const CatalogServiceSpoolMaxBatches = 2000

const CatalogServiceDLQMaxBatches = 500

const CatalogDeliveryTTLHours = 72

const CatalogRetryBaseSeconds = 5

const CatalogRetryMaxSeconds = 300

const CatalogRetryMaxExponent = 6

const CatalogRetryJitterPercent = 25

var CatalogEnvelopeRequiredFields = []string{"schema", "occurredAt", "observedAt", "logKind", "severity", "signal", "message", "resource"}

var CatalogEnvelopeOptionalFields = []string{"recordId", "correlation", "step", "event", "result", "method", "route", "status", "durationMs", "action", "target", "errorCode", "fingerprint", "attributes"}

var CatalogResourceRequiredFields = []string{"sourceType", "service"}

var CatalogResourceOptionalFields = []string{"environment", "component", "appVersion", "service.version"}

var CatalogCorrelationOptionalFields = []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"}

var CatalogFieldOrder = map[string][]string{
	"deploy":    {"step", "result"},
	"runtime":   {"event", "result"},
	"access":    {"method", "route", "status", "durationMs"},
	"event":     {"event", "result"},
	"exception": {"errorCode"},
	"audit":     {"action", "target", "result"},
}

var CatalogRequiredFields = map[string]map[string]struct{}{
	"deploy":    {"step": {}, "result": {}},
	"runtime":   {"event": {}, "result": {}},
	"access":    {"method": {}, "route": {}, "status": {}, "durationMs": {}},
	"event":     {"event": {}, "result": {}},
	"exception": {"errorCode": {}},
	"audit":     {"action": {}, "target": {}, "result": {}},
}

var CatalogSignalLogKinds = map[string]string{
	"app.access.http":           "access",
	"app.exception.flutter":     "exception",
	"app.exception.platform":    "exception",
	"app.performance.anr":       "event",
	"app.performance.frame":     "event",
	"app.performance.media":     "event",
	"app.runtime.lifecycle":     "runtime",
	"data.exception.stage":      "exception",
	"data.runtime.stage":        "runtime",
	"ops.audit.control":         "audit",
	"ops.deploy.stackctl":       "deploy",
	"ops.exception.runtime":     "exception",
	"ops.runtime.process":       "runtime",
	"portal.exception.browser":  "exception",
	"service.access.http":       "access",
	"service.audit.control":     "audit",
	"service.exception.runtime": "exception",
	"service.runtime.process":   "runtime",
}

var CatalogSignalDefaultSeverities = map[string]string{
	"app.access.http":           "INFO",
	"app.exception.flutter":     "ERROR",
	"app.exception.platform":    "ERROR",
	"app.performance.anr":       "ERROR",
	"app.performance.frame":     "WARN",
	"app.performance.media":     "WARN",
	"app.runtime.lifecycle":     "INFO",
	"data.exception.stage":      "ERROR",
	"data.runtime.stage":        "INFO",
	"ops.audit.control":         "INFO",
	"ops.deploy.stackctl":       "INFO",
	"ops.exception.runtime":     "ERROR",
	"ops.runtime.process":       "INFO",
	"portal.exception.browser":  "ERROR",
	"service.access.http":       "INFO",
	"service.audit.control":     "INFO",
	"service.exception.runtime": "ERROR",
	"service.runtime.process":   "INFO",
}

var CatalogSignalRegistry = map[string]CatalogSignalMetadata{
	"app.access.http": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "access",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.exception.flutter": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.exception.platform": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart", "android", "ios"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.performance.anr": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "event",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "stallMs", "anrThresholdMs", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.performance.frame": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "event",
		DefaultSeverity:    "WARN",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "worstBuildFrameMs", "worstRasterFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.performance.media": {
		Owner:              "content-consumption",
		Producers:          []string{"dart", "android", "ios"},
		LogKind:            "event",
		DefaultSeverity:    "WARN",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.runtime.lifecycle": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"data.exception.stage": {
		Owner:              "runtime-data-engineering",
		Producers:          []string{"python"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"data.runtime.stage": {
		Owner:              "runtime-data-engineering",
		Producers:          []string{"python"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.audit.control": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "audit",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.deploy.stackctl": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "deploy",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.exception.runtime": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.runtime.process": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"portal.exception.browser": {
		Owner:              "product-ops-growth",
		Producers:          []string{"typescript"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.access.http": {
		Owner:              "system-architecture-and-engineering-guide",
		Producers:          []string{"go"},
		LogKind:            "access",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.audit.control": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"go"},
		LogKind:            "audit",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.exception.runtime": {
		Owner:              "system-architecture-and-engineering-guide",
		Producers:          []string{"go"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.runtime.process": {
		Owner:              "system-architecture-and-engineering-guide",
		Producers:          []string{"go"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
}
