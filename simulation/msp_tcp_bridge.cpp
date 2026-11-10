// Binary TCP <-> PTY adapter for the serial ROS driver and Betaflight SITL.
#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pty.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

#include <cerrno>
#include <csignal>
#include <cstring>
#include <iostream>
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <vector>

namespace {
volatile std::sig_atomic_t running = 1;
void interrupt(int) { running = 0; }
bool forward(int source, int target, bool target_is_socket) {
    char bytes[4096];
    const auto length = read(source, bytes, sizeof(bytes));
    if(length < 0 && errno == EINTR) return true;
    if(length <= 0) return false;
    ssize_t offset = 0;
    while(offset < length && running) {
        const auto sent = target_is_socket ? send(target, bytes + offset, length - offset, MSG_NOSIGNAL) :
                                           write(target, bytes + offset, length - offset);
        if(sent < 0 && errno == EINTR) continue;
        if(sent <= 0) return false;
        offset += sent;
    }
    return true;
}

bool response(int tcp, int master, std::vector<unsigned char>& buffered) {
    unsigned char bytes[4096];
    const auto length = read(tcp, bytes, sizeof(bytes));
    if(length < 0 && errno == EINTR) return true;
    if(length <= 0) return false;
    if(const char* trace = std::getenv("MSP_BRIDGE_TRACE")) {
        std::ofstream output(trace, std::ios::binary | std::ios::app);
        output.write(reinterpret_cast<char*>(bytes), length);
    }
    buffered.insert(buffered.end(), bytes, bytes + length);
    // Some UART configurations emit non-MSP startup/debug bytes. Only forward
    // complete MSP responses, retaining fragmented TCP headers and payloads.
    while(!buffered.empty()) {
        const auto marker = std::find(buffered.begin(), buffered.end(), '$');
        buffered.erase(buffered.begin(), marker);
        if(buffered.size() < 3) return true;
        const bool version1 = buffered[1] == 'M';
        if((!version1 && buffered[1] != 'X') || (buffered[2] != '>' && buffered[2] != '!')) {
            buffered.erase(buffered.begin());
            continue;
        }
        if(buffered.size() < (version1 ? 5u : 8u)) return true;
        auto payload = version1 ? static_cast<std::size_t>(buffered[3]) :
            static_cast<std::size_t>(buffered[6]) | (static_cast<std::size_t>(buffered[7]) << 8);
        std::size_t overhead = version1 ? 6 : 9;
        if(version1 && payload == 255) {
            if(buffered.size() < 7) return true;
            payload = static_cast<std::size_t>(buffered[5]) | (static_cast<std::size_t>(buffered[6]) << 8);
            overhead = 8;
        }
        const auto frame = payload + overhead;
        if(buffered.size() < frame) return true;
        std::size_t offset = 0;
        while(offset < frame && running) {
            const auto count = write(master, buffered.data() + offset, frame - offset);
            if(count < 0 && errno == EINTR) continue;
            if(count <= 0) return false;
            offset += static_cast<std::size_t>(count);
        }
        buffered.erase(buffered.begin(), buffered.begin() + frame);
    }
    return true;
}
}

int main() {
    std::signal(SIGINT, interrupt);
    std::signal(SIGTERM, interrupt);
    const int tcp = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in endpoint{};
    endpoint.sin_family = AF_INET;
    endpoint.sin_port = htons(5761);
    inet_pton(AF_INET, "127.0.0.1", &endpoint.sin_addr);
    if(tcp < 0 || connect(tcp, reinterpret_cast<sockaddr*>(&endpoint), sizeof(endpoint)) < 0) {
        std::cerr << "MSP TCP connection: " << std::strerror(errno) << '\n';
        if(tcp >= 0) close(tcp);
        return 1;
    }
    timeval send_timeout{1, 0};
    setsockopt(tcp, SOL_SOCKET, SO_SNDTIMEO, &send_timeout, sizeof(send_timeout));
    const int no_delay = 1;
    setsockopt(tcp, IPPROTO_TCP, TCP_NODELAY, &no_delay, sizeof(no_delay));
    int master = -1, slave = -1;
    char device[128]{};
    if(openpty(&master, &slave, device, nullptr, nullptr) != 0) {
        close(tcp);
        return 1;
    }
    termios settings{};
    tcgetattr(slave, &settings);
    cfmakeraw(&settings);
    tcsetattr(slave, TCSANOW, &settings);
    std::cout << "BRIDGE_DEVICE=" << device << std::endl;
    int result = 0;
    std::vector<unsigned char> buffered;
    while(running) {
        pollfd descriptors[]{{master, POLLIN, 0}, {tcp, POLLIN, 0}};
        if(poll(descriptors, 2, 100) < 0) {
            if(errno == EINTR) continue;
            result = 1;
            break;
        }
        if((descriptors[0].revents & POLLIN) && !forward(master, tcp, true)) {
            result = running ? 1 : 0;
            break;
        }
        if((descriptors[1].revents & POLLIN) && !response(tcp, master, buffered)) {
            result = running ? 1 : 0;
            break;
        }
        if((descriptors[0].revents | descriptors[1].revents) & (POLLERR | POLLHUP | POLLNVAL)) {
            result = running ? 1 : 0;
            break;
        }
    }
    close(slave);
    close(master);
    close(tcp);
    return result;
}
