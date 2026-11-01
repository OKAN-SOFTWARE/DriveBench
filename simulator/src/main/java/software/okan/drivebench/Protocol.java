package software.okan.drivebench;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class Protocol {
    public static final ObjectMapper JSON = new ObjectMapper()
            .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    private final VehicleState vehicle;
    public Protocol(VehicleState vehicle) { this.vehicle = vehicle; }

    public JsonNode parse(String line) throws Exception { return JSON.readTree(line); }
    public String id(JsonNode request) {
        if (request == null || !request.isObject() || !request.path("id").isTextual()) return null;
        String id = request.path("id").textValue();
        return id.matches("[A-Za-z0-9_-]{1,64}") ? id : null;
    }
    public boolean isInjection(JsonNode request) { return request != null && request.path("command").asText().equals("inject_transport"); }

    public Map<String, Object> dispatch(JsonNode request, TransportFaultInjector injector) {
        String id = id(request);
        try {
            if (id == null || !request.path("command").isTextual()) throw new ProtocolException("INVALID_REQUEST", "A valid id and string command are required");
            String command = request.path("command").textValue();
            Object data;
            switch (command) {
                case "reset" -> { fields(request); data = vehicle.reset(); }
                case "read", "diagnostics" -> { fields(request); data = vehicle.snapshot(); }
                case "ignition" -> {
                    fields(request, "on");
                    if (!request.path("on").isBoolean()) throw new ProtocolException("INVALID_REQUEST", "on must be a boolean");
                    data = vehicle.ignition(request.path("on").booleanValue());
                }
                case "set_sensor" -> {
                    fields(request, "sensor", "value");
                    if (!request.path("sensor").isTextual() || !request.path("value").isNumber()) throw new ProtocolException("INVALID_REQUEST", "sensor and numeric value are required");
                    data = vehicle.setSensor(request.path("sensor").textValue(), request.path("value").doubleValue());
                }
                case "clear_faults" -> { fields(request); data = vehicle.clearFaults(); }
                case "inject_transport" -> {
                    fields(request, "mode", "delay_ms");
                    if (!request.path("mode").isTextual()) throw new ProtocolException("INVALID_REQUEST", "mode must be a string");
                    int delay = 0;
                    if (request.has("delay_ms")) {
                        if (!request.path("delay_ms").isIntegralNumber() || !request.path("delay_ms").canConvertToInt()) throw new ProtocolException("INVALID_REQUEST", "delay_ms must be an integer");
                        delay = request.path("delay_ms").intValue();
                    }
                    injector.arm(request.path("mode").textValue(), delay);
                    data = Map.of("armed", request.path("mode").textValue(), "scope", "next non-injection request on this connection");
                }
                default -> throw new ProtocolException("INVALID_COMMAND", "Unknown command");
            }
            return Map.of("id", id, "ok", true, "data", data);
        } catch (ProtocolException e) { return error(id, e.code(), e.getMessage()); }
        catch (IllegalArgumentException e) { return error(id, "INVALID_VALUE", e.getMessage()); }
    }

    private void fields(JsonNode request, String... extra) {
        Set<String> allowed = new HashSet<>(Set.of("id", "command"));
        allowed.addAll(Set.of(extra));
        request.fieldNames().forEachRemaining(key -> {
            if (!allowed.contains(key)) throw new ProtocolException("INVALID_REQUEST", "Unknown field: " + key);
        });
    }

    public Map<String, Object> error(String id, String code, String message) {
        Map<String, Object> result = new java.util.LinkedHashMap<>();
        result.put("id", id); result.put("ok", false); result.put("error", Map.of("code", code, "message", message));
        return result;
    }
}
