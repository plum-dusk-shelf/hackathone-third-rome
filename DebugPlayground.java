import java.util.*;
import java.util.stream.*;

/**
 * Debug Playground — монолитное приложение для тренировки отладки.
 *
 * КАК ПОЛЬЗОВАТЬСЯ:
 *   1. Запусти программу.
 *   2. Выбери упражнение (1..10).
 *   3. Поставь брейкпоинты по подсказкам в комментариях "// BP:".
 *   4. Запусти под дебаггером (Shift+F9 в IntelliJ / F11 в Eclipse).
 *
 * ТИПЫ БРЕЙКПОИНТОВ, КОТОРЫЕ ТУТ ОСОБЕННО ПОЛЕЗНЫ:
 *   - Обычный (клик по серой полосе слева от номера строки)
 *   - Условный (правый клик → "More" / условие): например "i == data.length"
 *   - Exception (View Breakpoints → + → Java Exception Breakpoints):
 *       ArrayIndexOutOfBoundsException, NullPointerException, ConcurrentModificationException
 *   - Watch expression (Alt+F8): например "m.email", "sum", "list.iterator()"
 *   - "Evaluate Expression" (Alt+F8) прямо на паузе
 *
 * ВАЖНО: файл должен называться DebugPlayground.java (public class = имя файла).
 */
public class DebugPlayground {

    // ============================================================
    // МОДЕЛИ
    // ============================================================

    static class Member {
        String name;
        String email;  // может быть null — это часть бага #3
        Member(String name, String email) { this.name = name; this.email = email; }
    }

    // ============================================================
    // УПРАЖНЕНИЕ 1 — ArrayIndexOutOfBounds (off-by-one)
    // ============================================================
    static void exArraySum() {
        int[] data = {10, 20, 30, 40, 50};
        int sum = 0;
        // BP1 (условный): i == data.length   → остановится на последней итерации
        for (int i = 0; i <= data.length; i++) {      // ← должно быть <, а не <=
            sum += data[i];                            // BP2: на этой строке при i == 5 будет AIOOBE
        }
        System.out.println("sum = " + sum);
        // На паузе: Alt+F8 → "data.length" (5), "i" (5), "i < data.length" (false)
    }

    // ============================================================
    // УПРАЖНЕНИЕ 2 — логическая ошибка (скидка прибавляется)
    // ============================================================
    static void exDiscount() {
        double price = 1000.0;
        int discountPercent = 20;
        // BP: на строке ниже, затем Step Over и смотри finalPrice
        double finalPrice = price + (price * discountPercent / 100.0); // ← должно быть МИНУС
        System.out.println("Итог: " + finalPrice + " (ожидалось 800.0, получили " + finalPrice + ")");
        // Watch: "price * (100 - discountPercent) / 100.0"
    }

    // ============================================================
    // УПРАЖНЕНИЕ 3 — NullPointerException
    // ============================================================
    static void exNpe() {
        List<Member> members = new ArrayList<>();
        members.add(new Member("Ivan", "ivan@example.com"));
        members.add(new Member("Anna", null));          // ← виновник
        // BP (условный): m.email == null   → остановится только на Анне
        for (Member m : members) {
            // BP: на строке ниже, перед вызовом — watch "m.name", "m.email"
            System.out.println(m.name + ": " + m.email.toLowerCase()); // NPE на Анне
        }
        // На паузе (не дойдя до падения): можно поставить Exception BP на NPE
    }

    // ============================================================
    // УПРАЖНЕНИЕ 4 — StackOverflowError (нет базового случая для n <= 0)
    // ============================================================
    static long exFactorial(int n) {
        if (n == 1) return 1;                          // ← базовый случай только для 1
        return n * exFactorial(n - 1);                 // BP: n <= 0  → увидишь, как "уезжает" в минус
    }
    static void exRecursion() {
        System.out.println("fact(5) = " + exFactorial(5));  // работает
        System.out.println("fact(0) = " + exFactorial(0));  // ← StackOverflowError
        // На паузе BP: watch "n", "Thread.currentThread().getStackTrace().length"
    }

    // ============================================================
    // УПРАЖНЕНИЕ 5 — баг в Stream (не тот фильтр)
    // ============================================================
    static void exStream() {
        List<Integer> nums = Arrays.asList(-3, -1, 0, 2, 4, 5, 7, 8);
        // Хотели: только ЧЁТНЫЕ, потом ×2  → ожидали [0, 4, 8, 16]
        // BP (условный): x != null && x > 0   → смотри, какие значения проходят фильтр
        List<Integer> result = nums.stream()
                .filter(x -> x > 0)                    // ← должно быть x % 2 == 0
                .map(x -> x * 2)
                .collect(Collectors.toList());
        System.out.println("Результат: " + result + " (ожидалось [0, 4, 8, 16])");
        // BP после .collect() — сравни watch "nums" и "result"
    }

    // ============================================================
    // УПРАЖНЕНИЕ 6 — ConcurrentModificationException
    // ============================================================
    static void exConcurrentMod() {
        List<String> list = new ArrayList<>(
                Arrays.asList("apple", "banana", "avocado", "cherry", "apricot"));
        // BP: на строке for — watch "list.size()" и "list.iterator()"
        for (String s : list) {                        // ← итератор, а мы мутируем list
            if (s.startsWith("a")) {
                list.remove(s);                        // ← CME на следующем next()
            }
        }
        System.out.println(list);
        // Правильно: list.removeIf(s -> s.startsWith("a"));
    }

