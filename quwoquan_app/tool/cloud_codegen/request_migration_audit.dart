import 'dart:convert';
import 'dart:io';

import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/visitor.dart';

void main(List<String> arguments) {
  if (arguments.length != 2) {
    stderr.writeln(
      'usage: request_migration_audit.dart <contract-graph.lock.json> <output.json>',
    );
    exitCode = 64;
    return;
  }
  final lockFile = File(arguments[0]).absolute;
  final outputFile = File(arguments[1]).absolute;
  final lock = jsonDecode(lockFile.readAsStringSync()) as Map<String, Object?>;
  final operations = (lock['appExposedOperations'] as List<Object?>)
      .cast<Map<String, Object?>>();
  final packageSource = Directory(
    '${lockFile.parent.parent.parent.path}/packages/'
    'quwoquan_cloud_contracts/lib/src',
  );

  final classIndex = <String, List<Map<String, Object?>>>{};
  final functionIndex = <String, List<Map<String, Object?>>>{};
  for (final entity in packageSource.listSync(recursive: true)) {
    if (entity is! File ||
        !entity.path.endsWith('.dart') ||
        entity.path.contains(
          '${Platform.pathSeparator}generated${Platform.pathSeparator}',
        )) {
      continue;
    }
    final source = entity.readAsStringSync();
    final unit = parseString(
      content: source,
      path: entity.path,
      throwIfDiagnostics: false,
    ).unit;
    for (final declaration in unit.declarations) {
      if (declaration is ClassDeclaration) {
        final fields = <Map<String, Object?>>[];
        final constructors = <Map<String, Object?>>[];
        for (final member
            in declaration.body.childEntities.whereType<ClassMember>()) {
          if (member is FieldDeclaration && !member.isStatic) {
            final type = member.fields.type?.toSource() ?? '';
            for (final variable in member.fields.variables) {
              fields.add(<String, Object?>{
                'name': variable.name.lexeme,
                'type': type,
                'source': member.toSource(),
              });
            }
          } else if (member is ConstructorDeclaration && member.name == null) {
            constructors.add(<String, Object?>{
              'parameters': member.parameters.toSource(),
              'initializers': member.initializers
                  .map((item) => item.toSource())
                  .toList(),
              'body': member.body.toSource(),
              'const': member.constKeyword != null,
            });
          }
        }
        classIndex
            .putIfAbsent(declaration.namePart.typeName.lexeme, () => [])
            .add(<String, Object?>{
              'path': entity.path,
              'offset': declaration.offset,
              'end': declaration.end,
              'source': declaration.toSource(),
              'fields': fields,
              'constructors': constructors,
            });
      } else if (declaration is FunctionDeclaration) {
        final payloadCollector = _PayloadCollector();
        declaration.accept(payloadCollector);
        functionIndex.putIfAbsent(declaration.name.lexeme, () => []).add(
          <String, Object?>{
            'path': entity.path,
            'offset': declaration.offset,
            'end': declaration.end,
            'source': declaration.toSource(),
            'returnType': declaration.returnType?.toSource(),
            'parameters': declaration.functionExpression.parameters?.toSource(),
            'body': declaration.functionExpression.body.toSource(),
            'payloads': payloadCollector.payloads,
          },
        );
      }
    }
  }

  final audited = <Map<String, Object?>>[];
  for (final operation in operations) {
    final client = operation['clientContract'];
    if (client is! Map<String, Object?>) {
      continue;
    }
    final requestType = '${client['requestType'] ?? ''}'.trim();
    final requestEncoder = '${client['requestEncoder'] ?? ''}'.trim();
    audited.add(<String, Object?>{
      'canonicalOperationId': operation['canonicalOperationId'],
      'localOperationId': operation['localOperationId'],
      'sourcePath': operation['sourcePath'],
      'method': operation['method'],
      'requestEntity': operation['requestEntity'],
      'requestBodyKind': operation['requestBodyKind'],
      'requestBindings': operation['requestBindings'],
      'clientContract': client,
      'requestTypeDeclarations': classIndex[requestType] ?? const [],
      'requestEncoderDeclarations': functionIndex[requestEncoder] ?? const [],
    });
  }
  outputFile.parent.createSync(recursive: true);
  outputFile.writeAsStringSync(
    '${const JsonEncoder.withIndent('  ').convert(<String, Object?>{'operations': audited})}\n',
  );
}

final class _PayloadCollector extends RecursiveAstVisitor<void> {
  final List<Map<String, Object?>> payloads = <Map<String, Object?>>[];

  @override
  void visitInstanceCreationExpression(InstanceCreationExpression node) {
    if (node.constructorName.type.toSource() ==
        'CloudOperationRequestPayload') {
      _recordPayload(node.argumentList, node.toSource());
    }
    super.visitInstanceCreationExpression(node);
  }

  @override
  void visitMethodInvocation(MethodInvocation node) {
    if (node.target == null &&
        node.methodName.name == 'CloudOperationRequestPayload') {
      _recordPayload(node.argumentList, node.toSource());
    }
    super.visitMethodInvocation(node);
  }

  void _recordPayload(ArgumentList argumentList, String source) {
    final arguments = <String, Object?>{};
    final maps = <String, Object?>{};
    for (final argument in argumentList.arguments) {
      if (argument is! NamedArgument) {
        continue;
      }
      final name = argument.name.lexeme;
      final expression = argument.argumentExpression;
      arguments[name] = expression.toSource();
      if (expression is SetOrMapLiteral) {
        maps[name] = _mapEntries(expression.elements);
      }
    }
    payloads.add(<String, Object?>{
      'source': source,
      'arguments': arguments,
      'maps': maps,
    });
  }

  List<Map<String, Object?>> _mapEntries(
    Iterable<CollectionElement> elements, {
    String? guard,
  }) {
    final result = <Map<String, Object?>>[];
    for (final element in elements) {
      if (element is MapLiteralEntry) {
        result.add(<String, Object?>{
          'key': _stringKey(element.key),
          'value': element.value.toSource(),
          if (guard != null) 'guard': guard,
        });
      } else if (element is IfElement) {
        final nextGuard = element.caseClause == null
            ? element.expression.toSource()
            : '${element.expression.toSource()} '
                  '${element.caseClause!.toSource()}';
        result.addAll(
          _mapEntries(<CollectionElement>[
            element.thenElement,
          ], guard: nextGuard),
        );
      } else if (element is SpreadElement) {
        result.add(<String, Object?>{
          'spread': element.expression.toSource(),
          if (guard != null) 'guard': guard,
        });
      } else {
        result.add(<String, Object?>{
          'unsupported': element.toSource(),
          if (guard != null) 'guard': guard,
        });
      }
    }
    return result;
  }

  String? _stringKey(Expression expression) {
    if (expression is SimpleStringLiteral) {
      return expression.value;
    }
    return null;
  }
}
