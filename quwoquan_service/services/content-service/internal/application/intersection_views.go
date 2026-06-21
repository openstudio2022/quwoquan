package application

import "strings"

// IntersectionReasonView 是交集理由的服务端视图，与 recommendation/rec_model
// projections/intersection_reason.yaml 字段对齐（端只读、不本地拼装）。
type IntersectionReasonView struct {
	IntersectionID         string                               `json:"intersectionId"`
	IntersectionClass      string                               `json:"intersectionClass"` // fact | affinity
	Kind                   string                               `json:"kind"`              // §23 一等字段：交集 kind（registry.kinds.kind）；端查 IntersectionKindMetadata
	Vertical               string                               `json:"vertical"`          // §23.4 垂类正交标注（缺省 general）
	Dimension              string                               `json:"dimension"`
	DisplayName            string                               `json:"displayName"`
	AvatarURL              string                               `json:"avatarUrl"`
	PrimaryText            string                               `json:"primaryText"`   // 主交集结论句（蓝色，云侧产出，端只读直出）
	SecondaryText          string                               `json:"secondaryText"` // 副交集辅助说明（灰色；缺省端不展示）
	WeightTier             string                               `json:"weightTier"`    // light | heavy（内容卡交集轻重等级，云侧离散产出）
	ObjectKind             string                               `json:"objectKind"`    // person | circle | school | place | enterprise
	Strength               float64                              `json:"strength"`
	ConfidenceLabel        string                               `json:"confidenceLabel"`
	ModelReasonBucket      string                               `json:"modelReasonBucket"`
	RelationKind           string                               `json:"relationKind"`
	RelationObjectID       string                               `json:"relationObjectId"`
	ActionType             string                               `json:"actionType"`
	ActionTargetID         string                               `json:"actionTargetId"`
	Source                 string                               `json:"source"`
	TagRefs                []string                             `json:"tagRefs"`
	FreshAt                string                               `json:"freshAt"`
	ExpiresAt              string                               `json:"expiresAt"`
	IntersectionPoints     []IntersectionPointView              `json:"intersectionPoints"`
	PointSummarySnapshotID string                               `json:"pointSummarySnapshotId"`
	FactPointCount         int                                  `json:"factPointCount"`
	RecommendedPointCount  int                                  `json:"recommendedPointCount"`
	TotalPointCount        int                                  `json:"totalPointCount"`
	DimensionPointSummary  []IntersectionDimensionTallyView     `json:"dimensionPointSummary"`
	PointClassLabel        string                               `json:"pointClassLabel"`
	ConnectionSummary      string                               `json:"connectionSummary"`
	LastRecommendedAt      string                               `json:"lastRecommendedAt"`
	SeenAt                 string                               `json:"seenAt"`
	RankState              string                               `json:"rankState"`
	PrimarySpans           []IntersectionTextSpanView           `json:"primarySpans"`
	SampleVisuals          []IntersectionVisualView             `json:"sampleVisuals"`
	RepresentativeActor    *IntersectionRepresentativeActorView `json:"representativeActor,omitempty"`
	ActionHints            []IntersectionActionHintView         `json:"actionHints"`
	TimeBucket             string                               `json:"timeBucket"`
	DedupeKey              string                               `json:"dedupeKey"`
	AnchorUserWeight       float64                              `json:"anchorUserWeight"`
	MutualCount            int                                  `json:"mutualCount"`
	// 架构基线 v2（§21，对齐 recommendation/rec_model/projections/intersection_reason.yaml）：
	// 边生命周期 / Graph 边权 / 类型图标 / 尾部对象视觉。
	// lifecycleState/edgeWeight/previousStrength/strengthDelta 由异步投影真算填充（读路径零计算消费）；
	// iconKey/objectVisual 由 Explain 管线确定性产出（缺省端有回退）。
	LifecycleState   string                  `json:"lifecycleState"`
	PreviousStrength float64                 `json:"previousStrength"`
	StrengthDelta    float64                 `json:"strengthDelta"`
	EdgeWeight       float64                 `json:"edgeWeight"`
	IconKey          string                  `json:"iconKey"`
	ObjectVisual     *IntersectionVisualView `json:"objectVisual,omitempty"`
}

