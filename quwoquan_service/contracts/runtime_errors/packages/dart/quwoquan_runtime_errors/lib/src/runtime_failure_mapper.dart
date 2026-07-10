import 'package:quwoquan_runtime_errors/src/runtime_failure.dart';

abstract interface class RuntimeFailureMapper<TInput> {
  RuntimeFailureBase map(TInput input);
}
