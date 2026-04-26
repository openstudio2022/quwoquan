import 'dart:io';

void main() {
  final repoRoot = Directory.current;
  final failures = <String>[
    ..._reject(
      repoRoot,
      relativePath: 'apps/ops-portal/src/domains',
      pattern: RegExp(
        r'\.catch\(\(\)\s*=>\s*\{\s*setRemoteReady\(false\);\s*\}',
        dotAll: true,
      ),
      message: 'ops page silently swallows RuntimeError',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'apps/ops-portal/src/shared/api',
      pattern: RegExp(r'throw new Error|throw Error\('),
      message: 'ops api throws raw Error instead of RuntimeError',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'apps/ops-portal/src/shared/runtime/errors',
      pattern: RegExp(
        r'from\s+["'
        "'"
        r']\./[^"'
        "'"
        r'.]+["'
        "'"
        r']',
      ),
      message: 'ops runtime error barrel uses extensionless NodeNext import',
    ),
    ..._rejectUnregisteredRuntimeCodes(
      repoRoot,
      relativePath: 'apps/ops-portal/src',
      codePrefix: 'OPS',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'contracts/runtime/errors',
      pattern: RegExp(r'\b(retryable|details)\b'),
      message: 'runtime contract contains legacy retryable/details',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/contracts',
      pattern: RegExp(r'\bretryable\b'),
      message: 'service contract documentation uses legacy retryable semantics',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'specs',
      pattern: RegExp(
        r'\b(retryable|isRetryable|retry_after_seconds|errorClass|error_class)\b',
      ),
      message: 'spec uses legacy runtime error semantics',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'docs',
      pattern: RegExp(
        r'\b(retryable|isRetryable|retry_after_seconds|errorClass|error_class|Recoverable)\b|Details\s+map\[string\]any',
      ),
      message: 'doc uses legacy runtime error semantics',
    ),
    ..._reject(
      repoRoot,
      relativePath: '.cursor/rules',
      pattern: RegExp(
        r'\b(retryable|isRetryable|retry_after_seconds|errorClass|error_class|Recoverable)\b|Details\s+map\[string\]any',
      ),
      message: 'agent rule uses legacy runtime error semantics',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'changes',
      pattern: RegExp(
        r'\b(retryable|isRetryable|retry_after_seconds|errorClass|error_class)\b',
      ),
      message: 'change record uses legacy runtime error semantics',
    ),
    ..._reject(
      repoRoot,
      relativePath: '.cursor/commands',
      pattern: RegExp(
        r'\b(retryable|isRetryable|retry_after_seconds|errorClass|error_class)\b',
      ),
      message: 'agent command uses legacy runtime error semantics',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/assistant/docs',
      pattern: RegExp(
        r'\b(retryable|isRetryable|retry_after_seconds|errorClass|error_class|Recoverable)\b|Details\s+map\[string\]any',
      ),
      message: 'assistant doc uses legacy runtime error semantics',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/contracts/metadata/_shared',
      pattern: RegExp(r'\b(retryable|details)\s*:'),
      message: 'OpenAPI common error schema exposes legacy retryable/details',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/contracts/metadata',
      pattern: RegExp(
        r'\b(retryable|retry_after_seconds|expected_retryable|expected_retry_after|isRetryable)\b',
      ),
      message: 'metadata error policy uses legacy retryable naming',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/cloud',
      pattern: RegExp(r'\bisRetryable\b'),
      message: 'generated cloud error enum exposes retryability as error fact',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/assistant',
      pattern: RegExp(
        r'\b(retryable|isRetryable|retry_after_seconds|retryAfterSeconds|Recoverable)\b',
      ),
      message: 'assistant code uses legacy retryable naming',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/assets/assistant',
      pattern: RegExp(r'\b(retryable|isRetryable|retry_after_seconds)\b'),
      message: 'assistant assets use legacy retryable naming',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/ui',
      pattern: RegExp(
        r'(state\.copyWith\([^;\n]*(?:error|errorMessage)[^;\n]*\.toString\(\)|(?:_error|_errorText)\s*=\s*\w+\.toString\(\))',
      ),
      message: 'UI primary error state must use structured runtime display',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/core',
      pattern: RegExp(
        r'(state\.copyWith\([^;\n]*(?:error|errorMessage)[^;\n]*\.toString\(\)|(?:_error|_errorText)\s*=\s*\w+\.toString\(\))',
      ),
      message: 'core provider error state must use structured runtime display',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/assistant',
      pattern: RegExp(r'\bruntimeFailure:\s*result\.runtimeFailure\b'),
      message: 'assistant failure propagation must use effectiveRuntimeFailure',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/assistant/protocol',
      pattern: RegExp(r'shouldSkipSessionWrite[\s\S]*isDegradedText'),
      message: 'assistant session write must not use text degraded classifier',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/assistant',
      pattern: RegExp(r'AssistantContentFilters\.isDegradedText\('),
      message:
          'assistant production code must not call text degraded classifier',
      allow: (path) => path.endsWith('/assistant_content_filters.dart'),
    ),
    ..._rejectAssistantToolFailuresWithoutRuntimeFailure(repoRoot),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/services/chat-service',
      pattern: RegExp(
        r'\bretryable\b|Retryable|retryable_|Recoverable|recoverable_',
      ),
      message: 'chat service uses legacy retryable naming',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'apps/ops-portal/src',
      pattern: RegExp(
        r'from\s+["'
        "'"
        r'][^"'
        "'"
        r']*(?:runtime/errors|controlPlane)(?!\.js)["'
        "'"
        r']',
      ),
      message: 'ops page import must be NodeNext explicit',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'apps/ops-portal/src/domains',
      pattern: RegExp(
        r'setRemoteReady\(false\)(?![\s\S]{0,240}(?:coerceRuntimeError|setRuntimeError))',
      ),
      message:
          'ops page marks remote unavailable without structured RuntimeError',
    ),
    ..._rejectExistingFiles(
      repoRoot,
      relativePath: 'apps/ops-portal/.test-dist',
      message: 'ops portal test build artifact must not be committed',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service',
      pattern: RegExp(r'Details\s+map\[string\]any'),
      message: 'Go public response exposes weak Details map',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service',
      pattern: RegExp(
        r'NewAppError\([^\n)]*\b(true|false)\)|NewAppError\([\s\S]*?\n\s*(true|false),\s*\n\s*\)',
        multiLine: true,
      ),
      message: 'Go runtime AppError encodes retryability in constructor',
    ),
    ..._rejectGoNewAppErrorBoolArgs(repoRoot),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/services/assistant-service',
      pattern: RegExp(r'HTTPWriteOptions\{\}'),
      message: 'assistant-service error path drops request/trace ids',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/services',
      pattern: RegExp(r'HTTPWriteOptions\{\}'),
      message: 'service error path drops request/trace ids',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/services',
      pattern: RegExp(r'http\.(Error|NotFound)\('),
      message: 'service uses non-runtime HTTP error response',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/tools',
      pattern: RegExp(r'http\.(Error|NotFound)\('),
      message: 'service codegen tool emits non-runtime HTTP error response',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/runtime/observability',
      pattern: RegExp(r'WriteHeader\(\s*http\.StatusInternalServerError\s*\)'),
      message: 'panic middleware writes 500 without RuntimeErrorResponse body',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_service/services',
      pattern: RegExp(
        r'writeJSON\([^,\n]+,\s*http\.Status\w+,\s*map\[string\]any\{\s*"error"',
      ),
      message: 'service writes ad-hoc JSON error response',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/cloud/runtime/codec',
      pattern: RegExp(r'throw\s+CloudException\('),
      message:
          'cloud response decoder throws CloudException without RuntimeFailure',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib',
      pattern: RegExp(r'throw\s+CloudException\('),
      message: 'app throws CloudException without RuntimeFailure mapper',
      allow: (path) => path.endsWith('/cloud_error_mapper.dart'),
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/assistant',
      pattern: RegExp(r"'retryable'\s*:|'errorClass'\s*:"),
      message: 'assistant public payload exposes retryable/errorClass',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/assistant',
      pattern: RegExp(
        r'failureCode\s*:\s*[^,\n]+,\s*[\r\n]\s*degraded\s*:',
        dotAll: true,
      ),
      message:
          'assistant mainline constructs degraded failure without typed RuntimeFailure',
    ),
    ..._reject(
      repoRoot,
      relativePath: 'quwoquan_app/lib/assistant',
      pattern: RegExp(
        r'legacy_response|legacyErrorCode|legacy_response_adapter|_legacyRuntimeFailureCode',
      ),
      message: 'assistant run response keeps legacy runtime failure adapter',
    ),
  ];
  if (failures.isNotEmpty) {
    for (final failure in failures) {
      stderr.writeln(failure);
    }
    exitCode = 1;
    return;
  }
  stdout.writeln('runtime error cutover guards passed');
}

