package software.okan.drivebench;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProtocolTest {
    @Test void validatesTypesUnknownFieldsAndCorrelationIds() throws Exception {
        Protocol p = new Protocol(new VehicleState()); var faults = new TransportFaultInjector();
        var response = p.dispatch(p.parse("{\"id\":\"one\",\"command\":\"read\"}"), faults);
        assertEquals("one", response.get("id")); assertEquals(true, response.get("ok"));
        for (String frame : new String[]{"{\"id\":\"x\",\"command\":\"read\",\"extra\":1}", "{\"id\":\"x\",\"command\":\"ignition\",\"on\":1}", "null", "{}"}) {
            assertEquals(false, p.dispatch(p.parse(frame), faults).get("ok"));
        }
        assertThrows(Exception.class, () -> p.parse("{\"id\":\"a\",\"id\":\"b\"}"));
        assertThrows(Exception.class, () -> p.parse("{} {}"));
    }
    @Test void transportPlansAreOneShotAndConnectionLocal() {
        var a = new TransportFaultInjector(); var b = new TransportFaultInjector();
        a.arm("delay", 500); assertEquals("normal", b.consume().mode());
        assertEquals(500, a.consume().delayMillis()); assertEquals("normal", a.consume().mode());
        assertThrows(ProtocolException.class, () -> a.arm("delay", 5000));
    }
    @Test void tcpServerSupportsFragmentedAndCoalescedFrames() throws Exception {
        try (var server = new SimulatorServer(0); var socket = new Socket("127.0.0.1", server.port())) {
            socket.setSoTimeout(1500); var out = socket.getOutputStream();
            out.write("{\"id\":\"first\",\"command\":".getBytes(StandardCharsets.UTF_8)); out.flush();
            out.write("\"read\"}\n{\"id\":\"second\",\"command\":\"read\"}\n".getBytes(StandardCharsets.UTF_8)); out.flush();
            var reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
            assertEquals("first", Protocol.JSON.readTree(reader.readLine()).path("id").asText());
            assertEquals("second", Protocol.JSON.readTree(reader.readLine()).path("id").asText());
        }
    }
}
