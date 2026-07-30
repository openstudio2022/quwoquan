package com.quwoquan.quwoquan_app;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import android.util.Base64;
import androidx.annotation.Nullable;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** Keystore-backed recovery queue storage available before Flutter plugin registration. */
final class RecoveryFailureEncryptedStore {
  // Existing Keystore alias and file name are frozen canonical bytes.
  private static final String KEY_ALIAS = "qwq_recovery_failure_queue_v1";
  private static final String CIPHER = "AES/GCM/NoPadding";
  private static final int MAX_ENCRYPTED_BYTES = 2 << 20;

  private final File queueFile;
  private final AtomicFile atomicFile;

  RecoveryFailureEncryptedStore(Context context) {
    queueFile = new File(context.getNoBackupFilesDir(), "recovery_failures.v1.aesgcm");
    atomicFile = new AtomicFile(queueFile);
  }

  @Nullable
  synchronized String read() {
    if (!queueFile.isFile()) {
      return null;
    }
    try {
      byte[] encoded;
      try (FileInputStream input = atomicFile.openRead();
          ByteArrayOutputStream output = new ByteArrayOutputStream()) {
        byte[] buffer = new byte[8192];
        int read;
        while ((read = input.read(buffer)) >= 0) {
          if (output.size() + read > MAX_ENCRYPTED_BYTES) {
            throw new IllegalStateException("encrypted recovery queue size is invalid");
          }
          output.write(buffer, 0, read);
        }
        encoded = output.toByteArray();
      }
      if (encoded.length == 0) throw new IllegalStateException("encrypted recovery queue is empty");
      JSONObject envelope = new JSONObject(new String(encoded, StandardCharsets.UTF_8));
      byte[] iv = Base64.decode(envelope.getString("iv"), Base64.NO_WRAP);
      byte[] ciphertext = Base64.decode(envelope.getString("ciphertext"), Base64.NO_WRAP);
      Cipher cipher = Cipher.getInstance(CIPHER);
      cipher.init(Cipher.DECRYPT_MODE, secretKey(false), new GCMParameterSpec(128, iv));
      return new String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8);
    } catch (Exception ignored) {
      clear();
      return null;
    }
  }

  synchronized boolean write(String value) {
    try {
      byte[] plaintext = value == null ? new byte[0] : value.getBytes(StandardCharsets.UTF_8);
      if (plaintext.length == 0 || plaintext.length > MAX_ENCRYPTED_BYTES) {
        return false;
      }
      Cipher cipher = Cipher.getInstance(CIPHER);
      cipher.init(Cipher.ENCRYPT_MODE, secretKey(true));
      JSONObject envelope = new JSONObject();
      envelope.put("v", 1);
      envelope.put("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP));
      envelope.put(
          "ciphertext", Base64.encodeToString(cipher.doFinal(plaintext), Base64.NO_WRAP));
      FileOutputStream output = null;
      try {
        output = atomicFile.startWrite();
        output.write(envelope.toString().getBytes(StandardCharsets.UTF_8));
        atomicFile.finishWrite(output);
      } catch (Exception writeError) {
        if (output != null) atomicFile.failWrite(output);
        throw writeError;
      }
      return true;
    } catch (Exception ignored) {
      return false;
    }
  }

  synchronized boolean clear() {
    atomicFile.delete();
    return !queueFile.exists();
  }

  private SecretKey secretKey(boolean create) throws Exception {
    KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
    keyStore.load(null);
    java.security.Key existing = keyStore.getKey(KEY_ALIAS, null);
    if (existing instanceof SecretKey) {
      return (SecretKey) existing;
    }
    if (!create) {
      throw new IllegalStateException("recovery queue key is missing");
    }
    KeyGenerator generator =
        KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
    generator.init(
        new KeyGenParameterSpec.Builder(
                KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .build());
    return generator.generateKey();
  }
}
