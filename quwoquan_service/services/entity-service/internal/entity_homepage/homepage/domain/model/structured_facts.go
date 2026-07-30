package model

// StructuredFacts 是实体客观事实的机器可读投影。
//
// keyFacts 是四个字段拼出来的 Markdown，端侧只能整段渲染，筛选、交集与推荐都
// 消费不了。本类型的每个字段都是单值可核验事实，可以直接进筛选和「同季节窗口
// 到访」这类交集。
//
// 信源政策按用途分轨：正文底稿仍锁在三百科闭集，这些字段额外允许官网与政府/文旅
// 门户，因为营业时间、票价、时长、海拔与官网由官方第一手发布，百科在这些字段上
// 最不及时。放开的代价是逐字段留证，所以 FactSources 是准入条件而不是附属说明：
// Sanitize 会丢掉任何没有对应证据的字段，宁可缺字段也不展示无来源的事实。

import (
	"net/url"
	"slices"
	"sort"
	"strings"
	"time"
)

// StructuredFactField 对齐 _shared/types.yaml 的 HomepageStructuredFactField。
type StructuredFactField string

const (
	FactFieldOpeningHours               StructuredFactField = "openingHours"
	FactFieldTicketPriceRange           StructuredFactField = "ticketPriceRange"
	FactFieldRecommendedDurationMinutes StructuredFactField = "recommendedDurationMinutes"
	FactFieldBestSeasonTagRefs          StructuredFactField = "bestSeasonTagRefs"
	FactFieldAltitudeMeters             StructuredFactField = "altitudeMeters"
	FactFieldOfficialWebsite            StructuredFactField = "officialWebsite"
)

// StructuredFactSourceClass 对齐 HomepageStructuredFactSourceClass，与
// content_source_registry 的 structuredFactsPolicy.allowedSourceClasses 同集。
type StructuredFactSourceClass string

const (
	FactSourceEncyclopedia      StructuredFactSourceClass = "encyclopedia"
	FactSourceOfficialSite      StructuredFactSourceClass = "official_site"
	FactSourceGovernmentTourism StructuredFactSourceClass = "government_tourism"
)

// MinuteOfDayUpperBound 允许跨零点场次超过 1440，例如夜场 22:00-次日 02:00
// 记为 1320-1560。上限取两天，超过即为数据错误。
const MinuteOfDayUpperBound = 2880

type OpeningHoursEntry struct {
	AppliesFrom      string `json:"appliesFrom,omitempty" bson:"appliesFrom,omitempty"`
	AppliesTo        string `json:"appliesTo,omitempty" bson:"appliesTo,omitempty"`
	Weekdays         []int  `json:"weekdays,omitempty" bson:"weekdays,omitempty"`
	OpenMinuteOfDay  int    `json:"openMinuteOfDay" bson:"openMinuteOfDay"`
	CloseMinuteOfDay int    `json:"closeMinuteOfDay" bson:"closeMinuteOfDay"`
	Closed           bool   `json:"closed" bson:"closed"`
}

type TicketPriceRange struct {
	Currency       string `json:"currency" bson:"currency"`
	MinAmountCents int    `json:"minAmountCents" bson:"minAmountCents"`
	MaxAmountCents int    `json:"maxAmountCents" bson:"maxAmountCents"`
	Free           bool   `json:"free" bson:"free"`
}

type DurationRange struct {
	MinMinutes int `json:"minMinutes" bson:"minMinutes"`
	MaxMinutes int `json:"maxMinutes" bson:"maxMinutes"`
}

type FactSource struct {
	Field                  StructuredFactField       `json:"field" bson:"field"`
	SourceID               string                    `json:"sourceId" bson:"sourceId"`
	SourceClass            StructuredFactSourceClass `json:"sourceClass" bson:"sourceClass"`
	SourceURL              string                    `json:"sourceUrl" bson:"sourceUrl"`
	ObservedAt             time.Time                 `json:"observedAt" bson:"observedAt"`
	Confidence             float64                   `json:"confidence" bson:"confidence"`
	ConflictsWithSourceIDs []string                  `json:"conflictsWithSourceIds,omitempty" bson:"conflictsWithSourceIds,omitempty"`
}

