package software.okan.drivebench;

public final class AnalogSensor implements Sensor {
    private final String name;
    private final double minimum;
    private final double maximum;
    private double value;

    public AnalogSensor(String name, double minimum, double maximum, double initial) {
        if (!Double.isFinite(minimum) || !Double.isFinite(maximum) || minimum > maximum) {
            throw new IllegalArgumentException("Invalid sensor bounds");
        }
        this.name = name;
        this.minimum = minimum;
        this.maximum = maximum;
        set(initial);
    }

    @Override public String name() { return name; }
    @Override public double read() { return value; }
    @Override public void set(double next) {
        if (!Double.isFinite(next) || next < minimum || next > maximum) {
            throw new IllegalArgumentException(name + " must be between " + minimum + " and " + maximum);
        }
        value = next;
    }
}
