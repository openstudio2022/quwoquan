import 'dart:io';

import '../lib/src/dart_generator.dart';
import '../lib/src/go_generator.dart';
import '../lib/src/python_generator.dart';
import '../lib/src/typescript_generator.dart';

void main(List<String> args) {
  final repoRoot = Directory.current;
  final contractDir = Directory('${repoRoot.path}/contracts/runtime/errors');
  final failures = _validateContracts(contractDir);
  if (failures.isNotEmpty) {
    for (final failure in failures) {
      stderr.writeln(failure);
    }
    exitCode = 1;
    return;
  }
  if (args.contains('--check')) {
    stdout.writeln('runtime error contracts validated');
    return;
  }

  const DartRuntimeErrorGenerator().generate();
  const GoRuntimeErrorGenerator().generate();
  const TypeScriptRuntimeErrorGenerator().generate();
  const PythonRuntimeErrorGenerator().generate();
}

List<String> _validateContracts(Directory contractDir) {
  final failures = <String>[];
  if (!contractDir.existsSync()) {
    return <String>['missing contracts/runtime/errors directory'];
  }
  final requiredFiles = <String>[
    'runtime_failure.schema.yaml',
    'runtime_failure_codes.yaml',
    'runtime_recovery_policy.schema.yaml',
  ];
  for (final fileName in requiredFiles) {
    final file = File('${contractDir.path}/$fileName');
    if (!file.existsSync()) {
      failures.add('missing $fileName');
      continue;
    }
    final text = file.readAsStringSync();
    final legacyRetryFact =
        'retry'
        'able:';
    final legacyDetailsFact = 'details:';
    if (text.contains(legacyRetryFact) || text.contains(legacyDetailsFact)) {
      failures.add('$fileName contains legacy recovery/details field');
    }
    if (text.contains('Map<String') || text.contains('map[string]')) {
      failures.add('$fileName contains weak map type');
    }
  }

  final schemaFile = File('${contractDir.path}/runtime_failure.schema.yaml');
  if (schemaFile.existsSync()) {
    failures.addAll(_validateRuntimeFailureSchema(schemaFile));
  }

  final codesFile = File('${contractDir.path}/runtime_failure_codes.yaml');
  if (codesFile.existsSync()) {
    failures.addAll(_validateRuntimeFailureCodes(codesFile, schemaFile));
  }
  failures.addAll(_validateLanguagePackages(Directory.current));
  return failures;
}

List<String> _validateRuntimeFailureSchema(File schemaFile) {
  final failures = <String>[];
  final schema = _readRuntimeFailureSchema(schemaFile);
  const primitiveTypes = <String>{
    'string',
    'int',
    'bool',
    'boolean',
    'double',
    'number',
    'object',
  };
  final knownTypes = <String>{
    ...primitiveTypes,
    ...schema.types,
    ...schema.enums.keys,
  };
  for (final reference in schema.typeReferences) {
    if (!knownTypes.contains(reference.name)) {
      failures.add(
        'runtime_failure.schema.yaml references undefined type ${reference.name} at line ${reference.lineNumber}',
      );
    }
  }
  return failures;
}