type StructuredFacts struct {
	OpeningHours               []OpeningHoursEntry `json:"openingHours,omitempty" bson:"openingHours,omitempty"`
	TicketPriceRange           *TicketPriceRange   `json:"ticketPriceRange,omitempty" bson:"ticketPriceRange,omitempty"`
	RecommendedDurationMinutes *DurationRange      `json:"recommendedDurationMinutes,omitempty" bson:"recommendedDurationMinutes,omitempty"`
	BestSeasonTagRefs          []string            `json:"bestSeasonTagRefs,omitempty" bson:"bestSeasonTagRefs,omitempty"`
	AltitudeMeters             *int                `json:"altitudeMeters,omitempty" bson:"altitudeMeters,omitempty"`
	OfficialWebsite            string              `json:"officialWebsite,omitempty" bson:"officialWebsite,omitempty"`
	FactSources                []FactSource        `json:"factSources,omitempty" bson:"factSources,omitempty"`
}

// IsEmpty 判定投影是否无内容可展示，便于调用方把空投影收敛为 nil。
func (f *StructuredFacts) IsEmpty() bool {
	if f == nil {
		return true
	}
	return len(f.OpeningHours) == 0 &&
		f.TicketPriceRange == nil &&
		f.RecommendedDurationMinutes == nil &&
		len(f.BestSeasonTagRefs) == 0 &&
		f.AltitudeMeters == nil &&
		strings.TrimSpace(f.OfficialWebsite) == ""
}

// SanitizeStructuredFacts 把输入收敛为可投影的事实集，返回被丢弃字段的原因。
//
// 丢弃而不是报错，是因为主页导入是批量流水线：一个字段缺证据不应该让整个主页
// 无法发布。但被丢的字段必须能被诊断，所以原因随返回值一起交给调用方落日志。
func SanitizeStructuredFacts(input *StructuredFacts) (*StructuredFacts, []string) {
	if input == nil {
		return nil, nil
	}
	var dropped []string
	sources, sourceDrops := sanitizeFactSources(input.FactSources)
	dropped = append(dropped, sourceDrops...)
	evidenced := make(map[StructuredFactField]bool, len(sources))
	for _, source := range sources {
		evidenced[source.Field] = true
	}

	out := &StructuredFacts{}
	keep := func(field StructuredFactField, valid bool, invalidReason string, apply func()) {
		if !valid {
			dropped = append(dropped, string(field)+": "+invalidReason)
			return
		}
		if !evidenced[field] {
			dropped = append(dropped, string(field)+": no factSource")
			return
		}
		apply()
	}

	if len(input.OpeningHours) > 0 {
		entries, entryDrops := sanitizeOpeningHours(input.OpeningHours)
		dropped = append(dropped, entryDrops...)
		keep(FactFieldOpeningHours, len(entries) > 0, "no valid entry", func() {
			out.OpeningHours = entries
		})
	}
	if input.TicketPriceRange != nil {
		price := *input.TicketPriceRange
		keep(FactFieldTicketPriceRange, validTicketPrice(price), "invalid range", func() {
			price.Currency = strings.ToUpper(strings.TrimSpace(price.Currency))
			out.TicketPriceRange = &price
		})
	}
	if input.RecommendedDurationMinutes != nil {
		duration := *input.RecommendedDurationMinutes
		valid := duration.MinMinutes > 0 && duration.MaxMinutes >= duration.MinMinutes
		keep(FactFieldRecommendedDurationMinutes, valid, "invalid range", func() {
			out.RecommendedDurationMinutes = &duration
		})
	}
	if len(input.BestSeasonTagRefs) > 0 {
		refs := sanitizeSeasonTagRefs(input.BestSeasonTagRefs)
		keep(FactFieldBestSeasonTagRefs, len(refs) > 0, "no valid tagRef", func() {
			out.BestSeasonTagRefs = refs
		})
	}
	if input.AltitudeMeters != nil {
		altitude := *input.AltitudeMeters
		// 死海 -430m 到珠峰 8848m 之外只可能是单位或解析错误。
		valid := altitude >= -500 && altitude <= 9000
		keep(FactFieldAltitudeMeters, valid, "out of range", func() {
			out.AltitudeMeters = &altitude
		})
	}
	if website := strings.TrimSpace(input.OfficialWebsite); website != "" {
		keep(FactFieldOfficialWebsite, isHTTPSAbsoluteURL(website), "not an https url", func() {
			out.OfficialWebsite = website
		})
	}

	// 只保留仍有对应字段的证据，避免主页带着一堆指向空字段的溯源条目。
	out.FactSources = retainSourcesForPresentFields(sources, out)
	if out.IsEmpty() {
		return nil, dropped
	}
	return out, dropped
}

