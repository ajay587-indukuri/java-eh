public class EH implements Thread.UncaughtExceptionHandler {

    public static void runTask(String taskName, Runnable task) {
        try {
            task.run();
        } catch (Throwable e) {
            System.out.println("\nException in " + taskName + ": " + e);
            System.out.println("Exception handled. Continuing program...\n");
        }
    }

    @Override
    public void uncaughtException(Thread thread, Throwable e) {
        System.out.println("Unhandled Exception: " + e);
    }
}