List<String> _rejectAssistantToolFailuresWithoutRuntimeFailure(
  Directory repoRoot,
) {
  final roots = <FileSystemEntity>[
    Directory('${repoRoot.path}/quwoquan_app/lib/assistant/tool/impl'),
    Directory('${repoRoot.path}/quwoquan_app/lib/assistant/tool/runtime'),
    Directory('${repoRoot.path}/quwoquan_app/lib/assistant/skill/execution'),
    Directory('${repoRoot.path}/quwoquan_app/lib/assistant/infrastructure'),
    File(
      '${repoRoot.path}/quwoquan_app/lib/assistant/application/remote_assistant_entry.dart',
    ),
  ].where((entity) => entity.existsSync()).toList(growable: false);
  final failures = <String>[];
  for (final root in roots) {
    final entities = root is Directory
        ? root.listSync(recursive: true, followLinks: false)
        : <FileSystemEntity>[root];
    for (final entity in entities) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final text = _readUtf8(entity);
      if (text == null) continue;
      var searchFrom = 0;
      while (true) {
        final start = text.indexOf('AssistantToolResult(', searchFrom);
        if (start < 0) break;
        final openParen = text.indexOf('(', start);
        final end = _findMatchingParen(text, openParen);
        if (end < 0) break;
        final call = text.substring(start, end + 1);
        if (RegExp(r'\bsuccess\s*:\s*false\b').hasMatch(call) &&
            !RegExp(r'\bruntimeFailure\s*:').hasMatch(call)) {
          failures.add(
            'assistant tool failure omits RuntimeFailure: ${entity.path.substring(repoRoot.path.length + 1)}',
          );
          break;
        }
        searchFrom = end + 1;
      }
    }
  }
  return failures;
}