List<String> _validateRuntimeFailureCodes(File codesFile, File schemaFile) {
  final failures = <String>[];
  final schema = schemaFile.existsSync()
      ? _readRuntimeFailureSchema(schemaFile)
      : const _RuntimeFailureSchema();
  final allowedOrigins =
      schema.enums['RuntimeFailureOrigin'] ?? const <String>{};
  final allowedKinds = schema.enums['RuntimeFailureKind'] ?? const <String>{};
  final allowedNatures =
      schema.enums['RuntimeFailureNature'] ?? const <String>{};
  final codePattern = RegExp(
    r'^\s*-\s*code:\s*([A-Z]+)\.([A-Z]+)\.([a-z0-9_]+)\s*$',
  );
  final invalidCodePattern = RegExp(r'^\s*-\s*code:\s*(.+)$');
  final fieldPattern = RegExp(r'^\s*(origin|kind|nature):\s*([A-Za-z]+)\s*$');
  String currentCode = '';
  final seenFields = <String>{};
  void closeCurrentCode(int lineNumber) {
    if (currentCode.isEmpty) return;
    for (final requiredField in const <String>['origin', 'kind', 'nature']) {
      if (!seenFields.contains(requiredField)) {
        failures.add(
          '$currentCode missing $requiredField before line $lineNumber',
        );
      }
    }
  }

  final lines = codesFile.readAsLinesSync();
  for (var index = 0; index < lines.length; index += 1) {
    final line = lines[index];
    final invalid = invalidCodePattern.firstMatch(line);
    if (invalid != null) {
      closeCurrentCode(index + 1);
      currentCode = invalid.group(1)?.trim() ?? '';
      seenFields.clear();
      if (!codePattern.hasMatch(line)) {
        failures.add('invalid runtime error code: $currentCode');
      }
      continue;
    }
    final field = fieldPattern.firstMatch(line);
    if (field == null || currentCode.isEmpty) continue;
    final fieldName = field.group(1)!;
    final value = field.group(2)!;
    seenFields.add(fieldName);
    final allowed = switch (fieldName) {
      'origin' => allowedOrigins,
      'kind' => allowedKinds,
      'nature' => allowedNatures,
      _ => const <String>{},
    };
    if (allowed.isNotEmpty && !allowed.contains(value)) {
      failures.add('$currentCode has invalid $fieldName: $value');
    }
  }
  closeCurrentCode(lines.length + 1);
  return failures;
}

List<String> _validateLanguagePackages(Directory repoRoot) {
  final failures = <String>[];
  final dartFailure = File(
    '${repoRoot.path}/packages/quwoquan_runtime_errors/lib/src/runtime_failure.dart',
  );
  final goFailure = File(
    '${repoRoot.path}/quwoquan_service/runtime/failures/failure.go',
  );
  final tsFailure = File(
    '${repoRoot.path}/apps/ops-portal/src/shared/runtime/errors/runtimeFailure.ts',
  );
  final pythonFailure = File(
    '${repoRoot.path}/packages/python/quwoquan_runtime_errors/quwoquan_runtime_errors/runtime_failure.py',
  );
  final requiredOriginValues = <String>[
    'user',
    'environment',
    'localClient',
    'remoteDependency',
    'system',
    'developer',
  ];
  final requiredKindValues = <String>[
    'validation',
    'contract',
    'permission',
    'auth',
    'network',
    'rateLimited',
    'unavailable',
    'timeout',
    'notFound',
    'unsupported',
    'cancelled',
    'storage',
    'parsing',
    'model',
    'internal',
  ];
  final requiredNatureValues = <String>[
    'transient',
    'permanent',
    'requiresUserAction',
    'requiresPermission',
    'bug',
  ];
  final requiredFailureFields = <String>[
    'code',
    'origin',
    'kind',
    'nature',
    'location',
    'context',
  ];
  final requiredLocationFields = <String>[
    'businessObject',
    'functionModule',
    'sourceFilePath',
    'sourceLineNumber',
    'sourceLineText',
  ];
  final requiredContextFields = <String>['attributes', 'key', 'value'];

  failures.addAll(
    _requireFileContains(dartFailure, 'Dart runtime failure', <String>[
      ...requiredOriginValues.map((value) => '$value,'),
      ...requiredKindValues.map((value) => '$value,'),
      ...requiredNatureValues.map((value) => '$value,'),
      ...requiredFailureFields,
    ]),
  );
  failures.addAll(
    _requireFileContains(goFailure, 'Go runtime failure', <String>[
      ...requiredOriginValues.map((value) => '"$value"'),
      ...requiredKindValues.map((value) => '"$value"'),
      ...requiredNatureValues.map((value) => '"$value"'),
      ...requiredFailureFields.map(_goExportedFieldName),
    ]),
  );
  failures.addAll(
    _requireFileContains(tsFailure, 'TypeScript runtime failure', <String>[
      ...requiredOriginValues.map((value) => '"$value"'),
      ...requiredKindValues.map((value) => '"$value"'),
      ...requiredNatureValues.map((value) => '"$value"'),
      ...requiredFailureFields.map((value) => '$value:'),
      ...requiredLocationFields.map((value) => value),
      ...requiredContextFields.map((value) => value),
    ]),
  );
  failures.addAll(
    _requireFileContains(pythonFailure, 'Python runtime failure', <String>[
      'class RuntimeFailure',
      'class RuntimeFailureLocation',
      'class RuntimeFailureContext',
      'class RuntimeContextAttribute',
      'code:',
      'origin:',
      'kind:',
      'nature:',
      'location:',
      'context:',
      'business_object:',
      'function_module:',
      'attributes:',
      'key:',
      'value:',
    ]),
  );
  return failures;
}

