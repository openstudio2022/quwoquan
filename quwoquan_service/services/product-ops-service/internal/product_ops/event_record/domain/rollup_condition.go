package domain

import (
	"fmt"
	"strconv"
	"strings"
)

// RollupCondition 是 rollups.yaml 的 filter/where 与
// product_telemetry_alerts.yaml 的 condition 共用的最小条件语言：
//
//	comparison := field ('='|'!='|'>'|'>='|'<'|'<=') value
//	            | field 'IS NOT NULL'
//	            | field 'IN' '(' value (',' value)* ')'
//	expr       := comparison | expr 'AND' expr | expr 'OR' expr | '(' expr ')'
//
// 值是裸标识符、数字或 true/false；两侧均可解析为数字时按数值比较，
// 否则按字符串比较。解析一次、可重复求值；未知字段视为 NULL/缺失。
type RollupCondition struct {
	root conditionNode
	raw  string
}

// ConditionEnv 提供字段取值；exists=false 表示字段缺失（NULL 语义）。
type ConditionEnv func(field string) (value string, exists bool)

func ParseRollupCondition(raw string) (*RollupCondition, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return &RollupCondition{raw: raw}, nil
	}
	parser := &conditionParser{tokens: tokenizeCondition(trimmed)}
	root, err := parser.parseOr()
	if err != nil {
		return nil, fmt.Errorf("parse condition %q: %w", raw, err)
	}
	if parser.position != len(parser.tokens) {
		return nil, fmt.Errorf(
			"parse condition %q: trailing token %q",
			raw, parser.tokens[parser.position],
		)
	}
	return &RollupCondition{root: root, raw: raw}, nil
}

// Evaluate 对给定环境求值；空条件恒真。
func (condition *RollupCondition) Evaluate(env ConditionEnv) bool {
	if condition == nil || condition.root == nil {
		return true
	}
	return condition.root.evaluate(env)
}

func (condition *RollupCondition) String() string { return condition.raw }

// ── AST ────────────────────────────────────────────────────

type conditionNode interface {
	evaluate(env ConditionEnv) bool
}

type binaryNode struct {
	operator    string // AND | OR
	left, right conditionNode
}

func (node binaryNode) evaluate(env ConditionEnv) bool {
	if node.operator == "AND" {
		return node.left.evaluate(env) && node.right.evaluate(env)
	}
	return node.left.evaluate(env) || node.right.evaluate(env)
}

type comparisonNode struct {
	field    string
	operator string // = != > >= < <= not_null in
	value    string
	values   []string
}

func (node comparisonNode) evaluate(env ConditionEnv) bool {
	actual, exists := env(node.field)
	switch node.operator {
	case "not_null":
		return exists && strings.TrimSpace(actual) != ""
	case "in":
		if !exists {
			return false
		}
		for _, candidate := range node.values {
			if actual == candidate {
				return true
			}
		}
		return false
	}
	if !exists {
		return false
	}
	leftNumber, leftNumeric := parseConditionNumber(actual)
	rightNumber, rightNumeric := parseConditionNumber(node.value)
	if leftNumeric && rightNumeric {
		switch node.operator {
		case "=":
			return leftNumber == rightNumber
		case "!=":
			return leftNumber != rightNumber
		case ">":
			return leftNumber > rightNumber
		case ">=":
			return leftNumber >= rightNumber
		case "<":
			return leftNumber < rightNumber
		case "<=":
			return leftNumber <= rightNumber
		}
	}
	switch node.operator {
	case "=":
		return actual == node.value
	case "!=":
		return actual != node.value
	}
	// 字符串不支持大小比较：显式拒绝为 false，避免静默字典序语义。
	return false
}

func parseConditionNumber(raw string) (float64, bool) {
	value, err := strconv.ParseFloat(strings.TrimSpace(raw), 64)
	return value, err == nil
}

// ── 解析 ───────────────────────────────────────────────────

