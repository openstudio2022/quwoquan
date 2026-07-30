package recommendation

import (
	"math"
	"testing"
)

const affinityEpsilon = 1e-9

// L0（仅曝光）的深度系数是 0，任何标签都拿不到权重，无法用来观察传播。
// 这里统一用 L3，并把期望值表达为 base 的倍数，避免把深度系数写死进断言。
const affinityTestDepth = 3

func affinityBaseWeight() float64 { return DepthLevelCoefficient[affinityTestDepth] }

func assertWeight(t *testing.T, got map[string]float64, tagRef string, want float64) {
	t.Helper()
	actual, ok := got[tagRef]
	if !ok {
		t.Fatalf("expected %q to carry affinity weight, got keys %v", tagRef, keysOf(got))
	}
	if math.Abs(actual-want) > affinityEpsilon {
		t.Fatalf("weight for %q = %v, want %v", tagRef, actual, want)
	}
}

func keysOf(m map[string]float64) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}

// 无 bridge 时兴趣轴的勾选对主题轴内容加权为零。
func TestClassifyAndWeightTagsWithBridge_NilResolverKeepsAxesIsolated(t *testing.T) {
	base := affinityBaseWeight()

	delta := ClassifyAndWeightTagsWithBridge(
		[]string{"Audience/用户/兴趣偏好/旅行摄影/摄影"}, affinityTestDepth, "", nil)

	if _, ok := delta.Topic["Topic/摄影"]; ok {
		t.Fatalf("Topic/摄影 must stay unweighted without a concept bridge")
	}
	assertWeight(t, delta.Audience, "Audience/用户/兴趣偏好/旅行摄影/摄影", base)
}

func TestClassifyAndWeightTagsWithBridge_CrossesAxisBoundary(t *testing.T) {
	base := affinityBaseWeight()
	resolver := StaticSameAsResolver{
		"Audience/用户/兴趣偏好/旅行摄影/摄影": {"Topic/摄影"},
	}

	delta := ClassifyAndWeightTagsWithBridge(
		[]string{"Audience/用户/兴趣偏好/旅行摄影/摄影"}, affinityTestDepth, "", resolver)

	// 直接观测到的标签保持满权重，桥接过去的概念按 SameAsBridgeWeight 折减。
	assertWeight(t, delta.Audience, "Audience/用户/兴趣偏好/旅行摄影/摄影", base)
	assertWeight(t, delta.Topic, "Topic/摄影", base*SameAsBridgeWeight)
}

// 桥接后的标签必须继续沿它自己的路径前缀上溯，否则「自驾」只能命中最深那一层，
// 命中不了「Topic/旅行」这类更泛的兴趣。
func TestClassifyAndWeightTagsWithBridge_BridgedTagPropagatesItsOwnHierarchy(t *testing.T) {
	base := affinityBaseWeight()
	resolver := StaticSameAsResolver{
		"Audience/用户/兴趣偏好/旅行摄影/自驾": {"Topic/旅行/出行方式/自驾"},
	}

	delta := ClassifyAndWeightTagsWithBridge(
		[]string{"Audience/用户/兴趣偏好/旅行摄影/自驾"}, affinityTestDepth, "", resolver)

	bridged := base * SameAsBridgeWeight
	assertWeight(t, delta.Topic, "Topic/旅行/出行方式/自驾", bridged)
	assertWeight(t, delta.Topic, "Topic/旅行/出行方式", bridged*0.5)
	assertWeight(t, delta.Topic, "Topic/旅行", bridged*0.25)
}

