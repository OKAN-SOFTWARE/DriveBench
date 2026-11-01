package software.okan.drivebench;

/** One-shot fault plans belong to a single TCP connection, not global vehicle state. */
public final class TransportFaultInjector {
    public record Plan(String mode, int delayMillis) {}
    private Plan next = new Plan("normal", 0);
    public void arm(String mode, int delay) {
        if (!mode.equals("normal") && !mode.equals("delay") && !mode.equals("disconnect")) {
            throw new ProtocolException("INVALID_VALUE", "Unknown transport fault mode");
        }
        if ((mode.equals("delay") && (delay < 50 || delay > 2000)) || (!mode.equals("delay") && delay != 0)) {
            throw new ProtocolException("INVALID_VALUE", "Delay must be 50–2000 ms, only in delay mode");
        }
        next = new Plan(mode, delay);
    }
    public Plan consume() { Plan current = next; next = new Plan("normal", 0); return current; }
}
