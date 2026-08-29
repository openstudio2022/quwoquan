package com.quwoquan.quwoquan_app;

import android.content.Context;
import java.time.Instant;

final class AndroidRuntimeConfig {
  private AndroidRuntimeConfig() {}

  static RuntimeConfigPackageStore createStore(Context context) {
    Context applicationContext = context.getApplicationContext();
    return new RuntimeConfigPackageStore(
        applicationContext.getNoBackupFilesDir(),
        () ->
            applicationContext
                .getAssets()
                .open(
                    RuntimeConfigPackageStore.ASSET_ROOT
                        + "/"
                        + RuntimeConfigPackageStore.TRUST_FILE_NAME),
        Instant::now,
        RuntimeConfigPackageStore.durableAtomicWriter());
  }
}