// IntersectionRepresentativeActorView 是人数句的代表人锚点，必须来自同一证据快照。
type IntersectionRepresentativeActorView struct {
	ActorID         string                  `json:"actorId"`
	DisplayName     string                  `json:"displayName"`
	AvatarURL       string                  `json:"avatarUrl"`
	RelationLabel   string                  `json:"relationLabel"`
	PrivacyState    string                  `json:"privacyState"`
	Target          *IntersectionTargetView `json:"target,omitempty"`
	EvidenceRank    int                     `json:"evidenceRank"`
	SnapshotVersion string                  `json:"snapshotVersion"`
}

// IntersectionActionHintView 是交集/影响力的下一步行动建议。
type IntersectionActionHintView struct {
	ActionKey string                  `json:"actionKey"`
	Label     string                  `json:"label"`
	Target    *IntersectionTargetView `json:"target,omitempty"`
	IsPrimary bool                    `json:"isPrimary"`
	Priority  int                     `json:"priority"`
}

// IntersectionPointView 是用户可见交集点列表；摘要数字只能由同一批点派生。
type IntersectionPointView struct {
	PointID          string                   `json:"pointId"`
	PointClass       string                   `json:"pointClass"` // fact | recommended
	Dimension        string                   `json:"dimension"`
	Label            string                   `json:"label"`
	DisplayText      string                   `json:"displayText"`
	SourceRef        string                   `json:"sourceRef"`
	Visibility       string                   `json:"visibility"`
	Count            int                      `json:"count"`            // 证据组聚合条数（如「共同好友 4」中的 4）
	SampleText       string                   `json:"sampleText"`       // 实例化样本（某好友名/地点名/内容标题）
	SampleAvatarURLs []string                 `json:"sampleAvatarUrls"` // 头像簇（≤3）
	SampleVisuals    []IntersectionVisualView `json:"sampleVisuals"`    // 结构化样本视觉，取代裸头像 URL
}

// IntersectionTargetView 是交集富文本片段 / 视觉样本的可点击目标。
type IntersectionTargetView struct {
	ObjectID   string `json:"objectId"`
	ObjectKind string `json:"objectKind"`
	RouteID    string `json:"routeId"`
}

// IntersectionTextSpanView 是 primaryText 的结构化富文本切分。
type IntersectionTextSpanView struct {
	Text   string                  `json:"text"`
	Role   string                  `json:"role"`
	Target *IntersectionTargetView `json:"target,omitempty"`
}

// IntersectionVisualView 是交集样本视觉标识。
type IntersectionVisualView struct {
	AssetKind   string                  `json:"assetKind"`
	ImageURL    string                  `json:"imageUrl"`
	DisplayName string                  `json:"displayName"`
	Target      *IntersectionTargetView `json:"target,omitempty"`
}

func (v IntersectionReasonView) coolKey() string {
	if strings.TrimSpace(v.ActionTargetID) != "" {
		return v.ActionTargetID
	}
	return v.RelationObjectID
}

// IntersectionDimensionTallyView 单维度计数（与 intersection_dimension_tally.yaml 对齐）。
type IntersectionDimensionTallyView struct {
	Dimension    string `json:"dimension"`
	Label        string `json:"label"`
	Count        int    `json:"count"`
	NewCount     int    `json:"newCount"`
	BriefText    string `json:"briefText"`    // 云侧实例化动态简报句（缺省端回落 label+newCount）
	SubtitleText string `json:"subtitleText"` // 动态简报证据摘要（具名样本，缺省端不展示）
}

// IntersectionInboxSummaryView 我的交集聚合摘要（与 intersection_inbox_summary.yaml 对齐）。
type IntersectionInboxSummaryView struct {
	TotalCount    int                              `json:"totalCount"`
	TotalNewCount int                              `json:"totalNewCount"`
	Dimensions    []IntersectionDimensionTallyView `json:"dimensions"`
	GeneratedAt   string                           `json:"generatedAt"`
}
