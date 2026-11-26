
public class Runner {

    public static void main(String[] args) {
        Thread.currentThread().setUncaughtExceptionHandler(new EH());

        try {
            Main.main(args);
        } catch (Throwable e) {
            new EH().uncaughtException(Thread.currentThread(), e);
        }
    }
}
