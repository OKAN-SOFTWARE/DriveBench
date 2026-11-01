package software.okan.drivebench;

import java.util.Map;
import java.util.concurrent.CountDownLatch;

public final class SimulatorMain {
    public static void main(String[] args) throws Exception {
        int port = 7071;
        if (args.length == 2 && args[0].equals("--port")) port = Integer.parseInt(args[1]);
        else if (args.length != 0) throw new IllegalArgumentException("Usage: java -jar drivebench-simulator.jar [--port 0..65535]");
        if (port < 0 || port > 65535) throw new IllegalArgumentException("Port must be 0..65535");
        SimulatorServer server = new SimulatorServer(port);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> { try { server.close(); } catch (Exception ignored) {} }));
        System.out.println(Protocol.JSON.writeValueAsString(Map.of("ready", true, "port", server.port(), "protocol", "DriveBench TCP v1")));
        System.out.flush();
        new CountDownLatch(1).await();
    }
}
