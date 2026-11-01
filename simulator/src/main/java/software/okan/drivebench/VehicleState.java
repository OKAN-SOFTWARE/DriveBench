package software.okan.drivebench;

import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Fictional diagnostic thresholds. This is not a model of a real vehicle. */
public final class VehicleState {
    public enum Fault { DB_TEMP_HIGH, DB_VOLT_LOW }
    private final Map<String, Sensor> sensors = new LinkedHashMap<>();
    private final EnumSet<Fault> active = EnumSet.noneOf(Fault.class);
    private final EnumSet<Fault> stored = EnumSet.noneOf(Fault.class);
    private boolean ignition;
    private long revision;

    public VehicleState() {
        sensors.put("temperature_c", new AnalogSensor("temperature_c", -40, 160, 85));
        sensors.put("battery_v", new AnalogSensor("battery_v", 0, 20, 12.6));
        sensors.put("speed_kph", new AnalogSensor("speed_kph", 0, 240, 0));
    }

    public synchronized Map<String, Object> reset() {
        ignition = false;
        sensors.get("temperature_c").set(85);
        sensors.get("battery_v").set(12.6);
        sensors.get("speed_kph").set(0);
        active.clear(); stored.clear(); revision++;
        return snapshot();
    }

    public synchronized Map<String, Object> ignition(boolean on) {
        ignition = on; revision++; evaluate(); return snapshot();
    }

    public synchronized Map<String, Object> setSensor(String name, double value) {
        Sensor sensor = sensors.get(name);
        if (sensor == null) throw new ProtocolException("UNKNOWN_SENSOR", "Unknown sensor: " + name);
        sensor.set(value); // Validation precedes every state mutation.
        revision++; evaluate(); return snapshot();
    }

    private void evaluate() {
        if (!ignition) { active.clear(); return; }
        double temperature = sensors.get("temperature_c").read();
        double voltage = sensors.get("battery_v").read();
        if (temperature >= 105) active.add(Fault.DB_TEMP_HIGH);
        else if (temperature <= 100) active.remove(Fault.DB_TEMP_HIGH);
        if (voltage < 11.5) active.add(Fault.DB_VOLT_LOW);
        else if (voltage >= 12.0) active.remove(Fault.DB_VOLT_LOW);
        stored.addAll(active);
    }

    public synchronized Map<String, Object> clearFaults() {
        if (!active.isEmpty()) throw new ProtocolException("ACTIVE_FAULT", "Resolve active faults before clearing stored diagnostics");
        stored.clear(); revision++; return snapshot();
    }

    public synchronized Map<String, Object> snapshot() {
        Map<String, Double> readings = new LinkedHashMap<>();
        sensors.forEach((name, sensor) -> readings.put(name, sensor.read()));
        return Map.of("ignition", ignition, "sensors", readings,
                "active_faults", names(active), "stored_faults", names(stored), "revision", revision);
    }

    private List<String> names(EnumSet<Fault> faults) { return faults.stream().map(Enum::name).toList(); }
}
