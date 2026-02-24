package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

type pgRepository struct {
	db     *sql.DB
	table  string
	pk     string
	fields []string
}

func newPGRepository(f *Factory, entityName string) (*pgRepository, error) {
	fieldDefs, err := f.reg.GetFieldPolicy(entityName)
	if err != nil {
		return nil, fmt.Errorf("get field policy for %q: %w", entityName, err)
	}

	pk := "id"
	fields := make([]string, 0, len(fieldDefs))
	for _, fd := range fieldDefs {
		fields = append(fields, fd.Name)
		for _, c := range fd.Constraints {
			if c == "PK" {
				pk = fd.Name
			}
		}
	}

	table := toSnakeCase(entityName) + "s"

	return &pgRepository{
		db:     f.pgDB,
		table:  table,
		pk:     pk,
		fields: fields,
	}, nil
}

func (r *pgRepository) FindByID(ctx context.Context, id string) (*map[string]any, error) {
	cols := strings.Join(r.fields, ", ")
	query := fmt.Sprintf("SELECT %s FROM %s WHERE %s = $1", cols, r.table, r.pk)

	row := r.db.QueryRowContext(ctx, query, id)

	values := make([]any, len(r.fields))
	ptrs := make([]any, len(r.fields))
	for i := range values {
		ptrs[i] = &values[i]
	}

	if err := row.Scan(ptrs...); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("scan %s: %w", r.table, err)
	}

	result := make(map[string]any, len(r.fields))
	for i, name := range r.fields {
		result[name] = values[i]
	}
	return &result, nil
}

func (r *pgRepository) FindAll(ctx context.Context, q Query) (*Page[map[string]any], error) {
	cols := strings.Join(r.fields, ", ")
	where, args := buildPGWhere(q.Filter, 1)
	orderBy := buildPGOrderBy(q.Sort)
	limit := q.Limit
	if limit <= 0 {
		limit = 20
	}

	query := fmt.Sprintf("SELECT %s FROM %s%s%s LIMIT %d",
		cols, r.table, where, orderBy, limit)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("query %s: %w", r.table, err)
	}
	defer rows.Close()

	var items []map[string]any
	for rows.Next() {
		values := make([]any, len(r.fields))
		ptrs := make([]any, len(r.fields))
		for i := range values {
			ptrs[i] = &values[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, fmt.Errorf("scan row: %w", err)
		}
		item := make(map[string]any, len(r.fields))
		for i, name := range r.fields {
			item[name] = values[i]
		}
		items = append(items, item)
	}

	var nextCursor string
	if len(items) == limit {
		last := items[len(items)-1]
		if pkVal, ok := last[r.pk]; ok {
			cursorBytes, _ := json.Marshal(pkVal)
			nextCursor = string(cursorBytes)
		}
	}

	return &Page[map[string]any]{
		Items:      items,
		NextCursor: nextCursor,
	}, nil
}

func (r *pgRepository) Create(ctx context.Context, entity *map[string]any) error {
	e := *entity
	cols := make([]string, 0, len(e))
	placeholders := make([]string, 0, len(e))
	args := make([]any, 0, len(e))
	i := 1

	for _, name := range r.fields {
		if v, ok := e[name]; ok {
			cols = append(cols, name)
			placeholders = append(placeholders, fmt.Sprintf("$%d", i))
			args = append(args, v)
			i++
		}
	}

	query := fmt.Sprintf("INSERT INTO %s (%s) VALUES (%s)",
		r.table, strings.Join(cols, ", "), strings.Join(placeholders, ", "))

	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}

func (r *pgRepository) Update(ctx context.Context, id string, entity *map[string]any) error {
	e := *entity
	sets := make([]string, 0, len(e))
	args := make([]any, 0, len(e)+1)
	i := 1

	for _, name := range r.fields {
		if name == r.pk {
			continue
		}
		if v, ok := e[name]; ok {
			sets = append(sets, fmt.Sprintf("%s = $%d", name, i))
			args = append(args, v)
			i++
		}
	}

	args = append(args, id)
	query := fmt.Sprintf("UPDATE %s SET %s WHERE %s = $%d",
		r.table, strings.Join(sets, ", "), r.pk, i)

	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}

func (r *pgRepository) Delete(ctx context.Context, id string) error {
	query := fmt.Sprintf("DELETE FROM %s WHERE %s = $1", r.table, r.pk)
	_, err := r.db.ExecContext(ctx, query, id)
	return err
}

func (r *pgRepository) Count(ctx context.Context, filter Filter) (int64, error) {
	where, args := buildPGWhere(filter, 1)
	query := fmt.Sprintf("SELECT COUNT(*) FROM %s%s", r.table, where)

	var count int64
	err := r.db.QueryRowContext(ctx, query, args...).Scan(&count)
	return count, err
}

func buildPGWhere(f Filter, startParam int) (string, []any) {
	if len(f.Conditions) == 0 {
		return "", nil
	}
	logic := " AND "
	if f.Logic == Or {
		logic = " OR "
	}
	parts := make([]string, 0, len(f.Conditions))
	args := make([]any, 0, len(f.Conditions))
	paramIdx := startParam

	for _, c := range f.Conditions {
		op := pgOperator(c.Operator)
		parts = append(parts, fmt.Sprintf("%s %s $%d", c.Field, op, paramIdx))
		args = append(args, c.Value)
		paramIdx++
	}

	return " WHERE " + strings.Join(parts, logic), args
}

func pgOperator(op Operator) string {
	switch op {
	case Eq:
		return "="
	case Ne:
		return "!="
	case Gt:
		return ">"
	case Gte:
		return ">="
	case Lt:
		return "<"
	case Lte:
		return "<="
	case In:
		return "= ANY"
	case Regex:
		return "~"
	default:
		return "="
	}
}

func buildPGOrderBy(sorts []SortField) string {
	if len(sorts) == 0 {
		return ""
	}
	parts := make([]string, 0, len(sorts))
	for _, s := range sorts {
		dir := "ASC"
		if s.Direction == Desc {
			dir = "DESC"
		}
		parts = append(parts, fmt.Sprintf("%s %s", s.Field, dir))
	}
	return " ORDER BY " + strings.Join(parts, ", ")
}

func toSnakeCase(s string) string {
	var result strings.Builder
	for i, r := range s {
		if r >= 'A' && r <= 'Z' {
			if i > 0 {
				result.WriteByte('_')
			}
			result.WriteRune(r + 32)
		} else {
			result.WriteRune(r)
		}
	}
	return result.String()
}
