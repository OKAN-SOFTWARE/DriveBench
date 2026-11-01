package software.okan.drivebench;

/** A validated sensor boundary, independent of the diagnostic controller. */
public interface Sensor {
    String name();
    double read();
    void set(double value);
}