List<String> _rejectGoNewAppErrorBoolArgs(Directory repoRoot) {
  final root = Directory('${repoRoot.path}/quwoquan_service');
  if (!root.existsSync()) return const <String>[];
  final failures = <String>[];
  for (final entity in root.listSync(recursive: true, followLinks: false)) {
    if (entity is! File || !entity.path.endsWith('.go')) continue;
    if (_isIgnored(entity.path)) continue;
    final text = _readUtf8(entity);
    if (text == null) continue;
    var searchFrom = 0;
    while (true) {
      final start = text.indexOf('NewAppError(', searchFrom);
      if (start < 0) break;
      final openParen = text.indexOf('(', start);
      final end = _findMatchingParen(text, openParen);
      if (end < 0) break;
      final call = text.substring(openParen + 1, end);
      if (_topLevelArgs(call).any((arg) => arg == 'true' || arg == 'false')) {
        failures.add(
          'Go runtime AppError encodes retryability in constructor: ${entity.path.substring(repoRoot.path.length + 1)}',
        );
        break;
      }
      searchFrom = end + 1;
    }
  }
  return failures;
}

List<String> _topLevelArgs(String callBody) {
  final args = <String>[];
  var depth = 0;
  String? quote;
  var escaped = false;
  var start = 0;
  for (var i = 0; i < callBody.length; i++) {
    final ch = callBody[i];
    if (quote != null) {
      if (escaped) {
        escaped = false;
      } else if (ch == '\\') {
        escaped = true;
      } else if (ch == quote) {
        quote = null;
      }
      continue;
    }
    if (ch == '"' || ch == "'") {
      quote = ch;
      continue;
    }
    if (ch == '(' || ch == '[' || ch == '{') depth++;
    if (ch == ')' || ch == ']' || ch == '}') depth--;
    if (ch == ',' && depth == 0) {
      args.add(callBody.substring(start, i).trim());
      start = i + 1;
    }
  }
  args.add(callBody.substring(start).trim());
  return args;
}

