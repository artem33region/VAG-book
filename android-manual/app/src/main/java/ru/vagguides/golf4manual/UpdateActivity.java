package ru.vagguides.golf4manual;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class UpdateActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable poll = this::pollDownload;
    private TextView status;
    private Button action;
    private ProgressBar progress;
    private SharedPreferences preferences;
    private DownloadManager downloads;
    private UpdateInfo release;
    private String releaseJson;
    private long downloadId = -1;
    private long installedVersion;
    private boolean working;
    private boolean resumed;
    private boolean destroyed;
    private boolean ready;
    private boolean pendingInstall;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Ui.NAVY_DARK);
        getWindow().setNavigationBarColor(Ui.NAVY_DARK);
        preferences = getSharedPreferences("app_updates", MODE_PRIVATE);
        downloads = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
        pendingInstall = state != null && state.getBoolean("pendingInstall");
        buildInterface();
        try {
            PackageInfo installed = getPackageManager().getPackageInfo(getPackageName(), 0);
            installedVersion = versionCode(installed);
            ((TextView) findViewById(android.R.id.text1)).setText(getString(R.string.update_installed_version, installed.versionName));
            downloadId = preferences.getLong("downloadId", -1);
            if (downloadId != -1) {
                releaseJson = preferences.getString("release", "");
                release = parseRelease(new JSONObject(releaseJson));
                if (!release.isNewerThan(installedVersion)) clearDownload();
            }
            if (downloadId == -1) checkForUpdate();
        } catch (Exception exception) {
            clearDownload();
            showError("Не удалось прочитать сведения об обновлении. Повторите проверку.");
        }
    }

    private void buildInterface() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int padding = Ui.dp(this, 20);
        root.setPadding(padding, padding, padding, padding);
        root.setBackgroundColor(Ui.PAPER);
        Button back = new Button(this);
        back.setText("‹ Назад к разделам");
        back.setOnClickListener(view -> finish());
        root.addView(back);
        root.addView(Ui.text(this, "Обновления", 26, Ui.NAVY_DARK, true));
        TextView version = Ui.text(this, "", 15, Ui.MUTED, false);
        version.setId(android.R.id.text1);
        root.addView(version);
        status = Ui.text(this, "", 17, Ui.INK, false);
        status.setPadding(0, padding, 0, padding);
        root.addView(status);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        root.addView(progress, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 12)));
        action = new Button(this);
        root.addView(action);
        TextView explanation = Ui.text(this,
                "Обновления загружаются с GitHub. Для проверки нужен интернет. Статьи доступны без сети. Установку новой версии подтверждаете вы.",
                14, Ui.MUTED, false);
        explanation.setPadding(0, padding, 0, 0);
        root.addView(explanation);
        scroll.addView(root);
        setContentView(scroll);
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        if (downloadId != -1 && !working) pollDownload();
    }

    @Override protected void onPause() {
        resumed = false;
        handler.removeCallbacks(poll);
        super.onPause();
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBoolean("pendingInstall", pendingInstall);
        super.onSaveInstanceState(state);
    }

    @Override protected void onDestroy() {
        destroyed = true;
        handler.removeCallbacks(poll);
        executor.shutdownNow();
        super.onDestroy();
    }

    private UpdateInfo parseRelease(JSONObject value) throws Exception {
        return new UpdateInfo(getPackageName(), value.getString("packageName"), value.getLong("versionCode"),
                value.getString("versionName"), value.getString("url"), value.getString("sha256"), value.getLong("size"));
    }

    private void checkForUpdate() {
        if (working) return;
        working = true;
        ready = false;
        status.setText("Проверяем наличие обновлений…");
        progress.setVisibility(View.VISIBLE);
        progress.setIndeterminate(true);
        action.setText("Проверка…");
        action.setEnabled(false);
        executor.execute(() -> {
            try {
                JSONObject manifest = new JSONObject(fetchManifest());
                if (manifest.getInt("schemaVersion") != 1) throw new IllegalArgumentException("Unsupported schema");
                JSONObject entry = manifest.getJSONObject("apps").getJSONObject(getPackageName());
                UpdateInfo found = parseRelease(entry);
                runOnUiThread(() -> {
                    if (destroyed) return;
                    working = false;
                    release = found;
                    releaseJson = entry.toString();
                    progress.setVisibility(View.GONE);
                    action.setEnabled(true);
                    if (found.isNewerThan(installedVersion)) {
                        status.setText(String.format(Locale.getDefault(), "Доступна версия %s (%.1f МБ).",
                                found.versionName, found.size / 1048576.0));
                        action.setText("Скачать обновление");
                        action.setOnClickListener(view -> startDownload());
                    } else {
                        status.setText("У вас установлена актуальная версия.");
                        setCheckAction();
                    }
                });
            } catch (Exception exception) {
                runOnUiThread(() -> showError("Не удалось проверить обновления. Проверьте подключение к интернету и повторите попытку."));
            }
        });
    }

    private String fetchManifest() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(UpdateInfo.MANIFEST_URL).openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(15000);
        connection.setInstanceFollowRedirects(false);
        connection.setUseCaches(false);
        connection.setRequestProperty("Cache-Control", "no-cache");
        try {
            if (connection.getResponseCode() != 200) throw new IllegalStateException("Manifest unavailable");
            try (InputStream input = connection.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (output.size() + count > 64 * 1024) throw new IllegalStateException("Manifest too large");
                    output.write(buffer, 0, count);
                }
                return new String(output.toByteArray(), StandardCharsets.UTF_8);
            }
        } finally {
            connection.disconnect();
        }
    }

    private File downloadedFile() {
        File directory = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (directory == null) throw new IllegalStateException("Storage unavailable");
        return new File(directory, "update-" + release.versionCode + ".apk");
    }

    private void startDownload() {
        try {
            File destination = downloadedFile();
            if (destination.exists() && !destination.delete()) throw new IllegalStateException("Cannot replace APK");
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(release.url))
                    .setTitle(getString(ru.vagguides.golf4manual.R.string.app_name) + " — обновление")
                    .setDescription("Версия " + release.versionName)
                    .setMimeType("application/vnd.android.package-archive")
                    .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
                    .setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, destination.getName());
            downloadId = downloads.enqueue(request);
            preferences.edit().putLong("downloadId", downloadId).putString("release", releaseJson).apply();
            pollDownload();
        } catch (Exception exception) {
            clearDownload();
            showError("Не удалось начать загрузку. Проверьте доступность загрузок и свободное место.");
        }
    }

    private void pollDownload() {
        handler.removeCallbacks(poll);
        if (!resumed || destroyed || working || downloadId == -1) return;
        try (Cursor cursor = downloads.query(new DownloadManager.Query().setFilterById(downloadId))) {
            if (cursor == null || !cursor.moveToFirst()) throw new IllegalStateException("Download missing");
            int state = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
            if (state == DownloadManager.STATUS_SUCCESSFUL) {
                verifyDownload();
                return;
            }
            if (state == DownloadManager.STATUS_FAILED) throw new IllegalStateException("Download failed");
            long bytes = cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
            if (bytes > release.size) throw new IllegalStateException("Unexpected file size");
            progress.setVisibility(View.VISIBLE);
            progress.setIndeterminate(false);
            progress.setProgress((int) (bytes * 100 / release.size));
            status.setText(state == DownloadManager.STATUS_PAUSED ? "Загрузка приостановлена. Ожидаем подключения…"
                    : String.format(Locale.getDefault(), "Загрузка обновления: %d%%", bytes * 100 / release.size));
            action.setEnabled(true);
            action.setText("Отменить загрузку");
            action.setOnClickListener(view -> {
                clearDownload();
                status.setText("Загрузка отменена.");
                progress.setVisibility(View.GONE);
                setCheckAction();
            });
            handler.postDelayed(poll, 1000);
        } catch (Exception exception) {
            clearDownload();
            showError("Загрузка не завершена. Проверьте интернет и свободное место, затем повторите проверку.");
        }
    }

    private void verifyDownload() {
        if (ready) {
            showInstallAction();
            return;
        }
        working = true;
        status.setText(R.string.update_verifying);
        action.setEnabled(false);
        progress.setVisibility(View.VISIBLE);
        progress.setIndeterminate(true);
        executor.execute(() -> {
            try {
                File file = downloadedFile();
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                long bytes = 0;
                try (InputStream input = new FileInputStream(file)) {
                    byte[] buffer = new byte[32768];
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        bytes += count;
                        if (bytes > release.size) throw new IllegalStateException("File too large");
                        digest.update(buffer, 0, count);
                    }
                }
                if (!release.matchesFile(bytes, hex(digest.digest()))) throw new IllegalStateException("Digest mismatch");
                int flags = Build.VERSION.SDK_INT >= 28 ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
                PackageInfo archive = getPackageManager().getPackageArchiveInfo(file.getAbsolutePath(), flags);
                PackageInfo installed = getPackageManager().getPackageInfo(getPackageName(), flags);
                if (archive == null || !getPackageName().equals(archive.packageName)
                        || versionCode(archive) != release.versionCode || !release.isNewerThan(versionCode(installed))
                        || signers(archive).isEmpty() || !signers(archive).equals(signers(installed))) {
                    throw new IllegalStateException("Incompatible APK");
                }
                runOnUiThread(() -> {
                    if (destroyed) return;
                    working = false;
                    ready = true;
                    showInstallAction();
                });
            } catch (Exception exception) {
                runOnUiThread(() -> {
                    if (destroyed) return;
                    clearDownload();
                    showError("APK не прошёл проверку целостности или подписи. Файл удалён. Повторите загрузку.");
                });
            }
        });
    }

    private void showInstallAction() {
        progress.setVisibility(View.GONE);
        status.setText(getString(R.string.update_ready, release.versionName));
        action.setEnabled(true);
        action.setText("Установить обновление");
        action.setOnClickListener(view -> install());
        if (pendingInstall && resumed) {
            pendingInstall = false;
            if (Build.VERSION.SDK_INT < 26 || getPackageManager().canRequestPackageInstalls()) install();
            else status.setText("Для установки разрешите обновления из этого приложения. Нажмите «Установить обновление» ещё раз.");
        }
    }

    private void install() {
        try {
            if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
                pendingInstall = true;
                startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
                return;
            }
            Uri uri = downloads.getUriForDownloadedFile(downloadId);
            if (uri == null) throw new IllegalStateException("Download missing");
            Intent intent = new Intent(Intent.ACTION_VIEW)
                    .setDataAndType(uri, "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(intent);
        } catch (ActivityNotFoundException exception) {
            status.setText(R.string.update_installer_unavailable);
        } catch (Exception exception) {
            status.setText("Не удалось открыть установщик. Повторите попытку.");
        }
    }

    private void clearDownload() {
        handler.removeCallbacks(poll);
        if (downloadId != -1 && downloads != null) {
            try { downloads.remove(downloadId); } catch (RuntimeException ignored) { }
        }
        downloadId = -1;
        ready = false;
        pendingInstall = false;
        preferences.edit().clear().apply();
    }

    private void setCheckAction() {
        action.setEnabled(true);
        action.setText("Проверить обновления");
        action.setOnClickListener(view -> checkForUpdate());
    }

    private void showError(String message) {
        if (destroyed) return;
        working = false;
        progress.setVisibility(View.GONE);
        status.setText(message);
        setCheckAction();
    }

    private static long versionCode(PackageInfo info) {
        return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
    }

    private static Set<String> signers(PackageInfo info) throws Exception {
        Signature[] signatures = Build.VERSION.SDK_INT >= 28
                ? (info.signingInfo == null ? null : info.signingInfo.getApkContentsSigners()) : info.signatures;
        Set<String> values = new HashSet<>();
        if (signatures != null) for (Signature signature : signatures) {
            values.add(hex(MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())));
        }
        return values;
    }

    private static String hex(byte[] bytes) {
        StringBuilder output = new StringBuilder();
        for (byte value : bytes) output.append(String.format(Locale.ROOT, "%02x", value & 0xff));
        return output.toString();
    }
}
