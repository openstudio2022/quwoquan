import 'package:quwoquan_runtime_errors/runtime_errors.dart';

RuntimeFailure testRuntimeFailure({
  String code = 'APP.SYSTEM.test_failure',
  RuntimeFailureKind kind = RuntimeFailureKind.internal,
  RuntimeFailureNature nature = RuntimeFailureNature.permanent,
}) {
  return RuntimeFailure(
    code: code,
    origin: RuntimeFailureOrigin.developer,
    kind: kind,
    nature: nature,
    location: const RuntimeFailureLocation(
      businessObject: 'test_fixture',
      functionModule: 'test_runtime_failure',
    ),
    context: const RuntimeFailureContext(),
  );
}
