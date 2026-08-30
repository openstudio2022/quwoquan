package servicekit

import (
	"fmt"
	"os"
	"reflect"
	"strconv"
	"strings"
)

// ApplyEnvOverrides 按 config struct 的声明式 tag 应用部署面 env 覆盖：
// 叶子字段 `env:"<SUFFIX>"`、嵌套结构 `envPrefix:"<SEGMENT>"`，完整键为
// `<prefix>_<SEGMENT>..._<SUFFIX>`；`envAbsolute:"<KEY>"` 声明不带前缀的
// 全局契约键。取值先 TrimSpace，空 env 不覆盖；支持 string、[]string
// （逗号分割）、bool、int，带 env tag 的其他类型 fail-closed 报错。
// 手写覆盖钩子由该引擎取代（DEC-028）。
func ApplyEnvOverrides(prefix string, target any) error {
	value, err := structValue(target)
	if err != nil {
		return err
	}
	return walkEnvFields(strings.TrimSpace(prefix), value, func(key string, field reflect.Value) error {
		raw := strings.TrimSpace(os.Getenv(key))
		if raw == "" {
			return nil
		}
		return setFieldFromEnv(key, field, raw)
	})
}

// EnvOverrideKeys 列出 config struct 声明派生的全部 env 键，供迁移服务断言
// 声明键集与被删除的手写钩子键集逐一相等。
func EnvOverrideKeys(prefix string, target any) ([]string, error) {
	value, err := structValue(target)
	if err != nil {
		return nil, err
	}
	var keys []string
	err = walkEnvFields(strings.TrimSpace(prefix), value, func(key string, _ reflect.Value) error {
		keys = append(keys, key)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return keys, nil
}

// RejectRetiredEnvKeys 在任一声明的退役键出现在进程环境时启动失败。它按
// LookupEnv 判定「出现」而非「非空」：空值同样是一次显式注入，必须被拒收，
// 否则退役键会退化为 warn-only 逃逸。
func RejectRetiredEnvKeys(keys []string) error {
	for _, key := range keys {
		trimmed := strings.TrimSpace(key)
		if trimmed == "" {
			continue
		}
		if _, found := os.LookupEnv(trimmed); found {
			return fmt.Errorf("%s is retired and must not be injected", trimmed)
		}
	}
	return nil
}

// ValidateRequired 在 env 覆盖应用之后统一校验 `required:"true"` 字段：
// 仅支持 string 类型，TrimSpace 后为空即启动失败（DEC-028 required 时机裁决）。
func ValidateRequired(target any) error {
	value, err := structValue(target)
	if err != nil {
		return err
	}
	return walkRequiredFields("", value)
}

func structValue(target any) (reflect.Value, error) {
	pointer := reflect.ValueOf(target)
	if pointer.Kind() != reflect.Pointer || pointer.IsNil() {
		return reflect.Value{}, fmt.Errorf("env override target must be a non-nil struct pointer")
	}
	value := pointer.Elem()
	if value.Kind() != reflect.Struct {
		return reflect.Value{}, fmt.Errorf("env override target must point to a struct, got %s", value.Kind())
	}
	return value, nil
}

func walkEnvFields(
	prefix string,
	value reflect.Value,
	visit func(key string, field reflect.Value) error,
) error {
	valueType := value.Type()
	for index := 0; index < valueType.NumField(); index++ {
		fieldType := valueType.Field(index)
		if !fieldType.IsExported() {
			continue
		}
		field := value.Field(index)

		// envAbsolute 声明不带服务前缀的全局键名，供环境装配契约已固定为
		// 无前缀形态的键使用（如 secretRefs 声明的 MONGO_URI）。
		if absolute, ok := fieldType.Tag.Lookup("envAbsolute"); ok {
			absolute = strings.TrimSpace(absolute)
			if absolute == "" {
				return fmt.Errorf("field %s declares an empty envAbsolute tag", fieldType.Name)
			}
			if _, conflicting := fieldType.Tag.Lookup("env"); conflicting {
				return fmt.Errorf(
					"field %s declares both env and envAbsolute; keep one key per field",
					fieldType.Name,
				)
			}
			if err := visit(absolute, field); err != nil {
				return err
			}
			continue
		}

		if suffix, ok := fieldType.Tag.Lookup("env"); ok {
			suffix = strings.TrimSpace(suffix)
			if suffix == "" {
				return fmt.Errorf("field %s declares an empty env tag", fieldType.Name)
			}
			if err := visit(joinEnvKey(prefix, suffix), field); err != nil {
				return err
			}
			continue
		}

		if field.Kind() == reflect.Struct {
			segment := strings.TrimSpace(fieldType.Tag.Get("envPrefix"))
			if err := walkEnvFields(joinEnvKey(prefix, segment), field, visit); err != nil {
				return err
			}
		}
	}
	return nil
}

func joinEnvKey(prefix, segment string) string {
	if segment == "" {
		return prefix
	}
	if prefix == "" {
		return segment
	}
	return prefix + "_" + segment
}

func setFieldFromEnv(key string, field reflect.Value, raw string) error {
	if !field.CanSet() {
		return fmt.Errorf("env %s targets an unsettable field", key)
	}
	switch field.Kind() {
	case reflect.String:
		field.SetString(raw)
		return nil
	case reflect.Bool:
		parsed, err := parseEnvBool(raw)
		if err != nil {
			return fmt.Errorf("env %s: %w", key, err)
		}
		field.SetBool(parsed)
		return nil
	case reflect.Int, reflect.Int64:
		parsed, err := strconv.ParseInt(raw, 10, 64)
		if err != nil {
			return fmt.Errorf("env %s must be an integer, got %q", key, raw)
		}
		field.SetInt(parsed)
		return nil
	case reflect.Float32, reflect.Float64:
		parsed, err := strconv.ParseFloat(raw, 64)
		if err != nil {
			return fmt.Errorf("env %s must be numeric, got %q", key, raw)
		}
		field.SetFloat(parsed)
		return nil
	case reflect.Slice:
		if field.Type().Elem().Kind() != reflect.String {
			return fmt.Errorf("env %s targets unsupported slice type %s", key, field.Type())
		}
		// 逗号分隔列表逐项 TrimSpace 并丢弃空项：部署面模板常留下尾随
		// 分隔符与换行缩进，空项会被下游当成一个真实地址去连接。
		items := make([]string, 0, strings.Count(raw, ",")+1)
		for _, item := range strings.Split(raw, ",") {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				items = append(items, trimmed)
			}
		}
		if len(items) == 0 {
			return fmt.Errorf("env %s must list at least one non-empty value", key)
		}
		field.Set(reflect.ValueOf(items))
		return nil
	default:
		return fmt.Errorf("env %s targets unsupported field type %s", key, field.Type())
	}
}

func parseEnvBool(raw string) (bool, error) {
	switch strings.ToLower(raw) {
	case "true", "1", "yes", "on":
		return true, nil
	case "false", "0", "no", "off":
		return false, nil
	default:
		return false, fmt.Errorf("must be a boolean literal (true/1/yes/on or false/0/no/off), got %q", raw)
	}
}

func walkRequiredFields(path string, value reflect.Value) error {
	valueType := value.Type()
	for index := 0; index < valueType.NumField(); index++ {
		fieldType := valueType.Field(index)
		if !fieldType.IsExported() {
			continue
		}
		field := value.Field(index)
		fieldPath := fieldType.Name
		if path != "" {
			fieldPath = path + "." + fieldType.Name
		}

		if required := strings.TrimSpace(fieldType.Tag.Get("required")); required == "true" {
			if field.Kind() != reflect.String {
				return fmt.Errorf(
					"required tag on %s only supports string fields, got %s",
					fieldPath, field.Type(),
				)
			}
			if strings.TrimSpace(field.String()) == "" {
				return fmt.Errorf("required config %s is missing", fieldPath)
			}
			continue
		}

		if field.Kind() == reflect.Struct {
			if err := walkRequiredFields(fieldPath, field); err != nil {
				return err
			}
		}
	}
	return nil
}
