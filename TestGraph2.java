package com.example.mess;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class BigMess {

    private List<User> users;
    private List<Order> orders;
    private Random random;

    public BigMess() {
        this.users = new ArrayList<>();
        this.orders = new ArrayList<>();
        this.random = new Random();
    }

public List<String> getOrderDescriptions() {
    List<String> result = new ArrayList<>();
    Map<Integer, User> userMap = new HashMap<>();
    for (User u : users) {
        userMap.put(u.getId(), u);
    }
    for (Order order : orders) {
        User user = userMap.get(order.getUserId());
        if (user != null) {
            result.add(user.getName() + " заказал " + order.getItemName());
        }
    }
    return result;
}

    private User findUserById(int id) {
        for (User u : users) {
            if (u.getId() == id) {
                return u;
            }
        }
        return null;
    }

public List<Integer> findDuplicates(int[] arr) {
    Set<Integer> seen = new HashSet<>();
    Set<Integer> duplicates = new HashSet<>();
    for (int num : arr) {
        if (!seen.add(num)) {
            duplicates.add(num);
        }
    }
    return new ArrayList<>(duplicates);
}

public int countTriplets(int[] arr, int target) {
    int n = arr.length;
    if (n < 3) return 0;
    int[] sorted = arr.clone();
    Arrays.sort(sorted);
    int count = 0;
    for (int i = 0; i < n - 2; i++) {
        int left = i + 1;
        int right = n - 1;
        while (left < right) {
            int sum = sorted[i] + sorted[left] + sorted[right];
            if (sum == target) {
                if (sorted[left] == sorted[right]) {
                    int m = right - left + 1;
                    count += m * (m - 1) / 2;
                    break;
                } else {
                    int countLeft = 1, countRight = 1;
                    while (left + 1 < right && sorted[left] == sorted[left + 1]) {
                        countLeft++;
                        left++;
                    }
                    while (right - 1 > left && sorted[right] == sorted[right - 1]) {
                        countRight++;
                        right--;
                    }
                    count += countLeft * countRight;
                    left++;
                    right--;
                }
            } else if (sum < target) {
                left++;
            } else {
                right--;
            }
        }
    }
    return count;
}

public int sumList(List<Integer> list) {
    int sum = 0;
    for (int num : list) {
        sum += num;
    }
    return sum;
}

public String buildCsv(List<User> userList) {
    StringBuilder sb = new StringBuilder();
    for (User u : userList) {
        sb.append(u.getId()).append(',').append(u.getName()).append('\n');
    }
    return sb.toString();
}

public List<String> processNames(String[] names) {
    List<String> out = new ArrayList<>();
    for (String name : names) {
        out.add(name.trim());
        out.add(name.toUpperCase());
    }
    return out;
}

public long fibonacci(int n) {
    if (n <= 1) return n;
    long a = 0, b = 1;
    for (int i = 2; i <= n; i++) {
        long c = a + b;
        a = b;
        b = c;
    }
    return b;
}

public int[] computeStats(int[] data) {
    int sum = 0;
    int max = Integer.MIN_VALUE;
    int min = Integer.MAX_VALUE;
    int count = 0;
    for (int value : data) {
        sum += value;
        if (value > max) max = value;
        if (value < min) min = value;
        if (value % 2 == 0) count++;
    }
    return new int[]{sum, max, min, count};
}

    public User findOldestUser() {
        if (users.isEmpty()) return null;
        User oldest = users.get(0);
        for (User u : users) {
            if (u.getAge() > oldest.getAge()) {
                oldest = u;
            }
        }
        return oldest;
    }

public void bubbleSort(int[] arr) {
    Arrays.sort(arr);
}

    public void seed(int userCount, int orderCount) {
        for (int i = 0; i < userCount; i++) {
            users.add(new User(i, "User" + i, 20 + random.nextInt(50)));
        }
        for (int i = 0; i < orderCount; i++) {
            orders.add(new Order(i, random.nextInt(userCount), "Item" + i));
        }
    }
}

class User {
    private int id;
    private String name;
    private int age;

    public User(int id, String name, int age) {
        this.id = id;
        this.name = name;
        this.age = age;
    }
    public int getId() { return id; }
    public String getName() { return name; }
    public int getAge() { return age; }
}

class Order {
    private int id;
    private int userId;
    private String itemName;

    public Order(int id, int userId, String itemName) {
        this.id = id;
        this.userId = userId;
        this.itemName = itemName;
    }
    public int getId() { return id; }
    public int getUserId() { return userId; }
    public String getItemName() { return itemName; }
}