    // ============================================================
    // УПРАЖНЕНИЕ 7 — сравнение строк через == вместо equals()
    // ============================================================
    static void exStringCompare() {
        String a = "admin";                            // из пула строк
        String b = new String("admin");                // НЕ из пула
        // BP на строке ниже — Alt+F8 → "a == b" (false), "a.equals(b)" (true)
        System.out.println("a == b ? " + (a == b));    // false
        System.out.println("a.equals(b) ? " + a.equals(b)); // true
        // Полезно: в дебаггере посмотреть "a" и "b" — IntelliJ покажет id объекта
    }

    // ============================================================
    // УПРАЖНЕНИЕ 8 — Integer overflow
    // ============================================================
    static void exOverflow() {
        int sum = 0;
        // BP (условный): sum < 0   → остановится в момент первого переполнения
        for (int i = 0; i < 20; i++) {
            sum += 200_000_000;                        // 20 * 200M = 4B > Integer.MAX_VALUE (~2.1B)
        }
        System.out.println("sum = " + sum + " (ожидалось 4_000_000_000)"); // отрицательное число
        // Watch: "sum", "sum < 0", "Integer.MAX_VALUE"
    }

    // ============================================================
    // УПРАЖНЕНИЕ 9 — race condition (без синхронизации)
    // ============================================================
    static class RaceDemo {
        int counter = 0;                                // ← нет volatile/synchronized
        void run() throws InterruptedException {
            Runnable r = () -> { for (int i = 0; i < 500_000; i++) counter++; };
            Thread t1 = new Thread(r, "T1");
            Thread t2 = new Thread(r, "T2");
            // BP1: t1.start() — до старта счётчик 0
            // BP2 (условный): counter > 0 && counter < 200 — редко ловится, но можно
            t1.start();
            t2.start();
            t1.join(); t2.join();
            // BP3: на строке ниже — watch "counter" (будет < 1_000_000)
            System.out.println("counter = " + counter + " (ожидалось 1_000_000)");
        }
    }
    static void exRace() throws InterruptedException { new RaceDemo().run(); }

    // ============================================================
    // УПРАЖНЕНИЕ 10 — скрытая причина исключения
    // ============================================================
    static void exExceptionChain() {
        try {
            try {
                Integer.parseInt("not-a-number");      // ← НАСТОЯЩАЯ причина
            } catch (NumberFormatException nfe) {
                // BP: на строке ниже — watch "nfe.getMessage()"
                // Лучшая практика: throw new RuntimeException("parse failed", nfe);
                throw new RuntimeException("parse failed"); // ← причина ПОТЕРЯНА
            }
        } catch (RuntimeException e) {
            System.out.println("Поймано: " + e.getMessage());
            // BP: на строке ниже — watch "e.getCause()" (null!)
            System.out.println("Причина: " + e.getCause());
        }
        // Exception BP на NumberFormatException → остановит в момент throw внутри Integer.parseInt
        // Exception BP на RuntimeException (caught) → остановит раньше, чем catch
    }

    // ============================================================
    // МЕНЮ
    // ============================================================

    static final String[] NAMES = {
            "",
            "ArrayIndexOutOfBounds (off-by-one)",
            "Логическая ошибка (скидка)",
            "NullPointerException",
            "StackOverflowError (рекурсия)",
            "Баг в Stream (не тот фильтр)",
            "ConcurrentModificationException",
            "Сравнение строк через ==",
            "Integer overflow",
            "Race condition",
            "Скрытая причина исключения"
    };

    static final Map<Integer, Runnable> MENU = new LinkedHashMap<>();
    static {
        MENU.put(1,  DebugPlayground::exArraySum);
        MENU.put(2,  DebugPlayground::exDiscount);
        MENU.put(3,  DebugPlayground::exNpe);
        MENU.put(4,  DebugPlayground::exRecursion);
        MENU.put(5,  DebugPlayground::exStream);
        MENU.put(6,  DebugPlayground::exConcurrentMod);
        MENU.put(7,  DebugPlayground::exStringCompare);
        MENU.put(8,  DebugPlayground::exOverflow);
        MENU.put(9,  () -> { try { exRace(); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } });
        MENU.put(10, DebugPlayground::exExceptionChain);
    }

    static void printMenu() {
        System.out.println();
        System.out.println("=== Debug Playground ===");
        for (int i = 1; i < NAMES.length; i++) {
            System.out.printf("%2d) %s%n", i, NAMES[i]);
        }
        System.out.println(" 0) Выход");
        System.out.println(" A) Прогнать все по очереди (падения печатаются, но не роняют программу)");
        System.out.print("> ");
    }

    static void runOne(int id) {
        System.out.println("--- Упражнение " + id + ": " + NAMES[id] + " ---");
        try {
            MENU.get(id).run();
        } catch (Throwable t) {
            System.out.println("💥 " + t.getClass().getSimpleName() + ": " + t.getMessage());
        }
    }

    static void runAll() {
        for (int id = 1; id <= 10; id++) runOne(id);
    }

    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        while (true) {
            printMenu();
            String line = sc.nextLine().trim();
            if (line.isEmpty()) continue;
            if ("0".equals(line)) break;
            if (line.equalsIgnoreCase("A")) { runAll(); continue; }
            int id;
            try { id = Integer.parseInt(line); }
            catch (NumberFormatException e) {
                System.out.println("Введите номер (1..10), 0 или A");
                continue;
            }
            if (!MENU.containsKey(id)) {
                System.out.println("Нет пункта " + id);
                continue;
            }
            runOne(id);
        }
        System.out.println("До свидания!");
    }
}