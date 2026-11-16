package ru.vagguides.golf4manual;

public final class AutoUpdatePolicyTest {
    private static int checks;

    private static void check(boolean expected, long now, long attempt, long success, long oldVersion, long version) {
        checks++;
        if (AutoUpdatePolicy.shouldCheck(now, attempt, success, oldVersion, version) != expected) {
            throw new AssertionError("Automatic check scheduling: case " + checks);
        }
    }

    public static void main(String[] args) {
        long time = 1_800_000_000_000L;
        long day = AutoUpdatePolicy.SUCCESS_INTERVAL_MS;
        long hour = AutoUpdatePolicy.RETRY_INTERVAL_MS;
        check(true, time, 0, 0, -1, 6); // First launch.
        check(false, time, time, time, 6, 6); // Successful check just finished.
        check(false, time + day - 1, time, time, 6, 6);
        check(true, time + day, time, time, 6, 6);
        check(true, time + 2 * day, time, time, 6, 6);
        check(false, time + hour - 1, time, 0, 6, 6); // Failed/in-flight request.
        check(true, time + hour, time, 0, 6, 6);
        check(false, time + hour - 1, time, time - day, 6, 6);
        check(true, time + hour, time, time - day, 6, 6);
        check(true, time - 1, time, time, 6, 6); // Wall clock moved backwards.
        check(true, time + 1, time, time, 5, 6); // Installed a new APK.
        check(true, time + 1, time, 0, 5, 6); // Previous version had failed.
        System.out.println(checks + " automatic update checks passed");
    }
}