type conditionParser struct {
	tokens   []string
	position int
}

func tokenizeCondition(raw string) []string {
	replacer := strings.NewReplacer(
		"(", " ( ",
		")", " ) ",
		",", " , ",
		">=", " >= ",
		"<=", " <= ",
		"!=", " != ",
	)
	spaced := replacer.Replace(raw)
	// 单字符运算符在双字符替换后处理，避免拆散 >= / != 。
	var b strings.Builder
	for index := 0; index < len(spaced); index++ {
		char := spaced[index]
		if char == '=' || char == '>' || char == '<' {
			previous := byte(0)
			if b.Len() > 0 {
				previous = b.String()[b.Len()-1]
			}
			if previous != '>' && previous != '<' && previous != '!' && previous != '=' &&
				(index+1 >= len(spaced) || spaced[index+1] != '=') {
				b.WriteByte(' ')
				b.WriteByte(char)
				b.WriteByte(' ')
				continue
			}
		}
		b.WriteByte(char)
	}
	return strings.Fields(b.String())
}

func (parser *conditionParser) peek() string {
	if parser.position >= len(parser.tokens) {
		return ""
	}
	return parser.tokens[parser.position]
}

func (parser *conditionParser) next() string {
	token := parser.peek()
	parser.position++
	return token
}

func (parser *conditionParser) parseOr() (conditionNode, error) {
	left, err := parser.parseAnd()
	if err != nil {
		return nil, err
	}
	for strings.EqualFold(parser.peek(), "OR") {
		parser.next()
		right, err := parser.parseAnd()
		if err != nil {
			return nil, err
		}
		left = binaryNode{operator: "OR", left: left, right: right}
	}
	return left, nil
}

func (parser *conditionParser) parseAnd() (conditionNode, error) {
	left, err := parser.parsePrimary()
	if err != nil {
		return nil, err
	}
	for strings.EqualFold(parser.peek(), "AND") {
		parser.next()
		right, err := parser.parsePrimary()
		if err != nil {
			return nil, err
		}
		left = binaryNode{operator: "AND", left: left, right: right}
	}
	return left, nil
}

func (parser *conditionParser) parsePrimary() (conditionNode, error) {
	if parser.peek() == "(" {
		parser.next()
		inner, err := parser.parseOr()
		if err != nil {
			return nil, err
		}
		if parser.next() != ")" {
			return nil, fmt.Errorf("expected closing parenthesis")
		}
		return inner, nil
	}
	field := parser.next()
	if field == "" {
		return nil, fmt.Errorf("expected field name")
	}
	operator := parser.next()
	switch operator {
	case "=", "!=", ">", ">=", "<", "<=":
		value := parser.next()
		if value == "" {
			return nil, fmt.Errorf("comparison for %s misses its value", field)
		}
		return comparisonNode{field: field, operator: operator, value: value}, nil
	}
	if strings.EqualFold(operator, "IS") {
		if !strings.EqualFold(parser.next(), "NOT") || !strings.EqualFold(parser.next(), "NULL") {
			return nil, fmt.Errorf("only IS NOT NULL is supported for %s", field)
		}
		return comparisonNode{field: field, operator: "not_null"}, nil
	}
	if strings.EqualFold(operator, "IN") {
		if parser.next() != "(" {
			return nil, fmt.Errorf("IN for %s requires a value list", field)
		}
		values := make([]string, 0, 4)
		for {
			token := parser.next()
			switch token {
			case ")":
				if len(values) == 0 {
					return nil, fmt.Errorf("IN for %s has an empty list", field)
				}
				return comparisonNode{field: field, operator: "in", values: values}, nil
			case ",":
				continue
			case "":
				return nil, fmt.Errorf("IN for %s is unterminated", field)
			default:
				values = append(values, token)
			}
		}
	}
	return nil, fmt.Errorf("unsupported operator %q for %s", operator, field)
}
