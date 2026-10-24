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
        int max = Integer.MIN_VALUE;
        int count = 0;
        for (int value : data) {
            sum += value;
            if (value > max) {
                max = value;
            }
            if ((value & 1) == 0) {
                count++;
            }
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