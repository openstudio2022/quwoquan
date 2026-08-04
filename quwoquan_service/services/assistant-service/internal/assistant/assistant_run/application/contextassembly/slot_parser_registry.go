package contextassembly

import (
	"regexp"
	"sort"
	"strconv"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

var temporalExpressionPattern = regexp.MustCompile(
	`(?i)(今天|明天|后天|本周末|这周末|周末|本周|下周|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}月\d{1,2}(?:日|号)?)`,
)

type slotParseRequest struct {
	Definition skillpkg.SlotDefinition
	Text       string
	Source     string
	HintKind   string
}

type slotPrimitiveParser func(slotParseRequest) (string, bool)

// SlotParserRegistry is the platform primitive boundary. Skill packages select
// a parser by canonical reference; they never cause AgentLoop or the resolver
// to branch on skillId, domainId or slotId.
type SlotParserRegistry struct {
	parsers map[string]slotPrimitiveParser
}

func DefaultSlotParserRegistry() *SlotParserRegistry {
	return &SlotParserRegistry{parsers: map[string]slotPrimitiveParser{
		skillpkg.SlotParserTextAfterAlias:      parseTextAfterAlias,
		skillpkg.SlotParserLocationAfterAlias:  parseLocationAfterAlias,
		skillpkg.SlotParserLocationBeforeAlias: parseLocationBeforeAlias,
		skillpkg.SlotParserTemporalExpression:  parseTemporalExpression,
		skillpkg.SlotParserIntegerBeforeAlias:  parseIntegerBeforeAlias,
		skillpkg.SlotParserMoneyAfterAlias:     parseMoneyAfterAlias,
	}}
}

func (registry *SlotParserRegistry) parse(
	definition skillpkg.SlotDefinition,
	text string,
	source string,
	hintKind string,
) (string, bool) {
	if registry == nil {
		return "", false
	}
	request := slotParseRequest{
		Definition: definition,
		Text:       strings.TrimSpace(text),
		Source:     strings.TrimSpace(source),
		HintKind:   strings.TrimSpace(hintKind),
	}
	for _, parserRef := range definition.ParserRefs {
		parser := registry.parsers[strings.TrimSpace(parserRef)]
		if parser == nil {
			return "", false
		}
		if value, ok := parser(request); ok {
			return value, true
		}
	}
	return "", false
}

func parseTextAfterAlias(request slotParseRequest) (string, bool) {
	value, ok := afterAlias(request.Text, request.Definition.Aliases, `[^，。;；\n]{1,128}`)
	return strings.TrimSpace(value), ok
}

func parseLocationAfterAlias(request slotParseRequest) (string, bool) {
	value, ok := afterAlias(
		request.Text,
		request.Definition.Aliases,
		`[\p{Han}A-Za-z·]{2,16}?`,
		`(?:出发|去|到|前往|玩|旅行|旅游|出差|度假|看看|的|[，。,;；\s]|$)`,
	)
	if !ok && request.Source == skillpkg.SlotSourceLongTermMemory &&
		request.HintKind == "frequent_locations" {
		value = trimLocationCandidate(request.Text)
		ok = validTopicLocation(value) && len([]rune(value)) <= 32
	}
	if !ok {
		return "", false
	}
	value = trimLocationCandidate(value)
	return value, validTopicLocation(value)
}

func parseLocationBeforeAlias(request slotParseRequest) (string, bool) {
	aliases := quotedAlternatives(request.Definition.Aliases)
	if aliases == "" {
		return "", false
	}
	pattern, err := regexp.Compile(
		`(?i)([\p{Han}A-Za-z·]{2,16}?)(?:今天|明天|后天|本周末|这周末|周末|本周|下周)?(?:的)?(?:` + aliases + `)`,
	)
	if err != nil {
		return "", false
	}
	value, ok := firstCaptured(pattern, request.Text)
	if !ok && request.Source == skillpkg.SlotSourceLongTermMemory &&
		request.HintKind == "frequent_locations" {
		value = trimLocationCandidate(request.Text)
		ok = validTopicLocation(value) && len([]rune(value)) <= 32
	}
	if !ok {
		return "", false
	}
	value = trimLocationCandidate(value)
	return value, validTopicLocation(value)
}

func parseTemporalExpression(request slotParseRequest) (string, bool) {
	return firstCaptured(temporalExpressionPattern, request.Text)
}

func parseIntegerBeforeAlias(request slotParseRequest) (string, bool) {
	aliases := quotedAlternatives(request.Definition.Aliases)
	if aliases == "" {
		return "", false
	}
	pattern, err := regexp.Compile(
		`(?i)(\d{1,3}|一|二|两|三|四|五|六|七|八|九|十)(?:个)?(?:` + aliases + `)`,
	)
	if err != nil {
		return "", false
	}
	value, ok := firstCaptured(pattern, request.Text)
	if !ok {
		return "", false
	}
	return normalizeInteger(value)
}

func parseMoneyAfterAlias(request slotParseRequest) (string, bool) {
	return afterAlias(
		request.Text,
		request.Definition.Aliases,
		`[0-9]+(?:\.[0-9]+)?\s*(?:元|块|k|K|千|万)?`,
	)
}

func afterAlias(text string, aliases []string, valuePattern string, suffix ...string) (string, bool) {
	alternatives := quotedAlternatives(aliases)
	if alternatives == "" || strings.TrimSpace(text) == "" {
		return "", false
	}
	ending := ""
	if len(suffix) > 0 {
		ending = suffix[0]
	}
	pattern, err := regexp.Compile(
		`(?i)(?:` + alternatives + `)(?:是|为|大约|约)?\s*[:：]?\s*(` + valuePattern + `)` + ending,
	)
	if err != nil {
		return "", false
	}
	return firstCaptured(pattern, text)
}

func quotedAlternatives(values []string) string {
	items := append([]string(nil), values...)
	sort.SliceStable(items, func(i, j int) bool {
		return len([]rune(items[i])) > len([]rune(items[j]))
	})
	for index := range items {
		items[index] = regexp.QuoteMeta(strings.TrimSpace(items[index]))
	}
	return strings.Join(items, "|")
}

func firstCaptured(pattern *regexp.Regexp, text string) (string, bool) {
	matches := pattern.FindStringSubmatch(text)
	if len(matches) < 2 {
		return "", false
	}
	value := strings.TrimSpace(matches[1])
	return value, value != ""
}

func trimLocationCandidate(value string) string {
	value = strings.TrimSpace(value)
	for _, suffix := range []string{"玩几天", "玩", "旅行", "旅游", "出差", "度假", "看看", "的"} {
		value = strings.TrimSuffix(value, suffix)
	}
	return strings.TrimSpace(value)
}

func validTopicLocation(value string) bool {
	value = strings.TrimSpace(value)
	if value == "" {
		return false
	}
	for _, generic := range []string{
		"查一下", "看一下", "帮我", "请问", "想知道", "告诉我",
		"今天", "明天", "后天", "周末", "本周", "下周",
	} {
		if strings.Contains(value, generic) {
			return false
		}
	}
	return true
}

func normalizeInteger(raw string) (string, bool) {
	numbers := map[string]int{
		"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
		"六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
	}
	if value, ok := numbers[strings.TrimSpace(raw)]; ok {
		return strconv.Itoa(value), true
	}
	value := strings.TrimSpace(raw)
	if _, err := strconv.Atoi(value); err != nil {
		return "", false
	}
	return value, true
}
