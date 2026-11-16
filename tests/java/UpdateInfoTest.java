package ru.vagguides.golf4manual;

public final class UpdateInfoTest {
    private static final String PACKAGE = "ru.vagguides.golf4manual";
    private static final String URL = "https://raw.githubusercontent.com/artem33region/VAG-book/main/releases/golf4-5.apk";
    private static final String HASH = "a".repeat(64);
    private static int checks;

    private static UpdateInfo info(String packageName, long version, String url, String hash, long size) {
        return new UpdateInfo(PACKAGE, packageName, version, "5.0", url, hash, size);
    }

    private static void check(boolean result) {
        checks++;
        if (!result) throw new AssertionError("Check " + checks);
    }

    private static void rejects(Runnable action) {
        try { action.run(); } catch (IllegalArgumentException exception) { checks++; return; }
        throw new AssertionError("Invalid metadata accepted");
    }

    public static void main(String[] args) {
        UpdateInfo update = info(PACKAGE, 5, URL, HASH, 100);
        check(update.isNewerThan(4));
        check(!update.isNewerThan(5));
        check(!update.isNewerThan(6));
        check(update.matchesFile(100, HASH.toUpperCase()));
        check(!update.matchesFile(99, HASH));
        check(!update.matchesFile(100, "b".repeat(64)));
        rejects(() -> info("ru.vagguides.bfqmanual", 5, URL, HASH, 100));
        rejects(() -> info(PACKAGE, 0, URL, HASH, 100));
        rejects(() -> info(PACKAGE, 2147483648L, URL, HASH, 100));
        rejects(() -> info(PACKAGE, 5, URL, "bad-hash", 100));
        rejects(() -> info(PACKAGE, 5, URL, HASH, 0));
        rejects(() -> info(PACKAGE, 5, URL, HASH, 101L * 1024 * 1024));
        for (String address : new String[]{
                URL.replace("https:", "http:"), URL.replace("raw.githubusercontent.com", "example.com"),
                URL.replace("artem33region", "other"), URL.replace("/releases/", "/private/"),
                URL + "?redirect=evil", URL + "#fragment", URL.replace("/golf4-5", "/../golf4-5"),
                URL.replace("/golf4-5", "/%2e%2e/golf4-5"), URL.replace(".apk", ".html"),
                URL.replace("https://", "https://user@"), URL.replace(".com/", ".com:443/")}) {
            rejects(() -> info(PACKAGE, 5, address, HASH, 100));
        }
        System.out.println(checks + " update policy checks passed");
    }
}
