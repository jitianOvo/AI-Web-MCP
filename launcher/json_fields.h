#pragma once
#include <string>
#include <cctype>
#include <cstdlib>

inline std::string JsonField(const std::string& json, const std::string& key) {
    size_t pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return {};
    pos = json.find(':', pos + key.size() + 2);
    if (pos == std::string::npos) return {};
    while (++pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {}
    if (pos >= json.size()) return {};
    if (json[pos] != '"') {
        size_t end = json.find_first_of(",}\r\n \t", pos);
        return json.substr(pos, end - pos);
    }
    std::string out;
    for (++pos; pos < json.size(); ++pos) {
        char c = json[pos];
        if (c == '"') return out;
        if (c == '\\') {
            if (++pos >= json.size()) return {};
            c = json[pos];
            if (c == 'n') c = '\n';
            else if (c == 'r') c = '\r';
            else if (c == 't') c = '\t';
        }
        out += c;
    }
    return {};
}

inline unsigned short JsonPort(const std::string& json) {
    const std::string value = JsonField(json, "port");
    if (value.empty()) return 8765;
    char* end = nullptr;
    const long port = std::strtol(value.c_str(), &end, 10);
    return end && *end == 0 && port > 0 && port <= 65535 ? static_cast<unsigned short>(port) : 8765;
}
