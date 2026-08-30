package com.quwoquan.quwoquan_app;

import android.content.Context;
import android.content.Intent;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Public boundary used by production and physically isolated UAT hosts to consume one pending
 * runtime-config activation request.
 *
 * <p>The package store and activation coordinator deliberately remain package-private. A host may
 * request the production activation operation and inspect its immutable outcome, but cannot acquire
 * either internal state owner or bypass their validation/CAS/receipt sequence.
 */
public final class RuntimeConfigActivationGateway {
  public enum ResultKind {
    NOT_REQUESTED,
    ACTIVATED,
    FAILED
  }

  /** Immutable projection of the internal activation result. */
  public static final class Result {
    private final ResultKind kind;
    private final String errorCode;
    private final List<String> validationIssues;

    private Result(ResultKind kind, String errorCode, List<String> validationIssues) {
      this.kind = kind;
      this.errorCode = errorCode;
      this.validationIssues =
          Collections.unmodifiableList(new ArrayList<>(validationIssues));
    }

    public ResultKind kind() {
      return kind;
    }

    public String errorCode() {
      return errorCode;
    }

    public List<String> validationIssues() {
      return validationIssues;
    }
  }

  private final RuntimeConfigActivationCoordinator coordinator;

  private RuntimeConfigActivationGateway(RuntimeConfigActivationCoordinator coordinator) {
    this.coordinator = coordinator;
  }

  public static RuntimeConfigActivationGateway create(Context context) {
    Context applicationContext = context.getApplicationContext();
    RuntimeConfigPackageStore store = AndroidRuntimeConfig.createStore(applicationContext);
    return new RuntimeConfigActivationGateway(
        new RuntimeConfigActivationCoordinator(applicationContext.getNoBackupFilesDir(), store));
  }

  public Result consumePendingRequest(Intent intent, boolean coldStartAllowed) {
    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(intent, coldStartAllowed);
    return new Result(
        ResultKind.valueOf(result.kind.name()), result.errorCode, result.validationIssues);
  }
}