int _findMatchingParen(String text, int openParen) {
  if (openParen < 0 || openParen >= text.length || text[openParen] != '(') {
    return -1;
  }
  var depth = 0;
  String? quote;
  var escaped = false;
  for (var i = openParen; i < text.length; i++) {
    final ch = text[i];
    if (quote != null) {
      if (escaped) {
        escaped = false;
      } else if (ch == '\\') {
        escaped = true;
      } else if (ch == quote) {
        quote = null;
      }
      continue;
    }
    if (ch == '"' || ch == "'") {
      quote = ch;
      continue;
    }
    if (ch == '(') depth++;
    if (ch == ')') {
      depth--;
      if (depth == 0) return i;
    }
  }
  return -1;
}

List<String> _reject(
  Directory repoRoot, {
  required String relativePath,
  required RegExp pattern,
  required String message,
  bool Function(String path)? allow,
}) {
  final root = Directory('${repoRoot.path}/$relativePath');
  if (!root.existsSync()) return const <String>[];
  final failures = <String>[];
  for (final entity in root.listSync(recursive: true, followLinks: false)) {
    if (entity is! File) continue;
    if (_isIgnored(entity.path)) continue;
    if (allow?.call(entity.path) ?? false) continue;
    final text = _readUtf8(entity);
    if (text == null) continue;
    if (pattern.hasMatch(text)) {
      failures.add(
        '$message: ${entity.path.substring(repoRoot.path.length + 1)}',
      );
    }
  }
  return failures;
}

List<String> _rejectExistingFiles(
  Directory repoRoot, {
  required String relativePath,
  required String message,
}) {
  final root = Directory('${repoRoot.path}/$relativePath');
  if (!root.existsSync()) return const <String>[];
  final failures = <String>[];
  for (final entity in root.listSync(recursive: true, followLinks: false)) {
    if (entity is! File) continue;
    failures.add(
      '$message: ${entity.path.substring(repoRoot.path.length + 1)}',
    );
  }
  return failures;
}

List<String> _rejectUnregisteredRuntimeCodes(
  Directory repoRoot, {
  required String relativePath,
  required String codePrefix,
}) {
  final codesFile = File(
    '${repoRoot.path}/contracts/runtime/errors/runtime_failure_codes.yaml',
  );
  if (!codesFile.existsSync()) {
    return <String>['missing runtime failure code registry'];
  }
  final registeredCodes =
      RegExp(
            r'^\s*-\s*code:\s*([A-Z]+\.[A-Z]+\.[a-z0-9_]+)\s*$',
            multiLine: true,
          )
          .allMatches(codesFile.readAsStringSync())
          .map((match) => match.group(1)!)
          .toSet();
  final codePattern = RegExp(
    '$codePrefix'
    r'\.[A-Z]+\.[a-z0-9_]+',
  );
  final root = Directory('${repoRoot.path}/$relativePath');
  if (!root.existsSync()) return const <String>[];
  final failures = <String>[];
  for (final entity in root.listSync(recursive: true, followLinks: false)) {
    if (entity is! File) continue;
    if (_isIgnored(entity.path)) continue;
    final text = _readUtf8(entity);
    if (text == null) continue;
    for (final match in codePattern.allMatches(text)) {
      final code = match.group(0)!;
      if (!registeredCodes.contains(code)) {
        failures.add(
          'unregistered runtime failure code $code: ${entity.path.substring(repoRoot.path.length + 1)}',
        );
      }
    }
  }
  return failures.toSet().toList()..sort();
}

String? _readUtf8(File file) {
  try {
    return file.readAsStringSync();
  } on FileSystemException {
    return null;
  }
}

bool _isIgnored(String path) {
  return path.contains('/node_modules/') ||
      path.contains('/build/') ||
      path.contains('/dist/') ||
      path.contains('/.test-dist/') ||
      path.contains('/.dart_tool/') ||
      path.endsWith('.png') ||
      path.endsWith('.jpg') ||
      path.endsWith('.jpeg') ||
      path.endsWith('.webp') ||
      path.endsWith('.gif') ||
      path.endsWith('.ttf') ||
      path.endsWith('.otf') ||
      path.endsWith('_test.go');
}
