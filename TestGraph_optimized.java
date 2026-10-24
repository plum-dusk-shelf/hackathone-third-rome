package com.example.test;

public class TestGraph {
    private Helper helper;

    public TestGraph() {
        this.helper = new Helper();
    }

    public void startProcess() {
        System.out.println("Starting process...");
        helper.doWork();
        helper.doMoreWork();
    }

    public int calculate(int a, int b) {
        int result = a + b;
        if (result > 10) {
            helper.handleLargeResult(result);
        }
        return result;
    }

    // Большой цикл с несколькими операциями — кандидат на разбиение
public void processLargeArray(int[] data) {
        int sum = 0;
        for (int v : data) {
            sum += v;
        }
        int max = Integer.MIN_VALUE;
        for (int v : data) {
            if (v > max) max = v;
        }
        int count = 0;
        for (int v : data) {
            if (v % 2 == 0) count++;
        }
        System.out.println("Sum: " + sum + ", Max: " + max + ", Even count: " + count);
    }
}

class Helper {
    public void doWork() {
        System.out.println("Working...");
    }

    public void doMoreWork() {
        System.out.println("Working more...");
    }

    public void handleLargeResult(int value) {
        System.out.println("Large result: " + value);
    }
}