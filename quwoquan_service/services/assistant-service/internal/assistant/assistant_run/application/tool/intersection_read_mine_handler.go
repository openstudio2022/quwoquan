package tool

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

// MyIntersectionItem 是 intersection.read_mine 的单条输出投影：字段与 canonical
// Tool Catalog outputSchema 一一对应；primaryText 只透传云侧主句，禁止拼句。
type MyIntersectionItem struct {
	IntersectionID    string
	IntersectionClass string
	Kind              string
	Dimension         string
	ObjectKind        string
	DisplayName       string
	PrimaryText       string
	Strength          float64
	FreshAt           string
	ExpiresAt         string
	ActionKeys        []string
}

// MyIntersectionsQuery 是 read_mine 的输入面（catalog inputSchema 的闭集）。
type MyIntersectionsQuery struct {
	Limit     int
	Dimension string
	Filter    string
	Cursor    string
}

// MyIntersectionsReader 是 intersection.read_mine 的 domain_reader port：
// 生产实现经 content-service 正式 ListMyIntersections Slice（delegated persona
// token）读取当前用户交集只读投影；任何失败 fail-closed，不返回合成结果。
type MyIntersectionsReader interface {
	ListMyIntersections(
		ctx context.Context,
		personaID string,
		query MyIntersectionsQuery,
	) ([]MyIntersectionItem, error)
}

// ErrIntersectionReadMineUnavailable 表示绑定或上游读失败；结构化不可用，
// 禁止用空列表冒充成功。
var ErrIntersectionReadMineUnavailable = errors.New(
	"ASSISTANT.MIDDLEWARE.tool_unavailable: intersection reader degraded",
)

const readMineMaxLimit = 50

// NewIntersectionReadMineHandler 构造 intersection.read_mine 的可执行 handler。
// reader 为 nil 属于装配错误——composition 必须改走 UnavailableCanonicalBindings，
// 而不是注册一个会失败的 handler。
func NewIntersectionReadMineHandler(reader MyIntersectionsReader) (Handler, error) {
	if reader == nil {
		return nil, fmt.Errorf("intersection.read_mine reader binding is required")
	}
	return func(ctx context.Context, request Request) (Result, error) {
		personaID := strings.TrimSpace(request.PersonaID)
		if personaID == "" {
			return Result{}, fmt.Errorf(
				"ASSISTANT.USER.run_unauthorized: intersection.read_mine requires persona actor",
			)
		}
		query, err := decodeReadMineQuery(request.Input)
		if err != nil {
			return Result{}, err
		}
		items, err := reader.ListMyIntersections(ctx, personaID, query)
		if err != nil {
			return Result{}, fmt.Errorf(
				"%w: %v", ErrIntersectionReadMineUnavailable, err,
			)
		}
		projected := make([]map[string]any, 0, len(items))
		for _, item := range items {
			projected = append(projected, map[string]any{
				"intersectionId":    item.IntersectionID,
				"intersectionClass": item.IntersectionClass,
				"kind":              item.Kind,
				"dimension":         item.Dimension,
				"objectKind":        item.ObjectKind,
				"displayName":       item.DisplayName,
				"primaryText":       item.PrimaryText,
				"strength":          item.Strength,
				"freshAt":           item.FreshAt,
				"expiresAt":         item.ExpiresAt,
				"actionKeys":        append([]string(nil), item.ActionKeys...),
			})
		}
		return Result{
			Output: map[string]any{"intersections": projected},
		}, nil
	}, nil
}

func decodeReadMineQuery(input map[string]any) (MyIntersectionsQuery, error) {
	rawLimit, found := input["limit"]
	if !found {
		return MyIntersectionsQuery{}, fmt.Errorf(
			"ASSISTANT.USER.run_invalid_argument: intersection.read_mine limit is required",
		)
	}
	limit := 0
	switch value := rawLimit.(type) {
	case int:
		limit = value
	case int64:
		limit = int(value)
	case float64:
		limit = int(value)
	default:
		return MyIntersectionsQuery{}, fmt.Errorf(
			"ASSISTANT.USER.run_invalid_argument: intersection.read_mine limit must be an integer",
		)
	}
	if limit < 1 || limit > readMineMaxLimit {
		return MyIntersectionsQuery{}, fmt.Errorf(
			"ASSISTANT.USER.run_invalid_argument: intersection.read_mine limit must be 1..%d",
			readMineMaxLimit,
		)
	}
	stringField := func(name string) (string, error) {
		raw, ok := input[name]
		if !ok || raw == nil {
			return "", nil
		}
		value, isString := raw.(string)
		if !isString {
			return "", fmt.Errorf(
				"ASSISTANT.USER.run_invalid_argument: intersection.read_mine %s must be a string",
				name,
			)
		}
		return strings.TrimSpace(value), nil
	}
	dimension, err := stringField("dimension")
	if err != nil {
		return MyIntersectionsQuery{}, err
	}
	filter, err := stringField("filter")
	if err != nil {
		return MyIntersectionsQuery{}, err
	}
	cursor, err := stringField("cursor")
	if err != nil {
		return MyIntersectionsQuery{}, err
	}
	return MyIntersectionsQuery{
		Limit:     limit,
		Dimension: dimension,
		Filter:    filter,
		Cursor:    cursor,
	}, nil
}