func retainSourcesForPresentFields(sources []FactSource, facts *StructuredFacts) []FactSource {
	present := map[StructuredFactField]bool{
		FactFieldOpeningHours:               len(facts.OpeningHours) > 0,
		FactFieldTicketPriceRange:           facts.TicketPriceRange != nil,
		FactFieldRecommendedDurationMinutes: facts.RecommendedDurationMinutes != nil,
		FactFieldBestSeasonTagRefs:          len(facts.BestSeasonTagRefs) > 0,
		FactFieldAltitudeMeters:             facts.AltitudeMeters != nil,
		FactFieldOfficialWebsite:            strings.TrimSpace(facts.OfficialWebsite) != "",
	}
	out := make([]FactSource, 0, len(sources))
	for _, source := range sources {
		if present[source.Field] {
			out = append(out, source)
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func sanitizeFactSources(sources []FactSource) ([]FactSource, []string) {
	var dropped []string
	out := make([]FactSource, 0, len(sources))
	for _, source := range sources {
		reason := factSourceRejection(source)
		if reason != "" {
			dropped = append(dropped, "factSource "+string(source.Field)+"/"+source.SourceID+": "+reason)
			continue
		}
		source.SourceID = strings.TrimSpace(source.SourceID)
		source.SourceURL = strings.TrimSpace(source.SourceURL)
		source.ObservedAt = source.ObservedAt.UTC()
		source.ConflictsWithSourceIDs = cloneStrings(source.ConflictsWithSourceIDs)
		out = append(out, source)
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Field != out[j].Field {
			return out[i].Field < out[j].Field
		}
		return out[i].SourceID < out[j].SourceID
	})
	if len(out) == 0 {
		return nil, dropped
	}
	return out, dropped
}

func factSourceRejection(source FactSource) string {
	if !validStructuredFactField(source.Field) {
		return "unknown field"
	}
	if !validStructuredFactSourceClass(source.SourceClass) {
		return "sourceClass outside structuredFactsPolicy"
	}
	if strings.TrimSpace(source.SourceID) == "" {
		return "missing sourceId"
	}
	if !isHTTPSAbsoluteURL(strings.TrimSpace(source.SourceURL)) {
		return "sourceUrl is not https"
	}
	if source.ObservedAt.IsZero() {
		return "missing observedAt"
	}
	if source.Confidence <= 0 || source.Confidence > 1 {
		return "confidence outside (0, 1]"
	}
	return ""
}

func validStructuredFactField(field StructuredFactField) bool {
	switch field {
	case FactFieldOpeningHours,
		FactFieldTicketPriceRange,
		FactFieldRecommendedDurationMinutes,
		FactFieldBestSeasonTagRefs,
		FactFieldAltitudeMeters,
		FactFieldOfficialWebsite:
		return true
	default:
		return false
	}
}

func validStructuredFactSourceClass(class StructuredFactSourceClass) bool {
	switch class {
	case FactSourceEncyclopedia, FactSourceOfficialSite, FactSourceGovernmentTourism:
		return true
	default:
		return false
	}
}

func sanitizeOpeningHours(entries []OpeningHoursEntry) ([]OpeningHoursEntry, []string) {
	var dropped []string
	out := make([]OpeningHoursEntry, 0, len(entries))
	for index, entry := range entries {
		reason := openingHoursRejection(entry)
		if reason != "" {
			dropped = append(dropped, "openingHours["+itoa(index)+"]: "+reason)
			continue
		}
		entry.AppliesFrom = strings.TrimSpace(entry.AppliesFrom)
		entry.AppliesTo = strings.TrimSpace(entry.AppliesTo)
		entry.Weekdays = normalizeWeekdays(entry.Weekdays)
		if entry.Closed {
			entry.OpenMinuteOfDay = 0
			entry.CloseMinuteOfDay = 0
		}
		out = append(out, entry)
	}
	if len(out) == 0 {
		return nil, dropped
	}
	return out, dropped
}

func openingHoursRejection(entry OpeningHoursEntry) string {
	if !validMonthDay(entry.AppliesFrom) || !validMonthDay(entry.AppliesTo) {
		return "appliesFrom/appliesTo must be MM-DD"
	}
	// 适用期是闭区间，必须两端同时声明或同时省略；只给一端无法判定范围。
	if (strings.TrimSpace(entry.AppliesFrom) == "") != (strings.TrimSpace(entry.AppliesTo) == "") {
		return "appliesFrom and appliesTo must be declared together"
	}
	for _, weekday := range entry.Weekdays {
		if weekday < 1 || weekday > 7 {
			return "weekdays must be within 1..7"
		}
	}
	if entry.Closed {
		return ""
	}
	if entry.OpenMinuteOfDay < 0 || entry.OpenMinuteOfDay >= 1440 {
		return "openMinuteOfDay must be within 0..1439"
	}
	if entry.CloseMinuteOfDay <= entry.OpenMinuteOfDay ||
		entry.CloseMinuteOfDay > MinuteOfDayUpperBound {
		return "closeMinuteOfDay must be after open and within two days"
	}
	return ""
}

func validMonthDay(value string) bool {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return true
	}
	_, err := time.Parse("01-02", trimmed)
	return err == nil
}

func normalizeWeekdays(values []int) []int {
	if len(values) == 0 {
		return nil
	}
	out := slices.Clone(values)
	sort.Ints(out)
	return slices.Compact(out)
}

func validTicketPrice(price TicketPriceRange) bool {
	if !isISO4217(price.Currency) {
		return false
	}
	if price.MinAmountCents < 0 || price.MaxAmountCents < price.MinAmountCents {
		return false
	}
	// free 必须与金额自洽，否则端侧的「免费」角标会和票价区间互相打脸。
	return !price.Free || (price.MinAmountCents == 0 && price.MaxAmountCents == 0)
}

// isISO4217 按码位而非字节判定，否则「元」这类三字节汉字会被当成合法三字母币种。
func isISO4217(currency string) bool {
	runes := []rune(strings.ToUpper(strings.TrimSpace(currency)))
	if len(runes) != 3 {
		return false
	}
	for _, letter := range runes {
		if letter < 'A' || letter > 'Z' {
			return false
		}
	}
	return true
}

// sanitizeSeasonTagRefs 只接受季节轴上的 tagRef。自由文本或其他轴的标签会让
// 「同季节窗口到访」交集算出无意义的交集，因此直接丢弃。
func sanitizeSeasonTagRefs(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range cloneStrings(values) {
		if strings.HasPrefix(value, "Topic/时间/四季/") ||
			strings.HasPrefix(value, "Topic/旅行/季节窗口/") {
			if !slices.Contains(out, value) {
				out = append(out, value)
			}
		}
	}
	if len(out) == 0 {
		return nil
	}
	sort.Strings(out)
	return out
}

func isHTTPSAbsoluteURL(value string) bool {
	parsed, err := url.Parse(value)
	if err != nil {
		return false
	}
	return parsed.Scheme == "https" && parsed.Host != ""
}

func itoa(value int) string {
	if value == 0 {
		return "0"
	}
	digits := make([]byte, 0, 8)
	for value > 0 {
		digits = append([]byte{byte('0' + value%10)}, digits...)
		value /= 10
	}
	return string(digits)
}

// Clone 返回深拷贝，避免调用方持有聚合内部切片。
func (f *StructuredFacts) Clone() *StructuredFacts {
	return cloneStructuredFacts(f)
}

func cloneStructuredFacts(value *StructuredFacts) *StructuredFacts {
	if value == nil {
		return nil
	}
	result := *value
	result.OpeningHours = slices.Clone(value.OpeningHours)
	result.BestSeasonTagRefs = cloneStrings(value.BestSeasonTagRefs)
	result.TicketPriceRange = clonePrice(value.TicketPriceRange)
	result.RecommendedDurationMinutes = cloneDuration(value.RecommendedDurationMinutes)
	result.AltitudeMeters = cloneInt(value.AltitudeMeters)
	result.FactSources = cloneFactSources(value.FactSources)
	return &result
}

func clonePrice(value *TicketPriceRange) *TicketPriceRange {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}

func cloneDuration(value *DurationRange) *DurationRange {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}

func cloneFactSources(values []FactSource) []FactSource {
	if len(values) == 0 {
		return nil
	}
	out := make([]FactSource, 0, len(values))
	for _, value := range values {
		value.ConflictsWithSourceIDs = cloneStrings(value.ConflictsWithSourceIDs)
		out = append(out, value)
	}
	return out
}
