package presentationcontract

import (
	"fmt"
	"strings"
)

// RenderDart 输出不可变编译能力与同协议摘要，不依赖手写 runtime 支持数组。
func (m Model) RenderDart(modelImport string, enumMember func(string, string) string) (string, error) {
	var b strings.Builder
	b.WriteString(`// Code generated from contracts/metadata/_shared/types.yaml. DO NOT EDIT.
import 'dart:convert';
import 'package:crypto/crypto.dart';

`)
	fmt.Fprintf(&b, "import %q;\n\n", modelImport)
	for _, baseline := range []bool{false, true} {
		name := "compiled"
		if baseline {
			name = "missingDeclaration"
		}
		fmt.Fprintf(&b, "const %sContentPresentationCollections = <String, List<String>>{\n", name)
		for _, f := range m.Fields {
			v := f.Values
			if baseline {
				v = f.Baseline
			}
			fmt.Fprintf(&b, "  %q: <String>[%s],\n", f.Name, quoted(v))
		}
		b.WriteString("};\n")
		digest, err := m.Digest(m.Collections(baseline))
		if err != nil {
			return "", err
		}
		fmt.Fprintf(&b, "const %sContentPresentationContractDigest = %q;\n", name, digest)
		fmt.Fprintf(&b, "final %sContentPresentationContract = ClientContentPresentationContract(\n", name)
		for _, f := range m.Fields {
			values := f.Values
			if baseline {
				values = f.Baseline
			}
			members := make([]string, len(values))
			for i, v := range values {
				members[i] = f.EnumRef + "." + enumMember(f.EnumRef, v)
			}
			fmt.Fprintf(&b, "  %s: const <%s>[%s],\n", f.Name, f.EnumRef, strings.Join(members, ","))
		}
		fmt.Fprintf(&b, "  contractDigest: %sContentPresentationContractDigest,\n);\n\n", name)
	}
	b.WriteString("const _maxItems = <String, int>{\n")
	for _, f := range m.Fields {
		fmt.Fprintf(&b, "  %q: %d,\n", f.Name, f.MaxItems)
	}
	b.WriteString("};\n")
	b.WriteString(`
int _compareUtf8(String left, String right) {
  final a = utf8.encode(left);
  final b = utf8.encode(right);
  for (var i = 0; i < a.length && i < b.length; i++) {
    if (a[i] != b[i]) return a[i].compareTo(b[i]);
  }
  return a.length.compareTo(b.length);
}

String canonicalClientContentPresentationContract(ClientContentPresentationContract value) =>
    canonicalClientContentPresentationCollections(value.toWire());

String canonicalClientContentPresentationCollections(Map<String, Object?> value) {
  final fields = compiledContentPresentationCollections.keys.toSet();
  if (!value.keys.every((key) => fields.contains(key) || key == 'contractDigest') ||
      !fields.every(value.containsKey)) {
    throw const FormatException('Expected exactly four capability collections');
  }
  final normalized = <String, List<String>>{};
  for (final entry in compiledContentPresentationCollections.entries) {
    final values = value[entry.key];
    if (values is! List || values.length > _maxItems[entry.key]!) {
      throw const FormatException('Expected bounded non-null capability array');
    }
    final seen = <String>{};
    for (final member in values) {
      if (member is! String || !entry.value.contains(member) || !seen.add(member)) {
        throw const FormatException('Invalid or duplicate capability member');
      }
    }
    normalized[entry.key] = seen.toList()..sort(_compareUtf8);
  }
  return jsonEncode(normalized);
}

String digestClientContentPresentationContract(ClientContentPresentationContract value) =>
    'sha256:${sha256.convert(utf8.encode(canonicalClientContentPresentationContract(value)))}';

void validateClientContentPresentationContract(ClientContentPresentationContract value) {
  // 摘要只表示能力集合身份；不是授权。
  if (value.contractDigest != digestClientContentPresentationContract(value)) {
    throw const FormatException('Client presentation contract digest mismatch');
  }
}
`)
	return b.String(), nil
}
