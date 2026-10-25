import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class BigMess {

    // ---------- вложенные классы (проверяют рекурсивный дамп объектов) ----------

    static class Address {
        String city;
        String street;
        int zip;

        Address(String city, String street, int zip) {
            this.city = city;
            this.street = street;
            this.zip = zip;
        }
    }

    static class Person {
        String name;
        int age;
        boolean active;
        Address address;
        List<String> tags;

        Person(String name, int age, boolean active, Address address, List<String> tags) {
            this.name = name;
            this.age = age;
            this.active = active;
            this.address = address;
            this.tags = tags;
        }
    }

    static class Company {
        String title;
        Person founder;
        List<Person> employees;
        Map<String, Integer> departmentSizes;

        Company(String title, Person founder) {
            this.title = title;
            this.founder = founder;
            this.employees = new ArrayList<>();
            this.departmentSizes = new LinkedHashMap<>();
        }

        void hire(Person p, String dept) {
            employees.add(p);
            departmentSizes.merge(dept, 1, Integer::sum);
        }
    }

    // ---------- примитивы и строки ----------

    static void primitivesDemo() {
        byte b = 127;                     // BREAK 1
        short sh = -32000;                // BREAK 2
        int i = 2_000_000_000;
        long l = 9_000_000_000_000L;
        float f = 3.14f;
        double d = 2.718281828459045;
        char c = 'Ж';
        boolean flag = true;

        String empty = "";
        String latin = "hello";
        String cyrillic = "Привет, мир";
        String chinese = "你好，世界";
        String emoji = "🚀 manti 🥟";
        String longText = "Строка подлиннее, чтобы декодер UTF16 включился. ".repeat(3);

        int[] ints = {1, 2, 3, 4, 5};
        String[] names = {"Alice", "Bob", "Charlie"};
        double[][] matrix = {
            {1.0, 2.0, 3.0},
            {4.0, 5.0, 6.0}
        };

        System.out.println("primitivesDemo ok");
    }

    // ---------- коллекции ----------

    static void collectionsDemo() {
        List<Integer> numbers = new ArrayList<>();
        for (int i = 0; i < 10; i++) {
            numbers.add(i * i);           // BREAK 3
        }

        Set<String> unique = new HashSet<>(Arrays.asList("a", "b", "a", "c", "b"));
        Map<String, Integer> counts = new HashMap<>();
        for (String s : unique) {
            counts.put(s, counts.getOrDefault(s, 0) + 1);
        }

        Map<Integer, List<String>> grouped = new LinkedHashMap<>();
        for (int n : numbers) {
            grouped.computeIfAbsent(n % 3, k -> new ArrayList<>()).add("n=" + n);
        }

        System.out.println("collectionsDemo ok");
    }

    // ---------- объекты и вложенность ----------

    static void objectsDemo() {
        Address aliceAddr = new Address("Москва", "Тверская 1", 101000);
        Address bobAddr = new Address("Санкт-Петербург", "Невский 2", 190000);

        Person alice = new Person("Alice", 30, true, aliceAddr,
                new ArrayList<>(Arrays.asList("dev", "team-lead", "java")));
        Person bob = new Person("Bob", 25, false, bobAddr,
                new ArrayList<>(Arrays.asList("dev", "python")));
        Person charlie = new Person("Charlie", 40, true,
                new Address("Казань", "Баумана 3", 420000),
                new ArrayList<>(Arrays.asList("qa")));

        Company acme = new Company("Acme Corp", alice);
        acme.hire(alice, "Engineering");
        acme.hire(bob, "Engineering");
        acme.hire(charlie, "QA");         // BREAK 4

        List<Person> all = new ArrayList<>();
        all.add(alice);
        all.add(bob);
        all.add(charlie);

        int totalAge = 0;
        for (Person p : all) {
            totalAge += p.age;
        }
        double averageAge = (double) totalAge / all.size();

        System.out.println("objectsDemo ok, avg age=" + averageAge);
    }

    // ---------- рекурсия и алгоритмы ----------

static long factorial(int n) {
    long result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}

static int fib(int n) {
    if (n < 2) return n;
    int a = 0, b = 1;
    for (int i = 2; i <= n; i++) {
        int c = a + b;
        a = b;
        b = c;
    }
    return b;
}

    static void quickSort(int[] a, int lo, int hi) {
        if (lo >= hi) return;             // BREAK 7
        int pivot = a[(lo + hi) / 2];
        int i = lo, j = hi;
        while (i <= j) {
            while (a[i] < pivot) i++;
            while (a[j] > pivot) j--;
            if (i <= j) {
                int t = a[i]; a[i] = a[j]; a[j] = t;
                i++; j--;
            }
        }
        quickSort(a, lo, j);
        quickSort(a, i, hi);
    }

    static void algorithmsDemo() {
        int[] arr = {42, 7, 19, 3, 88, 1, 56, 23, 9};
        int[] sorted = arr.clone();
        quickSort(sorted, 0, sorted.length - 1);

        long fact = factorial(10);
        int fib10 = fib(10);

        System.out.println("algorithmsDemo ok, fact=" + fact + ", fib10=" + fib10);
    }

    // ---------- вложенные циклы и сложность ----------

static int[][] makeMatrix(int n) {
    int[][] m = new int[n][n];
    for (int i = 0; i < n; i++) {
        int iPlus1 = i + 1;
        for (int j = 0; j < n; j++) {
            m[i][j] = iPlus1 * (j + 1);
        }
    }
    return m;
}

    static int sumMatrix(int[][] m) {
        int s = 0;
        for (int[] row : m) {
            for (int v : row) {
                s += v;
            }
        }
        return s;
    }

    static void complexityDemo() {
        int[][] m = makeMatrix(4);
        int total = sumMatrix(m);

        // дубликаты
        int[] nums = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5};
        Set<Integer> seen = new HashSet<>();
        Set<Integer> dupes = new HashSet<>();
        for (int n : nums) {
            if (!seen.add(n)) dupes.add(n);   // BREAK 9
        }

        System.out.println("complexityDemo ok, total=" + total + ", dupes=" + dupes);
    }

    // ---------- строковые операции ----------

    static void stringsDemo() {
        String s = "The quick brown fox jumps over the lazy dog";
        String[] words = s.split(" ");       // BREAK 10
        StringBuilder sb = new StringBuilder();
        for (int i = words.length - 1; i >= 0; i--) {
            sb.append(words[i]);
            if (i > 0) sb.append(' ');
        }
        String reversed = sb.toString();
        String upper = reversed.toUpperCase();
        String sub = upper.substring(0, Math.min(10, upper.length()));

        Map<Character, Integer> freq = new HashMap<>();
        for (char ch : s.toCharArray()) {
            if (Character.isLetter(ch)) {
                freq.merge(ch, 1, Integer::sum);
            }
        }

        System.out.println("stringsDemo ok, sub=" + sub);
    }

    // ---------- main ----------

    public static void main(String[] args) {
        System.out.println("== BigMess start ==");

        primitivesDemo();     // BREAK 11
        collectionsDemo();
        objectsDemo();
        algorithmsDemo();
        complexityDemo();
        stringsDemo();

        System.out.println("== BigMess done ==");
    }
}