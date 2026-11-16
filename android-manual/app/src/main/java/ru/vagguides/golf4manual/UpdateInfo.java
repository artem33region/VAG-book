package ru.vagguides.golf4manual;

import java.net.URI;
import java.util.Locale;

/** Validated release metadata, independent of Android for offline tests. */
public final class UpdateInfo {
    public static final String MANIFEST_URL =
            "https://raw.githubusercontent.com/artem33region/VAG-book/main/updates.json";
    private static final String RELEASE_PATH = "/artem33region/VAG-book/main/releases/";
    public final String packageName;
    public final long versionCode;
    public final String versionName;
    public final String url;
    public final String sha256;
    public final long size;

    public UpdateInfo(String expectedPackage, String packageName, long versionCode,
                      String versionName, String url, String sha256, long size) {
        if (!expectedPackage.equals(packageName) || versionCode <= 0 || versionCode > Integer.MAX_VALUE
                || versionName == null || versionName.trim().isEmpty() || versionName.length() > 80
                || sha256 == null || !sha256.matches("[a-fA-F0-9]{64}")
                || size <= 0 || size > 100L * 1024 * 1024) {
            throw new IllegalArgumentException("Invalid release metadata");
        }
        URI address = URI.create(url);
        String path = address.getRawPath();
        if (!"https".equals(address.getScheme())
                || !"raw.githubusercontent.com".equals(address.getHost())
                || address.getPort() != -1 || address.getUserInfo() != null
                || address.getQuery() != null || address.getFragment() != null
                || path == null || !path.startsWith(RELEASE_PATH)
                || !path.substring(RELEASE_PATH.length()).matches("[a-z0-9-]+\\.apk")) {
            throw new IllegalArgumentException("Invalid release URL");
        }
        this.packageName = packageName;
        this.versionCode = versionCode;
        this.versionName = versionName;
        this.url = url;
        this.sha256 = sha256.toLowerCase(Locale.ROOT);
        this.size = size;
    }

    public boolean isNewerThan(long installedVersion) {
        return versionCode > installedVersion;
    }

    public boolean matchesFile(long bytes, String digest) {
        return size == bytes && sha256.equalsIgnoreCase(digest);
    }
}
