import java.util.ArrayList;
import java.util.List;

public class Company {
    private String name;
    private Person ceo;
    private List<Person> employees = new ArrayList<>();

    public Company(String name, Person ceo) {
        this.name = name;
        this.ceo = ceo;
    }

    public void addEmployee(Person p) {
        employees.add(p);
    }

    public int employeeCount() {
        return employees.size();
    }

    @Override
    public String toString() {
        return "Company{" + name + ", ceo=" + ceo + ", employees=" + employees.size() + "}";
    }
}