// 桥不得传递：桥的桥是另一个概念，链式跟随会让权重在整张图上漏出去。
func TestClassifyAndWeightTagsWithBridge_DoesNotFollowBridgesTransitively(t *testing.T) {
	base := affinityBaseWeight()
	resolver := StaticSameAsResolver{
		"Audience/用户/兴趣偏好/生活/美食": {"Topic/美食餐饮"},
		"Topic/美食餐饮":             {"Audience/用户/兴趣偏好/生活/美食", "Topic/摄影/美食摄影"},
	}

	delta := ClassifyAndWeightTagsWithBridge(
		[]string{"Audience/用户/兴趣偏好/生活/美食"}, affinityTestDepth, "", resolver)

	assertWeight(t, delta.Topic, "Topic/美食餐饮", base*SameAsBridgeWeight)
	if _, ok := delta.Topic["Topic/摄影/美食摄影"]; ok {
		t.Fatalf("bridge must not be followed transitively")
	}
}

// 双向桥不得让权重在两条轴之间自我放大：观测一次就只应产生一次桥接增量。
func TestClassifyAndWeightTagsWithBridge_BidirectionalBridgeDoesNotDoubleCount(t *testing.T) {
	base := affinityBaseWeight()
	resolver := StaticSameAsResolver{
		"Topic/摄影": {"Audience/用户/兴趣偏好/旅行摄影/摄影"},
		"Audience/用户/兴趣偏好/旅行摄影/摄影": {"Topic/摄影"},
	}

	delta := ClassifyAndWeightTagsWithBridge(
		[]string{"Topic/摄影"}, affinityTestDepth, "", resolver)

	assertWeight(t, delta.Topic, "Topic/摄影", base)
	assertWeight(t, delta.Audience, "Audience/用户/兴趣偏好/旅行摄影/摄影",
		base*SameAsBridgeWeight)
}

// 同 group 跨 dimension 的桥同样要生效：路径前缀传播跨不过 dimension 边界，
// 「同行人/家庭带娃」与「旅行主题/亲子游」除了靠桥没有其他联通方式。
func TestClassifyAndWeightTagsWithBridge_SameGroupCrossDimension(t *testing.T) {
	base := affinityBaseWeight()
	resolver := StaticSameAsResolver{
		"Topic/旅行/同行人/家庭带娃": {"Topic/旅行/旅行主题/亲子游"},
	}

	delta := ClassifyAndWeightTagsWithBridge(
		[]string{"Topic/旅行/同行人/家庭带娃"}, affinityTestDepth, "", resolver)

	assertWeight(t, delta.Topic, "Topic/旅行/同行人/家庭带娃", base)
	assertWeight(t, delta.Topic, "Topic/旅行/旅行主题/亲子游", base*SameAsBridgeWeight)
	// Topic/旅行 同时是两侧的祖先，两条上溯链的增量应当叠加。
	assertWeight(t, delta.Topic, "Topic/旅行",
		base*0.25+base*SameAsBridgeWeight*0.25)
}

// 桥接权重必须严格落在「自身」与「父节点泛化」之间：同一概念比父节点更可信，
// 但永远不该盖过直接观测到的标签。
func TestSameAsBridgeWeight_SitsBetweenSelfAndParentDecay(t *testing.T) {
	if SameAsBridgeWeight >= 1.0 {
		t.Fatalf("bridged concept must never outweigh a directly observed tag")
	}
	if SameAsBridgeWeight <= HierarchicalDecayFactors[0] {
		t.Fatalf("a same-concept bridge must outweigh parent generalization %v",
			HierarchicalDecayFactors[0])
	}
}

func TestClassifyAndWeightTagsWithBridge_IgnoresEmptyAndSelfReferences(t *testing.T) {
	base := affinityBaseWeight()
	resolver := StaticSameAsResolver{
		"Topic/摄影": {"", "Topic/摄影"},
	}

	delta := ClassifyAndWeightTagsWithBridge(
		[]string{"Topic/摄影"}, affinityTestDepth, "", resolver)

	assertWeight(t, delta.Topic, "Topic/摄影", base)
	if len(delta.Topic) != 1 {
		t.Fatalf("empty and self references must not create entries, got %v",
			keysOf(delta.Topic))
	}
}
