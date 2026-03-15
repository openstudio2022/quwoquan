import 'dart:io';

Future<void> main() async {
  final result = await Process.run(
    'dart',
    <String>['run', 'tool/assistant/domain_quality_runner.dart'],
    workingDirectory: Directory.current.path,
  );
  stdout.write(result.stdout);
  stderr.write(result.stderr);
  if (result.exitCode != 0) {
    stderr.writeln('NO-GO: at least one domain failed quality gate.');
    exitCode = result.exitCode;
    return;
  }
  stdout.writeln('GO: all domains passed quality gate.');
}