List<String> _requireFileContains(
  File file,
  String label,
  List<String> tokens,
) {
  if (!file.existsSync()) return <String>['missing $label file: ${file.path}'];
  final text = file.readAsStringSync();
  return <String>[
    for (final token in tokens)
      if (!text.contains(token)) '$label missing token: $token',
  ];
}

String _goExportedFieldName(String raw) {
  return raw[0].toUpperCase() + raw.substring(1);
}

_RuntimeFailureSchema _readRuntimeFailureSchema(File schemaFile) {
  final types = <String>{};
  final enums = <String, Set<String>>{};
  final references = <_TypeReference>[];
  String section = '';
  String currentEnum = '';
  final typeNamePattern = RegExp(r'^\s{2}([A-Za-z][A-Za-z0-9]*):\s*$');
  final enumNamePattern = RegExp(r'^\s{2}([A-Za-z][A-Za-z0-9]*):\s*$');
  final typeReferencePattern = RegExp(
    r'^\s+type:\s*([A-Za-z][A-Za-z0-9]*)\s*$',
  );
  final listReferencePattern = RegExp(
    r'^\s+listOf:\s*([A-Za-z][A-Za-z0-9]*)\s*$',
  );
  final enumValuePattern = RegExp(r'^\s{4}-\s*([A-Za-z][A-Za-z0-9]*)\s*$');
  final lines = schemaFile.readAsLinesSync();
  for (var index = 0; index < lines.length; index += 1) {
    final line = lines[index];
    final lineNumber = index + 1;
    if (line == 'types:') {
      section = 'types';
      currentEnum = '';
      continue;
    }
    if (line == 'enums:') {
      section = 'enums';
      currentEnum = '';
      continue;
    }
    if (section == 'types') {
      final typeName = typeNamePattern.firstMatch(line);
      if (typeName != null) {
        types.add(typeName.group(1)!);
        continue;
      }
      final typeReference =
          typeReferencePattern.firstMatch(line) ??
          listReferencePattern.firstMatch(line);
      if (typeReference != null) {
        references.add(_TypeReference(typeReference.group(1)!, lineNumber));
      }
      continue;
    }
    if (section == 'enums') {
      final enumName = enumNamePattern.firstMatch(line);
      if (enumName != null) {
        currentEnum = enumName.group(1)!;
        enums[currentEnum] = <String>{};
        continue;
      }
      final enumValue = enumValuePattern.firstMatch(line);
      if (enumValue != null && currentEnum.isNotEmpty) {
        enums[currentEnum]!.add(enumValue.group(1)!);
      }
    }
  }
  return _RuntimeFailureSchema(
    types: types,
    enums: enums,
    typeReferences: references,
  );
}

class _RuntimeFailureSchema {
  const _RuntimeFailureSchema({
    this.types = const <String>{},
    this.enums = const <String, Set<String>>{},
    this.typeReferences = const <_TypeReference>[],
  });

  final Set<String> types;
  final Map<String, Set<String>> enums;
  final List<_TypeReference> typeReferences;
}

class _TypeReference {
  const _TypeReference(this.name, this.lineNumber);

  final String name;
  final int lineNumber;
}
