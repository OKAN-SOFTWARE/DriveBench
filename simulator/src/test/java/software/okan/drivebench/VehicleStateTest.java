package software.okan.drivebench;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.*;

class VehicleStateTest {
    @Test void thermalFaultLatchesUntilRecoveryAndClear() {
        VehicleState state = new VehicleState(); state.ignition(true);
        state.setSensor("temperature_c", 110);
        assertTrue(state.snapshot().get("active_faults").toString().contains("DB_TEMP_HIGH"));
        assertThrows(ProtocolException.class, state::clearFaults);
        state.setSensor("temperature_c", 103);
        assertTrue(state.snapshot().get("active_faults").toString().contains("DB_TEMP_HIGH"));
        state.setSensor("temperature_c", 100);
        assertEquals("[]", state.snapshot().get("active_faults").toString());
        assertTrue(state.snapshot().get("stored_faults").toString().contains("DB_TEMP_HIGH"));
        assertEquals("[]", state.clearFaults().get("stored_faults").toString());
    }
    @Test void voltageHysteresisAndIgnition() {
        VehicleState state = new VehicleState(); state.setSensor("battery_v", 10);
        assertEquals("[]", state.snapshot().get("active_faults").toString());
        state.ignition(true);
        assertTrue(state.snapshot().get("active_faults").toString().contains("DB_VOLT_LOW"));
        state.setSensor("battery_v", 11.8);
        assertTrue(state.snapshot().get("active_faults").toString().contains("DB_VOLT_LOW"));
        state.setSensor("battery_v", 12.0);
        assertEquals("[]", state.snapshot().get("active_faults").toString());
    }
    @ParameterizedTest @ValueSource(doubles = {-100, 161, Double.NaN, Double.POSITIVE_INFINITY})
    void invalidSensorValuesCannotMutateState(double value) {
        VehicleState state = new VehicleState(); Object before = state.snapshot();
        assertThrows(IllegalArgumentException.class, () -> state.setSensor("temperature_c", value));
        assertEquals(before, state.snapshot());
    }
    @Test void resetClearsAllSubsystems() {
        VehicleState state = new VehicleState(); state.ignition(true); state.setSensor("battery_v", 10); state.setSensor("temperature_c", 120);
        var reset = state.reset();
        assertEquals(false, reset.get("ignition")); assertEquals("[]", reset.get("stored_faults").toString());
        assertThrows(ProtocolException.class, () -> state.setSensor("unknown", 5));
    }
}
