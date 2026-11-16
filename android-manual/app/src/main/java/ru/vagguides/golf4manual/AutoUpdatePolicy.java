package ru.vagguides.golf4manual;

/** Timing rules shared by the automatic checker and its JVM regression tests. */
public final class AutoUpdatePolicy {
    public static final long SUCCESS_INTERVAL_MS = 24L * 60 * 60 * 1000;
    public static final long RETRY_INTERVAL_MS = 60L * 60 * 1000;

    private AutoUpdatePolicy() { }

    public static boolean shouldCheck(long now, long lastAttempt, long lastSuccess,
                                      long checkedVersion, long installedVersion) {
        if (checkedVersion != installedVersion || lastAttempt <= 0 || now < lastAttempt) return true;
        long interval = lastSuccess >= lastAttempt ? SUCCESS_INTERVAL_MS : RETRY_INTERVAL_MS;
        return now - lastAttempt >= interval;
    }
}
