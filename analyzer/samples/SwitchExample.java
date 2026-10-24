public class SwitchExample {
    public static void main(String[] args) {
        int value = 2;

        switch (value) {
            case 1:
                System.out.println("One");
                break;

            case 2:
                System.out.println("Two");

            case 3:
                System.out.println("Three");
                break;

            default:
                System.out.println("Other");
        }

        System.out.println("Done");
    }
}
