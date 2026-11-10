// MSP v1 controller emulator.
#include <pty.h>
#include <poll.h>
#include <termios.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
volatile std::sig_atomic_t running = 1;
void stop(int) { running = 0; }
using Bytes = std::vector<uint8_t>;
void u16(Bytes& data, uint16_t v) {
    data.push_back(v & 255);
    data.push_back(v >> 8);
}
void u32(Bytes& data, uint32_t v) { u16(data, v & 65535); u16(data, v >> 16); }
Bytes text(const std::string& s) { return Bytes(s.begin(), s.end()); }
uint8_t checksum(const Bytes& bytes, std::size_t start = 0) {
    uint8_t crc = 0;
    for(std::size_t i = start; i < bytes.size(); ++i) crc ^= bytes[i];
    return crc;
}
bool write_all(int fd, const Bytes& bytes) {
    std::size_t offset = 0;
    while(offset < bytes.size() && running) {
        const auto n = write(fd, bytes.data() + offset, bytes.size() - offset);
        if(n < 0) { if(errno == EINTR) continue; return false; }
        offset += static_cast<std::size_t>(n);
    }
    return offset == bytes.size();
}
}  // namespace

int main(int argc, char** argv) {
    double cycle_seconds = 3.0;
    if(argc == 3 && std::string(argv[1]) == "--cycle-seconds") {
        try { cycle_seconds = std::stod(argv[2]); } catch(...) { return 2; }
        if(!(cycle_seconds >= 0.1 && cycle_seconds <= 3600.0)) return 2;
    } else if(argc != 1) {
        std::cerr << "Usage: msp_emulator [--cycle-seconds 3.0]\n";
        return 2;
    }
    int master = -1, slave = -1;
    char device[128]{};
    if(openpty(&master, &slave, device, nullptr, nullptr) != 0) {
        std::cerr << "openpty: " << std::strerror(errno) << '\n';
        return 1;
    }
    termios settings{};
    tcgetattr(slave, &settings);
    cfmakeraw(&settings);
    tcsetattr(slave, TCSANOW, &settings);
    std::signal(SIGINT, stop);
    std::signal(SIGTERM, stop);
    std::cout << "EMULATOR_DEVICE=" << device << std::endl;
    const auto start = std::chrono::steady_clock::now();
    Bytes input;
    const Bytes marker{'$', 'M', '<'};
    while(running) {
        pollfd ready{master, POLLIN, 0};
        if(poll(&ready, 1, 100) <= 0) continue;
        uint8_t buffer[4096];
        const auto count = read(master, buffer, sizeof(buffer));
        if(count <= 0) break;
        input.insert(input.end(), buffer, buffer + count);
        while(input.size() >= 6) {
            const auto header = std::search(input.begin(), input.end(), marker.begin(), marker.end());
            if(header == input.end()) {
                input.erase(input.begin(), input.end() - 2); // retain a partial header
                break;
            }
            input.erase(input.begin(), header);
            if(input.size() < 6) break;
            const auto length = static_cast<std::size_t>(input[3]) + 6;
            if(input.size() < length) break;
            const Bytes request(input.begin(), input.begin() + length);
            input.erase(input.begin(), input.begin() + length);
            if(checksum(request, 3) != 0) continue;
            const uint8_t id = request[4];
            const auto elapsed = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - start).count();
            const auto phase = static_cast<unsigned>(elapsed / cycle_seconds) % 4;
            // index: 0 HORIZON, 1 ARM, 2 FAILSAFE, 3 ANGLE, 4 BEEPER
            const uint32_t flags = phase == 1 ? (1u << 1 | 1u << 3) :
                phase == 2 ? (1u << 1 | 1u << 0) : phase == 3 ? (1u << 2) : 0;
            Bytes payload;
            bool supported = true;
            switch(id) {
            case 1: payload = {0, 1, 42}; break;
            case 2: payload = text("BTFL"); break; // canonical Betaflight wire identifier
            case 4:
                payload = text("SITL"); u16(payload, 1);
                payload.insert(payload.end(), {0, 0, 4, 'Q', 'E', 'M', 'U'}); break;
            case 64: payload = {0, 1, 2, 3}; break;
            case 100: payload = {230, 3, 1}; u32(payload, 4); break;
            case 101:
                u16(payload, 1000); u16(payload, 0); u16(payload, 7);
                u32(payload, flags); payload.push_back(0); break; // 11-byte legacy STATUS
            case 102:
                for(const int v : {0, 0, 512, 10, 20, 30, 100, 0, 0}) u16(payload, v);
                break;
            case 103: case 104:
                for(int i = 0; i < 8; ++i) u16(payload, 1000 + (phase == 1 || phase == 2 ? 100 : 0));
                break;
            case 105:
                for(int i = 0; i < 8; ++i) u16(payload, i == 3 ? 1000 : 1500);
                break;
            case 108: u16(payload, 100); u16(payload, 200); u16(payload, 30); break;
            case 109: u32(payload, 1234); u16(payload, 0); break;
            case 110: payload.push_back(120); u16(payload, 100); u16(payload, 500); u16(payload, 25); break;
            case 116: payload = text("HORIZON;ARM;FAILSAFE;ANGLE;BEEPER;"); break;
            case 119: payload = {2, 0, 27, 1, 13}; break;
            case 58: u32(payload, 150); break;
            case 200: case 214: break; // ACK commands; scripted states remain deterministic
            default: supported = false; break;
            }
            Bytes response{'$', 'M', static_cast<uint8_t>(supported ? '>' : '!'),
                static_cast<uint8_t>(payload.size()), id};
            response.insert(response.end(), payload.begin(), payload.end());
            response.push_back(checksum(response, 3));
            if(!write_all(master, response)) running = 0;
        }
    }
    close(slave);
    close(master);
    return 0;
}
