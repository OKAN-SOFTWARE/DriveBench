package software.okan.drivebench;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class SimulatorServer implements AutoCloseable {
    private final ServerSocket listener;
    private final Protocol protocol = new Protocol(new VehicleState());
    private final ThreadPoolExecutor clients = new ThreadPoolExecutor(4, 4, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(8));
    private final Set<Socket> sockets = ConcurrentHashMap.newKeySet();
    private final Thread acceptor;
    private volatile boolean running = true;

    public SimulatorServer(int port) throws IOException {
        listener = new ServerSocket(port, 16, InetAddress.getByName("127.0.0.1"));
        acceptor = new Thread(this::accept, "drivebench-tcp-acceptor");
        acceptor.setDaemon(true); acceptor.start();
    }
    public int port() { return listener.getLocalPort(); }

    private void accept() {
        while (running) {
            try {
                Socket socket = listener.accept(); socket.setSoTimeout(3000); socket.setTcpNoDelay(true); sockets.add(socket);
                try { clients.execute(() -> serve(socket)); }
                catch (RejectedExecutionException e) { sockets.remove(socket); socket.close(); }
            } catch (IOException e) { if (running) System.err.println("TCP accept failure: " + e.getClass().getSimpleName()); }
        }
    }

    private void serve(Socket socket) {
        TransportFaultInjector injector = new TransportFaultInjector();
        try (socket) {
            for (int count = 0; running && count < 1000; count++) {
                String frame = readFrame(socket.getInputStream()); if (frame == null) return;
                com.fasterxml.jackson.databind.JsonNode request;
                try { request = protocol.parse(frame); }
                catch (Exception e) { send(socket, protocol.error(null, "INVALID_JSON", "Malformed, duplicate-key, or trailing JSON data")); continue; }
                if (!protocol.isInjection(request)) {
                    TransportFaultInjector.Plan plan = injector.consume();
                    if (plan.mode().equals("disconnect")) return;
                    if (plan.delayMillis() > 0) Thread.sleep(plan.delayMillis());
                }
                send(socket, protocol.dispatch(request, injector));
            }
        } catch (IOException ignored) { /* peer close, deadline, or oversized frame */ }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        finally { sockets.remove(socket); }
    }

    private void send(Socket socket, Object response) throws IOException {
        byte[] data = (Protocol.JSON.writeValueAsString(response) + "\n").getBytes(StandardCharsets.UTF_8);
        socket.getOutputStream().write(data); socket.getOutputStream().flush();
    }

    private String readFrame(InputStream input) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        for (int value; (value = input.read()) != -1;) {
            if (value == '\n') {
                byte[] bytes = buffer.toByteArray();
                int size = bytes.length; if (size > 0 && bytes[size - 1] == '\r') size--;
                return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes, 0, size)).toString();
            }
            if (buffer.size() >= 8192) throw new IOException("Frame exceeds 8192 bytes");
            buffer.write(value);
        }
        return null;
    }

    @Override public void close() throws IOException {
        running = false; listener.close();
        for (Socket socket : sockets) { try { socket.close(); } catch (IOException ignored) {} }
        clients.shutdownNow();
        try { acceptor.join(1000); clients.awaitTermination(3, TimeUnit.SECONDS); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }
}
