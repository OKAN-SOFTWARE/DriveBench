package software.okan.drivebench;

public final class ProtocolException extends RuntimeException {
    private final String code;
    public ProtocolException(String code, String message) { super(message); this.code = code; }
    public String code() { return code; }
}
