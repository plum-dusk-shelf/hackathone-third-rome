import java.util.ArrayList;
import java.util.List;

public class Main {
    // статические поля — проверка scope "Static"
    static int counter = 0;
    static final String GREETING = "hello";

    public static void main(String[] args) {
        System.out.println("=== debug test start ===");

        // --- 1. примитивы (проверка Scope Locals) ---
        int a = 42;
        long big = 9_000_000_000L;
        double pi = 3.14159;
        boolean flag = true;
        char letter = 'Z';
        System.out.println("primitives: " + a + " " + big + " " + pi + " " + flag + " " + letter);

        // --- 2. массивы (проверка раскрытия массивов) ---
        int[] numbers = {10, 20, 30, 40, 50};
        String[] names = {"Alice", "Bob", "Charlie"};
        int[][] matrix = {
            {1, 2, 3},
            {4, 5, 6},
            {7, 8, 9}
        };
        System.out.println("numbers[2] = " + numbers[2]);
        System.out.println("matrix[1][1] = " + matrix[1][1]);

        // --- 3. объект и его поля ---
        Person alice = new Person("Alice", 30);
        Person bob = new Person("Bob", 25);
        System.out.println("alice = " + alice);

        // --- 4. вложенный объект ---
        Company acme = new Company("Acme Corp", alice);
        acme.addEmployee(bob);
        System.out.println("company = " + acme);

        // --- 5. коллекции ---
        List<Person> people = new ArrayList<>();
        people.add(alice);
        people.add(bob);
        people.add(new Person("Charlie", 40));

        // --- 6. вызов функции (шаг с заходом) ---
        int sum = add(15, 27);
        System.out.println("sum = " + sum);

        // --- 7. рекурсия (проверка стека вызовов) ---
        int fact = factorial(5);
        System.out.println("factorial(5) = " + fact);

        // --- 8. цикл (проверка изменения переменных по шагам) ---
        int total = 0;
        for (int i = 0; i < numbers.length; i++) {
            total += numbers[i];
        }
        System.out.println("total = " + total);

        // --- 9. вызов метода на объекте ---
        alice.birthday();
        System.out.println("alice after birthday = " + alice);

        // --- 10. обработка исключения ---
        try {
            int div = divide(10, 0);
            System.out.println("div = " + div);
        } catch (ArithmeticException e) {
            System.out.println("caught: " + e.getMessage());
        }

        // --- 11. статический счётчик ---
        for (int i = 0; i < 3; i++) {
            incrementCounter();
        }
        System.out.println("counter = " + counter);

        System.out.println("=== debug test end ===");
    }

    static int add(int x, int y) {
        int result = x + y;
        return result;
    }

    static int factorial(int n) {
        if (n <= 1) return 1;
        return n * factorial(n - 1);
    }

    static int divide(int a, int b) {
        return a / b;
    }

    static void incrementCounter() {
        counter++;
    }
}
