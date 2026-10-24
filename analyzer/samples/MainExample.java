import java.util.List;

class MainExample {
    private static final int LIMIT = 10;

    public static void main(String[] args) {
        List<String> names = List.of("Анна", "Иван");

        for (String name : names) {
            if (name.length() > LIMIT) {
                System.out.println(name);
            }
        }

        Helper.print("Готово");
    }
}
